mod amazon;
mod api;
mod auth;
mod config;
mod error;
mod models;
mod overview;
mod pipeline;
mod progress;
mod sellersprite;
mod signing;
mod summary;
mod transform;
mod usage;

use std::{net::SocketAddr, path::PathBuf, sync::Arc};

use tokio::sync::Semaphore;

use api::{app, AppState};
use auth::{AdminAuth, TokenManager};
use config::AppConfig;
use progress::JobStore;
use usage::UsageStore;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("backend has project parent")
        .to_path_buf();
    load_env(root.join(".env")).await?;
    default_refresh_command();
    let config = AppConfig::load(root.join("config.json")).await?;
    let usage = UsageStore::load(root.join("output/search_usage.json")).await?;
    let max_active_jobs = env_usize("SELLERSPRITE_MAX_ACTIVE_JOBS", 2).clamp(1, 8);
    let max_job_records = env_usize("SELLERSPRITE_MAX_JOB_RECORDS", 500).clamp(10, 5_000);
    let max_asins = env_usize("SELLERSPRITE_MAX_ASINS", 100).clamp(1, 1_000);
    let max_workers = env_usize("SELLERSPRITE_MAX_DETAIL_WORKERS", 2).clamp(1, 8);
    tracing::info!(
        max_active_jobs,
        max_job_records,
        max_asins,
        max_workers,
        "concurrency limits configured"
    );
    let state = Arc::new(AppState {
        root: root.clone(),
        config,
        token_manager: TokenManager::new(root.join(".token_cache.json")),
        admin_auth: AdminAuth::from_env()?,
        jobs: JobStore::default(),
        usage,
        client: reqwest::Client::builder()
            .user_agent("SellerSprite-Rust/0.1")
            .build()?,
        job_slots: Arc::new(Semaphore::new(max_active_jobs)),
        max_job_records,
        max_asins,
        max_workers,
    });

    let addr: SocketAddr = std::env::var("SELLERSPRITE_BIND")
        .unwrap_or_else(|_| "127.0.0.1:8787".to_string())
        .parse()?;
    let listener = tokio::net::TcpListener::bind(addr).await?;
    tracing::info!("backend listening on http://{addr}");
    axum::serve(listener, app(state)).await?;
    Ok(())
}

fn env_usize(name: &str, default: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|value| value.trim().parse::<usize>().ok())
        .unwrap_or(default)
}

async fn load_env(path: PathBuf) -> anyhow::Result<()> {
    let raw = match tokio::fs::read_to_string(path).await {
        Ok(raw) => raw,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(err) => return Err(err.into()),
    };
    for line in raw.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') || !line.contains('=') {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let value = value.trim().trim_matches('"').trim_matches('\'');
        if std::env::var_os(key.trim()).is_none() {
            std::env::set_var(key.trim(), value);
        }
    }
    Ok(())
}

fn default_refresh_command() {
    if std::env::var("KEEPA_TOKEN_REFRESH_COMMAND")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .is_some()
    {
        return;
    }
    let has_login = std::env::var("KEEPA_LOGIN_USERNAME")
        .ok()
        .is_some_and(|v| !v.trim().is_empty())
        && std::env::var("KEEPA_LOGIN_PASSWORD")
            .ok()
            .is_some_and(|v| !v.trim().is_empty());
    if has_login {
        std::env::set_var("KEEPA_TOKEN_REFRESH_COMMAND", "python3 refresh_tokens.py");
    }
}
