from html import escape

from fastapi.responses import HTMLResponse

PAGE_STYLE = """
* { box-sizing: border-box; }
body {
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    font-family: "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei",
        sans-serif;
    background: linear-gradient(120deg, #f7fafc 0%, #edf4f9 52%, #f8f5f2 100%);
    color: #1f2937;
}
.card {
    width: min(100%, 420px);
    padding: 32px 28px;
    background: #fff;
    border: 1px solid #d8e1ec;
    border-radius: 8px;
    box-shadow: 0 8px 20px rgba(24, 59, 91, 0.08);
}
h1 { margin: 0 0 12px; font-size: 22px; color: #183b5b; }
p { margin: 0 0 12px; line-height: 1.6; color: #475569; }
.details {
    margin: 0 0 12px;
    padding: 10px 12px;
    background: #f4f7fb;
    border-radius: 6px;
    font-size: 14px;
    color: #334155;
    word-break: break-all;
}
.details div + div { margin-top: 4px; }
.actions { display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; }
.btn {
    flex: 1;
    min-width: 120px;
    padding: 10px 16px;
    text-align: center;
    text-decoration: none;
    border-radius: 6px;
    border: 1px solid #d8e1ec;
    color: #475569;
    background: #fff;
    font-size: 15px;
}
.btn.primary { background: #db5d77; border-color: #db5d77; color: #fff; }
.btn.primary:hover { background: #b9415c; border-color: #b9415c; }
"""


def render_auth_page(
    title: str,
    message: str,
    *,
    status_code: int = 200,
    details: list[str] | None = None,
    actions: list[tuple[str, str, bool]] | None = None,
) -> HTMLResponse:
    """渲染登录相关的独立提示页；所有动态内容都会转义。"""
    details_html = ""
    if details:
        rows = "".join(f"<div>{escape(line)}</div>" for line in details)
        details_html = f'<div class="details">{rows}</div>'
    actions_html = "".join(
        f'<a class="btn{" primary" if primary else ""}" href="{escape(href)}">'
        f"{escape(label)}</a>"
        for label, href, primary in actions or []
    )
    title_html = escape(title)
    body = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{title_html} - 汉化进度管理</title><style>{PAGE_STYLE}</style>"
        f'</head><body><main class="card"><h1>{title_html}</h1>'
        f"<p>{escape(message)}</p>"
        f'{details_html}<div class="actions">{actions_html}</div></main></body></html>'
    )
    return HTMLResponse(
        body,
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )
