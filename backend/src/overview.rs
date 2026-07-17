use std::collections::BTreeMap;

use serde_json::Value;

use crate::{models::MarketOverview, transform::to_number};

pub fn derive_market_overview(rows: &[BTreeMap<String, Value>]) -> MarketOverview {
    let prices = numbers(rows, "price");
    let ratings = numbers(rows, "rating");
    let reviews = numbers(rows, "reviews");
    let units = numbers(rows, "units");
    let amounts = numbers(rows, "amount");

    let total_units = units.iter().sum::<f64>();
    let mut sorted_units = units.clone();
    sorted_units.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
    let top10_units = sorted_units.into_iter().take(10).sum::<f64>();

    MarketOverview {
        result_count: None,
        sample_size: rows.len(),
        avg_price: avg(&prices),
        avg_rating: avg(&ratings),
        avg_reviews: avg(&reviews),
        total_units: total_units as i64,
        total_amount: round2(amounts.iter().sum::<f64>()),
        top10_units_share: if total_units > 0.0 {
            Some(round4(top10_units / total_units))
        } else {
            None
        },
        price_distribution: hist(&prices, &[0.0, 15.0, 25.0, 40.0, 60.0, 100.0, 1_000_000.0]),
        rating_distribution: hist(&ratings, &[0.0, 3.5, 4.0, 4.3, 4.5, 4.7, 5.01]),
    }
}

fn numbers(rows: &[BTreeMap<String, Value>], key: &str) -> Vec<f64> {
    rows.iter()
        .filter_map(|row| to_number(row.get(key)))
        .collect()
}

fn avg(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        Some(round2(values.iter().sum::<f64>() / values.len() as f64))
    }
}

fn hist(values: &[f64], edges: &[f64]) -> BTreeMap<String, usize> {
    let mut bins = BTreeMap::new();
    for pair in edges.windows(2) {
        bins.insert(format!("{}~{}", pair[0], pair[1]), 0);
    }
    for value in values {
        for pair in edges.windows(2) {
            if pair[0] <= *value && *value < pair[1] {
                let key = format!("{}~{}", pair[0], pair[1]);
                *bins.entry(key).or_insert(0) += 1;
                break;
            }
        }
    }
    bins
}

fn round2(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

fn round4(value: f64) -> f64 {
    (value * 10_000.0).round() / 10_000.0
}
