use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RunRequest {
    pub asins: Vec<String>,
    #[serde(default = "RunMode::default")]
    pub mode: RunMode,
    pub workers: Option<usize>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RunMode {
    Fast,
    Full,
}

impl Default for RunMode {
    fn default() -> Self {
        Self::Full
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct RunResponse {
    pub products: Vec<BTreeMap<String, Value>>,
    pub overview: MarketOverview,
    pub failures: Vec<Failure>,
    pub output_dir: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Failure {
    pub asin: String,
    pub stage: String,
    pub message: String,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ProductDetail {
    pub list_price: Option<f64>,
    pub price_current: Option<f64>,
    pub discount_off_list_pct: Option<f64>,
    pub about: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct MarketOverview {
    pub result_count: Option<usize>,
    pub sample_size: usize,
    pub avg_price: Option<f64>,
    pub avg_rating: Option<f64>,
    pub avg_reviews: Option<f64>,
    pub total_units: i64,
    pub total_amount: f64,
    pub top10_units_share: Option<f64>,
    pub price_distribution: BTreeMap<String, usize>,
    pub rating_distribution: BTreeMap<String, usize>,
}
