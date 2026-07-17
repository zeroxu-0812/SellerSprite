use std::{path::PathBuf, sync::Arc};

use axum::{
    extract::{Path, State},
    routing::{get, post},
    Json, Router,
};
use tower_http::{cors::CorsLayer, services::ServeDir};

use crate::{
    auth::TokenManager,
    config::AppConfig,
    error::Result,
    models::RunRequest,
    pipeline,
    progress::{JobStore, RunProgress},
};

pub struct AppState {
    pub root: PathBuf,
    pub config: AppConfig,
    pub token_manager: TokenManager,
    pub jobs: JobStore,
    pub client: reqwest::Client,
}

pub fn app(state: Arc<AppState>) -> Router {
    let frontend_dist = state.root.join("frontend/dist");
    Router::new()
        .route("/api/health", get(health))
        .route("/api/jobs", post(create_job))
        .route("/api/jobs/:job_id", get(get_job))
        .nest_service("/", ServeDir::new(frontend_dist))
        .layer(CorsLayer::permissive())
        .with_state(state)
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "ok": true }))
}

async fn create_job(
    State(state): State<Arc<AppState>>,
    Json(request): Json<RunRequest>,
) -> Result<Json<RunProgress>> {
    let progress = state.jobs.create(request.asins.len()).await;
    let job_id = progress.job_id.clone();
    let task_state = state.clone();
    tokio::spawn(async move {
        match pipeline::process_asins_with_progress(&task_state, request, job_id.clone()).await {
            Ok(response) => task_state.jobs.done(&job_id, response).await,
            Err(err) => task_state.jobs.fail(&job_id, err.to_string()).await,
        }
    });
    Ok(Json(progress))
}

async fn get_job(
    State(state): State<Arc<AppState>>,
    Path(job_id): Path<String>,
) -> Result<Json<RunProgress>> {
    let progress = state
        .jobs
        .get(&job_id)
        .await
        .ok_or_else(|| crate::error::AppError::BadRequest("job not found".to_string()))?;
    Ok(Json(progress))
}
