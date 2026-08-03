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
    let RunRequest {
        asins,
        marketplace,
        include_summary: _,
        include_details: _,
        mode: _,
        workers,
    } = request;
    let asins = normalize_asins(asins);
    if asins.is_empty() {
        return Err(AppError::BadRequest("no valid ASINs".to_string()));
    }
    let runtime_config = config_for_marketplace(&state.config, marketplace.as_deref())?;
    state.jobs.set_total(&job_id, asins.len()).await;
    state
        .jobs
        .running(&job_id, format!("卖家精灵 {}", runtime_config.station))
        .await;
    let workers = workers.unwrap_or(runtime_config.concurrency.workers).max(1);
    let mut lookup =
        sellersprite::lookup_asins(&state.client, &runtime_config, &state.token_manager, &asins)
            .await?;
    let completed = if include_details { 0 } else { asins.len() };
    state
        .jobs
        .advance(&job_id, completed, None, format!("卖家精灵 {}", runtime_config.station))
        .await;
    let mut failures = Vec::new();
    failures.append(&mut lookup.failures);
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
        )
        .await;
        for (asin, result) in details {
            match result {
                Ok(detail) => apply_detail(by_asin.get_mut(&asin), detail),
                Err(message) => failures.push(Failure {
                    asin,
                    stage: "amazon_detail".to_string(),
                    message,
                }),
            }
        }
    }

    let mut rows = by_asin
        .values()
        .map(flatten_record)
        .map(|mut row| {
            enrich_derived(&mut row, &runtime_config.amazon.base_url);
            if include_summary {
                enrich_product_summary(&mut row);
            }
            apply_extraction_visibility(&mut row, include_summary, include_details);
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
    rows.sort_by(|a, b| {
        a.get("asin")
            .and_then(|v| v.as_str())
            .cmp(&b.get("asin").and_then(|v| v.as_str()))
    });
    let overview = derive_market_overview(&rows);
    let out_dir = state.root.join("output");
    write_outputs(&out_dir, &rows, &overview, &failures).await?;

    let response = RunResponse {
        products: rows,
        overview,
        failures,
        output_dir: out_dir.to_string_lossy().to_string(),
    };
    state.jobs.advance(&job_id, asins.len(), None, "完成").await;
    Ok(response)
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

fn config_for_marketplace(base: &AppConfig, marketplace: Option<&str>) -> Result<AppConfig> {
    let Some(raw) = marketplace.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok(base.clone());
    };
    let key = raw
        .to_ascii_lowercase()
        .chars()
        .filter(|ch| !matches!(ch, '_' | '-' | ' ' | '.'))
        .collect::<String>();
    let (station, amazon_base_url) = match key.as_str() {
        "com" | "us" | "usa" | "unitedstates" => ("US", "https://www.amazon.com"),
        "it" | "italy" | "italia" => ("IT", "https://www.amazon.it"),
        "uk" | "gb" | "greatbritain" | "unitedkingdom" | "couk" => {
            ("UK", "https://www.amazon.co.uk")
        }
        "fr" | "france" => ("FR", "https://www.amazon.fr"),
        "es" | "spain" | "espana" => ("ES", "https://www.amazon.es"),
        "de" | "germany" | "deutschland" => ("DE", "https://www.amazon.de"),
        "jp" | "japan" | "cojp" => ("JP", "https://www.amazon.co.jp"),
        _ => {
            return Err(AppError::BadRequest(format!(
                "unsupported marketplace: {raw}. supported: com, it, uk, fr, es, de, jp"
            )))
        }
    };
    let mut config = base.clone();
    config.station = station.to_string();
    config.amazon.base_url = amazon_base_url.to_string();
    Ok(config)
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

async fn fetch_details(
    state: &AppState,
    config: &AppConfig,
    asins: Vec<String>,
    workers: usize,
    job_id: &str,
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
                .advance(job_id, done, Some(asin.clone()), format!("详情页 {done}/{total}"))
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
    failures: &[Failure],
) -> Result<()> {
    tokio::fs::create_dir_all(out_dir)
        .await
        .map_err(|err| AppError::Anyhow(err.into()))?;
    let mut entries = tokio::fs::read_dir(out_dir)
        .await
        .map_err(|err| AppError::Anyhow(err.into()))?;
    while let Some(entry) = entries
        .next_entry()
        .await
        .map_err(|err| AppError::Anyhow(err.into()))?
    {
        let path = entry.path();
        if tokio::fs::remove_dir_all(&path).await.is_err() {
            let _ = tokio::fs::remove_file(&path).await;
        }
    }
    tokio::fs::write(
        out_dir.join("products.json"),
        serde_json::to_vec_pretty(products).map_err(anyhow::Error::from)?,
    )
    .await
    .map_err(|err| AppError::Anyhow(err.into()))?;
    tokio::fs::write(
        out_dir.join("market_overview.json"),
        serde_json::to_vec_pretty(overview).map_err(anyhow::Error::from)?,
    )
    .await
    .map_err(|err| AppError::Anyhow(err.into()))?;
    tokio::fs::write(
        out_dir.join("failures.json"),
        serde_json::to_vec_pretty(failures).map_err(anyhow::Error::from)?,
    )
    .await
    .map_err(|err| AppError::Anyhow(err.into()))?;
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
}
