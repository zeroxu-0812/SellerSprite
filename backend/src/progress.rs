use std::{collections::HashMap, sync::Arc};

use serde::Serialize;
use tokio::sync::Mutex;
use uuid::Uuid;

use crate::models::RunResponse;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum JobStatus {
    Queued,
    Running,
    Done,
    Error,
}

#[derive(Debug, Clone, Serialize)]
pub struct RunProgress {
    pub job_id: String,
    pub status: JobStatus,
    pub total: usize,
    pub completed: usize,
    pub current_asin: Option<String>,
    pub stage: String,
    pub result: Option<RunResponse>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct JobStore {
    inner: Arc<Mutex<HashMap<String, RunProgress>>>,
}

impl JobStore {
    pub async fn create(
        &self,
        total: usize,
        max_records: usize,
    ) -> Option<(RunProgress, Vec<String>)> {
        let mut jobs = self.inner.lock().await;
        let mut removed_ids = Vec::new();
        let max_records = max_records.max(1);

        while jobs.len() >= max_records {
            let removable = jobs.iter().find_map(|(job_id, progress)| {
                if matches!(&progress.status, JobStatus::Done | JobStatus::Error) {
                    Some(job_id.clone())
                } else {
                    None
                }
            });
            let Some(job_id) = removable else {
                return None;
            };
            jobs.remove(&job_id);
            removed_ids.push(job_id);
        }

        let job_id = format!("run-{}", Uuid::new_v4().simple());
        let progress = RunProgress {
            job_id: job_id.clone(),
            status: JobStatus::Queued,
            total,
            completed: 0,
            current_asin: None,
            stage: "排队".to_string(),
            result: None,
            error: None,
        };
        jobs.insert(job_id, progress.clone());
        Some((progress, removed_ids))
    }

    pub async fn get(&self, job_id: &str) -> Option<RunProgress> {
        self.inner.lock().await.get(job_id).cloned()
    }

    pub async fn set_total(&self, job_id: &str, total: usize) {
        self.update(job_id, |progress| {
            progress.total = total;
        })
        .await;
    }

    pub async fn running(&self, job_id: &str, stage: impl Into<String>) {
        self.update(job_id, |progress| {
            progress.status = JobStatus::Running;
            progress.stage = stage.into();
        })
        .await;
    }

    pub async fn advance(&self, job_id: &str, completed: usize, current_asin: Option<String>, stage: impl Into<String>) {
        self.update(job_id, |progress| {
            progress.status = JobStatus::Running;
            progress.completed = completed.min(progress.total);
            progress.current_asin = current_asin;
            progress.stage = stage.into();
        })
        .await;
    }

    pub async fn done(&self, job_id: &str, result: RunResponse) {
        self.update(job_id, |progress| {
            progress.status = JobStatus::Done;
            progress.completed = progress.total;
            progress.current_asin = None;
            progress.stage = "完成".to_string();
            progress.result = Some(result);
        })
        .await;
    }

    pub async fn fail(&self, job_id: &str, error: String) {
        self.update(job_id, |progress| {
            progress.status = JobStatus::Error;
            progress.stage = "失败".to_string();
            progress.error = Some(error);
        })
        .await;
    }

    async fn update(&self, job_id: &str, update: impl FnOnce(&mut RunProgress)) {
        if let Some(progress) = self.inner.lock().await.get_mut(job_id) {
            update(progress);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn creates_unique_ids() {
        let store = JobStore::default();
        let first = store.create(1, 10).await.unwrap().0;
        let second = store.create(1, 10).await.unwrap().0;

        assert_ne!(first.job_id, second.job_id);
    }

    #[tokio::test]
    async fn prunes_terminal_jobs_before_rejecting_new_work() {
        let store = JobStore::default();
        let first = store.create(1, 2).await.unwrap().0;
        let second = store.create(1, 2).await.unwrap().0;
        store.fail(&first.job_id, "test failure".to_string()).await;

        let (third, removed) = store.create(1, 2).await.unwrap();

        assert_eq!(removed, vec![first.job_id]);
        assert_ne!(third.job_id, second.job_id);
    }

    #[tokio::test]
    async fn rejects_when_all_job_slots_are_active_or_queued() {
        let store = JobStore::default();
        assert!(store.create(1, 1).await.is_some());
        assert!(store.create(1, 1).await.is_none());
    }
}
