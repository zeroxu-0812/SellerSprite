# tests/test_html_render.py
from html_render import render_html


def _template(tmp_path):
    """与 products.html 占位标记一致的最小模板。"""
    p = tmp_path / "products.html"
    p.write_text(
        "<head></head><body><script>\n"
        "const DATA = /*__DATA__*/{}/*__END__*/;\n"
        "console.log(DATA);\n"
        "</script></body>", encoding="utf-8")
    return p


def test_render_html_injects_products_and_overview(tmp_path):
    tpl = _template(tmp_path)
    out = tmp_path / "out" / "products.html"
    rows = [{"asin": "B0XX", "title": "镁油", "price": 9.99}]
    overview = {"sample_size": 1, "avg_price": 9.99}

    render_html(rows, overview, tpl, out)

    assert out.exists()
    txt = out.read_text(encoding="utf-8")
    # 标记保留，中间被替换为内联数据
    assert "/*__DATA__*/" in txt and "/*__END__*/" in txt
    # 商品 + 总览都已注入
    assert '"asin": "B0XX"' in txt
    assert '"title": "镁油"' in txt                  # 中文 ensure_ascii=False 直出
    assert '"sample_size": 1' in txt


def test_render_html_escapes_closing_script(tmp_path):
    """商品文本里的 </script> 不能截断脚本块。"""
    tpl = _template(tmp_path)
    out = tmp_path / "products.html"
    rows = [{"asin": "B0YY", "title": "x </script><b>evil"}]
    render_html(rows, {}, tpl, out)
    txt = out.read_text(encoding="utf-8")
    # 原 </script> 被转义为 <\/script>
    assert "<\\/script>" in txt
    # 真正闭合脚本块的 </script> 只应出现在转义串之后，且 DATA 注入内容不含裸 </script>
    injected = txt.split("/*__DATA__*/", 1)[1].split("/*__END__*/", 1)[0]
    assert "</script>" not in injected


def test_render_html_creates_parent_dir(tmp_path):
    tpl = _template(tmp_path)
    out = tmp_path / "deep" / "nested" / "products.html"
    render_html([], {}, tpl, out)
    assert out.exists()


def test_render_sales_parent_child_mapping():
    """销量块：父体取 units（父ASIN 聚合），子体取 month_units（本子体）。
    历史 bug：两者曾反了——父体错挂 month_units、子体错挂 units。"""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1] / "products.html").read_text(encoding="utf-8")
    seg = tpl[tpl.index("function renderSales"):tpl.index("// 销量趋势")]
    lines = seg.splitlines()
    fu = next(ln for ln in lines if "父体" in ln)
    zi = next(ln for ln in lines if "子体" in ln)
    assert "p.units" in fu and "p.month_units" not in fu, "父体应取 units（父ASIN 聚合）"
    assert "p.month_units" in zi and "p.units" not in zi, "子体应取 month_units（本子体）"


def test_render_amount_shows_parent_and_child():
    """销售额块应同时展示父体(amount)与子体(sub_total_amount)，与销量块对齐。"""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1] / "products.html").read_text(encoding="utf-8")
    seg = tpl[tpl.index("function renderAmount"):tpl.index("// 徽章")]
    assert "p.amount" in seg, "父体销售额取 amount"
    assert "p.sub_total_amount" in seg, "子体销售额取 sub_total_amount"


def test_render_trend_shows_child_and_parent():
    """趋势列应同时渲染子体(amz_unit_trend)与父体(parent_unit_trend)两序列。"""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1] / "products.html").read_text(encoding="utf-8")
    assert "renderTrend(p.amz_unit_trend, p.parent_unit_trend)" in tpl
