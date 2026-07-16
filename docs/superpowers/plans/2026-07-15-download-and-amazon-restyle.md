# 下载 HTML + 亚马逊风格重做实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Streamlit 版（`app.py`）加「下载 HTML」按钮，并把页面外壳重做为忠实亚马逊风（海军蓝顶栏 / 黄主按钮 / 白卡阴影），功能不变。

**Architecture:** 主题走新增 `.streamlit/config.toml`（底色 / 强调色 / 字体），细节走 `app.py` 模块级 `AMAZON_CSS` 常量经 `st.markdown` 注入（顶栏 / 按钮 / 卡片）。下载用 Streamlit 原生 `st.download_button`，导出当前自包含 `products.html`。不动 `products.html` 模板。

**Tech Stack:** Streamlit 1.59.2、CSS 注入（`unsafe_allow_html`）、config.toml 主题、pytest。

## Global Constraints

- **不自动提交**（用户惯例「保持现状不提交」）：执行时跳过所有 `git commit` 步骤，改动留工作区，收尾由 finishing-a-development-branch 呈现选项。
- **不改 `products.html` 模板**与嵌入表格样式（YAGNI）。
- 下载文件名固定 `products.html`，不加时间戳 / 分类前缀。
- 配色取亚马逊真值：顶栏 / 文字 `#131921`、强调 `#FF9900`、主按钮 `#FFD814`（hover `#F7CA00`）、底 `#EAEDED`、卡 `#ffffff`、字 `#0F1111`。
- CSS 选择器基于 Streamlit 1.59.2 的 `button[kind="primary"]` / `button[kind="secondary"]` / `[data-testid="stMetric"]`。
- `.streamlit/config.toml` 主题改动**需重启 streamlit**（非热重载）；CSS 注入随脚本运行即时生效。
- 文案 / 注释中文，与现有代码风格一致。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `app.py` | 新增模块级常量 `AMAZON_CSS`；`render_app()` 注入 CSS + 自定义顶栏 + 下载按钮 | 改 |
| `.streamlit/config.toml` | Streamlit 主题（底色 / 强调色 / 字体 / 文字色） | 新增 |
| `tests/test_app.py` | 追加 `AMAZON_CSS` 调色板回归测试 | 改 |

`products.html` 模板、`asin_pipeline.py` 等一律只读不动。

---

## Task 1: AMAZON_CSS 常量 + config.toml（TDD 调色板）

**Files:**
- Modify: `app.py`（在 `build_metrics` 之后、`render_app` 之前插入模块级常量 `AMAZON_CSS`）
- Create: `.streamlit/config.toml`
- Modify: `tests/test_app.py`（追加调色板测试）

**Interfaces:**
- Consumes: 无（纯 CSS 字符串常量）
- Produces: `app.AMAZON_CSS: str`——Task 2 的 `render_app()` 用 `st.markdown(f"<style>{AMAZON_CSS}</style>", unsafe_allow_html=True)` 注入。

- [ ] **Step 1: 追加失败测试**

在 `tests/test_app.py` 末尾追加：

```python
def test_amazon_css_pins_palette():
    """AMAZON_CSS 必须含亚马逊关键配色，防回归（误删颜色会被此测试挡住）。"""
    css = app.AMAZON_CSS
    for token in ["#131921", "#FF9900", "#FFD814", "#EAEDED"]:
        assert token in css, f"AMAZON_CSS 缺少配色 {token}"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_app.py::test_amazon_css_pins_palette -v`
Expected: FAIL，`AttributeError: module 'app' has no attribute 'AMAZON_CSS'`。

- [ ] **Step 3: 在 app.py 插入 AMAZON_CSS 常量**

在 `app.py` 的 `build_metrics` 函数（以 `    ]` 结尾）之后、`def render_app():` 之前，插入：

```python
AMAZON_CSS = """
/* 亚马逊忠实风格：海军蓝顶栏 + 浅灰底 + 白卡阴影 + 黄主按钮 */
body{ font-family:"Amazon Ember","Amazon Ember Display",Helvetica,Arial,sans-serif; }

/* 自定义顶部海军蓝标题栏（替换 st.title） */
.az-header{
  background:#131921;
  color:#ffffff;
  padding:14px 20px;
  border-bottom:3px solid #FF9900;
  border-radius:8px;
  margin-bottom:18px;
  font-size:22px;
  font-weight:700;
}
.az-header .az-sub{
  font-size:12px;
  font-weight:400;
  color:#cccccc;
  margin-top:4px;
}

/* 主按钮「开始抓取」→ 亚马逊黄 #FFD814 */
button[kind="primary"]{
  background-color:#FFD814 !important;
  border:1px solid #FCD200 !important;
  color:#0F1111 !important;
  border-radius:8px !important;
  font-weight:600 !important;
}
button[kind="primary"]:hover{
  background-color:#F7CA00 !important;
  border-color:#F2C200 !important;
}

/* 下载按钮（次要 secondary）→ 白底橙描边 */
button[kind="secondary"]{
  background-color:#ffffff !important;
  border:1px solid #FF9900 !important;
  color:#131921 !important;
  border-radius:8px !important;
}
button[kind="secondary"]:hover{
  background-color:#FFF3E0 !important;
  border-color:#E47911 !important;
}

/* 指标卡：白底圆角阴影 */
[data-testid="stMetric"]{
  background:#ffffff;
  border:1px solid #D5D9D9;
  border-radius:8px;
  padding:14px 16px;
  box-shadow:0 1px 2px rgba(15,17,17,.08);
}
[data-testid="stMetric"] label{ color:#565959 !important; }
[data-testid="stMetric"] [data-testid="stMetricValue"]{ color:#131921 !important; }
"""
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: 3 passed（原 2 + 新增 1）。

- [ ] **Step 5: 创建 .streamlit/config.toml**

新建 `.streamlit/config.toml`：

```toml
[theme]
base = "light"
primaryColor = "#FF9900"
backgroundColor = "#EAEDED"
secondaryBackgroundColor = "#ffffff"
textColor = "#131921"
font = "sans serif"
```

- [ ] **Step 6: 跳过提交（按全局约束）**

改动留工作区，不执行 `git commit`。

---

## Task 2: render_app 接入 CSS + 海军蓝顶栏 + 下载按钮

**Files:**
- Modify: `app.py` 的 `render_app()`（注入 CSS、自定义顶栏替换 `st.title`、加 `st.download_button`、html 读一次复用）

**Interfaces:**
- Consumes: Task 1 的 `AMAZON_CSS`；`asin_pipeline` 的 `process_asins` / `parse_asins` / `load_env` / `ROOT` / `CONFIG_PATH`；`ROOT / "output" / "products.html"` 与 `market_overview.json`。
- Produces: 亚马逊风格的 `streamlit run app.py` 页面 + 下载按钮。

- [ ] **Step 1: 注入 CSS + 自定义顶栏（替换 st.title/st.caption）**

在 `render_app()` 内，把开头的：

```python
    st.set_page_config(page_title="卖家精灵 ASIN 爬虫", page_icon="🛒", layout="wide")
    st.title("🛒 卖家精灵 ASIN 爬虫")
    st.caption("输入 ASIN → competitor-lookup + 详情页（折扣 / About）→ 市场总览 + 明细表。本地运行。")
```

替换为：

```python
    st.set_page_config(page_title="卖家精灵 ASIN 爬虫", page_icon="🛒", layout="wide")
    st.markdown(f"<style>{AMAZON_CSS}</style>", unsafe_allow_html=True)
    st.markdown(
        '<div class="az-header">🛒 卖家精灵 ASIN 爬虫'
        '<div class="az-sub">输入 ASIN → competitor-lookup + 详情页（折扣 / About）→ 市场总览 + 明细表。本地运行。</div>'
        "</div>",
        unsafe_allow_html=True,
    )
```

> 说明：CSS 在每次脚本运行时注入（含 iframe 内 SessionState 重渲染）；`AMAZON_CSS` 由 Task 1 提供为模块级常量。

- [ ] **Step 2: 加下载按钮 + html 读一次复用**

在 `render_app()` 内，把成功后的渲染块：

```python
        st.success(f"✅ 完成：{result['products']} 个商品")

        out_dir = ROOT / "output"
        overview = json.loads((out_dir / "market_overview.json").read_text(encoding="utf-8"))
        metrics = build_metrics(overview)
        cols = st.columns(len(metrics))
        for col, m in zip(cols, metrics):
            col.metric(m["label"], m["value"])

        html = (out_dir / "products.html").read_text(encoding="utf-8")
        st.components.v1.html(html, height=850, scrolling=True)
```

替换为（成功提示 → 下载按钮 → 指标卡 → 嵌入，html 只读一次）：

```python
        st.success(f"✅ 完成：{result['products']} 个商品")

        out_dir = ROOT / "output"
        overview = json.loads((out_dir / "market_overview.json").read_text(encoding="utf-8"))
        html = (out_dir / "products.html").read_text(encoding="utf-8")

        st.download_button("⬇ 下载 HTML", data=html, file_name="products.html", mime="text/html")

        metrics = build_metrics(overview)
        cols = st.columns(len(metrics))
        for col, m in zip(cols, metrics):
            col.metric(m["label"], m["value"])

        st.components.v1.html(html, height=850, scrolling=True)
```

- [ ] **Step 3: 确认 app.py 语法 / import 无误**

Run: `python3 -c "import app; print('render_app:', hasattr(app,'render_app'), '| AMAZON_CSS:', 'AMAZON_CSS' in dir(app))"`
Expected: 输出 `render_app: True | AMAZON_CSS: True`，无报错。

- [ ] **Step 4: 重启 streamlit（config.toml 主题需重启）并烟测**

先停掉当前在跑的 streamlit（如有），再 headless 启动 + curl 验证：

```bash
pkill -f "streamlit run app.py" 2>/dev/null; sleep 1
cd /Users/haiyi/Desktop/project/SellerSprite
python3 -m streamlit run app.py --server.headless true --server.port 8765 --browser.gatherUsageStats false >/tmp/streamlit_restyle.log 2>&1 &
PID=$!; sleep 12
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8765/
tail -6 /tmp/streamlit_restyle.log
kill $PID 2>/dev/null; wait $PID 2>/dev/null
```
Expected: `HTTP 200`，启动日志含 `You can now view your Streamlit app`，无 Traceback。

- [ ] **Step 5: 跳过提交（按全局约束）**

改动留工作区。

---

## Task 3: 全量测试 + 完成开发

**Files:**
- 无新增；验证整库。

- [ ] **Step 1: 跑全量 pytest**

Run: `python3 -m pytest -q`
Expected: 全绿（58 + Task 1 新增 1 = 59 passed）。

- [ ] **Step 2: 完成 / 呈现选项**

announce：使用 finishing-a-development-branch skill 收尾。
- 它会先跑测试（Step 1 已绿）。
- 环境：正常 repo（在 `main`），无 worktree → 标准 4 选项。
- 用户惯例「保持现状不提交」→ 默认走 Option 3，但**由用户选**。

---

## 验收清单（手动）

- [ ] `streamlit run app.py` 页面：顶部**海军蓝 #131921 标题栏**（白字 + 橙下边框），替换了原 Streamlit 标题。
- [ ] 页面底色浅灰 `#EAEDED`，主按钮「开始抓取」**黄 #FFD814**（hover 变深黄），下载按钮白底橙描边。
- [ ] 抓取成功后：成功提示 → **「⬇ 下载 HTML」按钮** → 5 个**白底圆角阴影**指标卡 → 嵌入明细表。
- [ ] 点「⬇ 下载 HTML」得到 `products.html`，双击离线打开，转置 / 隐藏列 / 搜索可用。
- [ ] 主题在**重启 streamlit 后**生效（config.toml 非热重载）；CSS 注入随运行即时生效。

---

## Self-Review（plan-vs-spec）

- **Spec coverage：** spec「下载按钮」→ Task 2 Step 2 `st.download_button`；spec「config.toml 主题」→ Task 1 Step 5；spec「CSS 注入：顶栏 / 主按钮 / 下载按钮 / 卡片 / 字体」→ Task 1 Step 3 `AMAZON_CSS` 全覆盖（.az-header / button[kind=primary] / button[kind=secondary] / [data-testid=stMetric] / body font）；spec「顶栏替换 st.title」→ Task 2 Step 1；spec「html 读一次复用」→ Task 2 Step 2 重构（去重读）；spec「不动 products.html」→ File Structure 明示只读；spec「config.toml 需重启」→ Task 2 Step 4 重启 + 验收清单。无遗漏。
- **Placeholder scan：** 无 TBD/TODO；CSS / config / 测试 / render_app 改动均含完整代码与确切命令。
- **Type consistency：** `AMAZON_CSS`（Task 1 定义为模块级 `str`）与 Task 2 `f"<style>{AMAZON_CSS}</style>"`、Task 1 测试 `app.AMAZON_CSS` 一致；下载按钮 `data=html` 复用同一 `html` 变量喂 `st.components.v1.html(html, ...)`，类型一致。
