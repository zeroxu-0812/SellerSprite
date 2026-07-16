# 下载 HTML + 亚马逊风格重做设计

- 日期：2026-07-15
- 状态：已批准，待实现
- 涉及文件：新增 `.streamlit/config.toml`；改 `app.py`

## 背景

Streamlit 版（`app.py`）已跑通：输入 ASIN → 抓取 → 市场总览指标卡 + 嵌入 `products.html`。当前 Streamlit 外壳是默认白底观感，与已具亚马逊风的嵌入表格不协调；且无导出入口，用户想直接下载当次查询结果。

## 目标

1. 抓取成功后提供「下载 HTML」按钮，导出当前嵌入的那份自包含 `products.html`。
2. 把 Streamlit 页面外壳（顶栏 / 按钮 / 卡片 / 配色 / 字体）重做为忠实亚马逊风，功能不变。

## 非目标（YAGNI）

- 不改 `products.html` 模板与嵌入表格样式（已是亚马逊风，避免动到能用的前端）。
- 下载文件名不加时间戳 / 分类前缀（保持 `products.html`）。
- 不改嵌入表格位置、不新增列 / 字段。
- 不做云端部署。

## 设计

### 1. 下载 HTML 按钮

抓取成功、指标卡渲染之后，放一个 Streamlit 原生下载按钮：

```python
html = (out_dir / "products.html").read_text(encoding="utf-8")
st.download_button(
    label="⬇ 下载 HTML",
    data=html,
    file_name="products.html",
    mime="text/html",
)
```

- `data` = 当前 `output/products.html` 文本（数据已内联的自包含版）。
- 双击下载文件即可离线打开，转置 / 隐藏列 / 排序 / 搜索全保留（与页面内嵌入的同一份）。
- 位置：成功提示之后、指标卡之前（`st.success` → `st.download_button` → `st.metric` 卡片）。抓取成功才出现。

### 2. 亚马逊风格（忠实）

**配色（亚马逊真值）：**
- 顶栏 / 文字主色：海军蓝 `#131921`
- 强调色：橙 `#FF9900`
- 主按钮：黄 `#FFD814`（hover `#F7CA00`），深色字 `#0F1111`
- 页面底色：浅灰 `#EAEDED`
- 卡片底：白 `#ffffff`
- 字体：Amazon Ember → `sans-serif` 回退（系统无 Ember）

**实现 = 主题 + CSS 注入，两处：**

#### a. 新增 `.streamlit/config.toml`（Streamlit 主题）

```toml
[theme]
base = "light"
primaryColor = "#FF9900"
backgroundColor = "#EAEDED"
secondaryBackgroundColor = "#ffffff"
textColor = "#131921"
font = "sans serif"
```

`primaryColor` 设橙，作用于链接 / 复选框 / 进度条等强调态。

#### b. `app.py` 注入 CSS（`st.markdown(..., unsafe_allow_html=True)`）

定义模块级常量 `AMAZON_CSS`（一段 CSS 字符串），在 `render_app()` 开头 `st.markdown(f"<style>{AMAZON_CSS}</style>", unsafe_allow_html=True)` 注入。覆盖：

1. **顶部标题栏**：用自定义 HTML 块替换原 `st.title`——一个 `.az-header` `<div>`，海军蓝 `#131921` 全宽背景、白字标题 + 橙色 `#FF9900` 下边框强调、内边距。
2. **主按钮「开始抓取」**：`st.button(..., type="primary")` 仍用 Streamlit 原生按钮，CSS 覆盖其背景为黄 `#FFD814`、字色 `#0F1111`、圆角 `8px`、hover `#F7CA00`（选择器 `[data-testid="stBaseButton-primary"] button`）。
3. **下载按钮**：次要样式 `st.download_button`（默认 secondary），CSS 给白底 + 橙 `#FF9900` 描边、hover 浅橙。
4. **`st.metric` 卡片**：`[data-testid="stMetric"]` 白底、圆角 `8px`、`box-shadow` 柔和阴影、内边距，呈现「白卡」感。
5. **全局字体**：`font-family: "Amazon Ember", Helvetica, Arial, sans-serif;`。

### 3. 数据流

```
render_app():
  st.markdown(<style>AMAZON_CSS</style>)     # 注入亚马逊 CSS（每次重渲染）
  <div.az-header> 卖家精灵 ASIN 爬虫 </div>    # 自定义顶栏（替换 st.title）
  st.text_area / st.button(primary)          # 黄主按钮
  ── 点击抓取 ──
  process_asins(...) → output/products.html + market_overview.json
  st.download_button("⬇ 下载 HTML", data=products.html 全文)
  st.metric 卡片 ×5（白卡 + 阴影）
  st.components.v1.html(products.html, height=850, scrolling=True)
```

### 4. 配置加载说明

`.streamlit/config.toml` 在 `streamlit run` 启动时由 Streamlit 自动读取（工作目录即项目根，`app.py` 在根）。改主题需重启 streamlit 才生效；CSS 注入随脚本运行即时生效。

## 测试策略

- 下载按钮 / CSS / 顶栏均为 UI，难单测；现有 `tests/test_app.py`（`build_metrics` 2 条）保持不变、继续通过。
- 验收（手动）：`streamlit run app.py` → 抓一批 ASIN → 看顶栏海军蓝、主按钮黄、指标卡白底阴影；点「⬇ 下载 HTML」得到 `products.html`，双击离线打开，转置 / 隐藏列可用。

## 实现要点 / 边界

- `AMAZON_CSS` 作为 `app.py` 模块级常量，避免在 `render_app()` 内拼大字符串。
- CSS 选择器基于 Streamlit 当前 data-testid（`stBaseButton-primary`、`stMetric`）；Streamlit 升级若改 testid 可能需跟进（当前 1.59.2 有效）。
- `config.toml` 的主题改动**需重启 streamlit**（不是热重载），实现后要重启验证，不只是 Rerun。
- 不读取 / 不日志 `.env`；下载内容仅为 `output/products.html`，不含鉴权信息。
