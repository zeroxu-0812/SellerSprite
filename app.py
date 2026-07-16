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


AMAZON_CSS = """
/* 亚马逊忠实风格：海军蓝顶栏 + 浅灰底 + 白卡阴影 + 黄主按钮 */
body{ font-family:"Amazon Ember","Amazon Ember Display",Helvetica,Arial,sans-serif; }
/* 页面底色 #EAEDED（与 config.toml 主题一致，双保险） */
.stApp, [data-testid="stAppViewContainer"]{ background-color:#EAEDED; }

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


def render_app():
    import streamlit as st
    from asin_pipeline import load_env, process_asins, parse_asins, ROOT, CONFIG_PATH
    from sellersprite_auth import KeepaTokenManager
    from sellersprite_enrich import AuthExpiredError

    st.set_page_config(page_title="卖家精灵 ASIN 爬虫", page_icon="🛒", layout="wide")
    st.markdown(f"<style>{AMAZON_CSS}</style>", unsafe_allow_html=True)
    st.markdown(
        '<div class="az-header">🛒 卖家精灵 ASIN 爬虫'
        '<div class="az-sub">输入 ASIN → competitor-lookup + 详情页（折扣 / About）→ 市场总览 + 明细表。本地运行。</div>'
        "</div>",
        unsafe_allow_html=True,
    )

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
        html = (out_dir / "products.html").read_text(encoding="utf-8")

        st.download_button("⬇ 下载 HTML", data=html, file_name="products.html", mime="text/html")

        metrics = build_metrics(overview)
        cols = st.columns(len(metrics))
        for col, m in zip(cols, metrics):
            col.metric(m["label"], m["value"])

        st.components.v1.html(html, height=850, scrolling=True)


if __name__ == "__main__":
    render_app()
