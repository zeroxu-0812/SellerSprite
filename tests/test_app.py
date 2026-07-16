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


def test_amazon_css_pins_palette():
    """AMAZON_CSS 必须含亚马逊关键配色，防回归（误删颜色会被此测试挡住）。"""
    css = app.AMAZON_CSS
    for token in ["#131921", "#FF9900", "#FFD814", "#EAEDED"]:
        assert token in css, f"AMAZON_CSS 缺少配色 {token}"
