# products.html 观感优化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留亚马逊品牌色的前提下精修 `products.html` 观感，并加入表头排序、顶部搜索、固定首列三项轻量交互，最后用现有 14 条数据重新渲染 `output/products.html`。

**Architecture:** 全部改动落在单文件 `products.html`（`<style>` + 内联 `<script>`），原生 JS 操作 `DATA.products` 过滤/排序后重渲染 tbody；不引入任何前端库；`html_render.py` 的 `/*__DATA__*/{}/*__END__*/` 注入机制与 Python 端逻辑零改动。

**Tech Stack:** HTML / CSS / 原生 JavaScript（零依赖）；Python `html_render.render_html` 仅用于重新生成输出文件。

## Global Constraints

- 不改 `html_render.py`，注入标记 `/*__DATA__*/{}/*__END__*/` 保持不变。
- 不引入任何前端库（必须维持 `file://` 双击自包含）。
- 保留亚马逊品牌色：表头深蓝 `#232f3e`、强调橙 `#ff9900`（收敛到大面积之外的关键处）。
- **不自动 `git commit`**：每个任务完成后向用户确认是否提交（遵循用户工作习惯）。
- 现有回归测试 `tests/test_pipeline.py` 必须全程保持 `passed`。

## 测试策略（前端无 JS 测试框架）

- **回归**：每个任务结束跑 `python3 -m pytest -q`，确保 HTML 结构断言（`'"asin": "B0F1QHNFJP"'`、`'"sample_size": 2'`）与注入机制不破。
- **手动验证**：用 `output/products.html`（或临时渲染一份）在浏览器双击打开，按各任务的验证清单逐项确认。
- 渲染临时预览命令（不重新抓取，仅用现有 `output/products.json` + `market_overview.json`）：

```bash
python3 -c "
import json, pathlib
from html_render import render_html
root = pathlib.Path('.')
rows = json.loads((root/'output/products.json').read_text(encoding='utf-8'))
ov = json.loads((root/'output/market_overview.json').read_text(encoding='utf-8'))
render_html(rows, ov, root/'products.html', root/'output/products.html')
print('已渲染 output/products.html')
"
```

---

### Task 1: CSS 视觉精修 + 固定首列

**Files:**
- Modify: `products.html` 的 `<style>` 块（第 7–85 行）

**Interfaces:**
- Produces: 柔和配色 / 放大字号 / 加大留白 / 圆角阴影 / 去斑马纹 / 固定首列的样式基础，供后续交互任务复用（表头可点击、排序指示符依赖 `.th-sort` 类）。

- [ ] **Step 1: 替换 `<style>` 块**

将 `products.html` 第 8–84 行（`* { box-sizing... }` 到 `.empty { color:#bbb; }` 之间）整段替换为下面的样式（保留 `<style>` 与 `</style>` 标签本身）。改动要点：背景柔和、字号 13→14、padding/行高加大、去斑马纹、圆角+阴影、overview 米色化、hover 淡蓝、首列 sticky。

```css
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f7fa; color:#23272e; font-size:14px; line-height:1.6; }
  header { background:#232f3e; color:#fff; padding:14px 22px; display:flex; align-items:center; gap:14px; box-shadow:0 2px 10px rgba(0,0,0,.12); position:relative; z-index:5; }
  header h1 { font-size:17px; margin:0; font-weight:600; letter-spacing:.5px; }
  header .meta { font-size:12px; opacity:.75; }
  .dropzone { margin:18px 22px; padding:26px; border:2px dashed #c7d0d8; border-radius:12px; background:#fff; text-align:center; color:#6b7480; cursor:pointer; }
  .dropzone.dragover { border-color:#ff9900; background:#fff7e6; }
  #fileInput { display:none; }
  .overview { margin:0 22px 12px; padding:12px 16px; background:#fef9f0; border:1px solid #f5e6c8; border-radius:10px; font-size:13px; color:#8a6d3b; line-height:1.9; }
  .overview b { color:#b15a00; }
  .toolbar { margin:0 22px 12px; display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
  .toolbar .count { color:#6b7480; font-size:13px; }
  .toggle { color:#007185; cursor:pointer; font-size:13px; }

  .table-wrap { margin:0 22px 44px; background:#fff; border:1px solid #e5e7eb; border-radius:12px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .scroll { overflow:auto; max-height:none; }
  table.products { width:100%; border-collapse:separate; border-spacing:0; font-size:14px; min-width:1700px; }
  table.products th, table.products td { padding:12px 14px; border-bottom:1px solid #f0f1f3; vertical-align:top; text-align:left; }
  table.products thead th { position:sticky; top:0; background:#232f3e; color:#fff; font-weight:500; font-size:13px; z-index:2; box-shadow:0 1px 0 rgba(0,0,0,.15); white-space:nowrap; }
  table.products thead th:first-child { position:sticky; left:0; z-index:4; }
  table.products tbody tr:hover td { background:#f0f7ff; }
  /* 固定首列：主图横向滚动时不消失；hover 同步高亮 */
  table.products tbody td:first-child { position:sticky; left:0; background:#fff; z-index:1; box-shadow:4px 0 6px -4px rgba(0,0,0,.18); }
  table.products tbody tr:hover td:first-child { background:#f0f7ff; }

  .img-cell img { width:92px; height:92px; object-fit:contain; background:#fafafa; border:1px solid #eceef1; border-radius:8px; display:block; }
  .title-cell { max-width:260px; min-width:200px; }
  .title-cell a { color:#0a7ea4; text-decoration:none; font-weight:500; line-height:1.45; display:block; }
  .title-cell a:hover { color:#c45500; text-decoration:underline; }
  .asin-line { color:#5b6470; font-size:13px; margin-top:4px; }
  .asin-line b { color:#1c2230; }
  .parent-line { color:#9aa3ad; font-size:12px; margin-top:2px; }

  .brand-link { color:#0a7ea4; text-decoration:none; }
  .brand-link:hover { text-decoration:underline; color:#c45500; }

  .stars { color:#ffa41c; font-size:15px; letter-spacing:-1px; }
  .rating-meta { color:#6b7480; font-size:13px; margin-top:2px; }

  .date-line { color:#1c2230; }
  .days-line { color:#9aa3ad; font-size:12px; margin-top:2px; }

  .dim-block { font-size:13px; line-height:1.75; color:#4a5260; }
  .dim-block .lbl { color:#9aa3ad; }

  .cat-path { font-size:13px; color:#5b6470; line-height:1.55; max-width:220px; word-break:break-word; }

  .bsr-block { font-size:13px; line-height:1.8; }
  .bsr-row { display:flex; justify-content:space-between; gap:8px; }
  .bsr-row .lbl { color:#5b6470; }
  .bsr-row .rk { color:#c0392b; font-weight:600; white-space:nowrap; }
  .bsr-row.main { font-weight:600; }
  .bsr-row.sub { color:#4a5260; padding-left:8px; }

  .seller-block { font-size:13px; line-height:1.7; }
  .seller-block .name { color:#1c2230; font-weight:500; }
  .seller-block .nat { color:#9aa3ad; }

  .sales-cell { font-size:13px; line-height:1.7; }
  .sales-cell .parent-u { color:#0a7ea4; font-weight:600; }
  .sales-cell .child-u { color:#4a5260; }
  .sales-cell .lbl { color:#9aa3ad; }
  .sales-cell .sub { color:#1a8a3c; font-size:12px; margin-top:1px; }
  .sales-cell .sub.neg { color:#c0392b; }

  .trend-cell { min-width:220px; }
  .spark { display:flex; gap:5px; align-items:flex-end; height:90px; padding-top:18px; border-bottom:1px solid #e5e7ea; position:relative; }
  .spark .bar { flex:1; min-width:14px; background:linear-gradient(180deg,#ff9900 0%,#ffb84d 100%); border-radius:3px 3px 0 0; position:relative; cursor:pointer; transition:filter .15s; }
  .spark .bar.zero { background:#e8eaed; }
  .spark .bar:hover { filter:brightness(1.12); box-shadow:0 0 0 2px #c45500 inset; }
  .spark .bar .val { position:absolute; top:-15px; left:50%; transform:translateX(-50%); font-size:10px; color:#4a5260; white-space:nowrap; font-weight:500; }
  .spark .bar .tip { position:absolute; bottom:100%; left:50%; transform:translateX(-50%); background:#232f3e; color:#fff; padding:4px 8px; border-radius:4px; font-size:11px; white-space:nowrap; opacity:0; pointer-events:none; margin-bottom:6px; z-index:5; }
  .spark .bar:hover .tip { opacity:1; }
  .spark .axis { display:flex; gap:5px; margin-top:4px; }
  .spark .axis span { flex:1; text-align:center; font-size:10px; color:#9aa3ad; }
  .spark-summary { font-size:12px; color:#6b7480; margin-top:6px; line-height:1.4; }
  .spark-summary b { color:#1a8a3c; }

  .empty { color:#c8ccd2; }

  /* 排序指示符（Task 2 用） */
  table.products thead th[data-sort] { cursor:pointer; user-select:none; }
  table.products thead th[data-sort]:hover { background:#2a3a52; }
  table.products thead th.sort-asc::after { content:" ▲"; font-size:10px; color:#ff9900; }
  table.products thead th.sort-desc::after { content:" ▼"; font-size:10px; color:#ff9900; }

  /* 搜索框（Task 3 用） */
  .search-box { flex:0 1 280px; padding:7px 12px; border:1px solid #d3d9df; border-radius:8px; font-size:13px; outline:none; transition:border-color .15s, box-shadow .15s; }
  .search-box:focus { border-color:#ff9900; box-shadow:0 0 0 3px rgba(255,153,0,.15); }
```

- [ ] **Step 2: 跑回归测试**

Run: `python3 -m pytest -q`
Expected: `53 passed`（CSS 改动不影响数据注入与结构断言）。

- [ ] **Step 3: 浏览器手动验证清单**

用"测试策略"中的渲染命令生成最新 `output/products.html`，双击打开，确认：
- [ ] 背景更柔和（`#f5f7fa`），字号略大、行间距更透气
- [ ] 表格容器有圆角 + 轻阴影，overview 条为柔和米色（不再刺眼）
- [ ] 无斑马纹，hover 行呈淡蓝 `#f0f7ff`
- [ ] **横向滚动时，首列「主图」固定在左侧不随滚动消失**（左缘有淡阴影分隔）

- [ ] **Step 4: 询问用户是否 commit**（默认不自动提交）

---

### Task 2: 表头点击排序

**Files:**
- Modify: `products.html` 的 `<script>`（render 组装 thead 处约第 299–316 行、show/render 入口约第 292–335 行）

**Interfaces:**
- Consumes: Task 1 的 `th[data-sort]` / `.sort-asc` / `.sort-desc` 样式。
- Produces: 模块内排序状态 `sortKey` / `sortDir`，`rerender()` 入口，供 Task 3 搜索复用。

- [ ] **Step 1: 给可排序列的 `<th>` 加 `data-sort`**

定位 `render(products)` 内 `const thead = ...`（约第 299 行），将 `<tr>` 内的表头替换为下面这版（数值/文本列带 `data-sort`）：

```js
  const thead = `<thead><tr>
    <th style="min-width:104px">主图</th>
    <th data-sort="title">标题</th>
    <th>ASIN</th>
    <th data-sort="brand">品牌</th>
    <th>徽章</th>
    <th data-sort="price">价格</th>
    <th data-sort="rating">评分</th>
    <th data-sort="available_date">上架时间</th>
    <th>尺寸/重量</th>
    <th data-sort="variations">变体数</th>
    <th>类目路径</th>
    <th data-sort="bsr">BSR排名</th>
    <th>卖家</th>
    <th data-sort="units">销量</th>
    <th data-sort="amount">销售额</th>
    <th>销量趋势</th>
  </tr></thead>`;
```

- [ ] **Step 2: 新增排序状态与辅助函数**

在 `<script>` 内、`function render(products){` 之前插入：

```js
// 视图状态：原始数据 + 排序/搜索
let ALL = [];
let sortKey = null;   // 当前排序列 key（null = 不排序）
let sortDir = 1;      // 1 升序 / -1 降序
let query = '';       // 搜索关键字

function toNum(v){ const n = parseFloat(v); return isNaN(n) ? null : n; }

// 取某列用于排序的值（数值列返回 number，文本列返回小写串，空统一为 null）
function sortValue(p, key){
  if(key === 'bsr') return toNum(p.bsr_list__main_rank);
  if(key === 'title' || key === 'brand' || key === 'available_date'){
    const s = p[key]; return (s===undefined||s===null||s==='') ? null : String(s).toLowerCase();
  }
  return toNum(p[key]); // price / units / rating / variations / amount
}

// 依据 query + sortKey/sortDir 计算当前应展示的行（不修改 ALL）
function visibleProducts(){
  let rows = ALL.filter(p => p && (p.asin || p.title));
  if(query){
    const q = query.toLowerCase();
    rows = rows.filter(p => [p.title, p.asin, p.parent, p.brand, p.seller_name]
      .some(v => v && String(v).toLowerCase().includes(q)));
  }
  if(sortKey){
    rows = [...rows].sort((a, b) => {
      const av = sortValue(a, sortKey), bv = sortValue(b, sortKey);
      const aE = av===null, bE = bv===null;   // 空值沉底
      if(aE && bE) return 0;
      if(aE) return 1;
      if(bE) return -1;
      if(av === bv) return 0;
      return (av < bv ? -1 : 1) * sortDir;
    });
  }
  return rows;
}

// 切换排序：点同列升→降→取消；点新列默认升序
function toggleSort(key){
  if(sortKey === key){
    if(sortDir === 1) sortDir = -1;
    else { sortKey = null; sortDir = 1; }
  } else { sortKey = key; sortDir = 1; }
  rerender();
}

// 刷新表头排序指示符
function updateSortIndicators(){
  container.querySelectorAll('th[data-sort]').forEach(th => {
    const on = th.dataset.sort === sortKey;
    th.classList.toggle('sort-asc',  on && sortDir ===  1);
    th.classList.toggle('sort-desc', on && sortDir === -1);
  });
}

// 计数文案：搜索时显示「命中 X / 共 Y」
function updateCount(visible){
  const total = ALL.length;
  countText.textContent = query ? `命中 ${visible} / 共 ${total} 个商品` : `共 ${total} 个商品`;
}

// 统一重渲染入口
function rerender(){
  const rows = visibleProducts();
  render(rows);
  updateSortIndicators();
  updateCount(rows.length);
}
```

- [ ] **Step 3: 接入排序（表头事件委托 + show 改用 rerender）**

把现有的 `function show(d){ ... }`（约第 331–335 行）替换为：

```js
function show(d){
  const {products, overview} = normalize(d);
  ALL = products;            // 保存原始全集
  renderOverview(overview);
  rerender();                // 走过滤/排序统一入口
}
```

在脚本末尾、`const DATA = ...` 之前，给 `container` 挂一次性表头点击委托（container 引用稳定，重渲染不丢）：

```js
container.addEventListener('click', e => {
  const th = e.target.closest('th[data-sort]');
  if(th) toggleSort(th.dataset.sort);
});
```

- [ ] **Step 4: 跑回归测试**

Run: `python3 -m pytest -q`
Expected: `53 passed`。

- [ ] **Step 5: 浏览器手动验证清单**

渲染并打开 `output/products.html`，确认：
- [ ] 点「价格」表头：升序（低→高），表头出现橙色 ▲
- [ ] 再点：降序，变 ▼
- [ ] 再点：取消排序，箭头消失，恢复原顺序
- [ ] 点「BSR排名」按数值升序（数字小的在前，空值沉底）
- [ ] 点「标题」按文本 A→Z
- [ ] 切换不同列时，只有当前列显示箭头

- [ ] **Step 6: 询问用户是否 commit**

---

### Task 3: 顶部搜索框

**Files:**
- Modify: `products.html` 的 toolbar HTML（约第 102–105 行）+ `<script>`（新增 input 监听）

**Interfaces:**
- Consumes: Task 2 的 `query` / `rerender()` / `updateCount()`。
- Produces: 搜索过滤可见行，计数实时更新。

- [ ] **Step 1: 在 toolbar 加搜索框**

定位 `<div class="toolbar" id="toolbar" style="display:none">`（约第 102 行），替换为：

```html
<div class="toolbar" id="toolbar" style="display:none">
  <span class="count" id="countText"></span>
  <input class="search-box" id="searchBox" type="search" placeholder="搜索 标题 / ASIN / 品牌 / 卖家" autocomplete="off">
  <span class="toggle" onclick="resetLoader()">重新加载</span>
</div>
```

- [ ] **Step 2: 绑定搜索输入**

在 Task 2 Step 3 的 `container.addEventListener(...)` 之后，追加：

```js
document.getElementById('searchBox').addEventListener('input', e => {
  query = e.target.value.trim();
  rerender();
});
```

- [ ] **Step 3: 跑回归测试**

Run: `python3 -m pytest -q`
Expected: `53 passed`。

- [ ] **Step 4: 浏览器手动验证清单**

渲染并打开 `output/products.html`，确认：
- [ ] toolbar 出现搜索框，聚焦时橙色边框光晕
- [ ] 输入 `magnesium`：列表实时过滤为标题/ASIN/品牌/卖家含该词的行，计数变为「命中 X / 共 14」
- [ ] 清空搜索框：恢复全部 14 行，计数回「共 14 个商品」
- [ ] 搜索 + 排序可叠加（先搜再点表头排序，结果正确）

- [ ] **Step 5: 询问用户是否 commit**

---

### Task 4: 重新渲染 output + 全量回归验收

**Files:**
- 运行渲染命令生成 `output/products.html`（不改源码）

**Interfaces:**
- Consumes: Task 1–3 完成后的 `products.html` 模板 + 现有 `output/products.json` / `market_overview.json`（14 条数据）。

- [ ] **Step 1: 用 14 条数据重新渲染输出**

Run（不重新抓取，仅复用现有 JSON）：

```bash
python3 -c "
import json, pathlib
from html_render import render_html
root = pathlib.Path('.')
rows = json.loads((root/'output/products.json').read_text(encoding='utf-8'))
ov = json.loads((root/'output/market_overview.json').read_text(encoding='utf-8'))
out = render_html(rows, ov, root/'products.html', root/'output/products.html')
print('已渲染:', out)
"
```
Expected: 打印 `已渲染: output/products.html`。

- [ ] **Step 2: 全量回归测试**

Run: `python3 -m pytest -q`
Expected: `53 passed`。

- [ ] **Step 3: 最终浏览器验收**

双击 `output/products.html`，整体确认：
- [ ] 14 条商品全部展示，视觉舒适（柔和、透气、有层次）
- [ ] 排序 / 搜索 / 固定首列三项交互均正常
- [ ] overview 市场总览条数据正确（均价 26.45 / 均评分 4.16 / 总销 26130 / 总销售额 763492.18 / Top10 集中度 0.9504）

- [ ] **Step 4: 询问用户是否提交本次全部改动**

---

## Self-Review（已对照 spec 自检）

- **Spec 覆盖**：视觉精修各项（背景/表头/字号/padding/边框/去斑马纹/圆角阴影/overview/hover）→ Task 1；排序（数值+文本列、升降取消、指示符、空值沉底）→ Task 2；搜索（标题/ASIN/父ASIN/品牌/卖家、命中计数）→ Task 3；固定首列 → Task 1；重新渲染 output → Task 4。spec 全部要求有对应任务。
- **占位符**：无 TBD/TODO，每步含完整代码或命令。
- **类型一致**：`sortKey`/`sortDir`/`query`/`ALL`/`rerender`/`visibleProducts`/`toggleSort`/`updateCount` 在 Task 2 定义、Task 3 复用，命名一致；`data-sort` 值与 `sortValue` 的 key 分支一致（`bsr`/`title`/`brand`/`available_date` 与数值列）。
- **边界**：空值沉底、sticky 首列不透明背景（`background:#fff` + hover 同步）、容器事件委托（重渲染不丢监听）均已在代码中处理。
