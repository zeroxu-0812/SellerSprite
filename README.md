# SellerSprite 核心竞手分析

面向 ASIN 列表的竞手分析工具。当前主线已收束为：

- `backend/`：Rust + Axum，负责鉴权、卖家精灵竞手接口、Amazon 详情页补充、清洗、进度任务和静态前端托管。
- `frontend/`：Vue 3 + TypeScript + Vite，负责 ASIN 输入、进度条、核心竞手矩阵、指标卡和交互式 HTML 导出。
- `refresh_tokens.py` + `sellersprite_signing.py`：Rust 后端调用的卖家精灵登录 token 刷新脚本。

旧 Python CLI、Streamlit、本地 `products.html` 模板和 pytest 旧测试已移除。

## 环境变量

复制 `.env.example` 为 `.env`，最小只需要：

```bash
KEEPA_LOGIN_USERNAME=卖家精灵账号
KEEPA_LOGIN_PASSWORD=卖家精灵密码
```

默认 `KEEPA_LOGIN_PASSWORD_MD5=true`，表示 `.env` 中填写明文密码，刷新脚本会自动 MD5。若直接填写 MD5，改为：

```bash
KEEPA_LOGIN_PASSWORD_MD5=false
```

通常不需要手填 `auth-token`。后端会按需执行：

```bash
python3 refresh_tokens.py
```

生成并缓存运行期鉴权信息。缓存文件 `.token_cache.json`、`.client_tokens.json` 不应提交。

工作台管理员权限需要额外配置：

```bash
SELLERSPRITE_ADMIN_USERNAME=admin
SELLERSPRITE_ADMIN_PASSWORD_SHA256=<管理员密码的 SHA-256>
SELLERSPRITE_ADMIN_SESSION_TTL_SECONDS=28800
```

也可以使用 `SELLERSPRITE_ADMIN_PASSWORD` 填写明文密码；同时配置时优先使用 SHA-256。管理员登录令牌只保存在当前浏览器会话中。

## 本地开发

后端：

```bash
cargo run --manifest-path backend/Cargo.toml
```

默认监听 `http://127.0.0.1:8787`。

前端：

```bash
cd frontend
npm install
npm run dev
```

默认访问 `http://127.0.0.1:5173`，Vite 会把 `/api` 代理到 Rust 后端。

检查：

```bash
cargo check --manifest-path backend/Cargo.toml
cd frontend && npm run build
```

## 生产部署：Docker

构建镜像：

```bash
docker compose build
```

启动：

```bash
docker compose up -d
```

访问：

```text
http://服务器IP:8787
```

健康检查：

```bash
curl http://127.0.0.1:8787/api/health
```

容器说明：

- 镜像内会构建前端静态文件，并由 Rust 后端托管。
- 运行时需要 Python 3，用于执行 `refresh_tokens.py`。
- `docker-compose.yml` 默认挂载 `./output:/app/output`，保留最近一次输出 JSON。
- `.env` 通过 `env_file` 注入容器，不会被 Docker build 打包进镜像。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/auth/login` | 管理员登录，返回工作台会话令牌 |
| `POST` | `/api/jobs` | 创建分析任务，返回 `job_id` 和初始进度 |
| `GET` | `/api/jobs/:job_id` | 查询任务进度，完成时返回结果 |
| `GET` | `/api/usage` | 查询各国家站点累计搜索次数和最近任务，需要 `Authorization: Bearer <token>` |
| `GET` | `/api/traffic/:marketplace/:asin` | 查询指定 ASIN 的 SIF 最近30天自然、广告、推荐流量占比；需配置 SIF 账号 |

管理员登录请求：

```json
{
  "username": "admin",
  "password": "管理员密码"
}
```

任务请求示例：

```json
{
  "asins": ["B0F1QHNFJP", "B09PVMTM9W"],
  "marketplaces": ["com", "de", "jp"],
  "includeSummary": true,
  "includeDetails": true,
  "workers": 2
}
```

`marketplaces` 支持 `com`、`it`、`uk`、`fr`、`es`、`de`、`jp`，至少选择一个站点。同一 ASIN 在多个站点返回时会保留为多条结果，并在 `marketplace_code`、`marketplace_station` 和前端“来源站点”列中标明来源。旧调用仍可使用单值 `marketplace` 字段。

抓取选项：

- 两项均为 `false`：快速抓取，只请求卖家精灵竞手接口，也是默认模式。
- `includeSummary: true`：在快速数据基础上生成商品信息摘要四项字段。
- `includeDetails: true`：补抓 Amazon 详情页折扣和五点描述。
- 两项可以独立启用，也可以同时启用；同时启用时为完整抓取。

后端仍兼容旧请求中的 `mode: "fast"` 与 `mode: "full"`，新调用应使用上述两个选项。

`workers` 表示 Amazon 详情页补抓并发数。默认配置为 `2`，生产环境建议保持 `1-2`。

## SIF 流量分析

核心竞手矩阵会在“销售额”后为每个 ASIN 内联加载最近30天流量占比，不再跳转独立页面。表格通过小型环形饼图展示自然流量和广告流量，推荐流量保留在饼图剩余扇区与悬浮提示中；数据使用 SIF 的原生最近30天口径（`latelyDay=30`），推荐流量按 `1 - 自然流量占比 - 广告流量占比` 计算。导出 HTML 时，当前已加载的流量结果和饼图会直接固化到文件中，离线打开不再请求 SIF。

当自然流量和广告流量都为 0、计算结果表现为推荐流量 100% 时，该结果视为暂无有效数据，页面显示“暂无流量数据”。

在 `.env` 中另行配置 SIF 账号池：

```bash
SIF_USERNAME_1=<SIF账号1>
SIF_PASSWORD_1=<SIF密码1>
SIF_USERNAME_2=<SIF账号2>
SIF_PASSWORD_2=<SIF密码2>
```

最多支持 10 组编号账号，也兼容原来的 `SIF_USERNAME`/`SIF_PASSWORD`，以及 `SIF_PHONE` 或 `SIF_ACCOUNT`。系统只维持一个活动 token；当前账号认证失效或不可用时才尝试下一组。SIF 登录 token 会独立缓存在 `.sif_token_cache.json`，不会与卖家精灵 token 混用。

最近30天请求之间默认随机间隔 `900-1600ms`，网络或 5xx 异常最多退避重试 2 次。检测到 403、429 或明确风控提示时，本次任务立即停止并进入默认 300 秒全局冷却，不会连续轮换账号继续请求。可通过 `SIF_REQUEST_DELAY_MS_MIN/MAX`、`SIF_RETRY_BACKOFF_MS` 和 `SIF_RISK_COOLDOWN_SECONDS` 调整，但不建议降低默认保护值。

前端按行串行加载流量数据，后端默认将同一“站点 + ASIN”的结果缓存 1800 秒，可通过 `SIF_TRAFFIC_CACHE_SECONDS` 调整。排序、筛选或重复查询缓存期内不会再次访问 SIF。

## 风控与限速

当前措施：

- 卖家精灵竞手接口按批次串行请求。
- 多批次之间使用 `config.json` 的 `quick_view.delay_seconds_min/max` 延迟。
- Amazon 详情页补抓受 `workers` 控制，并在请求前加入延迟。
- 卖家精灵请求有超时、重试、backoff。
- auth 过期会自动刷新 token 并重试。
- 后端使用全局任务信号量控制同时运行的抓取任务，超出的任务保持排队。
- 同一任务选择多个站点时按站点串行抓取，避免一次查询把上游请求并发放大。
- 每个任务强制使用独立的输出目录，避免并发任务互相覆盖结果。
- 服务端会限制单任务 ASIN 数量和 Amazon 详情页并发，不能通过直接调用 API 绕过。
- 前端显示真实任务进度，不使用假进度条。

生产建议：

- 批量 ASIN 较多时，将 `workers` 调为 `1`。
- 不要把 `quick_view.delay_seconds_min/max` 调得过低。
- 如果 Amazon 详情页频繁失败，优先使用 `fast` 模式或降低并发。

## 输出

每次运行会写入独立目录：

```text
output/jobs/{job_id}/products.json
output/jobs/{job_id}/market_overview.json
output/jobs/{job_id}/marketplace_overviews.json
output/jobs/{job_id}/failures.json
output/search_usage.json
```

`search_usage.json` 按国家站点累计任务创建次数，并保留最近搜索记录。该文件由后端管理，抓取结果刷新时不会被清理。达到任务记录上限时，后端只清理已完成或失败的旧任务及其对应输出，不会删除运行中的任务。

小范围单实例部署的并发保护参数通过 `.env` 配置：

```env
SELLERSPRITE_MAX_ACTIVE_JOBS=2
SELLERSPRITE_MAX_JOB_RECORDS=500
SELLERSPRITE_MAX_ASINS=100
SELLERSPRITE_MAX_DETAIL_WORKERS=2
```

当前方案要求只运行一个后端进程或一个 Docker 容器副本；如果以后扩展为多实例，需要迁移到共享任务队列和共享限流器。

前端的“导出 HTML”会在浏览器侧生成交互式报告，不依赖服务器文件。导出时可选择中文或英文界面，默认使用中文；商品标题、类目和摘要正文保留抓取到的原始语言。

## 项目结构

```text
.
├── backend/                  # Rust Axum 后端
│   └── src/
│       ├── api.rs            # API 路由、任务接口、静态文件托管
│       ├── auth.rs           # token 缓存与刷新命令调用
│       ├── pipeline.rs       # ASIN 分析编排、进度推进、输出写入
│       ├── progress.rs       # 内存任务进度状态
│       ├── sellersprite.rs   # 卖家精灵 competitor-lookup
│       ├── amazon.rs         # Amazon 详情页解析
│       └── transform.rs      # 字段扁平化和清洗
├── frontend/                 # Vue 3 + TypeScript 前端
│   └── src/
│       ├── components/       # 控制栏、指标卡、矩阵表格
│       └── utils/            # 字段渲染、竞手分析、HTML 导出
├── config.json               # 站点、并发、批大小、延迟、重试配置
├── refresh_tokens.py          # 卖家精灵登录刷新 auth-token
├── sellersprite_signing.py    # tk 签名算法
├── Dockerfile
└── docker-compose.yml
```
