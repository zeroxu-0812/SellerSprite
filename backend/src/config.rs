use std::path::Path;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AppConfig {
    pub station: String,
    pub language: String,
    pub version: String,
    pub extension_id: String,
    pub source: String,
    pub concurrency: ConcurrencyConfig,
    pub quick_view: QuickViewConfig,
    pub amazon: AmazonConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ConcurrencyConfig {
    pub workers: usize,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct QuickViewConfig {
    pub base_url: String,
    pub batch_size: usize,
    pub request_timeout_seconds: u64,
    pub retry_attempts: usize,
    pub retry_backoff_seconds: u64,
    pub delay_seconds_min: u64,
    pub delay_seconds_max: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AmazonConfig {
    pub base_url: String,
    pub user_agent: String,
}

impl AppConfig {
    pub async fn load(path: impl AsRef<Path>) -> anyhow::Result<Self> {
        let raw = tokio::fs::read_to_string(path).await?;
        Ok(serde_json::from_str(&raw)?)
    }
}
