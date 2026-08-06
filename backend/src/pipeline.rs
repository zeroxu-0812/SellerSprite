use std::{
    collections::BTreeMap,
    path::Path,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
};

use futures::{stream, StreamExt};
use serde_json::{json, Value};
use tokio::time::{sleep, Duration};
use uuid::Uuid;

use crate::{
    amazon,
    api::AppState,
    config::AppConfig,
    error::{AppError, Result},
    models::{Failure, ProductDetail, RunRequest, RunResponse},
    overview::derive_market_overview,
    sellersprite,
    summary::enrich_product_summary,
    transform::{clean_row, enrich_derived, flatten_record},
};

pub async fn process_asins_with_progress(
    state: &AppState,
    request: RunRequest,
    job_id: String,
) -> Result<RunResponse> {
    let (include_summary, include_details) = request.extraction_options();
    let selected_marketplaces = marketplace_codes(&request)?;
    let workers_requested = request.workers;
    let asins = normalize_asins(request.asins);
    if asins.is_empty() {
        return Err(AppError::BadRequest("no valid ASINs".to_string()));
    }
    let total_work = asins
        .len()
        .checked_mul(selected_marketplaces.len())
        .ok_or_else(|| AppError::BadRequest("任务规模超出限制".to_string()))?;
    state.jobs.set_total(&job_id, total_work).await;

    let mut failures = Vec::new();
    let mut rows = Vec::new();
    let mut marketplace_overviews = BTreeMap::new();

    for (marketplace_index, marketplace) in selected_marketplaces.iter().enumerate() {
        let progress_offset = marketplace_index * asins.len();
        let runtime_config = config_for_marketplace(&state.config, marketplace)?;
        state
            .jobs
            .running(&job_id, format!("卖家精灵 {}", runtime_config.station))
            .await;
        let workers = bounded_workers(
            workers_requested,
            runtime_config.concurrency.workers,
            state.max_workers,
        );
        let mut lookup = sellersprite::lookup_asins(
            &state.client,
            &runtime_config,
            &state.token_manager,
            &asins,
        )
        .await?;
        for failure in &mut lookup.failures {
            failure.marketplace = Some(marketplace.clone());
        }
        failures.append(&mut lookup.failures);
        let completed = if include_details {
            progress_offset
        } else {
            progress_offset + asins.len()
        };
        state
            .jobs
            .advance(
                &job_id,
                completed,
                None,
                format!("卖家精灵 {}", runtime_config.station),
            )
            .await;

        let mut by_asin: BTreeMap<String, Value> = lookup
            .items
            .into_iter()
            .filter_map(|item| {
                let asin = item
                    .get("asin")
                    .and_then(|v| v.as_str())
                    .map(str::to_string)?;
                Some((asin, item))
            })
            .collect();

        if include_details {
            let details = fetch_details(
                state,
                &runtime_config,
                by_asin.keys().cloned().collect(),
                workers,
                &job_id,
                progress_offset,
            )
            .await;
            for (asin, result) in details {
                match result {
                    Ok(detail) => apply_detail(by_asin.get_mut(&asin), detail),
                    Err(message) => failures.push(Failure {
                        asin,
                        stage: "amazon_detail".to_string(),
                        message,
                        marketplace: Some(marketplace.clone()),
                    }),
                }
            }
        }

        let mut marketplace_rows = by_asin
            .values()
            .map(flatten_record)
            .map(|mut row| {
                enrich_derived(&mut row, &runtime_config.amazon.base_url);
                if include_summary {
                    enrich_product_summary(&mut row);
                }
                apply_extraction_visibility(&mut row, include_summary, include_details);
                row.insert(
                    "marketplace_code".to_string(),
                    Value::String(marketplace.clone()),
                );
                row.insert(
                    "marketplace_station".to_string(),
                    Value::String(runtime_config.station.clone()),
                );
                row.insert(
                    "amazon_base_url".to_string(),
                    Value::String(runtime_config.amazon.base_url.clone()),
                );
                clean_row(row)
            })
            .collect::<Vec<_>>();
        marketplace_rows.sort_by(|a, b| {
            a.get("asin")
                .and_then(|v| v.as_str())
                .cmp(&b.get("asin").and_then(|v| v.as_str()))
        });
        let marketplace_overview = derive_market_overview(&marketplace_rows);
        marketplace_overviews.insert(marketplace.clone(), marketplace_overview);
        rows.append(&mut marketplace_rows);
    }

    rows.sort_by(|a, b| {
        a.get("marketplace_code")
            .and_then(|v| v.as_str())
            .cmp(&b.get("marketplace_code").and_then(|v| v.as_str()))
            .then_with(|| {
                a.get("asin")
                    .and_then(|v| v.as_str())
                    .cmp(&b.get("asin").and_then(|v| v.as_str()))
            })
    });
    let overview = primary_overview(&selected_marketplaces, &marketplace_overviews);
    let out_dir = state.root.join("output").join("jobs").join(&job_id);
    write_outputs(
        &out_dir,
        &rows,
        &overview,
        &marketplace_overviews,
        &failures,
    )
    .await?;

    let response = RunResponse {
        products: rows,
        overview,
        marketplace_overviews,
        failures,
        output_dir: out_dir.to_string_lossy().to_string(),
    };
    state.jobs.advance(&job_id, total_work, None, "完成").await;
    Ok(response)
}

fn bounded_workers(requested: Option<usize>, configured: usize, maximum: usize) -> usize {
    requested
        .unwrap_or(configured)
        .max(1)
        .min(maximum.max(1))
}

fn primary_overview(
    selected_marketplaces: &[String],
    marketplace_overviews: &BTreeMap<String, crate::models::MarketOverview>,
) -> crate::models::MarketOverview {
    selected_marketplaces
        .first()
        .and_then(|marketplace| marketplace_overviews.get(marketplace))
        .cloned()
        .unwrap_or_default()
}

fn apply_extraction_visibility(
    row: &mut BTreeMap<String, Value>,
    include_summary: bool,
    include_details: bool,
) {
    if !include_summary {
        for key in [
            "product_identity",
            "target_user",
            "primary_scene",
            "overall_summary",
        ] {
            row.remove(key);
        }
    }
    if !include_details {
        row.remove("about");
    }
}

fn config_for_marketplace(base: &AppConfig, marketplace: &str) -> Result<AppConfig> {
    let code = marketplace_code(Some(marketplace))?;
    let (station, amazon_base_url) = match code.as_str() {
        "com" => ("US", "https://www.amazon.com"),
        "it" => ("IT", "https://www.amazon.it"),
        "uk" => ("UK", "https://www.amazon.co.uk"),
        "fr" => ("FR", "https://www.amazon.fr"),
        "es" => ("ES", "https://www.amazon.es"),
        "de" => ("DE", "https://www.amazon.de"),
        "jp" => ("JP", "https://www.amazon.co.jp"),
        _ => unreachable!("marketplace_code only returns supported codes"),
    };
    let mut config = base.clone();
    config.station = station.to_string();
    config.amazon.base_url = amazon_base_url.to_string();
    Ok(config)
}

pub fn marketplace_codes(request: &RunRequest) -> Result<Vec<String>> {
    let raw_marketplaces = request
        .marketplaces
        .as_ref()
        .filter(|values| !values.is_empty())
        .cloned()
        .unwrap_or_else(|| {
            request
                .marketplace
                .clone()
                .map(|value| vec![value])
                .unwrap_or_else(|| vec!["com".to_string()])
        });
    let mut codes = Vec::new();
    for raw in raw_marketplaces {
        let code = marketplace_code(Some(&raw))?;
        if !codes.contains(&code) {
            codes.push(code);
        }
    }
    if codes.is_empty() {
        codes.push("com".to_string());
    }
    Ok(codes)
}

pub fn marketplace_code(marketplace: Option<&str>) -> Result<String> {
    let raw = marketplace
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("com");
    let key = raw
        .to_ascii_lowercase()
        .chars()
        .filter(|ch| !matches!(ch, '_' | '-' | ' ' | '.'))
        .collect::<String>();
    let code = match key.as_str() {
        "com" | "us" | "usa" | "unitedstates" => "com",
        "it" | "italy" | "italia" => "it",
        "uk" | "gb" | "greatbritain" | "unitedkingdom" | "couk" => "uk",
        "fr" | "france" => "fr",
        "es" | "spain" | "espana" => "es",
        "de" | "germany" | "deutschland" => "de",
        "jp" | "japan" | "cojp" => "jp",
        _ => {
            return Err(AppError::BadRequest(format!(
                "unsupported marketplace: {raw}. supported: com, it, uk, fr, es, de, jp"
            )))
        }
    };
    Ok(code.to_string())
}

fn normalize_asins(asins: Vec<String>) -> Vec<String> {
    let re = regex::Regex::new(r#"[A-Z0-9]{10}"#).expect("valid regex");
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::new();
    for raw in asins {
        for mat in re.find_iter(&raw.to_ascii_uppercase()) {
            let asin = mat.as_str().to_string();
            if seen.insert(asin.clone()) {
                out.push(asin);
            }
        }
    }
    out
}

pub fn normalized_asin_count(asins: &[String]) -> usize {
    normalize_asins(asins.to_vec()).len()
}

async fn fetch_details(
    state: &AppState,
    config: &AppConfig,
    asins: Vec<String>,
    workers: usize,
    job_id: &str,
    progress_offset: usize,
) -> Vec<(String, std::result::Result<ProductDetail, String>)> {
    let total = asins.len();
    let completed = Arc::new(AtomicUsize::new(0));
    stream::iter(asins.into_iter().enumerate())
        .map(|(index, asin)| {
            let completed = completed.clone();
            async move {
            sleep(request_delay(config, index)).await;
            let result = amazon::fetch_product_detail(&state.client, &asin, config)
                .await
                .map_err(|err| err.to_string());
            let done = completed.fetch_add(1, Ordering::SeqCst) + 1;
            state
                .jobs
                .advance(
                    job_id,
                    progress_offset + done,
                    Some(asin.clone()),
                    format!("{} 详情页 {done}/{total}", config.station),
                )
                .await;
            (asin, result)
            }
        })
        .buffer_unordered(workers)
        .collect()
        .await
}

fn request_delay(config: &crate::config::AppConfig, index: usize) -> Duration {
    let min = config.quick_view.delay_seconds_min;
    let max = config.quick_view.delay_seconds_max.max(min);
    let span = max.saturating_sub(min) + 1;
    Duration::from_secs(min + (index as u64 % span))
}

fn apply_detail(item: Option<&mut Value>, detail: ProductDetail) {
    let Some(item) = item.and_then(|v| v.as_object_mut()) else {
        return;
    };
    item.insert(
        "discount_off_list_pct".to_string(),
        json!(detail.discount_off_list_pct),
    );
    if let (Some(discount), Some(price)) = (
        detail.discount_off_list_pct,
        item.get("price").and_then(|v| v.as_f64()),
    ) {
        if price > 0.0 && discount < 100.0 {
            item.insert(
                "list_price".to_string(),
                json!((price / (1.0 - discount / 100.0) * 100.0).round() / 100.0),
            );
        }
    }
    item.insert("about".to_string(), json!(detail.about));
}

async fn write_outputs(
    out_dir: &Path,
    products: &[BTreeMap<String, Value>],
    overview: &crate::models::MarketOverview,
    marketplace_overviews: &BTreeMap<String, crate::models::MarketOverview>,
    failures: &[Failure],
) -> Result<()> {
    tokio::fs::create_dir_all(out_dir)
        .await
        .map_err(|err| AppError::Anyhow(err.into()))?;
    write_json_atomic(&out_dir.join("products.json"), products).await?;
    write_json_atomic(&out_dir.join("market_overview.json"), overview).await?;
    write_json_atomic(
        &out_dir.join("marketplace_overviews.json"),
        marketplace_overviews,
    )
    .await?;
    write_json_atomic(&out_dir.join("failures.json"), failures).await?;
    Ok(())
}

async fn write_json_atomic<T: serde::Serialize + ?Sized>(path: &Path, value: &T) -> Result<()> {
    let temporary = path.with_file_name(format!(
        ".{}.{}.tmp",
        path.file_name().and_then(|name| name.to_str()).unwrap_or("output"),
        Uuid::new_v4().simple()
    ));
    let bytes = serde_json::to_vec_pretty(value).map_err(anyhow::Error::from)?;
    if let Err(err) = tokio::fs::write(&temporary, bytes).await {
        let _ = tokio::fs::remove_file(&temporary).await;
        return Err(AppError::Anyhow(err.into()));
    }
    if let Err(err) = tokio::fs::rename(&temporary, path).await {
        let _ = tokio::fs::remove_file(&temporary).await;
        return Err(AppError::Anyhow(err.into()));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn optional_row() -> BTreeMap<String, Value> {
        BTreeMap::from([
            ("product_identity".to_string(), json!("定位")),
            ("target_user".to_string(), json!("用户")),
            ("primary_scene".to_string(), json!("场景")),
            ("overall_summary".to_string(), json!("总结")),
            ("about".to_string(), json!(["一点", "二点"])),
        ])
    }

    #[test]
    fn fast_mode_hides_both_optional_sections() {
        let mut row = optional_row();
        apply_extraction_visibility(&mut row, false, false);
        assert!(!row.contains_key("product_identity"));
        assert!(!row.contains_key("about"));
    }

    #[test]
    fn summary_mode_hides_only_five_point_details() {
        let mut row = optional_row();
        apply_extraction_visibility(&mut row, true, false);
        assert!(row.contains_key("product_identity"));
        assert!(!row.contains_key("about"));
    }

    #[test]
    fn full_mode_keeps_both_optional_sections() {
        let mut row = optional_row();
        apply_extraction_visibility(&mut row, true, true);
        assert!(row.contains_key("overall_summary"));
        assert!(row.contains_key("about"));
    }

    #[test]
    fn requested_workers_are_bounded_by_server_limit() {
        assert_eq!(bounded_workers(Some(100), 2, 2), 2);
        assert_eq!(bounded_workers(Some(0), 2, 2), 1);
        assert_eq!(bounded_workers(None, 4, 2), 2);
    }

    #[test]
    fn canonicalizes_and_deduplicates_selected_marketplaces() {
        let request: RunRequest = serde_json::from_value(json!({
            "asins": ["B0BHV5TTL6"],
            "marketplaces": ["DE", "jp", "germany", "JP"]
        }))
        .expect("valid request");

        assert_eq!(
            marketplace_codes(&request).expect("supported marketplaces"),
            vec!["de", "jp"]
        );
    }

    #[test]
    fn falls_back_to_legacy_single_marketplace_field() {
        let request: RunRequest = serde_json::from_value(json!({
            "asins": ["B0BHV5TTL6"],
            "marketplace": "uk"
        }))
        .expect("valid request");

        assert_eq!(marketplace_codes(&request).unwrap(), vec!["uk"]);
    }

    #[test]
    fn legacy_overview_uses_first_selected_marketplace() {
        let selected = vec!["jp".to_string(), "de".to_string()];
        let overviews = BTreeMap::from([
            (
                "de".to_string(),
                crate::models::MarketOverview {
                    sample_size: 0,
                    ..Default::default()
                },
            ),
            (
                "jp".to_string(),
                crate::models::MarketOverview {
                    sample_size: 1,
                    ..Default::default()
                },
            ),
        ]);

        assert_eq!(primary_overview(&selected, &overviews).sample_size, 1);
    }
}
