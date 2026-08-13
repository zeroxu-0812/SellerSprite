use std::{path::{Path, PathBuf}, sync::Arc};

use axum::{
    extract::{Path as AxumPath, State},
    http::{
        header::{AUTHORIZATION, CACHE_CONTROL, EXPIRES, PRAGMA},
        HeaderMap, HeaderValue,
    },
    middleware,
    response::Response,
    routing::{get, post},
    Json, Router,
};
use tokio::sync::Semaphore;
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
    pub job_slots: Arc<Semaphore>,
    pub max_job_records: usize,
    pub max_asins: usize,
    pub max_workers: usize,
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
        .layer(middleware::map_response(require_revalidation))
        .layer(CorsLayer::permissive())
        .with_state(state)
}

async fn require_revalidation(mut response: Response) -> Response {
    response
        .headers_mut()
        .insert(
            CACHE_CONTROL,
            HeaderValue::from_static("no-store, no-cache, must-revalidate, max-age=0"),
        );
    response
        .headers_mut()
        .insert(PRAGMA, HeaderValue::from_static("no-cache"));
    response
        .headers_mut()
        .insert(EXPIRES, HeaderValue::from_static("0"));
    response
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
    if asin_count > state.max_asins {
        return Err(crate::error::AppError::BadRequest(format!(
            "too many ASINs: maximum is {}",
            state.max_asins
        )));
    }
    let marketplaces = pipeline::marketplace_codes(&request)?;
    let work_units = asin_count
        .checked_mul(marketplaces.len())
        .ok_or_else(|| crate::error::AppError::BadRequest("任务规模超出限制".to_string()))?;
    let (progress, removed_job_ids) = state
        .jobs
        .create(work_units, state.max_job_records)
        .await
        .ok_or_else(|| {
            crate::error::AppError::Busy(
                "任务队列已满，请等待当前任务完成后重试".to_string(),
            )
        })?;
    cleanup_job_outputs(&state.root, &removed_job_ids).await;

    if let Err(err) = state.usage.record_many(&marketplaces, asin_count).await {
        state.jobs.fail(&progress.job_id, err.to_string()).await;
        return Err(err);
    }

    let job_id = progress.job_id.clone();
    let task_state = state.clone();
    tokio::spawn(async move {
        let _permit = match task_state.job_slots.clone().acquire_owned().await {
            Ok(permit) => permit,
            Err(err) => {
                task_state
                    .jobs
                    .fail(&job_id, format!("任务调度器不可用: {err}"))
                    .await;
                return;
            }
        };
        match pipeline::process_asins_with_progress(&task_state, request, job_id.clone()).await {
            Ok(response) => task_state.jobs.done(&job_id, response).await,
            Err(err) => task_state.jobs.fail(&job_id, err.to_string()).await,
        }
    });
    Ok(Json(progress))
}

async fn cleanup_job_outputs(root: &Path, job_ids: &[String]) {
    for job_id in job_ids {
        let path = root.join("output/jobs").join(job_id);
        match tokio::fs::remove_dir_all(&path).await {
            Ok(()) => tracing::debug!(job_id, "removed expired job output"),
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
            Err(err) => tracing::warn!(job_id, error = %err, "failed to remove expired job output"),
        }
    }
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
    AxumPath(job_id): AxumPath<String>,
) -> Result<Json<RunProgress>> {
    let progress = state
        .jobs
        .get(&job_id)
        .await
        .ok_or_else(|| crate::error::AppError::BadRequest("job not found".to_string()))?;
    Ok(Json(progress))
}
