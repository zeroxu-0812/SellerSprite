use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Debug, Clone, Deserialize)]
pub struct AdminLoginRequest {
    pub username: String,
    pub password: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct AdminLoginResponse {
    pub token: String,
    #[serde(rename = "expiresInSeconds")]
    pub expires_in_seconds: u64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RunRequest {
    pub asins: Vec<String>,
    #[serde(default, alias = "station")]
    pub marketplace: Option<String>,
    #[serde(default)]
    pub include_summary: Option<bool>,
    #[serde(default)]
    pub include_details: Option<bool>,
    #[serde(default)]
    pub mode: Option<RunMode>,
    pub workers: Option<usize>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RunMode {
    Fast,
    Full,
}

impl RunRequest {
    pub fn extraction_options(&self) -> (bool, bool) {
        let legacy_full = self.mode == Some(RunMode::Full);
        let include_details = self.include_details.unwrap_or(legacy_full);
        let include_summary = self.include_summary.unwrap_or(legacy_full);
        (include_summary, include_details)
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

#[cfg(test)]
mod tests {
    use super::*;

    fn request(json: &str) -> RunRequest {
        serde_json::from_str(json).expect("valid request")
    }

    #[test]
    fn defaults_to_fast_extraction() {
        let request = request(r#"{"asins":["B0BHV5TTL6"]}"#);
        assert_eq!(request.extraction_options(), (false, false));
    }

    #[test]
    fn details_can_be_requested_without_summary() {
        let request = request(
            r#"{"asins":["B0BHV5TTL6"],"includeSummary":false,"includeDetails":true}"#,
        );
        assert_eq!(request.extraction_options(), (false, true));
    }

    #[test]
    fn summary_can_be_requested_without_details() {
        let request = request(
            r#"{"asins":["B0BHV5TTL6"],"includeSummary":true,"includeDetails":false}"#,
        );
        assert_eq!(request.extraction_options(), (true, false));
    }

    #[test]
    fn keeps_legacy_full_mode_compatible() {
        let request = request(r#"{"asins":["B0BHV5TTL6"],"mode":"full"}"#);
        assert_eq!(request.extraction_options(), (true, true));
    }
}
