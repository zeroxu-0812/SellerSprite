use std::collections::BTreeMap;

use regex::Regex;
use serde_json::Value;

/// Add stable, Chinese listing-summary fields without calling an external model.
///
/// SellerSprite and Amazon provide localized listing facts. This layer turns the
/// facts we can identify confidently into the four fields used by the UI while
/// preserving any upstream values that may already exist.
pub fn enrich_product_summary(row: &mut BTreeMap<String, Value>) {
    let source = source_text(row);
    if source.trim().is_empty() {
        return;
    }

    let lower = source.to_lowercase();
    let is_lint_remover = contains_any(
        &lower,
        &[
            "毛玉取り",
            "毛玉クリーナー",
            "毛球",
            "毛球修剪",
            "lint remover",
            "fabric shaver",
            "pilling",
        ],
    );
    let battery_powered = contains_any(
        &lower,
        &[
            "電池式",
            "乾電池",
            "単3",
            "単4",
            "电池",
            "干电池",
            "battery",
        ],
    );
    let handheld = contains_any(
        &lower,
        &[
            "手持",
            "スリムグリップ",
            "グリップ",
            "handheld",
            "portable",
            "便携",
        ],
    );

    let product_identity = if is_lint_remover {
        if battery_powered && handheld {
            "一个手持式干电池驱动的毛球修剪器".to_string()
        } else if battery_powered {
            "一款干电池驱动的毛球修剪器".to_string()
        } else {
            "一款用于衣物护理的毛球修剪器".to_string()
        }
    } else {
        "一款面向日常使用的实用商品".to_string()
    };

    let target_user = if is_lint_remover {
        "家里有毛衣、针织衫等易起球衣物，且追求高性价比的家庭用户".to_string()
    } else {
        "有明确日常使用需求，并关注实用性与性价比的家庭用户".to_string()
    };

    let primary_scene = if is_lint_remover {
        "在家里整理衣物时，手持机器在毛衣表面来回移动，快速清理起球部位".to_string()
    } else {
        "在日常生活场景中使用该商品，完成对应的功能需求".to_string()
    };

    let overall_summary = if is_lint_remover {
        lint_remover_summary(&source, &lower, battery_powered)
    } else {
        let title = row
            .get("title")
            .map(value_text)
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "该商品".to_string());
        format!(
            "{}围绕日常使用需求提供核心功能，当前摘要根据 listing 标题与详情特征自动生成。",
            title
        )
    };

    insert_if_missing(row, "product_identity", product_identity);
    insert_if_missing(row, "target_user", target_user);
    insert_if_missing(row, "primary_scene", primary_scene);
    insert_if_missing(row, "overall_summary", overall_summary);
}

fn lint_remover_summary(source: &str, lower: &str, battery_powered: bool) -> String {
    let blade = find_millimeter_size(source).unwrap_or_else(|| "大尺寸".to_string());
    let mut summary = format!(
        "这款产品最大的亮点是{}的大刀头，能一次性覆盖更多面积，大幅提升清理效率。",
        blade
    );

    if contains_any(source, &["安全スイッチ", "安全开关", "safety switch"]) {
        summary.push_str("机身设计了安全开关，拆卸刀头时会自动阻止启动。");
    }
    if contains_any(source, &["外刃カバー", "カバー", "保护盖", "cover"]) {
        summary.push_str("同时配有外刃保护盖，收纳时更安心。");
    }
    if contains_any(
        source,
        &[
            "毛玉収納ケース",
            "収納ケース",
            "可拆卸",
            "着脱式",
            "收集盒",
            "collector",
        ],
    ) {
        summary.push_str("可拆卸的毛屑收集盒便于清理和日常维护。");
    }
    if battery_powered && contains_any(source, &["単3", "单三", "AA"]) {
        summary.push_str("采用单三干电池供电，无需固定电源，适合家庭随时使用。");
    } else if battery_powered {
        summary.push_str("采用电池供电，使用位置更灵活。");
    }
    if contains_any(lower, &["約80分", "约80分钟", "80 minutes", "80 min"]) {
        summary.push_str("单次使用时间约80分钟。");
    }
    summary
}

fn source_text(row: &BTreeMap<String, Value>) -> String {
    ["title", "about", "brand", "node_label_path"]
        .iter()
        .filter_map(|key| row.get(*key).map(value_text))
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn value_text(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::String(value) => value.clone(),
        Value::Array(values) => values
            .iter()
            .map(value_text)
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>()
            .join(" "),
        Value::Object(values) => values
            .values()
            .map(value_text)
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>()
            .join(" "),
        other => other.to_string(),
    }
}

fn contains_any(source: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| source.contains(needle))
}

fn find_millimeter_size(source: &str) -> Option<String> {
    let re = Regex::new(r"(?i)(\d{2,3})\s*mm").ok()?;
    re.captures(source)
        .map(|capture| format!("{}mm", &capture[1]))
}

fn insert_if_missing(row: &mut BTreeMap<String, Value>, key: &str, value: String) {
    let has_value = row
        .get(key)
        .map(value_text)
        .is_some_and(|current| !current.trim().is_empty());
    if !has_value {
        row.insert(key.to_string(), Value::String(value));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn generates_japanese_lint_remover_summary() {
        let mut row = BTreeMap::from([
            (
                "title".to_string(),
                json!("オーム電機 毛玉取り器 電動 電池式 スリムグリップ 外刃42mm"),
            ),
            (
                "about".to_string(),
                json!([
                    "約42mm外刃で一度にたくさん毛玉が取れます",
                    "安全スイッチ付きで外刃を外した状態のときは電源が入りません",
                    "外刃カバー付き",
                    "着脱式の毛玉収納ケース",
                    "単3乾電池2本使用",
                    "動作時間:約80分",
                ]),
            ),
        ]);

        enrich_product_summary(&mut row);

        assert_eq!(
            row.get("product_identity"),
            Some(&json!("一个手持式干电池驱动的毛球修剪器"))
        );
        assert_eq!(
            row.get("target_user"),
            Some(&json!("家里有毛衣、针织衫等易起球衣物，且追求高性价比的家庭用户"))
        );
        assert!(value_text(row.get("primary_scene").unwrap()).contains("毛衣表面"));
        assert!(value_text(row.get("overall_summary").unwrap()).contains("42mm"));
        assert!(value_text(row.get("overall_summary").unwrap()).contains("安全开关"));
    }

    #[test]
    fn does_not_replace_upstream_summary_values() {
        let mut row = BTreeMap::from([
            ("title".to_string(), json!("毛玉取り器")),
            (
                "product_identity".to_string(),
                json!("上游已提供的商品定位"),
            ),
        ]);

        enrich_product_summary(&mut row);

        assert_eq!(
            row.get("product_identity"),
            Some(&json!("上游已提供的商品定位"))
        );
        assert!(row.contains_key("target_user"));
    }
}
