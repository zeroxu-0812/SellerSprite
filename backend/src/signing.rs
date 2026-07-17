pub fn extension_version_token(version: &str) -> String {
    let mut out = version.replacen('.', "00", 1);
    out = out.replacen('.', "0", 1);
    format!("{out}.1364508470")
}

pub fn sellersprite_token(parts: &[&str], ext_version: &str) -> String {
    let text = parts
        .iter()
        .filter(|p| !p.is_empty())
        .copied()
        .collect::<String>();
    if text.is_empty() {
        return String::new();
    }
    token_calculate(&text, ext_version)
}

fn token_calculate(text: &str, tkk: &str) -> String {
    fn mix(mut value: i64, seed: &str) -> i64 {
        let bytes = seed.as_bytes();
        let mut index = 0;
        while index < bytes.len() - 2 {
            let shift_char = bytes[index + 2] as char;
            let shift = if shift_char >= 'a' {
                shift_char as i64 - 87
            } else {
                shift_char.to_digit(10).unwrap_or(0) as i64
            };
            let shifted = if bytes[index + 1] as char == '+' {
                ((value as u32) >> shift) as i64
            } else {
                ((value as u32) << shift) as i64
            };
            value = if bytes[index] as char == '+' {
                ((value + shifted) as u32) as i64
            } else {
                ((value as u32) ^ (shifted as u32)) as i64
            };
            index += 3;
        }
        value
    }

    let (first, second) = tkk.split_once('.').unwrap_or(("0", "0"));
    let base = first.parse::<i64>().unwrap_or(0);
    let mut value = base;

    for byte in text.as_bytes() {
        value += *byte as i64;
        value = mix(value, "+-a^+6");
    }
    value = mix(value, "+-3^+b+-f");
    value ^= second.parse::<i64>().unwrap_or(0);
    if value < 0 {
        value = 0x80000000 + (value & 0x7fffffff);
    }
    let token = value % 1_000_000;
    format!("{token}.{}", token ^ base)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_token_matches_python_shape() {
        assert_eq!(extension_version_token("5.0.4"), "500004.1364508470");
    }

    #[test]
    fn asin_token_matches_python_value() {
        let ext = extension_version_token("5.0.4");
        assert_eq!(sellersprite_token(&["B0DPH6BP7C"], &ext), "355796.183536");
    }
}
