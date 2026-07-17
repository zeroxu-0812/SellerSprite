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

## 持久化文件

`docker-compose.yml` 默认挂载：

```text
./output:/app/output
```

这里保存最近一次运行的：

- `products.json`
- `market_overview.json`
- `failures.json`

token 缓存默认在容器内生成。若需要跨容器重建保留登录缓存，可额外挂载：

```yaml
volumes:
  - ./output:/app/output
  - ./.token_cache.json:/app/.token_cache.json
  - ./.client_tokens.json:/app/.client_tokens.json
```

通常不需要这么做，程序会自动重新登录刷新。
