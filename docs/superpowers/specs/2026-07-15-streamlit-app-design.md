# Streamlit Web 版设计

- 日期：2026-07-15
- 状态：已批准，待实现
- 涉及文件：新增 `app.py`、`requirements.txt`（加 streamlit）

## 背景

现有卖家精灵爬虫是 CLI（`asin_pipeline.py`）：终端输入 ASIN → competitor-lookup + 详情页抓取 → `output/products.json` + `products.html`。`products.html` 已是功能丰富的自包含前端（转置 / 隐藏列 / about 浮层 / 拖拽列宽 / 排序 / 搜索 / 固定首列）。

目标：做一个 **Streamlit Web 界面**，复刻 CLI 全流程（输入 → 抓取 → 展示），**本地运行**，明细表**直接嵌入现有 `products.html`**（最大化复用前端，不重做）。

## 目标

1. Web 界面输入 ASIN（多行粘贴），点按钮触发抓取。
2. 复用现有抓取链路（`process_asins` 等），不改 CLI。
3. 抓取后在页面展示：市场总览指标 + 嵌入 `products.html` 明细表。
4. 本地 `streamlit run app.py` 即用。

## 非目标（YAGNI）

- 不做云端部署（playwright / 反爬 / token 鉴权不适合云）。
- 不做异步后台任务（同步 `st.spinner` 等待即可）。
- 不做抓取进度实时回显（避免改 `process_asins` 的 print 流；spinner 够用）。
- 不用 Streamlit 原生组件重做明细表（`st.dataframe` 做不出转置/隐藏列/about，故嵌入现有前端）。
- 不改 CLI 与现有模块逻辑。

## 设计

### 1. 架构

新增 `app.py`（Streamlit 入口），**纯编排层**，复用现有模块：

| 复用 | 用途 |
|---|---|
| `asin_pipeline.load_env` | 读 `.env` 鉴权 |
| `asin_pipeline.process_asins` | 抓取 + 落地 `output/`（competitor-lookup + 详情页折扣/about） |
| `asin_pipeline.parse_asins` | 文本 → 去重 ASIN 列表 |
| `sellersprite_auth.KeepaTokenManager` | token 管理 |
| `config.json` | 站点 / 并发 / 批大小 |

### 2. 界面（`app.py`）

- 标题 + 简短说明。
- `st.text_area("输入 ASIN", ...)`：多行粘贴，逗号 / 空格 / 换行分隔。
- `st.button("开始抓取")`：点击触发。
- 点击逻辑：
  1. `load_env()`
  2. `config = json.load(config.json)`；`tm = KeepaTokenManager(.token_cache.json)`
  3. `asins = parse_asins(text)`
  4. `with st.spinner("抓取中…约 1-2 分钟"):` → `result = process_asins(asins, config, tm)`
  5. 失败（`AuthExpiredError` / 其它）→ `st.error` 提示检查 `.env`。
- 展示（成功后）：
  - 读 `output/market_overview.json` → `st.metric` 网格：均价 / 均评分 / 总销量 / 总销售额 / Top10 集中度。
  - 读 `output/products.html` 文本 → `streamlit.components.v1.html(html, height=850, scrolling=True)` 嵌入明细表。

### 3. 数据流

```
st.text_area → parse_asins → process_asins(写 output/)
   → 读 output/market_overview.json → st.metric
   → 读 output/products.html        → st.components.v1.html 嵌入
```

### 4. 嵌入与 localStorage 限制

`st.components.v1.html` 用 iframe（srcdoc）渲染。内联数据模式（`/*__DATA__*/` 注入）不依赖 `fetch`，iframe 内能正常渲染表格。但 **iframe 沙箱可能使 `localStorage` 不持久**——拖拽列宽 / 隐藏列的记忆**刷新后丢失**（当次有效）。所有 `localStorage` 调用已有 `try/catch`，不会报错崩页。转置 / 隐藏 / 排序 / 搜索等**当次操作全部正常**。

## 需要提供 / 准备

- **`.env` 鉴权**（`KEEPA_AUTH_FP` / `KEEPA_RANDOM_TOKEN` / `KEEPA_LOGIN_USERNAME` / `KEEPA_LOGIN_PASSWORD`）—— 已有，复用。
- `pip install streamlit`（playwright、pytest 已装）。
- 首次运行：`.token_cache.json` 会自动生成。

## 运行

```
streamlit run app.py
```
浏览器自动打开，输入 ASIN → 抓取 → 看结果。

## 测试策略

- `app.py` 是 UI 编排层，难单测；其依赖的 `process_asins` / `parse_asins` / `render_html` 等已有测试覆盖。
- 可加一个轻量单测：`app.py` 内若抽出纯函数（如「读 market_overview.json → 指标 dict」），则单测之；否则仅手动验收。
- 验收清单：输入 ASIN → 抓取成功 → 市场总览指标显示 → 嵌入表格可转置/隐藏列/排序/搜索；鉴权失败时 `st.error` 提示。

## 实现要点 / 边界

- `process_asins` 内部 `print` 到 stdout，Streamlit 页面不显示——用 `st.spinner` 文案告知「抓取中」即可，不必接管 print。
- `process_asins` 每次清空 `output/` 重写；Streamlit 多次抓取自然覆盖（始终最新）。
- 嵌入高度 `height=850` + `scrolling=True`，保证宽表横向、长表纵向可滚。
- `app.py` 放项目根；`streamlit run app.py` 的工作目录即项目根，相对路径（`config.json` / `output/` / `.env`）有效。
