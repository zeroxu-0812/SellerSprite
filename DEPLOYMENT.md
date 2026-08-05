# Docker 部署指南

## 服务器要求

- Docker Engine
- Docker Compose v2
- 服务器能访问：
  - `https://e.sellersprite.com`
  - `https://www.sellersprite.com`
  - `https://www.amazon.com`

## 准备环境变量

```bash
cp .env.example .env
```

填写：

```bash
KEEPA_LOGIN_USERNAME=卖家精灵账号
KEEPA_LOGIN_PASSWORD=卖家精灵密码
```

不要把 `.env` 提交到 Git。

## 构建与启动

```bash
docker compose build
docker compose up -d
```

访问：

```text
http://服务器IP:8787
```

查看日志：

```bash
docker compose logs -f sellersprite
```

停止：

```bash
docker compose down
```

## 健康检查

```bash
curl http://127.0.0.1:8787/api/health
```

期望返回：

```json
{"ok":true}
```

## 生产参数建议

`config.json` 中：

```json
{
  "concurrency": {
    "workers": 2
  },
  "quick_view": {
    "delay_seconds_min": 5,
    "delay_seconds_max": 8
  }
}
```

建议：

- 普通批量：`workers=2`
- 大批量或 Amazon 详情页失败较多：`workers=1`
- 不建议把 `delay_seconds_min/max` 调得过低

`.env` 中还可以配置单实例任务并发保护：

```env
SELLERSPRITE_MAX_ACTIVE_JOBS=2
SELLERSPRITE_MAX_JOB_RECORDS=500
SELLERSPRITE_MAX_ASINS=100
SELLERSPRITE_MAX_DETAIL_WORKERS=2
```

这表示最多同时执行 2 个任务，其他任务排队；每个任务最多抓取 100 个 ASIN，详情页并发最多为 2。当前部署保持单个 `sellersprite` 容器副本，不要启动多个后端副本，否则进程内的并发限制不会跨实例共享。

## 持久化文件

`docker-compose.yml` 默认挂载：

```text
./output:/app/output
```

这里按任务保存：

- `jobs/{job_id}/products.json`
- `jobs/{job_id}/market_overview.json`
- `jobs/{job_id}/failures.json`

任务写入使用临时文件完成后原子替换，达到任务记录上限时只清理已完成或失败任务的目录。

token 缓存默认在容器内生成。若需要跨容器重建保留登录缓存，可额外挂载：

```yaml
volumes:
  - ./output:/app/output
  - ./.token_cache.json:/app/.token_cache.json
  - ./.client_tokens.json:/app/.client_tokens.json
```

通常不需要这么做，程序会自动重新登录刷新。
