use std::{
    collections::HashMap,
    path::PathBuf,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use anyhow::Context;
use sha2::{Digest, Sha256};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CachePayload {
    headers: HashMap<String, String>,
    expires_at: f64,
}

pub struct TokenManager {
    cache_file: PathBuf,
    lock: Mutex<()>,
}

pub struct AdminAuth {
    username: String,
    password_sha256: String,
    session_ttl: Duration,
    sessions: Mutex<HashMap<String, Instant>>,
}

pub struct AdminSession {
    pub token: String,
    pub expires_in_seconds: u64,
}

impl AdminAuth {
    pub fn from_env() -> anyhow::Result<Self> {
        let username = std::env::var("SELLERSPRITE_ADMIN_USERNAME")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .context("missing SELLERSPRITE_ADMIN_USERNAME")?;
        let password_sha256 = configured_password_sha256()?;
        let ttl_seconds = std::env::var("SELLERSPRITE_ADMIN_SESSION_TTL_SECONDS")
            .ok()
            .and_then(|value| value.trim().parse::<u64>().ok())
            .filter(|value| *value > 0)
            .unwrap_or(8 * 60 * 60);

        Ok(Self {
            username,
            password_sha256,
            session_ttl: Duration::from_secs(ttl_seconds),
            sessions: Mutex::new(HashMap::new()),
        })
    }

    pub async fn login(&self, username: &str, password: &str) -> Option<AdminSession> {
        if username != self.username || sha256_hex(password) != self.password_sha256 {
            return None;
        }

        let now = Instant::now();
        let expires_at = now + self.session_ttl;
        let token = Uuid::new_v4().simple().to_string();
        let mut sessions = self.sessions.lock().await;
        sessions.retain(|_, expires| *expires > now);
        sessions.insert(token.clone(), expires_at);

        Some(AdminSession {
            token,
            expires_in_seconds: self.session_ttl.as_secs(),
        })
    }

    pub async fn authorize(&self, authorization: Option<&str>) -> bool {
        let Some(token) = authorization
            .and_then(|value| value.strip_prefix("Bearer "))
            .map(str::trim)
            .filter(|value| !value.is_empty())
        else {
            return false;
        };
        let now = Instant::now();
        let mut sessions = self.sessions.lock().await;
        sessions.retain(|_, expires| *expires > now);
        sessions.get(token).is_some_and(|expires| *expires > now)
    }
}

fn configured_password_sha256() -> anyhow::Result<String> {
    if let Some(value) = std::env::var("SELLERSPRITE_ADMIN_PASSWORD_SHA256")
        .ok()
        .filter(|value| value.trim().len() == 64)
    {
        return Ok(value.trim().to_ascii_lowercase());
    }

    let password = std::env::var("SELLERSPRITE_ADMIN_PASSWORD")
        .ok()
        .filter(|value| !value.is_empty())
        .context("missing SELLERSPRITE_ADMIN_PASSWORD_SHA256 or SELLERSPRITE_ADMIN_PASSWORD")?;
    Ok(sha256_hex(&password))
}

fn sha256_hex(value: &str) -> String {
    let digest = Sha256::digest(value.as_bytes());
    format!("{digest:x}")
}

impl TokenManager {
    pub fn new(cache_file: PathBuf) -> Self {
        Self {
            cache_file,
            lock: Mutex::new(()),
        }
    }

    pub async fn headers(&self) -> anyhow::Result<HashMap<String, String>> {
        if env_bool("KEEPA_TOKEN_REFRESH_EACH_RUN", true) {
            if let Some(headers) = self.refresh_from_command().await? {
                return Ok(headers);
            }
        }
        if let Some(headers) = self.load_cache().await? {
            return Ok(headers);
        }
        let env = self.load_from_env();
        if has_required(&env) {
            self.save_cache(&env, 5400).await?;
            return Ok(env);
        }
        if let Some(headers) = self.refresh_from_command().await? {
            return Ok(headers);
        }
        anyhow::bail!("missing KEEPA_AUTH_TOKEN/KEEPA_AUTH_FP/KEEPA_RANDOM_TOKEN or KEEPA_TOKEN_REFRESH_COMMAND")
    }

    pub async fn invalidate_cache(&self) -> anyhow::Result<()> {
        match tokio::fs::remove_file(&self.cache_file).await {
            Ok(_) => Ok(()),
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(err) => Err(err.into()),
        }
    }

    async fn load_cache(&self) -> anyhow::Result<Option<HashMap<String, String>>> {
        let raw = match tokio::fs::read_to_string(&self.cache_file).await {
            Ok(raw) => raw,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(err) => return Err(err.into()),
        };
        let payload: CachePayload = serde_json::from_str(&raw)?;
        if payload.expires_at <= now_secs() + 60.0 || !has_required(&payload.headers) {
            return Ok(None);
        }
        Ok(Some(payload.headers))
    }

    async fn save_cache(
        &self,
        headers: &HashMap<String, String>,
        ttl_seconds: u64,
    ) -> anyhow::Result<()> {
        if !has_required(headers) {
            return Ok(());
        }
        let payload = CachePayload {
            headers: headers.clone(),
            expires_at: now_secs() + ttl_seconds as f64,
        };
        tokio::fs::write(&self.cache_file, serde_json::to_vec_pretty(&payload)?).await?;
        Ok(())
    }

    fn load_from_env(&self) -> HashMap<String, String> {
        [
            ("auth-token", "KEEPA_AUTH_TOKEN"),
            ("auth-fp", "KEEPA_AUTH_FP"),
            ("random-token", "KEEPA_RANDOM_TOKEN"),
            ("cookie", "KEEPA_COOKIE"),
        ]
        .into_iter()
        .filter_map(|(header, env)| {
            std::env::var(env)
                .ok()
                .filter(|v| !v.trim().is_empty())
                .map(|v| (header.to_string(), v))
        })
        .collect()
    }

    async fn refresh_from_command(&self) -> anyhow::Result<Option<HashMap<String, String>>> {
        let command = match std::env::var("KEEPA_TOKEN_REFRESH_COMMAND") {
            Ok(value) if !value.trim().is_empty() => value,
            _ => return Ok(None),
        };
        let _guard = self.lock.lock().await;
        if !env_bool("KEEPA_TOKEN_REFRESH_EACH_RUN", true) {
            if let Some(cached) = self.load_cache().await? {
                return Ok(Some(cached));
            }
        }
        let output = tokio::process::Command::new("sh")
            .arg("-lc")
            .arg(command)
            .output()
            .await
            .context("failed to execute KEEPA_TOKEN_REFRESH_COMMAND")?;
        if !output.status.success() {
            anyhow::bail!(
                "KEEPA_TOKEN_REFRESH_COMMAND failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }
        let payload: serde_json::Value = serde_json::from_slice(&output.stdout)?;
        let mut headers = HashMap::new();
        for key in ["auth-token", "auth-fp", "random-token", "cookie"] {
            if let Some(value) = payload
                .get(key)
                .and_then(|v| v.as_str())
                .filter(|v| !v.trim().is_empty())
            {
                headers.insert(key.to_string(), value.to_string());
            }
        }
        if !has_required(&headers) {
            anyhow::bail!(
                "KEEPA_TOKEN_REFRESH_COMMAND output missing auth-token/auth-fp/random-token"
            );
        }
        let ttl = payload
            .get("ttl_seconds")
            .and_then(|v| v.as_u64())
            .unwrap_or(5400);
        self.save_cache(&headers, ttl).await?;
        Ok(Some(headers))
    }
}

fn has_required(headers: &HashMap<String, String>) -> bool {
    ["auth-token", "auth-fp", "random-token"]
        .iter()
        .all(|key| headers.get(*key).is_some_and(|v| !v.trim().is_empty()))
}

fn env_bool(name: &str, default: bool) -> bool {
    std::env::var(name)
        .ok()
        .map(|v| {
            matches!(
                v.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on" | "y"
            )
        })
        .unwrap_or(default)
}

fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
