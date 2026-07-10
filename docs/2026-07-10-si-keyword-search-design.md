# 卖家精灵关键词搜索爬虫（si-keyword-search）设计文档

- **日期**：2026-07-10
- **项目根目录**：`/Users/haiyi/Desktop/project/SellerSprite/`（**自包含，不修改 OceanwingAgent-main**）
- **状态**：已通过复核（按"全部保存在 SellerSprite、不动 OceanwingAgent-main"约束修订）

---

## 1. 背景与目标

在亚马逊搜索关键词时，卖家精灵 Chrome 扩展会在结果页上叠加丰富的市场/商品数据。本项目的目标：**在后端用 CLI 输入关键词，复刻并落地这些数据**——即"输入关键词 → 抓取该搜索下卖家精灵所展示的数据"。

技术路线沿用 `keepa-monitor` 已验证的"**扩展接口逆向**"方式（伪装成扩展请求 `e.sellersprite.com`），不调用 Keepa 官方 API。

### 关键前提（已通过抓包验证）

**卖家精灵扩展本身没有"关键词 → 商品列表"接口。** 扩展真实工作流：
1. 扩展在亚马逊搜索页**自己抓取亚马逊 HTML** → 得到 ASIN 列表 + 亚马逊基础字段；
2. 扩展拿这批 ASIN 调 `quick-view` 批量接口 → 卖家精灵返回增强指标（销量/销售额/利润…）。

因此本项目是**两段流水线**：Leg A（关键词→ASIN，来自亚马逊）+ Leg B（ASIN→增强指标，来自卖家精灵）。

### 与 keepa-monitor 的关系（重要）
- **只读参考**：本项目从 keepa-monitor 借鉴鉴权（`KeepaTokenManager`）与 tk 签名算法的**实现思路**，把所需代码**复制**进 SellerSprite。
- **不修改 OceanwingAgent-main**：不抽公共层、不改 keepa-monitor 的 import。代价是签名算法在本项目内有一份副本（路线 B，受"不动 OceanwingAgent-main"硬约束的必然结果）。

---

## 2. 已验证的技术事实

| 事实 | 验证方式 | 结论 |
|------|---------|------|
| tk 签名算法可照搬 keepa-monitor | 本地 `token_calculate` 复现抓包 tk | ✅ 单个、批量 ASIN 均完全一致 |
| 鉴权三件套 `auth-token/auth-fp/random-token`，cookie 可选 | 抓包 cURL 在终端返回 `code:OK` JSON | ✅ 脱离浏览器可复现 |
| 域名 / 版本 | 抓包 | `e.sellersprite.com`、`version=5.0.4`（旧配置 5.0.2 已过期） |
| 扩展 ID / 语言 | 抓包 | `lnbmbgocenenhhhdojdielgnmeflbnfb` / `zh_CN` |
| 批量 quick-view 接口 | tk 对逗号拼接 ASIN 串签名，复现一致 | ✅ `competitor-lookup/quick-view/{station}?asins=A,B,C,...` |

**tk 签名公式（已验证）：**
```
tkk = extension_version_token(version)   # "5.0.4" → "500004.1364508470"
tk  = token_calculate(asins_str, tkk)    # asins_str = "ASIN1,ASIN2,..."
```
黄金值：`token_calculate("B0GDY15VMN", tkk) == "56333.490793"`、`token_calculate("B091FX694F,B00NUQT3R2", tkk) == "82711.451123"`。

---

## 3. 范围

### v1 做
- CLI 交互：输入关键词 → 抓取 → 打印摘要 + 商品表 → 落地 → 循环（`q` 退出）。
- **Leg A**：Playwright 无头浏览器搜亚马逊，翻 `max_pages` 页，抓 ASIN + 全部亚马逊字段。
- **Leg B**：每 `batch_size` 个 ASIN 一批调 `quick-view`，拿全部增强指标（开 `withRelation=true`、`withSaleTrend=true`）。
- **合并**：亚马逊字段 + 卖家精灵字段按"同字段同单元格 + 来源标注"规则合并成统一商品行。
- **输出**：CSV / JSON；含商品明细 + 派生市场总览。
- 鉴权 + 签名代码自包含复制进项目（不改 OceanwingAgent-main）。

### v1 不做
- 真实**关键词搜索量 / 竞争度指数**：亚马逊与 quick-view 都不返回，需另抓卖家精灵"关键词研究"接口（Phase 2）。
- HTML 看板、`seller-info-batch`、Keepa 趋势。

---

## 4. 架构

```
关键词
  │
  ▼  Leg A（Playwright 无头浏览器）
amazon.com 搜索 → 翻 max_pages 页 → 抓 ASIN + 亚马逊字段
  │
  ▼  Leg B（quick-view 批量，已验证）
每 batch_size 个 ASIN 一批 → sellersprite quick-view → 增强指标
  │
  ▼  合并（同字段同单元格 + 来源标注）+ 派生市场总览
统一商品表 + 市场总览 → CSV/JSON → 终端打印
```

### 项目布局（全部在 SellerSprite/）
```
SellerSprite/
├── code_standards.md                     # 参考准则（已有）
├── keepa-monitor爬虫逻辑分析.md           # 参考文档（已有）
├── docs/
│   └── 2026-07-10-si-keyword-search-design.md   # 本 spec
├── README.md
├── config.json                           # 亚马逊+卖家精灵参数、翻页、批大小、限速、重试
├── sellersprite_signing.py               # tk 签名三函数（复制自 keepa-monitor，自包含）
├── sellersprite_auth.py                  # KeepaTokenManager（复制自 keepa-monitor，自包含）
├── amazon_search.py                      # 【Leg A】Playwright 抓亚马逊搜索
├── sellersprite_enrich.py                # 【Leg B】quick-view 批量调用（鉴权+签名+重试+限速）
├── keyword_pipeline.py                   # 编排 + CLI 交互入口
├── keyword_output.py                     # CSV/JSON 落地 + 派生市场总览
├── .env.example                          # auth-token/auth-fp/random-token/cookie + 刷新命令
├── tests/
│   ├── test_signing.py                   # 用抓包真实 tk 做黄金值断言
│   └── fixtures/                         # 抓包响应样本（解析器测试用）
└── output/                               # 运行时产物（每关键词一子目录）
```

---

## 5. 组件设计

### 5.1 `sellersprite_signing.py`（复制自 keepa-monitor `fetch_keepa.py:266-335`）
- `extension_version_token(version) -> str`
- `token_calculate(text, tkk) -> str`（保留完整 UTF-8 代理对处理）
- `sellersprite_token(*parts, ext_version) -> str`
- 纯函数、无 IO、无副作用。

### 5.2 `sellersprite_auth.py`（复制自 keepa-monitor `keepa_auth.py`）
- `KeepaTokenManager`：`get_valid_headers / invalidate_cache / refresh_from_command`。
- 刷新优先 + 三层兜底（刷新命令 → 本地缓存 TTL → env 变量）。
- 环境变量：`KEEPA_AUTH_TOKEN / KEEPA_AUTH_FP / KEEPA_RANDOM_TOKEN / KEEPA_COOKIE` + `KEEPA_TOKEN_REFRESH_COMMAND`。
- 缓存文件落在 `SellerSprite/.token_cache.json`。

### 5.3 `amazon_search.py`（Leg A）
- **输入**：keyword、station、max_pages。
- **职责**：Playwright 启动无头 Chromium → 访问 `https://www.amazon.com/s?k=<quote(keyword)>&page=N` → 翻页 → 从渲染 DOM 提取每个商品的 ASIN + 亚马逊字段。
- **抓取字段**参照抓包 `listing-batch` body（等于"亚马逊页该抓什么"的现成清单）：asin、parent、title、brand、price、primeExclusivePrice、rating、reviews、bsr、bsrList、sellers、sellerId、sellerName、fulfillment、weight、dimensions、variations、variationList、firstAvailableDay、realSales、relation(fbt/vav)、reviewSummary、reviewHighlights、features、overviews、informationList、badges、allImages、allVideos 等。
- **稳健性**：随机翻页延时（默认 2–5s）、真实 UA、遇验证码/拦截重试或降级提示、`data-asin` 选择器为主。

### 5.4 `sellersprite_enrich.py`（Leg B）
- **输入**：ASIN 列表、station、token_manager。
- **URL**：`GET https://e.sellersprite.com/v2/extension/competitor-lookup/quick-view/{station}?asins=A,B,C,...&source=chrome&miniMode=false&withRelation=true&withSaleTrend=true&tk=<sig>&version=5.0.4&language=zh_CN&extension=<id>`
- `asins` 做 URL 编码；`tk = sellersprite_token(asins_str, ext_version=extension_version_token("5.0.4"))`。
- **批量**：按 `batch_size`（默认 20）分批，逐批调用。
- **重试**：408/429/5xx/超时重试，线性退避；鉴权失效 → `invalidate_cache()` + `refresh_from_command()` + 重试一次 → 仍失败熔断停止。
- **限速**：每批间 `sleep(random.uniform(delay_min, delay_max))`（默认 5–8s）。

### 5.5 `keyword_pipeline.py`（编排 + CLI）
```
加载 config + .env → 初始化 token_manager → 启动 Playwright（复用一个 browser 实例）
循环：
  提示 "输入关键词 (q 退出): "
  → amazon_search(keyword) → asin_records[]
  → 按 batch_size 切片 → sellersprite_enrich(asins) → enriched{asin: metrics}
  → merge(asin_records, enriched) → 统一商品行[]
  → 派生市场总览
  → 终端打印摘要 + 商品表
  → keyword_output 落地 output/keyword_{关键词}_{日期}/
  → 回到提示
q / Ctrl-C → 关闭 browser → 退出
```

### 5.6 `keyword_output.py`
- 合并统一商品行 → `products.csv` / `products.json`。
- 派生市场总览 → `market_overview.csv` / `market_overview.json`。

---

## 6. 字段方案（全部保留 + 合并规则）

### 6.1 合并规则（核心）
- 字段**仅一边有** → 直接写值（来源不言自明，不标）。
- 字段**两边都有且值不同** → `值A(亚马逊) / 值B(卖家精灵)`，对照展示。
- 两边值**相同** → 写一个值。
- **合并单位 = 叶子字段**：先扁平化再合并。嵌套字段 `dict[str,list]` → `field__sub`、`dict` → `field__subkey`、`list/tuple` → JSON 字符串；扁平到叶子后，每个叶子独立套用上面三条规则。例：`bsrList` 拆成 `bsr_main_rank`、`bsr_sub_rank` 等叶子，每个叶子若两边都有就单格双值带来源。
- 字段名归一：驼峰转下划线 + `CANONICAL_FIELD_MAP` 别名（如 `buyPrice→buy_price`）。
- **容错**：解析器全量保留原始字段、容忍未知字段（后续数据包新增字段不崩）。

### 6.2 派生市场总览（Layer 1，v1 从样本派生）
- 亚马逊结果总数（搜索页 "1-48 of 10,000"）。
- 样本均价 / 均评分 / 均评论。
- 样本总销量 / 总销售额（求和 quick-view 的 `units` / `amount`）。
- 价格 / 评分 / 销量分布（直方图）。
- 头部集中度（Top10 销量占样本比）。
- 各主类目商品数分布。
> 真实搜索量 / 竞争度指数不在 v1（需 Phase 2 另抓关键词研究接口）。

### 6.3 字段目录（全保留，标注来源 🅰=亚马逊 🅱=卖家精灵 🅰🅱=两边）

| 类目 | 字段（来源） |
|------|-------------|
| 商品标识 | asin🅰🅱 · parent🅰🅱 · alias🅰 · title🅰 · url/image/brandUrl🅰 |
| 类目节点 | nodeIdPath/nodeLabelPath🅰 · bsrId/bsrLabel🅰🅱 · bsrList🅰🅱 |
| 价格 | price🅰 · primeExclusivePrice🅰 · currency🅱 |
| 销量/营收/利润 | realSales🅰 · units/month_units/units_growth🅱 · amount/amount_growth🅱 · profit/fba🅱 · trends🅱(withSaleTrend) |
| BSR/排名/变化 | bsr🅰 · bsrList[].rank🅰🅱 · bsr_cr/bsr_cv🅱 · lqs🅱 |
| 评论 | rating/reviews🅰 · reviewSummary/reviewHighlights🅰 |
| 卖家 | sellers🅰🅱 · sellerId🅰🅱 · sellerName🅰🅱 · fulfillment🅰 · seller_type🅱 · seller_dto.nation🅱 |
| 物流/包装 | weight🅰🅱 · dimensions/dimension🅰🅱 · pkg_weight/pkg_dimensions/pkg_volume_weights🅱 · pkg_dimension_type(+中英日标签)🅱 |
| 变体 | variations🅰🅱 · variationList🅰 · sku🅰🅱 |
| 关联/关键词 | relation.fbt/vav🅰(关联商品ASIN) · relationKeyword🅱(关联关键词计数 ads/nature/total/recommend) |
| 媒体/内容 | features🅰 · allImages/allVideos🅰 · overviews/informationList🅰 · badges/badgesDetail🅰 |
| 上架/时间 | firstAvailableDay🅰(ISO) · available🅱(ms) · available_days🅱 |

---

## 7. 配置项（config.json）

```json
{
  "station": "US",
  "language": "zh_CN",
  "version": "5.0.4",
  "extension_id": "lnbmbgocenenhhhdojdielgnmeflbnfb",
  "source": "chrome",
  "quick_view": {
    "base_url": "https://e.sellersprite.com/v2/extension/competitor-lookup/quick-view",
    "batch_size": 20,
    "with_relation": true,
    "with_sale_trend": true,
    "request_timeout_seconds": 50,
    "retry_attempts": 2,
    "retry_backoff_seconds": 2,
    "delay_seconds_min": 5,
    "delay_seconds_max": 8
  },
  "amazon": {
    "base_url": "https://www.amazon.com",
    "max_pages": 1,
    "page_delay_seconds_min": 2,
    "page_delay_seconds_max": 5,
    "user_agent": "Mozilla/5.0 ... Chrome/150.0.0.0 Safari/537.36"
  }
}
```

---

## 8. 输出格式

每关键词一目录：`output/keyword_{关键词}_{YYYY-MM-DD}/`
- `products.csv` / `products.json`：每商品一行；冲突字段按合并规则单格双值带来源标注。
- `market_overview.csv` / `market_overview.json`：派生总览（单行/单对象）。

---

## 9. 错误处理

- **鉴权失效**：`code/message` 双重判定 → 抛 `AuthExpiredError` → 清缓存 → 刷新 → 重试一次 → 仍失败熔断停止（避免烧接口）。
- **业务错误码**：非 `None/200/"200"/"OK"` 打印并跳过该批，不中断循环。
- **亚马逊反爬**（验证码/拦截）：重试若干次，仍失败则该关键词标注降级并继续，不崩溃。
- **网络瞬时错误**：重试 + 随机退避。

---

## 10. 测试

- `tests/test_signing.py`：用抓包真实值做黄金断言——
  - `token_calculate("B0GDY15VMN", tkk5.0.4) == "56333.490793"`
  - `token_calculate("B091FX694F,B00NUQT3R2", tkk5.0.4) == "82711.451123"`
- 解析器测试：用 `tests/fixtures/` 下的抓包响应做 fixture，验证字段提取、归一、合并规则。
- 端到端冒烟（手测）：输入一个词，确认 CSV 落地 + 终端摘要正确。

---

## 11. 依赖

- Python 3。
- **Playwright**（新增）：`pip install playwright && playwright install chromium`。
- 标准库（csv/json/urllib/random/subprocess 等）。

---

## 12. 风险与待办

| 风险 | 说明 | 对策 |
|------|------|------|
| 亚马逊反爬 | Leg A 直接搜亚马逊可能遇验证码/封 IP | Playwright 真浏览器 + 随机延时 + 真实 UA + 重试降级；必要时加代理 |
| 字段漂移 | 后续数据包字段可能变/增 | 解析器全量保留原始字段、容忍未知字段 |
| 登录态过期 | 扩展 token 会过期 | `KEEPA_TOKEN_REFRESH_COMMAND` 自动刷新，或定期手动更新 .env |
| 真实搜索量缺失 | v1 市场总览为派生值 | Phase 2 抓卖家精灵关键词研究接口补搜索量/竞争度 |
| 签名算法副本 | 自包含复制，与 keepa-monitor 重复一份 | 受"不动 OceanwingAgent-main"约束的取舍；若将来允许改 OceanwingAgent-main，可再抽公共层 |

---

## 13. 验收标准

1. CLI 输入关键词能跑完 Leg A + Leg B，终端打印市场摘要 + 商品表。
2. `products.csv` 含全部保留字段，冲突字段按"单格双值带来源标注"呈现。
3. `market_overview.*` 含派生总览各项。
4. `test_signing.py` 黄金断言通过。
5. 鉴权失效能自愈一次；业务错误码跳过不崩。
6. **OceanwingAgent-main 零改动**（全部产物落在 `SellerSprite/`）。
