# html_render.py
"""把 products.json 直接渲染进自包含 HTML（双击 file:// 即可查看，无需服务器 / CSV）。

模板：项目根 products.html，内含占位标记
    const DATA = /*__DATA__*/{}/*__END__*/;
本模块把 {products, overview} 的 JSON 写到两个标记之间。模板里有内联数据时
直接渲染；空对象 {} 时前端走 dropzone / 同目录 fetch products.json 兜底。"""
import json
from pathlib import Path

# 占位标记（与 products.html 中的 const DATA 行保持一致）
_START = "/*__DATA__*/"
_END = "/*__END__*/"


def _inline_payload(rows: list, overview: dict) -> str:
    """序列化为可直接嵌入 <script> 的 JS 对象字面量。
    转义 </ → <\\/ 防止商品文本里的 </script> 截断脚本块。"""
    payload = {"products": rows, "overview": overview or {}}
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_html(rows: list, overview: dict, template_path: Path, out_path: Path) -> Path:
    """读模板 → 在占位标记间注入数据 → 写自包含 HTML。返回 out_path。"""
    template = template_path.read_text(encoding="utf-8")
    i = template.index(_START)
    j = template.index(_END)
    html = template[: i + len(_START)] + _inline_payload(rows, overview) + template[j:]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
