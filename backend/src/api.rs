use std::{path::PathBuf, sync::Arc};

use axum::{
    extract::{Path, State},
    http::{header::AUTHORIZATION, HeaderMap},
    routing::{get, post},
    Json, Router,
};
use tower_http::{cors::CorsLayer, services::ServeDir};

use crate::{
    auth::TokenManager,
    config::AppConfig,
    error::Result,
    models::{AdminLoginRequest, AdminLoginResponse, RunRequest},
    pipeline,
    progress::{JobStore, RunProgress},
    usage::{UsageSnapshot, UsageStore},
};

pub struct AppState {
    pub root: PathBuf,
    pub config: AppConfig,
    pub token_manager: TokenManager,
    pub admin_auth: crate::auth::AdminAuth,
    pub jobs: JobStore,
    pub usage: UsageStore,
    pub client: reqwest::Client,
}

pub fn app(state: Arc<AppState>) -> Router {
    let frontend_dist = state.root.join("frontend/dist");
    Router::new()
        .route("/api/health", get(health))
        .route("/api/auth/login", post(admin_login))
        .route("/api/jobs", post(create_job))
        .route("/api/jobs/:job_id", get(get_job))
        .route("/api/usage", get(get_usage))
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
    let asin_count = pipeline::normalized_asin_count(&request.asins);
    if asin_count == 0 {
        return Err(crate::error::AppError::BadRequest(
            "no valid ASINs".to_string(),
        ));
    }
    let marketplace = pipeline::marketplace_code(request.marketplace.as_deref())?;
    state.usage.record(&marketplace, asin_count).await?;
    let progress = state.jobs.create(asin_count).await;
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

async fn admin_login(
    State(state): State<Arc<AppState>>,
    Json(request): Json<AdminLoginRequest>,
) -> Result<Json<AdminLoginResponse>> {
    let Some(session) = state.admin_auth.login(&request.username, &request.password).await else {
        return Err(crate::error::AppError::Unauthorized(
            "管理员账号或密码错误".to_string(),
        ));
    };
    Ok(Json(AdminLoginResponse {
        token: session.token,
        expires_in_seconds: session.expires_in_seconds,
    }))
}

async fn get_usage(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
) -> Result<Json<UsageSnapshot>> {
    let authorization = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok());
    if !state.admin_auth.authorize(authorization).await {
        return Err(crate::error::AppError::Unauthorized(
            "需要管理员登录后查看工作台数据".to_string(),
        ));
    }
    Ok(Json(state.usage.snapshot().await))
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
