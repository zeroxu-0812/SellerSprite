# keepa-monitor 爬虫逻辑分析

> 分析对象：`OceanwingAgent-main/modules/keepa-monitor`
> 核心文件：`fetch_keepa.py` · `keepa_sources.py` · `keepa_auth.py` · `asin_inputs.py`
> 整理日期：2026-07-09

---

## 一、项目定位（一句话）

它**不是**调用 Keepa 官方 API，而是**逆向了「卖家精灵」Chrome 扩展**，伪装成扩展去请求卖家精灵的 Keepa 数据接口
`https://www.sellersprite.com/v2/extension/keepa`，拿到 Keepa 风格的时间序列（BSR、价格、评分等），
再落地成宽表 / 长表 / 摘要 / HTML 看板。

核心入口：`fetch_keepa.py` 的 `main()`。

---

## 二、整体流程

```
加载 .env → 加载 config.json → 鉴权头(KeepaTokenManager) → 加载 ASIN 列表
   ↓
for 每个 ASIN:
   构造 URL(含反爬签名 tk) → 发请求(带重试/限速) → 解析时间序列 → 累积
   ↓
每 20 个存一次 checkpoint → 全部完成后保存 CSV / JSON / 摘要 / 看板
```

---

## 三、分层详解

### 1. 输入层：ASIN 从哪来（`load_input_records` · `fetch_keepa.py:205`）

支持 5 种来源，默认 `feishu`：

| 来源 | 说明 | 关键代码 |
|------|------|---------|
| `feishu` | 调飞书开放 API 读表格，ASIN 列 + 任意标签列；主图 URL 用 VLOOKUP 时还能自动查辅助表「商品主图URL」补图 | `keepa_sources.py:65` `FeishuSheetSource` |
| `txt` | 本地 `config/asins.txt`，正则 `\b[A-Z0-9]{10}\b` 抽 ASIN | `asin_inputs.py:11` `ASIN_RE` |
| `csv` | 自动识别含 "asin" 的列，其余列当标签 | `asin_inputs.py:102` |
| `excel` | 同上，依赖 `openpyxl` | `asin_inputs.py:111` |
| `manual` | 命令行 `--manual-asins` | `asin_inputs.py:66` |

ASIN 合法性 / 去重：`normalize_asin`（大写归一）、`is_valid_asin`（10 位字母数字）、
`_dedupe`（按归一后的 ASIN 去重）。

飞书读取要点：
- 两种 URL 都支持：`/sheets/{token}` 直链 和 `/wiki/{token}`（需 `wiki/v2/spaces/get_node` 解析出 `obj_token`）
- 鉴权用 `tenant_access_token`（`auth/v3/app_access_token/internal`）
- 富文本单元格用 `extract_cell_text` 递归取 `text/link/value`

---

### 2. 鉴权层（`keepa_auth.py`）— 模拟扩展登录态

请求需要 4 个扩展登录头：

| Header | 环境变量 | 必填 |
|--------|---------|------|
| `auth-token` | `KEEPA_AUTH_TOKEN` | ✅ |
| `auth-fp` | `KEEPA_AUTH_FP` | ✅ |
| `random-token` | `KEEPA_RANDOM_TOKEN` | ✅ |
| `cookie` | `KEEPA_COOKIE` | 可选 |

`KeepaTokenManager`（`keepa_auth.py:28`）做了**刷新优先 + 三层兜底**策略：

1. 若 `KEEPA_TOKEN_REFRESH_EACH_RUN=true`（默认）→ 每次运行先执行刷新命令
2. 否则读本地缓存 `.keepa_token_cache.json`（TTL 默认 90 分钟，`ttl_seconds=5400`）
3. 缓存过期 → 读 `.env` 中的 4 个变量
4. 都没有 → 执行 `KEEPA_TOKEN_REFRESH_COMMAND`

**可插拔的自动刷新命令**（`refresh_from_command` · `keepa_auth.py:110`）：
- 在仓库根目录执行一个 shell 命令
- 该命令的 **stdout 必须是 JSON**，含 `auth-token/auth-fp/random-token`（`cookie` 可选）
- 可选字段 `ttl_seconds` 自定义本次缓存活多久
- 输出会被校验（缺必需字段直接抛错）并写入缓存

> 这套设计是因为扩展登录态会频繁过期，需要一个**外部可替换的刷新源**（例如另一个脚本去扩展里捞最新 token）。

---

### 3. ⭐ 反爬签名（爬虫真正的核心）—— `tk` 参数

请求 URL 里的 `tk` 参数是卖家精灵做的**反爬签名**，本质是逆向自其扩展的算法。
代码位置：`fetch_keepa.py:266-335`。

**两层构造：**

```python
tk = sellersprite_token(asin, ext_version=extension_version_token(version))
```

#### 第一层：`extension_version_token(version)` · `fetch_keepa.py:266`

把扩展版本号拼成 TKK 种子。例如 `5.0.2` →
```
5.0.2  →  "5.0.2".replace('.', '00', 1)  → "5002.2"
       →  再把第二个 '.' 替换为 '0'       → "50020.1364508470"  # 形如 tkk
```
> 实现细节：第一次替换第一个 `.` → `00`，第二次替换剩余第一个 `.` → `0`，
> 末尾拼固定后缀 `.1364508470`。版本号 `5.0.2` 的结果是 `50002.1364508470`。

#### 第二层：`token_calculate(text, tkk)` · `fetch_keepa.py:277`

把 ASIN 字符串做 **UTF-8 编码**后，套用经典的 **Google Translate TKK 算法**：

1. 把字符串编码成字节序列（完整的 UTF-8 多字节处理，含代理对 surrogate pair）
2. 用 `value = base`（tkk 第一段）累加每个码点，每步过 `mix(value, "+-a^+6")`
3. 最后过一次 `mix(value, "+-3^+b+-f")`，再 `value ^= int(tkk 第二段)`
4. 负数修正：`0x80000000 + (value & 0x7FFFFFFF)`
5. 取 `value % 1_000_000` 得到 `token`，返回 `f"{token}.{token ^ base}"`

`mix` 函数（`fetch_keepa.py:278`）按 3 字符一组解析种子串，根据中间符号做移位（`+` 右移 / 其他左移）和累加 / 异或。

> 这个 `token_calculate` 是业内非常眼熟的 **TKK 签名算法**（原 Google 翻译接口的 `tk` 计算逻辑被搬到卖家精灵这里做接口校验）。

#### 最终 URL（`build_url` · `fetch_keepa.py:338`）

```
https://www.sellersprite.com/v2/extension/keepa
  ?station=US
  &asin=B0XXXXXXXX
  &period=DAY
  &tk=<动态签名>
  &version=5.0.2
  &language=zh_CN
  &extension=lnbmbgocenenhhhdojdielgnmeflbnfb   # 扩展 ID
  &source=chrome
```

这些 query 参数全部来自 `config/config.json`：

```json
{
  "base_url": "https://www.sellersprite.com/v2/extension/keepa",
  "station": "US",
  "period": "DAY",
  "version": "5.0.2",
  "language": "zh_CN",
  "extension_id": "lnbmbgocenenhhhdojdielgnmeflbnfb",
  "source": "chrome"
}
```

---

### 4. 请求执行（`fetch_keepa` · `fetch_keepa.py:362`）

```
build_url(asin) → urlopen(带 auth headers, timeout=50s) → json 解析
```

**重试策略**（`fetch_keepa.py:369`）：
- 对 `408 / 429 / 5xx / 超时 / 网络波动`（含 "timed out" / "tempor" 关键字）重试
- 重试次数 `retry_attempts`（默认 2），退避 `retry_backoff_seconds * attempt`（线性退避）

**鉴权失效处理**（`is_auth_expired_response` · `fetch_keepa.py:100`）：
- 识别 HTTP 401，**或**响应体里：
  - `code ∈ {401, UNAUTHORIZED, TOKEN_EXPIRED, AUTH_EXPIRED}`
  - `message` 含 `令牌过期 / token expired / token invalid / auth expired / unauthorized / 登录失效 / 重新登录`
- → 抛 `AuthExpiredError`

**业务错误码**：`code` 非 `None/200/"200"/"OK"` 时按 API 错误打印并返回 `None`（跳过该 ASIN）。

**main 里的鉴权失效自愈**（`fetch_keepa.py:759`）：
1. 捕获 `AuthExpiredError` → `token_manager.invalidate_cache()` 清缓存
2. 尝试 `refresh_from_command()` 刷新后重试一次
3. 仍失败 → **停止整个抓取**（避免持续打无效请求，烧接口）

---

### 5. 限速（防封）

`fetch_keepa.py:805`：每个 ASIN 之间 `sleep(random.uniform(delay_min, delay_max))`，
区间来自 config 的 `delay_seconds_min`（默认 5）/ `delay_seconds_max`（默认 8）。

> **用随机区间而非固定间隔**，降低被识别为机器人的风险。

另有**断点保护**：每抓 20 个 ASIN 存一次 `_checkpoint` 中间结果（`fetch_keepa.py:809`），
防止长时间运行中途崩溃丢失全部进度。

---

### 6. 响应解析（`extract_all_fields` · `fetch_keepa.py:465`）

Keepa 返回的是「时间轴 + 各指标序列」结构：

```json
{
  "times": [<分钟戳或字符串时间轴>],
  "keepa": {
    "bsr":   [...],
    "price": [...],
    "rating": [...],
    "rootRanks": { "<category>": [...] }
  }
}
```

解析逻辑：
- `parse_keepa_time`（`fetch_keepa.py:424`）：兼容**旧版 Keepa 分钟戳**
  （基准 `2011-12-31 23:00`）和**新版字符串**（`%Y-%m-%d %H:%M`）
- `get_keepa_times`（`fetch_keepa.py:432`）：兼容旧 `keepa.time` 和新顶层 `times`
- 把每个指标按时间点展开成长表行 `{asin, date, datetime, metric, value}`
- **嵌套字段扁平化**：`rootRanks` 这类 `dict[str, list]` → `metric__sub`（`fetch_keepa.py:521`）；
  值是 `dict` → `metric__subkey`；值是 `list/tuple` → 存成 JSON 字符串
- **字段名标准化**：驼峰转下划线，并用 `CANONICAL_FIELD_MAP`（`fetch_keepa.py:76`）做别名归一
  （如 `buyPrice → buy_price`、`price_amazon → amazon_price`、`sellers → seller_count`）

---

### 7. 输出（`save_results` · `fetch_keepa.py:612`）

四份产物 + 看板，全部写入 `output/` 目录，文件名带日期 `YYYY-MM-DD`：

| 文件 | 内容 |
|------|------|
| `keepa_data_<date>.csv` | **宽表**：每个 ASIN 每天一行，列是各指标 |
| `keepa_data_long_<date>.csv` | 长表（明细时间序列） |
| `keepa_raw_<date>.json` | 原始响应（按 ASIN 索引） |
| `keepa_summary_<date>.csv` | 每个 ASIN **最新一天**的摘要 |
| `keepa_dashboard_<date>.html` | HTML 可视化看板（`keepa_dashboard.py`） |

**宽表聚合细节**（`build_wide_rows` · `fetch_keepa.py:536`）：
- 以 `(asin, date)` 为主键聚合
- 同一指标同一天可能有多条记录，用隐藏键 `__metric_datetime__<metric>` 做 tie-break，
  **保留当天 datetime 最新的那个值**
- 输出列顺序：`asin + 标签列 + date + latest_datetime + 指标列（按 METRIC_COLUMN_ORDER 排序）`

**摘要表**（`build_summary_rows` · `fetch_keepa.py:583`）：每个 ASIN 取 `(date, latest_datetime)` 最大那天的一行。

---

## 四、总结图

```
┌─────────────┐   ┌──────────────┐   ┌───────────────────────────────┐
│ ASIN 输入    │ → │ 鉴权头管理    │ → │ 构造请求:                      │
│ feishu/txt/ │   │ KeepaToken   │   │  sellersprite keepa 接口       │
│ csv/excel   │   │ Manager      │   │  + tk 反爬签名(TKK 算法)      │
└─────────────┘   │ (缓存+刷新)  │   │  + 4 个扩展登录头              │
                  └──────────────┘   └──────────────┬────────────────┘
                                                     │ urlopen + 重试 + 随机限速
                                                     ▼
                              ┌────────────────────────────────────────┐
                              │ 解析: 时间轴 × 指标 → 长表 → 宽表/摘要  │
                              │ 落地: CSV / JSON / HTML 看板            │
                              └────────────────────────────────────────┘
```

---

## 五、重点代码索引（建议精读顺序）

| 主题 | 位置 | 为什么重要 |
|------|------|-----------|
| **反爬签名算法** | `fetch_keepa.py:277` `token_calculate` | 爬虫技术核心，TKK 签名 |
| 签名种子构造 | `fetch_keepa.py:266` `extension_version_token` | 版本号 → tkk |
| URL 拼装 | `fetch_keepa.py:338` `build_url` | 看清请求全貌 |
| **登录态自动刷新** | `keepa_auth.py:110` `refresh_from_command` | 可插拔刷新源 |
| 鉴权头管理 | `keepa_auth.py:77` `get_valid_headers` | 缓存 / env / 刷新 三层兜底 |
| **请求执行+重试+限速** | `fetch_keepa.py:362` `fetch_keepa` | 工程化处理 |
| 鉴权失效识别 | `fetch_keepa.py:100` `is_auth_expired_response` | 关键字 + 错误码双重判定 |
| 响应解析 | `fetch_keepa.py:465` `extract_all_fields` | 长表展开 + 字段归一 |
| 飞书取 ASIN | `keepa_sources.py:65` `FeishuSheetSource` | wiki/sheets 双链路 |

---

## 六、可复用的工程技巧

1. **反爬签名逆向**：TKK 算法（Google Translate 同款），是很多国产 SaaS 接口的通用校验手段
2. **登录态解耦**：把易过期的 token 刷新逻辑抽成可配置的 shell 命令（输出 JSON），主程序只负责调用
3. **随机限速**：用 `[min, max]` 随机区间而非固定 sleep，规避机器人特征
4. **断点续存**：批量任务每 N 条落一次 checkpoint，长任务抗崩溃
5. **鉴权失效自愈**：检测到失效 → 清缓存 → 刷新 → 重试一次 → 仍失败则熔断停止，避免无意义重试烧接口
6. **字段归一**：`CANONICAL_FIELD_MAP` + 驼峰转下划线，兼容上游字段命名漂移
