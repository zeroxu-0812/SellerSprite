use std::{
    collections::HashMap,
    env,
    path::PathBuf,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use reqwest::{header::SET_COOKIE, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::sync::Mutex;
use tokio::time::sleep;
use uuid::Uuid;

use crate::{
    error::{AppError, Result},
    models::{TrafficResponse, TrafficShare},
};

const USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36";
const TOKEN_REFRESH_BUFFER_SECONDS: f64 = 10.0 * 60.0;

pub struct SifTrafficClient {
    cache_file: PathBuf,
    refresh_lock: Mutex<()>,
    risk_until: Mutex<Option<Instant>>,
    last_request_at: Mutex<Option<Instant>>,
    traffic_cache: Mutex<HashMap<String, CachedTraffic>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TokenCache {
    token: String,
    expires_at: f64,
    #[serde(default)]
    account_index: usize,
}

#[derive(Debug, Clone)]
struct TokenLease {
    token: String,
    account_index: usize,
}

#[derive(Debug, Clone)]
struct SifAccount {
    username: String,
    password: String,
}

enum LoginFailure {
    Credential(String),
    Risk(String),
    Upstream(String),
}

#[derive(Clone)]
struct CachedTraffic {
    response: TrafficResponse,
    expires_at: Instant,
}

impl SifTrafficClient {
    pub fn new(cache_file: PathBuf) -> Self {
        Self {
            cache_file,
            refresh_lock: Mutex::new(()),
            risk_until: Mutex::new(None),
            last_request_at: Mutex::new(None),
            traffic_cache: Mutex::new(HashMap::new()),
        }
    }

    pub async fn fetch_recent_30_days(
        &self,
        client: &reqwest::Client,
        asin: &str,
        marketplace: &str,
    ) -> Result<TrafficResponse> {
        configured_accounts()?;
        self.ensure_not_cooling_down().await?;
        let station = sif_station(marketplace).ok_or_else(|| {
            AppError::BadRequest(format!("unsupported SIF marketplace: {marketplace}"))
        })?;
        let cache_key = format!("{station}:{asin}");
        if let Some(response) = self.cached_traffic(&cache_key).await {
            return Ok(response);
        }
        let snapshot = self.fetch_snapshot(client, asin, station).await?;

        let response = TrafficResponse {
            asin: asin.to_string(),
            marketplace: marketplace.to_string(),
            station: station.to_string(),
            window_days: 30,
            snapshot,
        };
        self.cache_traffic(cache_key, response.clone()).await;
        Ok(response)
    }

    async fn fetch_snapshot(
        &self,
        client: &reqwest::Client,
        asin: &str,
        station: &str,
    ) -> Result<Option<TrafficShare>> {
        let account_count = configured_accounts()?.len();
        let mut next_account = None;
        let mut auth_failures = 0usize;
        let mut transient_retries = 0usize;
        loop {
            self.ensure_not_cooling_down().await?;
            let lease = self.token(client, next_account).await?;
            next_account = None;
            let base_url = sif_base_url();
            self.wait_for_request_slot().await;
            let response = match client
                .post(format!("{base_url}/api/search/asinScoreOverview"))
                .query(&request_params(Some(station)))
                .header("accept", "application/json, text/plain, */*")
                .header("content-type", "application/json;charset=UTF-8")
                .header("origin", &base_url)
                .header(
                    "referer",
                    format!("{base_url}/reverse?country={station}&asin={asin}&piece=latelyDay&date=30&isListingSearch=true"),
                )
                .header("user-agent", USER_AGENT)
                .header("authorization", &lease.token)
                .header("cookie", format!("sif_token={}", lease.token))
                .json(&json!({
                    "asin": asin,
                    "listingSearch": true,
                    "timePieceType": "latelyDay",
                    "timePieceValue": "30",
                }))
                .send()
                .await
            {
                Ok(response) => response,
                Err(error) if transient_retries < 2 => {
                    transient_retries += 1;
                    tracing::warn!(
                        asin,
                        station,
                        attempt = transient_retries,
                        error = %error,
                        "SIF request transport retry"
                    );
                    sleep(retry_delay(transient_retries)).await;
                    continue;
                }
                Err(error) => {
                    return Err(AppError::Upstream(format!("SIF request failed: {error}")));
                }
            };
            let status = response.status();
            let payload = response.json::<Value>().await.unwrap_or(Value::Null);

            if is_risk_error(status, &payload) {
                let message = sif_message(&payload);
                self.activate_risk_cooldown().await;
                return Err(AppError::Busy(format!(
                    "SIF risk control or rate limit detected; requests paused: {message}"
                )));
            }
            if is_auth_error(status, &payload) {
                auth_failures += 1;
                self.invalidate_cache().await;
                if auth_failures >= account_count {
                    return Err(AppError::Unauthorized(
                        "all configured SIF accounts were rejected by the data API".to_string(),
                    ));
                }
                next_account = Some((lease.account_index + 1) % account_count);
                sleep(retry_delay(auth_failures)).await;
                continue;
            }
            if status.is_server_error() && transient_retries < 2 {
                transient_retries += 1;
                tracing::warn!(
                    asin,
                    station,
                    attempt = transient_retries,
                    status = %status,
                    "SIF server response retry"
                );
                sleep(retry_delay(transient_retries)).await;
                continue;
            }
            if status != StatusCode::OK {
                return Err(AppError::Upstream(format!("SIF HTTP {status}")));
            }
            if payload.get("code").and_then(Value::as_i64) != Some(1) {
                return Err(AppError::Upstream(sif_message(&payload)));
            }
            let data = payload.get("data").ok_or_else(|| {
                AppError::Upstream("SIF has no score overview for the latest 30 days".to_string())
            })?;
            let organic = ratio(data.get("nfScoreRatio"));
            let ads = ratio(data.get("adScoreRatio"));
            return Ok(traffic_share(organic, ads));
        }
    }

    async fn token(
        &self,
        client: &reqwest::Client,
        start_account: Option<usize>,
    ) -> Result<TokenLease> {
        self.ensure_not_cooling_down().await?;
        if start_account.is_none() {
            if let Some(cache) = self.load_cache().await {
                return Ok(TokenLease {
                    token: cache.token,
                    account_index: cache.account_index,
                });
            }
        }
        let _guard = self.refresh_lock.lock().await;
        if start_account.is_none() {
            if let Some(cache) = self.load_cache().await {
                return Ok(TokenLease {
                    token: cache.token,
                    account_index: cache.account_index,
                });
            }
        }

        let accounts = configured_accounts()?;
        let start = start_account.unwrap_or(0) % accounts.len();
        for offset in 0..accounts.len() {
            let account_index = (start + offset) % accounts.len();
            match self
                .login_account(client, &accounts[account_index], account_index)
                .await
            {
                Ok(cache) => {
                    let lease = TokenLease {
                        token: cache.token.clone(),
                        account_index: cache.account_index,
                    };
                    self.save_cache(&cache).await?;
                    tracing::info!(account = account_index + 1, "SIF account authenticated");
                    return Ok(lease);
                }
                Err(LoginFailure::Credential(message)) => {
                    tracing::warn!(
                        account = account_index + 1,
                        error = %message,
                        "SIF account authentication failed; trying next configured account"
                    );
                }
                Err(LoginFailure::Risk(message)) => {
                    self.activate_risk_cooldown().await;
                    return Err(AppError::Busy(format!(
                        "SIF login risk control or rate limit detected; requests paused: {message}"
                    )));
                }
                Err(LoginFailure::Upstream(message)) => {
                    return Err(AppError::Upstream(message));
                }
            }
        }

        Err(AppError::Unauthorized(format!(
            "all {} configured SIF accounts failed authentication",
            accounts.len()
        )))
    }

    async fn login_account(
        &self,
        client: &reqwest::Client,
        account: &SifAccount,
        account_index: usize,
    ) -> std::result::Result<TokenCache, LoginFailure> {
        let base_url = sif_base_url();
        let response = client
            .post(format!("{base_url}/api/user/login"))
            .query(&request_params(None))
            .header("accept", "application/json, text/plain, */*")
            .header("content-type", "application/json;charset=UTF-8")
            .header("origin", &base_url)
            .header("referer", format!("{base_url}/?country=US"))
            .header("user-agent", USER_AGENT)
            .json(&json!({ "phone": &account.username, "password": &account.password }))
            .send()
            .await
            .map_err(|error| {
                LoginFailure::Upstream(format!("SIF login request failed: {error}"))
            })?;
        let status = response.status();
        let cookies = response
            .headers()
            .get_all(SET_COOKIE)
            .iter()
            .filter_map(|value| value.to_str().ok())
            .filter_map(sif_token_from_cookie)
            .collect::<Vec<_>>();
        let payload = response.json::<Value>().await.unwrap_or(Value::Null);
        if is_risk_error(status, &payload) {
            return Err(LoginFailure::Risk(sif_message(&payload)));
        }
        if status.is_server_error() {
            return Err(LoginFailure::Upstream(format!("SIF login HTTP {status}")));
        }
        if status != StatusCode::OK || payload.get("code").and_then(Value::as_i64) != Some(1) {
            return Err(LoginFailure::Credential(sif_message(&payload)));
        }
        let token = cookies.into_iter().next().ok_or_else(|| {
            LoginFailure::Credential(
                "SIF login succeeded but did not provide sif_token".to_string(),
            )
        })?;
        Ok(TokenCache {
            expires_at: token_expiry(&token)
                .unwrap_or_else(|| now_seconds() + 7.0 * 24.0 * 60.0 * 60.0),
            token,
            account_index,
        })
    }

    async fn load_cache(&self) -> Option<TokenCache> {
        let raw = tokio::fs::read_to_string(&self.cache_file).await.ok()?;
        let cache = serde_json::from_str::<TokenCache>(&raw).ok()?;
        (cache.expires_at > now_seconds() + TOKEN_REFRESH_BUFFER_SECONDS && !cache.token.is_empty())
            .then_some(cache)
    }

    async fn save_cache(&self, cache: &TokenCache) -> Result<()> {
        let tmp = self.cache_file.with_extension("json.tmp");
        tokio::fs::write(
            &tmp,
            serde_json::to_vec(cache).map_err(anyhow::Error::from)?,
        )
        .await
        .map_err(|error| AppError::Anyhow(error.into()))?;
        // Windows cannot replace an existing file with rename the way Unix can.
        let _ = tokio::fs::remove_file(&self.cache_file).await;
        tokio::fs::rename(tmp, &self.cache_file)
            .await
            .map_err(|error| AppError::Anyhow(error.into()))
    }

    async fn invalidate_cache(&self) {
        let _ = tokio::fs::remove_file(&self.cache_file).await;
    }

    async fn ensure_not_cooling_down(&self) -> Result<()> {
        let mut risk_until = self.risk_until.lock().await;
        let Some(deadline) = *risk_until else {
            return Ok(());
        };
        let now = Instant::now();
        if deadline <= now {
            *risk_until = None;
            return Ok(());
        }
        let remaining = deadline.saturating_duration_since(now).as_secs().max(1);
        Err(AppError::Busy(format!(
            "SIF requests are cooling down after a risk-control response; retry in {remaining}s"
        )))
    }

    async fn activate_risk_cooldown(&self) {
        let seconds = env_u64("SIF_RISK_COOLDOWN_SECONDS", 300).clamp(30, 3_600);
        *self.risk_until.lock().await = Some(Instant::now() + Duration::from_secs(seconds));
        tracing::warn!(seconds, "SIF request cooldown activated");
    }

    async fn wait_for_request_slot(&self) {
        let mut last_request_at = self.last_request_at.lock().await;
        let delay = request_delay(current_millis() as usize);
        if let Some(previous) = *last_request_at {
            let elapsed = previous.elapsed();
            if elapsed < delay {
                sleep(delay - elapsed).await;
            }
        }
        *last_request_at = Some(Instant::now());
    }

    async fn cached_traffic(&self, key: &str) -> Option<TrafficResponse> {
        let now = Instant::now();
        let mut cache = self.traffic_cache.lock().await;
        cache.retain(|_, value| value.expires_at > now);
        cache.get(key).map(|value| value.response.clone())
    }

    async fn cache_traffic(&self, key: String, response: TrafficResponse) {
        let seconds = env_u64("SIF_TRAFFIC_CACHE_SECONDS", 1_800).clamp(60, 86_400);
        self.traffic_cache.lock().await.insert(
            key,
            CachedTraffic {
                response,
                expires_at: Instant::now() + Duration::from_secs(seconds),
            },
        );
    }
}

fn request_params(country: Option<&str>) -> Vec<(String, String)> {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let mut params = vec![
        ("_t".to_string(), timestamp.to_string()),
        (
            "_m".to_string(),
            format!("Sif_{}-{timestamp}", Uuid::new_v4()),
        ),
    ];
    if let Some(country) = country {
        params.push(("country".to_string(), country.to_string()));
    }
    params
}

fn sif_station(marketplace: &str) -> Option<&'static str> {
    match marketplace {
        "com" => Some("US"),
        "it" => Some("IT"),
        "uk" => Some("UK"),
        "fr" => Some("FR"),
        "es" => Some("ES"),
        "de" => Some("DE"),
        "jp" => Some("JP"),
        _ => None,
    }
}

fn sif_base_url() -> String {
    env::var("SIF_BASE_URL")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "https://www.sif.com".to_string())
        .trim_end_matches('/')
        .to_string()
}

fn env_value(names: &[&str]) -> Option<String> {
    names.iter().find_map(|name| {
        env::var(name)
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
    })
}

fn configured_accounts() -> Result<Vec<SifAccount>> {
    let mut accounts = Vec::new();
    for index in 1..=10 {
        let username = env_trimmed(&format!("SIF_USERNAME_{index}"));
        let password = env_trimmed(&format!("SIF_PASSWORD_{index}"));
        match (username, password) {
            (None, None) => {}
            (Some(username), Some(password)) => accounts.push(SifAccount { username, password }),
            _ => {
                return Err(AppError::BadRequest(format!(
                    "SIF account {index} is incomplete; configure both SIF_USERNAME_{index} and SIF_PASSWORD_{index}"
                )));
            }
        }
    }

    if accounts.is_empty() {
        let username = env_value(&["SIF_USERNAME", "SIF_PHONE", "SIF_ACCOUNT"]);
        let password = env_value(&["SIF_PASSWORD"]);
        if let (Some(username), Some(password)) = (username, password) {
            accounts.push(SifAccount { username, password });
        }
    }

    if accounts.is_empty() {
        return Err(AppError::BadRequest(
            "SIF traffic analysis needs a numbered SIF account pair or the legacy SIF_USERNAME/SIF_PASSWORD pair in .env".to_string(),
        ));
    }
    Ok(accounts)
}

fn env_trimmed(name: &str) -> Option<String> {
    env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn env_u64(name: &str, default: u64) -> u64 {
    env_trimmed(name)
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(default)
}

fn request_delay(index: usize) -> Duration {
    let minimum = env_u64("SIF_REQUEST_DELAY_MS_MIN", 900).clamp(500, 10_000);
    let maximum = env_u64("SIF_REQUEST_DELAY_MS_MAX", 1_600).clamp(minimum, 15_000);
    let spread = maximum - minimum + 1;
    let jitter =
        current_millis().wrapping_add((index as u128).wrapping_mul(1_009)) % spread as u128;
    Duration::from_millis(minimum + jitter as u64)
}

fn retry_delay(attempt: usize) -> Duration {
    let base = env_u64("SIF_RETRY_BACKOFF_MS", 1_500).clamp(500, 10_000);
    let jitter = (current_millis() % 751) as u64;
    Duration::from_millis(base.saturating_mul(attempt as u64).saturating_add(jitter))
}

fn current_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn sif_token_from_cookie(header: &str) -> Option<String> {
    header
        .split(';')
        .find_map(|part| part.trim().strip_prefix("sif_token="))
        .map(str::to_string)
        .filter(|value| !value.is_empty())
}

fn token_expiry(token: &str) -> Option<f64> {
    let payload = token.split('.').nth(1)?;
    let raw = URL_SAFE_NO_PAD.decode(payload).ok()?;
    serde_json::from_slice::<Value>(&raw)
        .ok()?
        .get("exp")?
        .as_f64()
}

fn ratio(value: Option<&Value>) -> f64 {
    let number = match value {
        Some(Value::Number(value)) => value.as_f64().unwrap_or(0.0),
        Some(Value::String(value)) => value
            .trim()
            .trim_end_matches('%')
            .parse::<f64>()
            .unwrap_or(0.0),
        _ => 0.0,
    };
    let normalized = if number > 1.0 { number / 100.0 } else { number };
    normalized.clamp(0.0, 1.0)
}

fn traffic_share(organic: f64, ads: f64) -> Option<TrafficShare> {
    if organic == 0.0 && ads == 0.0 {
        return None;
    }
    let remainder = (1.0 - organic - ads).max(0.0);
    Some(TrafficShare {
        organic,
        ads,
        recommendation: if remainder < 1e-9 { 0.0 } else { remainder },
    })
}

fn is_auth_error(status: StatusCode, payload: &Value) -> bool {
    if status == StatusCode::UNAUTHORIZED {
        return true;
    }
    has_auth_error_code(payload)
}

fn is_risk_error(status: StatusCode, payload: &Value) -> bool {
    if status == StatusCode::TOO_MANY_REQUESTS {
        return true;
    }
    if status == StatusCode::FORBIDDEN && !has_auth_error_code(payload) {
        return true;
    }
    let message = sif_message(payload).to_ascii_lowercase();
    [
        "频繁",
        "风控",
        "稍后再试",
        "too many",
        "rate limit",
        "risk control",
    ]
    .iter()
    .any(|marker| message.contains(marker))
}

fn has_auth_error_code(payload: &Value) -> bool {
    matches!(
        payload.get("code").and_then(Value::as_i64),
        Some(-5 | -7 | -10)
    )
}

fn sif_message(payload: &Value) -> String {
    payload
        .get("message")
        .or_else(|| payload.get("msg"))
        .and_then(Value::as_str)
        .unwrap_or("unknown SIF response")
        .to_string()
}

fn now_seconds() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_ratio_formats() {
        assert_eq!(ratio(Some(&json!(0.32))), 0.32);
        assert_eq!(ratio(Some(&json!(32))), 0.32);
        assert_eq!(ratio(Some(&json!("32%"))), 0.32);
        assert_eq!(ratio(Some(&json!("invalid"))), 0.0);
    }

    #[test]
    fn treats_one_hundred_percent_recommendation_as_unavailable() {
        assert!(traffic_share(0.0, 0.0).is_none());
        assert!(traffic_share(0.01, 0.0).is_some());
        assert_eq!(traffic_share(0.8, 0.2).unwrap().recommendation, 0.0);
    }

    #[test]
    fn extracts_sif_cookie() {
        assert_eq!(
            sif_token_from_cookie("sif_token=token-value; Path=/; HttpOnly"),
            Some("token-value".to_string())
        );
    }

    #[test]
    fn detects_risk_control_responses() {
        assert!(is_risk_error(StatusCode::TOO_MANY_REQUESTS, &Value::Null));
        assert!(is_risk_error(
            StatusCode::OK,
            &json!({ "message": "请求过于频繁" })
        ));
        assert!(!is_risk_error(StatusCode::OK, &json!({ "message": "ok" })));
        let expired_token = json!({ "code": -5, "message": "token expired" });
        assert!(is_auth_error(StatusCode::FORBIDDEN, &expired_token));
        assert!(!is_risk_error(StatusCode::FORBIDDEN, &expired_token));
    }

    #[test]
    fn reads_legacy_token_cache_without_account_index() {
        let cache: TokenCache = serde_json::from_value(json!({
            "token": "legacy-token",
            "expires_at": 123.0
        }))
        .expect("legacy token cache should deserialize");
        assert_eq!(cache.account_index, 0);
    }
}
