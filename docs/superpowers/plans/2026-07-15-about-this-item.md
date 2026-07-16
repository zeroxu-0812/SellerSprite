# 追加 about this item 抓取与展示 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复用现有亚马逊详情页请求抓取「About this item」要点，落地 `products.json` 的 `about` 字段，并在 `products.html` 新增「关于商品」列展示（摘要 + hover 全文）。

**Architecture:** `amazon_search.py` 在同一次 Playwright 详情页请求里用 `inner_text("#feature-bullets")` 取要点文本 → `split_about_bullets` 纯函数拆分；`asin_pipeline._enrich_detail` 把 `about` 写入商品记录；`field_merge._flatten` 自动把 `list[str]` 存为 JSON 字符串（同 badges/trend）；前端 `JSON.parse` 渲染。

**Tech Stack:** Python / Playwright（抓取）、原生 JS（展示）、pytest（回归）。

## Global Constraints

- **不新增网络请求**——复用既有详情页请求（`fetch_product_discount` 那次）。
- 不改 `competitor-lookup` 抓取逻辑，不改 `field_merge._flatten`。
- `about` 在 `products.json` 存为 **JSON 字符串**，前端务必 `JSON.parse` 容错。
- **不自动 `git commit`**：每个任务完成后向用户确认是否提交。
- `pytest` 全程保持 `passed`（改名跨文件同步，不留中间断裂状态）。
- 实现完成后**必须重跑 14 个 ASIN**（`about` 是新字段，旧 `output/` 没有，不能只重渲染）。

## 测试策略

- `split_about_bullets` 是纯函数 → 严格 TDD（测试先行）。
- `fetch_product_detail` 依赖 Playwright + 网络，不可单测 → 实跑验证留到 Task 4 重跑。
- 前端 JS → `node --check` 语法 + 渲染后浏览器手动验收。
- 改名（`fetch_product_discount→fetch_product_detail`、`_enrich_discount→_enrich_detail`）跨 `amazon_search.py` / `asin_pipeline.py` / `tests/test_pipeline.py` 同步，保证每步 pytest 绿。

---

### Task 1: `split_about_bullets` 纯函数（TDD）

**Files:**
- Modify: `amazon_search.py`（顶部 `import re` 之后新增函数）
- Create: `tests/test_amazon_search.py`

**Interfaces:**
- Produces: `split_about_bullets(raw_text: str) -> list[str]`，供 Task 2 的 `fetch_product_detail` 调用。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_amazon_search.py`：

```python
"""amazon_search 解析层单测（不触网）。"""
from amazon_search import split_about_bullets


def test_split_about_bullets_basic():
    text = "\n".join([
        "Magnesium cream for muscles and joints",
        "Fast absorbing, non-greasy formula",
        "See more",
        "",
        "ab",                       # 过短，过滤
        "With MSM, Arnica & B6",
    ])
    assert split_about_bullets(text) == [
        "Magnesium cream for muscles and joints",
        "Fast absorbing, non-greasy formula",
        "With MSM, Arnica & B6",
    ]


def test_split_about_bullets_empty():
    assert split_about_bullets("") == []
    assert split_about_bullets(None) == []


def test_split_about_bullets_caps_at_20():
    many = "\n".join(f"bullet number {i}" for i in range(30))
    assert len(split_about_bullets(many)) == 20
    assert split_about_bullets(many)[0] == "bullet number 0"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_amazon_search.py -v`
Expected: FAIL — `ImportError: cannot import name 'split_about_bullets'`（函数尚未定义）。

- [ ] **Step 3: 实现 `split_about_bullets`**

在 `amazon_search.py` 的 `import re` 之后、`def parse_price` 之前插入：

```python
def split_about_bullets(raw_text: str) -> list:
    """把 #feature-bullets 区块文本拆成要点列表，过滤噪音。
    输入来自 Playwright inner_text（按换行分隔的要点）。空/过短/“See more”等过滤，上限 20 条。"""
    if not raw_text:
        return []
    drop = {"see more", "see less", "see all"}
    out = []
    for line in raw_text.splitlines():
        t = line.strip()
        if not t or len(t) <= 2:
            continue
        if t.lower() in drop:
            continue
        out.append(t)
    return out[:20]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_amazon_search.py -v`
Expected: `3 passed`。

- [ ] **Step 5: 询问用户是否 commit**

---

### Task 2: 详情页抓取接线（fetch_product_detail + about 落地）

**Files:**
- Modify: `amazon_search.py`（`fetch_product_discount` → `fetch_product_detail`）
- Modify: `asin_pipeline.py`（import / `_enrich_discount` → `_enrich_detail` / 调用点 / about 写入 / print 文案）
- Modify: `tests/test_pipeline.py`（stub 改名 + about）

**Interfaces:**
- Consumes: Task 1 的 `split_about_bullets`。
- Produces: `fetch_product_detail(asin, config) -> dict`（含 `about`）；商品记录带 `about: list[str]`，经 flatten 变 JSON 字符串。供 Task 3 前端 `JSON.parse`。

- [ ] **Step 1: `amazon_search.py` 重命名 + 提取 about**

把现有的 `fetch_product_discount` 整体替换为 `fetch_product_detail`（同一次请求增加 `inner_text`）：

old:
```python
def fetch_product_discount(asin: str, config: dict) -> dict:
    """用 Playwright 抓亚马逊商品详情页(dp/<asin>)，解析页面显示的折扣。best-effort。"""
    from playwright.sync_api import sync_playwright
    az = config["amazon"]
    url = f"{az['base_url']}/dp/{asin}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page_obj = browser.new_context(user_agent=az["user_agent"]).new_page()
            page_obj.goto(url, timeout=60000)
            html = page_obj.content()
        finally:
            browser.close()
    return parse_price_detail(html)
```

new:
```python
def fetch_product_detail(asin: str, config: dict) -> dict:
    """用 Playwright 抓亚马逊详情页(dp/<asin>)，解析折扣 + About this item。best-effort。"""
    from playwright.sync_api import sync_playwright
    az = config["amazon"]
    url = f"{az['base_url']}/dp/{asin}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page_obj = browser.new_context(user_agent=az["user_agent"]).new_page()
            page_obj.goto(url, timeout=60000)
            html = page_obj.content()
            try:
                bullets_text = page_obj.inner_text("#feature-bullets")
            except Exception:
                bullets_text = ""
        finally:
            browser.close()
    detail = parse_price_detail(html)
    detail["about"] = split_about_bullets(bullets_text)
    return detail
```

- [ ] **Step 2: `asin_pipeline.py` 接线**

2a. import 改名。old: `from amazon_search import fetch_product_discount` → new: `from amazon_search import fetch_product_detail`

2b. `_enrich_discount` → `_enrich_detail`（函数名 + 内部调用 + about 写入 + print 文案）。整体替换：

old:
```python
def _enrich_discount(items: dict, config: dict) -> None:
    """并发抓亚马逊详情页拿【页面显示的折扣%】（币种无关），再用 competitor 的准确 USD 现价
    反推出 USD 的折扣前价。best-effort，单个失败不影响整体。"""
    workers = max(1, int((config.get("concurrency") or {}).get("workers", 3)))
    asins = [a for a in items if a]
    if not asins:
        return
    print(f"   亚马逊详情页折扣: {len(asins)} 个 ASIN（并发 {workers}）...")

    def fetch_one(asin):
        try:
            return asin, fetch_product_discount(asin, config)
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠️ {asin} 折扣抓取失败，跳过: {e}")
            return asin, {}

    results = {}
    if workers == 1 or len(asins) <= 1:
        for asin in asins:
            a, detail = fetch_one(asin)
            results[a] = detail
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for asin, detail in ex.map(fetch_one, asins):
                results[asin] = detail

    for asin, detail in results.items():
        disc = detail.get("discount_off_list_pct")
        items[asin]["discount_off_list_pct"] = disc
        price = items[asin].get("price")           # competitor 准确 USD 现价（折扣后）
        if disc and isinstance(price, (int, float)) and price > 0:
            # USD 折扣前价 = 现价 / (1 - 折扣%)
            items[asin]["list_price"] = round(price / (1 - disc / 100), 2)
```

new:
```python
def _enrich_detail(items: dict, config: dict) -> None:
    """并发抓亚马逊详情页拿【折扣% + About this item】。折扣% 用 competitor 准确 USD 现价
    反推折扣前价；about 取 feature-bullets 要点。best-effort，单个失败不影响整体。"""
    workers = max(1, int((config.get("concurrency") or {}).get("workers", 3)))
    asins = [a for a in items if a]
    if not asins:
        return
    print(f"   亚马逊详情页(折扣+About): {len(asins)} 个 ASIN（并发 {workers}）...")

    def fetch_one(asin):
        try:
            return asin, fetch_product_detail(asin, config)
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠️ {asin} 详情抓取失败，跳过: {e}")
            return asin, {}

    results = {}
    if workers == 1 or len(asins) <= 1:
        for asin in asins:
            a, detail = fetch_one(asin)
            results[a] = detail
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for asin, detail in ex.map(fetch_one, asins):
                results[asin] = detail

    for asin, detail in results.items():
        disc = detail.get("discount_off_list_pct")
        items[asin]["discount_off_list_pct"] = disc
        price = items[asin].get("price")           # competitor 准确 USD 现价（折扣后）
        if disc and isinstance(price, (int, float)) and price > 0:
            # USD 折扣前价 = 现价 / (1 - 折扣%)
            items[asin]["list_price"] = round(price / (1 - disc / 100), 2)
        items[asin]["about"] = detail.get("about") or []
```

2c. `process_asins` 里的调用改名。old: `    _enrich_discount(items, config)   # 亚马逊详情页折扣信息` → new: `    _enrich_detail(items, config)   # 亚马逊详情页：折扣 + About this item`

- [ ] **Step 3: `tests/test_pipeline.py` stub 改名 + about**

3a. stub 函数。old:
```python
def _stub_discount(items, config):
    for asin in items:
        items[asin]["discount_off_list_pct"] = 30.0
        price = items[asin].get("price")
        if isinstance(price, (int, float)) and price > 0:
            items[asin]["list_price"] = round(price / (1 - 0.30), 2)
```
new:
```python
def _stub_detail(items, config):
    for asin in items:
        items[asin]["discount_off_list_pct"] = 30.0
        price = items[asin].get("price")
        if isinstance(price, (int, float)) and price > 0:
            items[asin]["list_price"] = round(price / (1 - 0.30), 2)
        items[asin]["about"] = ["要点一", "要点二"]
```

3b. monkeypatch 目标改名。old: `    monkeypatch.setattr(asin_pipeline, "_enrich_discount", _stub_discount)` → new: `    monkeypatch.setattr(asin_pipeline, "_enrich_detail", _stub_detail)`

- [ ] **Step 4: 跑回归确认全绿**

Run: `python3 -m pytest -q`
Expected: `56 passed`（原 53 + Task 1 新增 3）。

- [ ] **Step 5: 询问用户是否 commit**

---

### Task 3: `products.html` 新增「关于商品」列

**Files:**
- Modify: `products.html`（CSS + `renderAbout` + thead + renderRow）

**Interfaces:**
- Consumes: Task 2 落地的 `about`（JSON 字符串）。
- Produces: 表格第 17 列「关于商品」，摘要 + hover 全文。

- [ ] **Step 1: 追加 CSS（在 `.search-box:focus ...` 那条之后）**

在 `products.html` 的 `<style>` 块末尾（`.search-box:focus { ... }` 之后、`</style>` 之前）插入：

```css

  /* 关于商品列 */
  .about-cell { max-width:230px; min-width:160px; position:relative; }
  .about-cell .about-summary { margin:0; padding-left:16px; color:#4a5260; font-size:13px; line-height:1.65; }
  .about-cell .about-summary li.more { list-style:none; margin-left:-16px; color:#9aa3ad; }
  .about-cell .about-full { display:none; position:absolute; top:0; left:100%; margin-left:8px; background:#232f3e; color:#fff; padding:10px 12px; border-radius:6px; font-size:12px; line-height:1.6; width:300px; z-index:6; box-shadow:0 4px 14px rgba(0,0,0,.22); }
  .about-cell .about-full ul { margin:0; padding-left:16px; }
  .about-cell:hover .about-full { display:block; }
```

- [ ] **Step 2: 新增 `renderAbout` 函数**

在 `products.html` 的 `function renderRow(p, idx){` 之前插入：

```js
// About this item：摘要前2条 + hover 浮层全文
function renderAbout(p){
  let arr = [];
  try{ arr = typeof p.about==='string' ? JSON.parse(p.about) : (Array.isArray(p.about)?p.about:[]); }catch(e){ arr=[]; }
  if(!arr.length) return '<span class="empty">—</span>';
  const preview = arr.slice(0,2).map(x=>`<li>${safe(x)}</li>`).join('');
  const more = arr.length>2 ? '<li class="more">…</li>' : '';
  const full = arr.map(x=>`<li>${safe(x)}</li>`).join('');
  return `<ul class="about-summary">${preview}${more}</ul><div class="about-full"><ul>${full}</ul></div>`;
}

```

- [ ] **Step 3: 表头加列**

在 `render(products)` 的 `const thead` 中，`<th data-sort="title">标题</th>` 之后插入 `<th>关于商品</th>`：

old:
```js
    <th data-sort="title">标题</th>
    <th>ASIN</th>
```
new:
```js
    <th data-sort="title">标题</th>
    <th>关于商品</th>
    <th>ASIN</th>
```

- [ ] **Step 4: `renderRow` 加单元格（位置与表头对齐：标题单元格之后）**

old:
```js
    <td class="title-cell">
      <a href="${safe(url)}" target="_blank">${safe(title)}</a>
    </td>
    <td>
      <div class="asin-line"><span class="lbl">子ASIN:</span> <b>${fmt(p.asin)}</b></div>
```
new:
```js
    <td class="title-cell">
      <a href="${safe(url)}" target="_blank">${safe(title)}</a>
    </td>
    <td class="about-cell">${renderAbout(p)}</td>
    <td>
      <div class="asin-line"><span class="lbl">子ASIN:</span> <b>${fmt(p.asin)}</b></div>
```

- [ ] **Step 5: JS 语法 + 回归**

Run:
```bash
python3 -c "import re,pathlib; html=pathlib.Path('products.html').read_text(encoding='utf-8'); pathlib.Path('/tmp/ss_check.js').write_text('\n'.join(re.findall(r'<script>(.*?)</script>', html, re.S)), encoding='utf-8')"
node --check /tmp/ss_check.js && echo "JS OK"
python3 -m pytest -q
```
Expected: `JS OK` + `56 passed`。

- [ ] **Step 6: 询问用户是否 commit**

---

### Task 4: 重跑 14 个 ASIN 抓 about + 全量验收

**Files:**
- 运行抓取（重生成 `output/products.json` + `output/products.html`）

**Interfaces:**
- Consumes: Task 1–3 完成的抓取链路 + 展示。

- [ ] **Step 1: 重跑 14 个 ASIN（单行喂入，抓 about）**

Run:
```bash
printf '%s\nq\n' 'B0FTWL9DG6 B0FN3RJ53V B0GZCKSRWP B0GV3JV7BH B0GTKFKFZF B0GLYKR2F8 B0H21BT3DT B0GX9RVPHM B0GVJ9755P B0GQGQ82P6 B0GQBBTTR3 B0DSJYJ2G2 B0F71Z8KCV B0D8VWNB3P' | python3 asin_pipeline.py 2>&1 | tail -30
```
Expected: `competitor-lookup: 14 个 ASIN` → 详情页抓取（14 个，并发 3）→ 摘要表出现「关于商品」列 → 保存到 output。详情页反爬可能致个别 about 为空，属正常 best-effort。

- [ ] **Step 2: 校验 about 落地**

Run:
```bash
python3 -c "
import json, pathlib
rows = json.load(open('output/products.json'))
has = sum(1 for r in rows if r.get('about') and r['about'] not in ('[]',''))
print('共', len(rows), '条 | about 非空:', has)
r = next(x for x in rows if x.get('about') and x['about'] not in ('[]',''))
print('示例 asin:', r['asin'])
print('about:', r['about'][:120])
"
```
Expected: 打印非空 about 的条数 ≥ 1，并显示一个示例的要点文本（JSON 字符串）。

- [ ] **Step 3: 全量回归**

Run: `python3 -m pytest -q`
Expected: `56 passed`。

- [ ] **Step 4: 浏览器最终验收**

双击 `output/products.html`，确认：
- [ ] 「标题」后新增「关于商品」列，显示前 2 条要点 + …
- [ ] hover 该列单元格，右侧浮层显示全部要点
- [ ] 无 about 的商品显示 `—`
- [ ] 排序 / 搜索 / 固定首列仍正常；「关于商品」列不参与排序
- [ ] 其余 16 列数据与之前一致

- [ ] **Step 5: 询问用户是否提交本次全部改动**

---

## Self-Review（已对照 spec 自检）

- **Spec 覆盖**：`split_about_bullets`（Task 1）；`fetch_product_detail` 重命名+about（Task 2 Step1）；`_enrich_detail` 接线+about 落地（Task 2 Step2）；stub 改名（Task 2 Step3）；前端新列+renderAbout+CSS（Task 3）；重跑 14 ASIN（Task 4）。spec 全部要求有对应任务。
- **占位符**：无 TBD/TODO，每步含完整代码或命令。
- **类型一致**：`split_about_bullets`、`fetch_product_detail`、`_enrich_detail`、`_stub_detail`、`renderAbout` 命名在各任务间一致；`about` 在 Python 端为 `list[str]`、JSON 落地为字符串、前端 `JSON.parse`，链路一致。
- **中间状态可测**：Task 2 把所有改名（amazon_search / asin_pipeline / test_pipeline）放同一任务，避免 import 断裂；Task 1 独立，先于改名完成。
