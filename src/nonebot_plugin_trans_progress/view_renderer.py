from io import BytesIO
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont


RESOURCE_DIR = Path(__file__).parent / "resources" / "fonts"
TITLE_FONT_PATH = RESOURCE_DIR / "FZMINGSTJW.TTF"
BODY_FONT_PATH = RESOURCE_DIR / "fangsong_GB2312.ttf"

IMAGE_WIDTH = 900
MIN_IMAGE_HEIGHT = 420
MAX_IMAGE_HEIGHT = 8000
OUTER_MARGIN = 28
CONTENT_MARGIN = 64
TITLE_SIZE = 46
MODULE_TITLE_SIZE = 32
BODY_SIZE = 28
LINE_SPACING = 12
MODULE_GAP = 22


class RenderModule(NamedTuple):
    title: str
    lines: list[str]


def render_text_pages(title: str, lines: list[str]) -> list[bytes]:
    modules: list[RenderModule] = []
    current_lines: list[str] = []
    for line in lines:
        if line == "────────────────────":
            if current_lines:
                modules.append(RenderModule("", current_lines))
                current_lines = []
        else:
            current_lines.append(line)
    if current_lines or not modules:
        modules.append(RenderModule("", current_lines))
    return render_modules(title, modules)


def render_modules(title: str, modules: list[RenderModule]) -> list[bytes]:
    title_font = ImageFont.truetype(TITLE_FONT_PATH, TITLE_SIZE)
    module_title_font = ImageFont.truetype(TITLE_FONT_PATH, MODULE_TITLE_SIZE)
    body_font = ImageFont.truetype(BODY_FONT_PATH, BODY_SIZE)
    max_width = IMAGE_WIDTH - CONTENT_MARGIN * 2 - 36
    prepared_modules = [
        RenderModule(
            module.title,
            [
                wrapped_line
                for source_line in module.lines
                for wrapped_line in _wrap_text(source_line, body_font, max_width)
            ],
        )
        for module in modules
    ]
    pages: list[list[RenderModule]] = [[]]
    content_top = CONTENT_MARGIN + 92
    available_height = MAX_IMAGE_HEIGHT - content_top - CONTENT_MARGIN
    used_height = 0
    for module in prepared_modules:
        module_height = _module_height(module, module_title_font, body_font)
        if pages[-1] and used_height + MODULE_GAP + module_height > available_height:
            pages.append([])
            used_height = 0
        pages[-1].append(module)
        used_height += module_height + (MODULE_GAP if used_height else 0)
    return [
        _render_page(
            title,
            page,
            max(MIN_IMAGE_HEIGHT, content_top + _page_height(page, module_title_font, body_font) + CONTENT_MARGIN),
            title_font,
            module_title_font,
            body_font,
        )
        for page in pages
    ]


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return [""]

    lines: list[str] = []
    current_line = ""
    for char in text:
        candidate = current_line + char
        if current_line and font.getlength(candidate) > max_width:
            lines.append(current_line)
            current_line = char
        else:
            current_line = candidate
    if current_line:
        lines.append(current_line)
    return lines


def _module_height(
    module: RenderModule,
    module_title_font: ImageFont.FreeTypeFont,
    body_font: ImageFont.FreeTypeFont,
) -> int:
    title_height = 52 if module.title else 0
    line_height = _line_height(body_font)
    return 34 + title_height + max(1, len(module.lines)) * line_height + 24


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    bbox = font.getbbox("汉")
    return bbox[3] - bbox[1] + LINE_SPACING


def _page_height(
    modules: list[RenderModule],
    module_title_font: ImageFont.FreeTypeFont,
    body_font: ImageFont.FreeTypeFont,
) -> int:
    return sum(
        _module_height(module, module_title_font, body_font) for module in modules
    ) + MODULE_GAP * max(0, len(modules) - 1)


def _render_page(
    title: str,
    modules: list[RenderModule],
    image_height: int,
    title_font: ImageFont.FreeTypeFont,
    module_title_font: ImageFont.FreeTypeFont,
    body_font: ImageFont.FreeTypeFont,
) -> bytes:
    image = Image.new("RGB", (IMAGE_WIDTH, image_height), "#f6f0e5")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (OUTER_MARGIN, OUTER_MARGIN, IMAGE_WIDTH - OUTER_MARGIN, image_height - OUTER_MARGIN),
        fill="#fffdf7",
        outline="#5b3030",
        width=4,
    )
    draw.rectangle(
        (OUTER_MARGIN + 12, OUTER_MARGIN + 12, IMAGE_WIDTH - OUTER_MARGIN - 12, image_height - OUTER_MARGIN - 12),
        outline="#c9a56a",
        width=2,
    )
    header_top = CONTENT_MARGIN - 18
    draw.rounded_rectangle(
        (CONTENT_MARGIN, header_top, IMAGE_WIDTH - CONTENT_MARGIN, header_top + 82),
        radius=8,
        fill="#6d3131",
    )
    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_box[2] - title_box[0]
    draw.text(
        ((IMAGE_WIDTH - title_width) // 2, header_top + 15),
        title,
        font=title_font,
        fill="#fff7df",
    )

    y = header_top + 110
    line_height = _line_height(body_font)
    for module in modules:
        module_height = _module_height(module, module_title_font, body_font)
        draw.rounded_rectangle(
            (CONTENT_MARGIN, y, IMAGE_WIDTH - CONTENT_MARGIN, y + module_height),
            radius=8,
            fill="#fffaf0",
            outline="#b89561",
            width=2,
        )
        text_y = y + 18
        if module.title:
            draw.text((CONTENT_MARGIN + 18, text_y), module.title, font=module_title_font, fill="#6d3131")
            text_y += 52
            draw.line((CONTENT_MARGIN + 18, text_y - 10, IMAGE_WIDTH - CONTENT_MARGIN - 18, text_y - 10), fill="#dec69d", width=1)
        for line in module.lines or [""]:
            draw.text((CONTENT_MARGIN + 18, text_y), line, font=body_font, fill="#302b28")
            text_y += line_height
        y += module_height + MODULE_GAP

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()