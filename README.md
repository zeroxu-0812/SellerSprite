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
| `POST` | `/api/jobs` | 创建分析任务，返回 `job_id` 和初始进度 |
| `GET` | `/api/jobs/:job_id` | 查询任务进度，完成时返回结果 |

任务请求示例：

```json
{
  "asins": ["B0F1QHNFJP", "B09PVMTM9W"],
  "mode": "full",
  "workers": 2
}
```

`mode`：

- `fast`：只请求卖家精灵竞手接口。
- `full`：在卖家精灵数据基础上补 Amazon 详情页折扣和 About 信息。

`workers` 表示 Amazon 详情页补抓并发数。默认配置为 `2`，生产环境建议保持 `1-2`。

## 风控与限速

当前措施：

- 卖家精灵竞手接口按批次串行请求。
- 多批次之间使用 `config.json` 的 `quick_view.delay_seconds_min/max` 延迟。
- Amazon 详情页补抓受 `workers` 控制，并在请求前加入延迟。
- 卖家精灵请求有超时、重试、backoff。
- auth 过期会自动刷新 token 并重试。
- 前端显示真实任务进度，不使用假进度条。

生产建议：

- 批量 ASIN 较多时，将 `workers` 调为 `1`。
- 不要把 `quick_view.delay_seconds_min/max` 调得过低。
- 如果 Amazon 详情页频繁失败，优先使用 `fast` 模式或降低并发。

## 输出

每次运行会写入：

```text
output/products.json
output/market_overview.json
output/failures.json
```

前端的“导出 HTML”会在浏览器侧生成交互式报告，不依赖服务器文件。

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
