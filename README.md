# 卖家精灵 ASIN 爬虫

输入亚马逊 ASIN（粘贴或文件）→ 并发抓取卖家精灵 `competitor-lookup` 全量数据 + 亚马逊详情页折扣 → 落地 JSON。

## 它做什么

给定一批 ASIN，伪装成卖家精灵 Chrome 扩展请求 `e.sellersprite.com` 的 `competitor-lookup` 接口，一次性拿回每个 ASIN 的全量字段：

- **亚马逊侧**：标题、准确 USD 现价、评分、评论数、BSR 排名、封面图、badges
- **卖家精灵增强**：月销量 / 销售额 / 利润 / FBA 费、月度销量趋势 `amz_unit_trends`、评论增长、Listing 质量分 `lqs`
- **卖家信息**：卖家公司全称 / 地址 / 国别（`seller_dto`）
- **折扣**：划线价 `list_price` / 折扣% `discount_off_list_pct`（competitor-lookup 不返回，额外抓亚马逊详情页补）

**并发抓取**（默认 3 worker）：competitor-lookup 按批（每批 20）并发请求，折扣详情页也并发抓取。

## 安装

```
pip install -r requirements.txt
playwright install chromium
```

## 配置鉴权

复制 `.env.example` 为 `.env`，填卖家精灵登录账号 + 两个客户端稳定值：

```
KEEPA_AUTH_FP=<抓包获取，稳定不变>
KEEPA_RANDOM_TOKEN=<抓包获取，稳定不变>
KEEPA_LOGIN_USERNAME=<卖家精灵账号>
KEEPA_LOGIN_PASSWORD=<密码明文，自动 MD5；或直接填 MD5 哈希并设 KEEPA_LOGIN_PASSWORD_MD5=false>
```

- `KEEPA_AUTH_FP` / `KEEPA_RANDOM_TOKEN`：从扩展 devtools 抓任意一条 sellersprite 请求头获取（一次即可，长期不变）。
- `auth-token` **无需手填**——token 过期会自动登录刷新。

## 运行

```
python asin_pipeline.py
```

然后两种输入方式（自动识别）：
- **粘贴 ASIN**：逗号 / 空格 / 换行分隔多个，回车开始
- **文件路径**：输入含 ASIN 的 `.txt` 文件路径（一行多个或一个都可，支持 `#` 注释），适合批量

输入 `q` 退出。

```
输入 ASIN 或文件路径: B0F1QHNFJP B0FN3QLFVG
输入 ASIN 或文件路径: asins.txt
```

## 输出

**扁平单份**：`output/` 每次运行前自动清空上一次结果，永远只保留最新一次的 3 个文件：
- `products.json`：每个商品一个对象，全字段保留（去空值、去冗余原始 JSON、camelCase 转下划线、嵌套扁平化），并派生 `image_large`（1500px 高清封面）、`url`（商品详情页链接）、`available_date`（上架日期 yyyy-mm-dd）
- `market_overview.json`：派生市场总览（均价 / 均评分 / 总销量 / 总销售额 / Top10 集中度 / 价格与评分分布）
- `products.html`：**自包含富表格视图**——把上面两份 JSON 直接内联渲染，**双击用浏览器打开即可查看**（无需服务器 / 不依赖 CSV；`file://` 下也能用）。无内联数据时退化为拖拽 `products.json` 手动加载的查看器。

终端同步打印关键字段摘要表 + 市场总览，并给出 HTML 路径。

## 配置（config.json）

| 项 | 说明 |
|---|---|
| `concurrency.workers` | 并发线程数（默认 3）。设为 1 则退回顺序抓取（competitor-lookup 批间延时 5–8s） |
| `quick_view.batch_size` | competitor-lookup 每批 ASIN 数（默认 20） |
| `quick_view.retry_attempts` | 408/429/5xx/超时重试次数（默认 2） |
| `amazon.user_agent` | 抓详情页用的 UA |

## 项目结构

```
asin_pipeline.py        # 编排 + CLI：输入 → 并发增强 → JSON 落地
sellersprite_enrich.py  # competitor-lookup 批量调用（并发 + 重试 + 鉴权自愈）
sellersprite_auth.py    # 鉴权头管理（并发安全：锁 + 双检缓存，token 过期自动登录刷新）
refresh_tokens.py       # 自动登录 signin 刷新 auth-token
sellersprite_signing.py # tk 反爬签名（TKK 算法）
amazon_search.py        # 亚马逊详情页折扣抓取（Playwright）
field_merge.py          # 字段扁平化 + camelCase→snake_case + 高清图派生
market_overview.py      # 派生市场总览
output_writer.py        # 扁平单份 JSON 落地（每次清空 output）
html_render.py          # 把 products.json 内联渲染进自包含 products.html
products.html           # 富表格视图模板（16 列，BSR/趋势/价格等）
config.json             # 站点 / 并发 / 批大小 / 限速 / 重试
tests/                  # pytest：签名黄金值、解析、并发、端到端落盘
```

## 测试

```
python -m pytest -v
```

## 鉴权与稳健性

- **token 分钟级过期**：`auth-token` 几分钟失效，靠 `refresh_tokens.py` 自动登录刷新（`KEEPA_TOKEN_REFRESH_COMMAND`）；并发时锁保证只登录一次。
- **鉴权自愈**：接口返回过期码（401 / `ERR_NEED_RE_AUTHORIZED` 等）→ 清缓存 → 刷新 → 重试一次 → 仍失败熔断。
- **业务错误**：单批业务错误码跳过该批，不中断整体。
- **反爬**：抓亚马逊详情页可能遇验证码 / 封 IP，必要时调低 `concurrency.workers` 或加代理。
