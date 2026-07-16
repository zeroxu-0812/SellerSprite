# 追加 about this item 抓取与展示 设计

- 日期：2026-07-15
- 状态：已批准，待实现
- 涉及文件：`amazon_search.py`、`asin_pipeline.py`、`products.html`、`tests/`

## 背景

爬虫目前两类数据源：
1. 卖家精灵 `competitor-lookup`（`sellersprite_enrich.py`）——57 字段，**不含商品描述**。
2. 亚马逊详情页（`amazon_search.py` 的 `fetch_product_discount`）——已用 Playwright 抓 `dp/<asin>` 拿整页 HTML，目前只解析价格/折扣。

「About this item」是亚马逊详情页 `#feature-bullets` 区块的要点列表，是选品分析的重要信息。现有详情页请求已经在抓该页，只需扩展解析层即可拿到，**零额外请求、零额外反爬风险**。

自然流量词 / 广告流量词本轮**不做**——`competitor-lookup` 不含关键词数据，需要卖家精灵的另一个接口，等用户提供抓包后另开。

## 目标

1. 抓取每个 ASIN 的「About this item」要点列表。
2. 以 `about` 字段落地 `products.json`。
3. 在 `products.html` 新增「关于商品」列展示（摘要 + hover 看全文）。

## 非目标（YAGNI）

- 不做自然/广告流量词（等抓包）。
- 不改 `competitor-lookup` 抓取逻辑或其字段。
- 不改 `_flatten` 对 list 的处理（about 走现有「JSON 字符串」模式）。
- 不新增网络请求（复用既有详情页请求）。

## 设计

### 1. 抓取（`amazon_search.py`）

- 新增纯函数 `split_about_bullets(raw_text: str) -> list[str]`：
  - 输入 `#feature-bullets` 区块的纯文本（来自 Playwright `inner_text`）。
  - 按换行拆分，strip 每行，过滤噪音：空行、`See more` / `See less`、长度 ≤ 2 的碎片。
  - 返回要点列表，上限 20 条。**纯函数，可单测**。
- `fetch_product_discount` → 重命名为 `fetch_product_detail(asin, config) -> dict`：
  - 同一次 Playwright 请求：`page.content()` 给价格解析（不变）；新增 `page.inner_text("#feature-bullets")`（try/except，元素缺失返回 `""`）→ `split_about_bullets`。
  - 返回 `{list_price, price_current, discount_off_list_pct, about: list[str]}`。
  - best-effort：about 抓取失败 → `about=[]`，不影响价格字段。

### 2. 落地（`asin_pipeline.py` + `products.json`）

- `_enrich_discount` → 改名 `_enrich_detail`，调用 `fetch_product_detail`。
- 折扣逻辑不变；新增 `items[asin]["about"] = detail.get("about") or []`。
- 经 `field_merge.flatten_record` 后，`about`（`list[str]`）按 `field_merge.py:49-50` 规则存为 **JSON 字符串**（与 `badges` / `amz_unit_trend` 一致），字段名仍为 `about`。

### 3. 展示（`products.html`）

- 表头：在「标题」列后插入 `<th>关于商品</th>`。
- 新增 `renderAbout(p)`：
  - `JSON.parse(p.about)`（容错：非数组 → `[]`）。
  - 渲染 `<ul class="about-summary">`：前 2 条要点（CSS 限高），尾部 `…`；完整列表放入 `.about-full` 浮层。
  - 空数组 → `<span class="empty">—</span>`。
- `renderRow` 在标题单元格后插入 `<td class="about-cell">${renderAbout(p)}</td>`。
- CSS：`.about-cell { max-width:230px; position:relative; }`、`.about-summary` 列表样式 + 限高、`.about-full` 绝对定位浮层（复用 `.spark .bar .tip` 视觉：深蓝底/白字/圆角），`hover` 显示。
- `data-sort` 不加到「关于商品」列（文本太长，不排序）。

### 4. 范围与回归

- 改动文件：`amazon_search.py`、`asin_pipeline.py`、`products.html`、`tests/test_pipeline.py`、`tests/test_amazon_search.py`（新增）。
- `tests/test_pipeline.py`：`_stub_discount` → `_stub_detail`（stub 名随实现改名）；端到端 HTML 断言保持（注入机制不变）。
- 新增单测：`split_about_bullets`（纯函数，样本文本→预期列表）、`parse_price_detail`（已有逻辑，补 about 相关不涉及）。
- JS 语法用 `node --check` 校验；pytest 全程保持 passed。

### 5. ⚠️ 重新抓取（实现后必做）

`about` 是新字段，现有 `output/products.json`（14 条）没有它。**不能像上次 UI 优化只重渲染，必须重跑 14 个 ASIN**：
- 重新调 `competitor-lookup`（数据不变，token 自愈）。
- 重新抓 14 个详情页（Playwright，与折扣那次同路径，已验证可用）。
- 得到带 `about` 的新 `output/products.json` + `products.html`。

## 实现要点 / 边界

- `inner_text("#feature-bullets")` 元素缺失会抛 → 必须 try/except 归一为 `""`。
- `about` 在 `products.json` 是 JSON 字符串，前端务必 `JSON.parse` 容错（非字符串/非数组 → `[]`）。
- 「关于商品」列不参与排序（`data-sort` 不加）。
- best-effort 贯穿：单个 ASIN 的 about 失败不影响其他字段与整体。
