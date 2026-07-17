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
    error::{AppError, Result},
    models::{Failure, ProductDetail, RunMode, RunRequest, RunResponse},
    overview::derive_market_overview,
    sellersprite,
    transform::{clean_row, enrich_derived, flatten_record},
};

pub async fn process_asins_with_progress(
    state: &AppState,
    request: RunRequest,
    job_id: String,
) -> Result<RunResponse> {
    let asins = normalize_asins(request.asins);
    if asins.is_empty() {
        return Err(AppError::BadRequest("no valid ASINs".to_string()));
    }
    state.jobs.set_total(&job_id, asins.len()).await;
    state.jobs.running(&job_id, "卖家精灵").await;
    let workers = request
        .workers
        .unwrap_or(state.config.concurrency.workers)
        .max(1);
    let mut lookup =
        sellersprite::lookup_asins(&state.client, &state.config, &state.token_manager, &asins)
            .await?;
    let completed = if request.mode == RunMode::Fast { asins.len() } else { 0 };
    state
        .jobs
        .advance(&job_id, completed, None, "卖家精灵")
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

    if request.mode == RunMode::Full {
        let details = fetch_details(state, by_asin.keys().cloned().collect(), workers, &job_id).await;
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
            enrich_derived(&mut row);
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
            sleep(request_delay(&state.config, index)).await;
            let result = amazon::fetch_product_detail(&state.client, &asin, &state.config)
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
    if tokio::fs::try_exists(out_dir).await.unwrap_or(false) {
        tokio::fs::remove_dir_all(out_dir)
            .await
            .map_err(|err| AppError::Anyhow(err.into()))?;
    }
    tokio::fs::create_dir_all(out_dir)
        .await
        .map_err(|err| AppError::Anyhow(err.into()))?;
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
