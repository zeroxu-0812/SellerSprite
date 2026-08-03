use regex::Regex;

use crate::{config::AppConfig, models::ProductDetail};

const MAX_PLAUSIBLE_DISCOUNT_PCT: f64 = 90.0;

pub async fn fetch_product_detail(
    client: &reqwest::Client,
    asin: &str,
    config: &AppConfig,
) -> anyhow::Result<ProductDetail> {
    let url = format!(
        "{}/dp/{}",
        config.amazon.base_url.trim_end_matches('/'),
        asin
    );
    let html = client
        .get(url)
        .header("user-agent", &config.amazon.user_agent)
        .send()
        .await?
        .text()
        .await?;
    Ok(parse_product_detail(&html))
}

pub fn parse_product_detail(html: &str) -> ProductDetail {
    let mut detail = ProductDetail::default();
    if has_deal(html) {
        let current = Regex::new(r#"a-offscreen">([^<]{1,25})<"#)
            .ok()
            .and_then(|re| re.captures(html))
            .and_then(|cap| parse_price(&cap[1]));
        let list = Regex::new(r#"a-text-strike[^0-9]{0,25}([\d,]+(?:\.\d+)?)"#)
            .ok()
            .and_then(|re| re.captures(html))
            .and_then(|cap| parse_price(&cap[1]));
        detail.price_current = current;
        detail.list_price = list;
        if let (Some(list), Some(current)) = (list, current) {
            if list > current {
                let discount = ((list - current) / list * 1000.0).round() / 10.0;
                if discount <= MAX_PLAUSIBLE_DISCOUNT_PCT {
                    detail.discount_off_list_pct = Some(discount);
                }
            }
        }
    }
    detail.about = parse_about(html);
    detail
}

fn has_deal(html: &str) -> bool {
    Regex::new(
        r#"class="[^"]*dealBadge|dealsCountdownTimer|deals_countdown_timer|deal_expiry_timer"#,
    )
    .is_ok_and(|re| re.is_match(html))
}

fn parse_price(text: &str) -> Option<f64> {
    let raw = Regex::new(r#"-?[\d][\d\s,.]*"#)
        .ok()?
        .find(text)?
        .as_str()
        .replace(' ', "");
    let comma = raw.rfind(',');
    let dot = raw.rfind('.');
    let normalized = match (comma, dot) {
        (Some(c), Some(d)) if c > d => raw.replace('.', "").replace(',', "."),
        (Some(_), Some(_)) => raw.replace(',', ""),
        (Some(c), None) if raw.len().saturating_sub(c + 1) == 2 => raw.replace(',', "."),
        (Some(_), None) => raw.replace(',', ""),
        (None, Some(d)) if raw.len().saturating_sub(d + 1) == 2 => raw,
        (None, Some(_)) => raw.replace('.', ""),
        (None, None) => raw,
    };
    normalized.parse().ok()
}

fn parse_about(html: &str) -> Vec<String> {
    let feature_block = Regex::new(r#"(?s)<div[^>]+id="feature-bullets"[^>]*>(.*?)</div>"#)
        .ok()
        .and_then(|re| re.captures(html))
        .map(|cap| cap[1].to_string())
        .unwrap_or_default();
    let li_re = match Regex::new(r#"(?s)<li[^>]*>\s*<span[^>]*>(.*?)</span>\s*</li>"#) {
        Ok(re) => re,
        Err(_) => return Vec::new(),
    };
    li_re
        .captures_iter(&feature_block)
        .filter_map(|cap| clean_text(&cap[1]))
        .filter(|line| {
            let lower = line.to_ascii_lowercase();
            !matches!(lower.as_str(), "see more" | "see less" | "see all")
        })
        .take(20)
        .collect()
}

fn clean_text(input: &str) -> Option<String> {
    let tag_re = Regex::new(r#"(?s)<[^>]+>"#).ok()?;
    let text = tag_re
        .replace_all(input, " ")
        .replace("&amp;", "&")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&nbsp;", " ");
    let compact = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if compact.len() <= 2 {
        None
    } else {
        Some(compact)
    }
}
