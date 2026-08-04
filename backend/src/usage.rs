use std::{collections::BTreeMap, path::PathBuf};

use chrono::Utc;
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;

use crate::error::{AppError, Result};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MarketplaceUsage {
    pub count: u64,
    pub last_searched_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchUsageEvent {
    pub marketplace: String,
    pub asin_count: usize,
    pub searched_at: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct PersistedUsage {
    marketplaces: BTreeMap<String, MarketplaceUsage>,
    recent: Vec<SearchUsageEvent>,
}

#[derive(Debug, Clone, Serialize)]
pub struct UsageSnapshot {
    pub total: u64,
    pub marketplaces: BTreeMap<String, MarketplaceUsage>,
    pub recent: Vec<SearchUsageEvent>,
}

pub struct UsageStore {
    path: PathBuf,
    state: Mutex<PersistedUsage>,
}

impl UsageStore {
    pub async fn load(path: PathBuf) -> Result<Self> {
        let state = match tokio::fs::read(&path).await {
            Ok(raw) => serde_json::from_slice(&raw).map_err(anyhow::Error::from)?,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => PersistedUsage::default(),
            Err(err) => return Err(AppError::Anyhow(err.into())),
        };
        Ok(Self {
            path,
            state: Mutex::new(state),
        })
    }

    pub async fn snapshot(&self) -> UsageSnapshot {
        let state = self.state.lock().await;
        snapshot(&state)
    }

    pub async fn record(&self, marketplace: &str, asin_count: usize) -> Result<UsageSnapshot> {
        let mut state = self.state.lock().await;
        apply_record(&mut state, marketplace, asin_count, Utc::now().to_rfc3339());
        self.persist(&state).await?;
        Ok(snapshot(&state))
    }

    async fn persist(&self, state: &PersistedUsage) -> Result<()> {
        let parent = self
            .path
            .parent()
            .ok_or_else(|| AppError::Anyhow(anyhow::anyhow!("usage path has no parent")))?;
        tokio::fs::create_dir_all(parent)
            .await
            .map_err(|err| AppError::Anyhow(err.into()))?;
        let temporary = self.path.with_extension("json.tmp");
        tokio::fs::write(
            &temporary,
            serde_json::to_vec_pretty(state).map_err(anyhow::Error::from)?,
        )
        .await
        .map_err(|err| AppError::Anyhow(err.into()))?;
        tokio::fs::rename(&temporary, &self.path)
            .await
            .map_err(|err| AppError::Anyhow(err.into()))?;
        Ok(())
    }
}

fn apply_record(
    state: &mut PersistedUsage,
    marketplace: &str,
    asin_count: usize,
    searched_at: String,
) {
    let counter = state
        .marketplaces
        .entry(marketplace.to_string())
        .or_default();
    counter.count += 1;
    counter.last_searched_at = Some(searched_at.clone());
    state.recent.insert(
        0,
        SearchUsageEvent {
            marketplace: marketplace.to_string(),
            asin_count,
            searched_at,
        },
    );
    state.recent.truncate(50);
}

fn snapshot(state: &PersistedUsage) -> UsageSnapshot {
    UsageSnapshot {
        total: state.marketplaces.values().map(|item| item.count).sum(),
        marketplaces: state.marketplaces.clone(),
        recent: state.recent.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn records_one_search_per_job_and_keeps_recent_first() {
        let mut state = PersistedUsage::default();
        apply_record(&mut state, "jp", 3, "2026-08-03T10:00:00Z".to_string());
        apply_record(&mut state, "de", 2, "2026-08-03T10:01:00Z".to_string());
        apply_record(&mut state, "jp", 1, "2026-08-03T10:02:00Z".to_string());

        let result = snapshot(&state);
        assert_eq!(result.total, 3);
        assert_eq!(result.marketplaces["jp"].count, 2);
        assert_eq!(result.marketplaces["de"].count, 1);
        assert_eq!(result.recent[0].marketplace, "jp");
        assert_eq!(result.recent[0].asin_count, 1);
    }
}
