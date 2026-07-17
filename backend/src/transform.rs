use std::collections::BTreeMap;

use chrono::{DateTime, Utc};
use regex::Regex;
use serde_json::Value;

pub fn flatten_record(record: &Value) -> BTreeMap<String, Value> {
    let mut out = BTreeMap::new();
    flatten_into(record, "", &mut out);
    out
}

pub fn enrich_derived(row: &mut BTreeMap<String, Value>) {
    if let Some(image) = row.get("image").and_then(|v| v.as_str()) {
        row.insert(
            "image_large".to_string(),
            string_value(large_image_url(image)),
        );
    }
    if let Some(asin) = row.get("asin").and_then(|v| v.as_str()) {
        row.insert(
            "url".to_string(),
            string_value(format!("https://www.amazon.com/dp/{asin}")),
        );
    }
    if let Some(available) = row.get("available").and_then(number_to_f64) {
        let millis = available as i64;
        if let Some(dt) = DateTime::<Utc>::from_timestamp_millis(millis) {
            row.insert(
                "available_date".to_string(),
                string_value(dt.format("%Y-%m-%d").to_string()),
            );
        }
    }
    if let Some(trends) = row.get("trends").and_then(trend_pairs_to_map) {
        row.insert("parent_unit_trend".to_string(), Value::String(trends));
    }
}

pub fn clean_row(row: BTreeMap<String, Value>) -> BTreeMap<String, Value> {
    row.into_iter()
        .filter(|(key, value)| {
            !matches!(key.as_str(), "bsr_list" | "amz_unit_trends" | "trends") && !is_empty(value)
        })
        .collect()
}

pub fn to_number(value: Option<&Value>) -> Option<f64> {
    value.and_then(number_to_f64).or_else(|| {
        value.and_then(|v| v.as_str()).and_then(|s| {
            Regex::new(r#"-?\d+(?:\.\d+)?"#)
                .ok()?
                .find(&s.replace(',', ""))
                .and_then(|m| m.as_str().parse().ok())
        })
    })
}

fn flatten_into(value: &Value, prefix: &str, out: &mut BTreeMap<String, Value>) {
    match value {
        Value::Object(map) => {
            let mut scalars = Vec::new();
            let mut nested = Vec::new();
            for (key, value) in map {
                if value.is_array() || value.is_object() {
                    nested.push((key, value));
                } else {
                    scalars.push((key, value));
                }
            }
            for (key, value) in scalars {
                let flat_key = join_key(prefix, &camel_to_snake(key));
                out.insert(flat_key, value.clone());
            }
            for (key, value) in nested {
                let flat_key = join_key(prefix, &camel_to_snake(key));
                flatten_into(value, &flat_key, out);
            }
        }
        Value::Array(items) if items.iter().all(Value::is_object) => {
            flatten_rank_array(items, prefix, out);
            out.insert(prefix.to_string(), value.clone());
        }
        Value::Array(_) => {
            out.insert(prefix.to_string(), value.clone());
        }
        _ => {
            out.insert(prefix.to_string(), value.clone());
        }
    }
}

fn flatten_rank_array(items: &[Value], prefix: &str, out: &mut BTreeMap<String, Value>) {
    let mut sub_done = false;
    for item in items {
        let Some(map) = item.as_object() else {
            continue;
        };
        let rank = map.get("rank").cloned().unwrap_or(Value::Null);
        let label = map.get("label").cloned().unwrap_or(Value::Null);
        if map.get("main").and_then(|v| v.as_bool()).unwrap_or(false) {
            out.insert(format!("{prefix}__main_rank"), rank);
            out.insert(format!("{prefix}__main_label"), label);
        } else if !sub_done {
            out.insert(format!("{prefix}__sub_rank"), rank);
            out.insert(format!("{prefix}__sub_label"), label);
            sub_done = true;
        }
    }
}

fn join_key(prefix: &str, key: &str) -> String {
    if prefix.is_empty() {
        key.to_string()
    } else {
        format!("{prefix}__{key}")
    }
}

fn camel_to_snake(input: &str) -> String {
    let canonical = match input {
        "buyPrice" => "buy_price",
        "bsrList" => "bsr_list",
        other => other,
    };
    let re1 = Regex::new(r#"(.)([A-Z][a-z]+)"#).expect("valid regex");
    let re2 = Regex::new(r#"([a-z0-9])([A-Z])"#).expect("valid regex");
    let step = re1.replace_all(canonical, "$1_$2");
    re2.replace_all(&step, "$1_$2").to_ascii_lowercase()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn canonical_field_names_match_python() {
        assert_eq!(camel_to_snake("buyPrice"), "buy_price");
        assert_eq!(camel_to_snake("bsrList"), "bsr_list");
    }

    #[test]
    fn flattens_bsr_list_to_expected_keys() {
        let row = flatten_record(&json!({
            "bsrList": [
                {"rank": 13465, "main": true, "label": "Health & Household"},
                {"rank": 53, "main": false, "label": "Bath Oils"}
            ]
        }));
        assert_eq!(row.get("bsr_list__main_rank"), Some(&json!(13465)));
        assert_eq!(
            row.get("bsr_list__main_label"),
            Some(&json!("Health & Household"))
        );
        assert_eq!(row.get("bsr_list__sub_rank"), Some(&json!(53)));
        assert_eq!(row.get("bsr_list__sub_label"), Some(&json!("Bath Oils")));
    }
}

fn large_image_url(url: &str) -> String {
    let re = Regex::new(r#"/images/I/([^/.]+?)\._"#).expect("valid regex");
    re.captures(url)
        .map(|cap| {
            format!(
                "https://images-na.ssl-images-amazon.com/images/I/{}._AC_SL1500_.jpg",
                &cap[1]
            )
        })
        .unwrap_or_else(|| url.to_string())
}

fn trend_pairs_to_map(value: &Value) -> Option<String> {
    let arr = match value {
        Value::String(s) => serde_json::from_str::<Value>(s).ok()?,
        other => other.clone(),
    };
    let mut map = serde_json::Map::new();
    for item in arr.as_array()? {
        let Some(dk) = item.get("dk").and_then(|v| v.as_str()) else {
            continue;
        };
        let Some(sales) = item.get("sales") else {
            continue;
        };
        map.insert(dk.to_string(), sales.clone());
    }
    if map.is_empty() {
        None
    } else {
        Some(Value::Object(map).to_string())
    }
}

fn is_empty(value: &Value) -> bool {
    match value {
        Value::Null => true,
        Value::String(s) => s.is_empty() || matches!(s.trim(), "{}" | "[]" | "null"),
        Value::Array(a) => a.is_empty(),
        Value::Object(o) => o.is_empty(),
        _ => false,
    }
}

fn number_to_f64(value: &Value) -> Option<f64> {
    match value {
        Value::Number(n) => n.as_f64(),
        _ => None,
    }
}

fn string_value(value: String) -> Value {
    Value::String(value)
}
