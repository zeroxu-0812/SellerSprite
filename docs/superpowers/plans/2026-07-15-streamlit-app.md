# Streamlit Web 版实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `app.py`（Streamlit 本地入口），复用 `asin_pipeline` 抓取链路，输入 ASIN → 抓取 → 展示市场总览指标 + 嵌入现有 `products.html` 明细表。

**Architecture:** `app.py` 是纯编排层，不动 CLI 与现有模块。市场总览的格式化抽成纯函数 `build_metrics`（可单测）；Streamlit UI 收在 `render_app()` 里、`streamlit` 惰性导入，使 `import app` 在未装 streamlit 时也能用于测试。抓取完成后读 `output/market_overview.json` 渲染 `st.metric` 网格，读 `output/products.html` 用 `st.components.v1.html` 嵌入。

**Tech Stack:** Python 3.14（`/opt/homebrew/bin/python3`，`--break-system-packages` 装 pip）、Streamlit、复用现有 `asin_pipeline` / `sellersprite_auth` / `sellersprite_enrich`、pytest。

## Global Constraints

- **本地运行**，不做云端部署（playwright / 反爬 / token 鉴权不适合云）。
- **不改 CLI 与现有模块逻辑**（`asin_pipeline.py` / `output_writer.py` / `html_render.py` / `market_overview.py` 等一律只读复用）。
- **`.env` 鉴权**（`KEEPA_AUTH_FP` / `KEEPA_RANDOM_TOKEN` / `KEEPA_LOGIN_USERNAME` / `KEEPA_LOGIN_PASSWORD`）复用，绝不打印 / 日志泄露。
- pip 装到 Homebrew Python 需 `--break-system-packages`（externally-managed）。
- **提交策略：本项目惯例是不自动提交**（用户多次选择「保持现状不提交」）。执行时**跳过 git commit 步骤**，改动保留在工作区；全部完成后由 finishing-a-development-branch 呈现选项，由用户决定提交与否。
- 文案 / 注释用中文，与现有代码风格一致（`asin_pipeline.py` 等）。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `app.py` | Streamlit 入口：纯函数 `build_metrics` + `render_app()` UI 编排 | 新增 |
| `requirements.txt` | 声明依赖（streamlit 新增；playwright 运行期、pytest 测试期） | 新增 / 更新 |
| `tests/test_app.py` | 纯函数 `build_metrics` 单测 | 新增 |

`app.py` 只依赖标准库 + 惰性导入 streamlit；现有模块全部只读复用，不在本计划修改。

---

## Task 1: 纯函数 build_metrics（TDD）+ requirements.txt

**Files:**
- Create: `app.py`
- Create: `tests/test_app.py`
- Create / Update: `requirements.txt`

**Interfaces:**
- Consumes: `output/market_overview.json` 写出的 overview dict（键 `avg_price` / `avg_rating` / `total_units` / `total_amount` / `top10_units_share`；`top10_units_share` 为小数，如 `0.654`）
- Produces: `app.build_metrics(overview: dict) -> list[dict]`，每项 `{"label": str, "value": str}`；以及格式化助手 `fmt_money` / `fmt_int` / `fmt_pct` / `fmt_rating`（空值统一返回 `"-"`）。后续 Task 2 的 `render_app()` 依赖此函数渲染 `st.metric` 网格。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_app.py`：

```python
"""app.py 纯函数单测：build_metrics 把市场总览 dict 格式化成 st.metric 卡片。

UI 编排（render_app）走 Streamlit，难单测；这里只覆盖纯函数。app.py 顶层不
导入 streamlit（惰性导入），故 import app 不需要 streamlit 已装。"""
import app


def _overview():
    return {
        "sample_size": 14,
        "avg_price": 28.45,
        "avg_rating": 4.32,
        "avg_reviews": 1500.5,
        "total_units": 12345,
        "total_amount": 351200.5,
        "top10_units_share": 0.654,
    }


def test_build_metrics_formats_full_overview():
    metrics = {m["label"]: m["value"] for m in app.build_metrics(_overview())}
    assert metrics["均价"] == "$28.45"
    assert metrics["均评分"] == "4.32"
    assert metrics["样本总销量"] == "12,345"
    assert metrics["总销售额"] == "$351,200.50"
    assert metrics["Top10 集中度"] == "65.4%"


def test_build_metrics_handles_missing_values():
    metrics = {m["label"]: m["value"] for m in app.build_metrics({})}
    assert len(metrics) == 5
    assert all(v == "-" for v in metrics.values()), list(metrics.values())
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app'`（或 `AttributeError: build_metrics`）。

- [ ] **Step 3: 写最小实现**

新建 `app.py`（**仅放纯函数 + 惰性导入的 render_app 框架，本步先只写纯函数部分**）：

```python
"""Streamlit Web 版入口（本地运行）：输入 ASIN → 复用 asin_pipeline 抓取链路
→ 市场总览指标 + 嵌入 products.html 明细表。

纯编排层，不改 CLI / 现有模块。build_metrics 为纯函数可单测；Streamlit UI 收在
render_app() 内、streamlit 惰性导入，使 import app 在未装 streamlit 时也能用于测试。"""
import json


def fmt_money(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "-"


def fmt_int(v):
    return f"{int(v):,}" if isinstance(v, (int, float)) else "-"


def fmt_pct(v):
    return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "-"


def fmt_rating(v):
    return f"{v:.2f}" if isinstance(v, (int, float)) else "-"


def build_metrics(overview: dict) -> list:
    """市场总览 dict → st.metric 卡片列表（每项 {label, value}）。空值统一显示 '-'。"""
    return [
        {"label": "均价", "value": fmt_money(overview.get("avg_price"))},
        {"label": "均评分", "value": fmt_rating(overview.get("avg_rating"))},
        {"label": "样本总销量", "value": fmt_int(overview.get("total_units"))},
        {"label": "总销售额", "value": fmt_money(overview.get("total_amount"))},
        {"label": "Top10 集中度", "value": fmt_pct(overview.get("top10_units_share"))},
    ]
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: 2 passed。

- [ ] **Step 5: 确认 import 无 streamlit 副作用**

Run: `python3 -c "import app; print(len(app.build_metrics({})))"`
Expected: 输出 `5`，且不报 streamlit 相关错误（证明惰性导入成立，`import app` 不触发 Streamlit）。

- [ ] **Step 6: 创建 / 更新 requirements.txt**

若 `requirements.txt` 不存在则创建；存在则确保含 `streamlit`。目标最终内容至少包含以下三行（streamlit 为本次新增；playwright 为运行期依赖、amazon_search 抓详情页用；pytest 为测试期）：

```
streamlit>=1.30
playwright>=1.40
pytest>=7.0
```

- [ ] **Step 7: 跳过提交（按全局约束：不自动提交）**

改动保留在工作区（`app.py`、`tests/test_app.py`、`requirements.txt`），不执行 `git commit`。

---

## Task 2: render_app() Streamlit UI 编排

**Files:**
- Modify: `app.py`（在 `build_metrics` 之后追加 `render_app()` + 入口守卫）

**Interfaces:**
- Consumes: Task 1 的 `build_metrics`；`asin_pipeline.load_env` / `process_asins` / `parse_asins` / `ROOT` / `CONFIG_PATH`；`sellersprite_auth.KeepaTokenManager`；`sellersprite_enrich.AuthExpiredError`。`process_asins(asins, config, token_manager) -> {"products": int, "out_dir": str}`（无数据返回 `{}`）。
- Produces: `streamlit run app.py` 可启动的本地 Web 界面。

- [ ] **Step 1: 在 app.py 末尾追加 render_app() + 守卫**

在 `app.py` 现有内容之后追加（不要重复 `import json` / 纯函数）：

```python
def render_app():
    import streamlit as st
    from asin_pipeline import load_env, process_asins, parse_asins, ROOT, CONFIG_PATH
    from sellersprite_auth import KeepaTokenManager
    from sellersprite_enrich import AuthExpiredError

    st.set_page_config(page_title="卖家精灵 ASIN 爬虫", page_icon="🛒", layout="wide")
    st.title("🛒 卖家精灵 ASIN 爬虫")
    st.caption("输入 ASIN → competitor-lookup + 详情页（折扣 / About）→ 市场总览 + 明细表。本地运行。")

    raw = st.text_area(
        "输入 ASIN（逗号 / 空格 / 换行分隔，可多行粘贴）",
        placeholder="B0XXXXXXX, B0YYYYYYY\nB0ZZZZZZZZ",
        height=120,
    )

    if st.button("开始抓取", type="primary"):
        load_env()
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        token_manager = KeepaTokenManager(ROOT / ".token_cache.json")
        asins = parse_asins(raw)
        if not asins:
            st.warning("未识别到 ASIN，请检查输入。")
            return

        try:
            with st.spinner(f"抓取中…约 1-2 分钟（{len(asins)} 个 ASIN）"):
                result = process_asins(asins, config, token_manager)
        except AuthExpiredError as e:
            st.error(f"鉴权失效: {e}（请检查 .env 里的登录账号 / auth-fp / random-token）")
            return
        except Exception as e:  # noqa: BLE001
            st.error(f"出错: {e}")
            return

        if not result:
            st.warning("抓取无数据。")
            return

        st.success(f"✅ 完成：{result['products']} 个商品")

        out_dir = ROOT / "output"
        overview = json.loads((out_dir / "market_overview.json").read_text(encoding="utf-8"))
        metrics = build_metrics(overview)
        cols = st.columns(len(metrics))
        for col, m in zip(cols, metrics):
            col.metric(m["label"], m["value"])

        html = (out_dir / "products.html").read_text(encoding="utf-8")
        st.components.v1.html(html, height=850, scrolling=True)


if __name__ == "__main__":
    render_app()
```

> 说明：`streamlit run app.py` 会以 `__name__ == "__main__"` 执行脚本，故 `if __name__ == "__main__": render_app()` 守卫既能被 streamlit 启动、又不会在 pytest `import app` 时触发 UI（与 Task 1 的 import 烟测一致）。

- [ ] **Step 2: 确认 app.py 语法 / import 无误**

Run: `python3 -c "import app; print(hasattr(app, 'render_app'))"`
Expected: 输出 `True`，无报错（仍不触发 streamlit）。

- [ ] **Step 3: 确认 streamlit 已装**

Run: `python3 -c "import streamlit; print(streamlit.__version__)"`
Expected: 打印版本号。
若报 `ModuleNotFoundError`：`python3 -m pip install --break-system-packages 'streamlit>=1.30'`。

- [ ] **Step 4: 烟测启动（headless，验证不崩、能起服务）**

Run（headless、自动选空闲端口、15 秒后超时退出是预期的）：
```bash
python3 -m streamlit run app.py --server.headless true --server.port 8765 --browser.gatherUsageStats false & PID=$!; sleep 12; curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/; kill $PID 2>/dev/null
```
Expected: curl 输出 `200`（Streamlit 起服务、app.py 无 import/语法错误）。非 200 / 报错则需排查。

- [ ] **Step 5: 跳过提交（按全局约束：不自动提交）**

改动保留在工作区。

---

## Task 3: 全量测试 + 完成开发

**Files:**
- 无新增；验证整库。

- [ ] **Step 1: 跑全量 pytest**

Run: `python3 -m pytest -q`
Expected: 全绿（原有 56 条 + Task 1 新增 2 条 = 58 passed）。若有失败先修。

- [ ] **Step 2: 完成 / 呈现选项**

announce：使用 finishing-a-development-branch skill 收尾。
- 它会先跑测试（Step 1 已绿）。
- 环境：正常 repo（在 `main`），呈现 4 选项。
- 用户惯例为「保持现状不提交」→ 默认走 Option 3（Keep as-is），但**由用户选**，不替用户决定。

---

## 验收清单（手动）

- [ ] `streamlit run app.py` 浏览器自动打开，标题 / 文本框 / 按钮可见。
- [ ] 粘贴 ASIN → 点「开始抓取」→ spinner → 抓取成功提示 + 市场总览指标卡 + 嵌入明细表。
- [ ] 嵌入表格内：转置 / 隐藏列 / 排序 / 搜索 / 拖拽列宽 当次全部可用（localStorage 刷新后丢失，符合预期）。
- [ ] 鉴权失效（断网或改坏 `.env`）→ `st.error` 提示检查 `.env`，不崩页。
- [ ] 空输入 → `st.warning`「未识别到 ASIN」。

---

## Self-Review（plan-vs-spec）

- **Spec coverage：** spec「界面 st.text_area / st.button / st.spinner 包 process_asins / st.metric / st.components.v1.html 嵌入」→ Task 2 render_app 全覆盖；「读 market_overview.json → 指标」→ build_metrics（Task 1）+ render_app 读取；「复用 load_env / process_asins / parse_asins / KeepaTokenManager / config.json」→ render_app 全导入；「失败 AuthExpiredError / 其它 → st.error」→ render_app except 分支；「嵌入高度 850 + scrolling」→ `st.components.v1.html(html, height=850, scrolling=True)`；「localStorage 限制」→ 验收清单已注明当次有效。requirements.txt + 运行命令 + 测试策略均有对应步骤。无遗漏。
- **Placeholder scan：** 无 TBD / TODO；每步含完整代码与确切命令。
- **Type consistency：** `build_metrics(overview: dict) -> list[dict]`（Task 1 定义）与 render_app（Task 2）调用 `build_metrics(overview)`、`len(metrics)`、`m["label"]` / `m["value"]` 一致；`process_asins` 返回 `{"products","out_dir"}` 与 `result['products']` 一致；overview 键名与 `market_overview.py` 输出一致。
