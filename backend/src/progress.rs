use std::{collections::HashMap, sync::Arc};

use chrono::Utc;
use serde::Serialize;
use tokio::sync::Mutex;

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
    pub async fn create(&self, total: usize) -> RunProgress {
        let job_id = format!("run-{}", Utc::now().timestamp_millis());
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
        self.inner.lock().await.insert(job_id, progress.clone());
        progress
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
