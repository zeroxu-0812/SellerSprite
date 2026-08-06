use std::collections::HashMap;
use std::time::Duration;

use reqwest::StatusCode;
use serde_json::Value;
use tokio::time::sleep;

use crate::{
    auth::TokenManager,
    config::AppConfig,
    error::{AppError, Result},
    models::Failure,
    signing::{extension_version_token, sellersprite_token},
};

#[derive(Debug, Default)]
pub struct LookupOutput {
    pub items: Vec<Value>,
    pub failures: Vec<Failure>,
}

pub async fn lookup_asins(
    client: &reqwest::Client,
    config: &AppConfig,
    token_manager: &TokenManager,
    asins: &[String],
) -> Result<LookupOutput> {
    let batch_size = config.quick_view.batch_size.max(1);
    let mut out = LookupOutput::default();
    let chunks = asins.chunks(batch_size).collect::<Vec<_>>();
    for (index, chunk) in chunks.iter().enumerate() {
        if index > 0 {
            sleep(batch_delay(config, index)).await;
        }
        match fetch_chunk(client, config, token_manager, chunk, false).await {
            Ok(mut chunk_out) => {
                out.items.append(&mut chunk_out.items);
                out.failures.append(&mut chunk_out.failures);
            }
            Err(AppError::Upstream(message)) => {
                tracing::warn!("competitor lookup skipped batch: {message}");
                out.failures.extend(chunk.iter().map(|asin| Failure {
                    asin: asin.to_string(),
                    stage: "sellersprite_lookup".to_string(),
                    message: message.clone(),
                    marketplace: None,
                }));
            }
            Err(err) => return Err(err),
        }
    }
    Ok(out)
}

fn batch_delay(config: &AppConfig, index: usize) -> Duration {
    let min = config.quick_view.delay_seconds_min;
    let max = config.quick_view.delay_seconds_max.max(min);
    let span = max.saturating_sub(min) + 1;
    Duration::from_secs(min + (index as u64 % span))
}

async fn fetch_chunk(
    client: &reqwest::Client,
    config: &AppConfig,
    token_manager: &TokenManager,
    chunk: &[String],
    healed: bool,
) -> Result<LookupOutput> {
    let url = build_competitor_url(config, chunk);
    let attempts = config.quick_view.retry_attempts + 1;
    let mut last_error = None;
    for attempt in 1..=attempts {
        let headers = token_manager
            .headers()
            .await
            .map_err(|err| AppError::AuthExpired(err.to_string()))?;
        let response = request_json(
            client,
            &url,
            headers,
            config.quick_view.request_timeout_seconds,
        )
        .await;
        match response {
            Ok((status, payload)) => {
                if is_auth_expired(status, &payload) {
                    if !healed {
                        token_manager.invalidate_cache().await.ok();
                        return Box::pin(fetch_chunk(client, config, token_manager, chunk, true))
                            .await;
                    }
                    return Err(AppError::AuthExpired(
                        "refresh did not recover token".to_string(),
                    ));
                }
                if status == StatusCode::OK && is_ok_payload(&payload) {
                    return Ok(parse_payload(payload));
                }
                return Err(AppError::Upstream(format!(
                    "code={:?} http={status}",
                    payload.get("code")
                )));
            }
            Err(err) => {
                last_error = Some(err.to_string());
                if attempt < attempts {
                    sleep(Duration::from_secs(
                        config.quick_view.retry_backoff_seconds * attempt as u64,
                    ))
                    .await;
                }
            }
        }
    }
    Err(AppError::Upstream(
        last_error.unwrap_or_else(|| "request failed".to_string()),
    ))
}

fn build_competitor_url(config: &AppConfig, asins: &[String]) -> String {
    let asins_str = asins.join(",");
    let ext = extension_version_token(&config.version);
    let tk = sellersprite_token(&[&asins_str], &ext);
    let base = config
        .quick_view
        .base_url
        .rsplit_once("/quick-view")
        .map(|(base, _)| base)
        .unwrap_or(&config.quick_view.base_url);
    format!(
        "{}/{station}?asins={asins}&source={source}&tk={tk}&version={version}&language={language}&extension={extension}",
        base,
        station = config.station,
        asins = asins_str,
        source = config.source,
        version = config.version,
        language = config.language,
        extension = config.extension_id,
    )
}

async fn request_json(
    client: &reqwest::Client,
    url: &str,
    headers: HashMap<String, String>,
    timeout_seconds: u64,
) -> anyhow::Result<(StatusCode, Value)> {
    let mut req = client
        .get(url)
        .timeout(Duration::from_secs(timeout_seconds))
        .header("accept", "application/json");
    for (key, value) in headers {
        req = req.header(key, value);
    }
    let resp = req.send().await?;
    let status = resp.status();
    let payload = resp.json::<Value>().await.unwrap_or(Value::Null);
    Ok((status, payload))
}

fn is_ok_payload(payload: &Value) -> bool {
    match payload.get("code") {
        None => true,
        Some(Value::Number(n)) => n.as_i64() == Some(200),
        Some(Value::String(s)) => s == "200" || s == "OK",
        _ => false,
    }
}

fn is_auth_expired(status: StatusCode, payload: &Value) -> bool {
    if status == StatusCode::UNAUTHORIZED {
        return true;
    }
    let code = payload
        .get("code")
        .and_then(|v| v.as_str())
        .unwrap_or_default();
    let message = payload
        .get("message")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    matches!(
        code,
        "401"
            | "UNAUTHORIZED"
            | "TOKEN_EXPIRED"
            | "AUTH_EXPIRED"
            | "ERR_NEED_RE_AUTHORIZED"
            | "ERR_GLOBAL_SESSION_EXPIRED"
    ) || [
        "令牌过期",
        "token expired",
        "token invalid",
        "auth expired",
        "unauthorized",
        "登录失效",
        "重新登录",
    ]
    .iter()
    .any(|needle| message.contains(&needle.to_ascii_lowercase()))
}

fn parse_payload(mut payload: Value) -> LookupOutput {
    let crawl_asins = payload
        .get("data")
        .and_then(|d| d.get("crawlAsins"))
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let items = payload
        .get_mut("data")
        .and_then(|d| d.get_mut("items"))
        .and_then(|items| items.as_array_mut())
        .map(std::mem::take)
        .unwrap_or_default();
    let items = items
        .into_iter()
        .map(|mut item| {
            normalize_no_data(&mut item);
            item
        })
        .collect();
    let failures = crawl_asins
        .into_iter()
        .filter_map(|value| value.as_str().map(str::to_string))
        .map(|asin| Failure {
            asin,
            stage: "sellersprite_lookup".to_string(),
            message:
                "卖家精灵返回 crawlAsins，表示该 ASIN 暂无现成明细，可能正在排队抓取；稍后重试。"
                    .to_string(),
            marketplace: None,
        })
        .collect();
    LookupOutput { items, failures }
}

fn normalize_no_data(item: &mut Value) {
    let fields = [
        "units",
        "month_units",
        "amount",
        "amount_growth",
        "profit",
        "fba",
        "sellers",
        "variations",
        "reviews",
        "lqs",
    ];
    if let Some(map) = item.as_object_mut() {
        for field in fields {
            if map.get(field).and_then(|v| v.as_i64()) == Some(-1) {
                map.insert(field.to_string(), Value::Null);
            }
        }
    }
}
