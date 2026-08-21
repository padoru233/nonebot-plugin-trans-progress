from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont


RESOURCE_DIR = Path(__file__).parent / "resources" / "fonts"
FONT_PATH = RESOURCE_DIR / "LXGWNeoXiHeiPlus.ttf"
EMOJI_FONT_PATH = RESOURCE_DIR / "NotoColorEmoji.ttf"
EMOJI_FONT_SIZE = 109

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


class ColorPalette(NamedTuple):
    background: str
    panel: str
    border: str
    inner_border: str
    header: str
    header_text: str
    module: str
    module_border: str
    module_title: str
    divider: str
    body_text: str


BROWN_PALETTE = ColorPalette(
    "#f6f0e5", "#fffdf7", "#5b3030", "#c9a56a", "#6d3131", "#fff7df",
    "#fffaf0", "#b89561", "#6d3131", "#dec69d", "#302b28",
)
LIGHT_BLUE_PALETTE = ColorPalette(
    "#eaf6ff", "#fafdff", "#5b9bc8", "#9dcae8", "#4d91c2", "#f6fcff",
    "#f5fbff", "#8fc4e6", "#397cae", "#c6e1f2", "#26333c",
)
MINT_PALETTE = ColorPalette(
    "#e9f8f5", "#fbfefd", "#4ca58d", "#9bd6c6", "#3e927d", "#f5fffb",
    "#f4fcf9", "#88ccb9", "#347d6b", "#c3e7dc", "#263833",
)
GREEN_PALETTE = ColorPalette(
    "#edf8ed", "#fcfffb", "#62a56d", "#aad9ae", "#4c9859", "#f7fff7",
    "#f6fcf5", "#9dcea2", "#3c8349", "#cce7ce", "#28372a",
)
AMBER_PALETTE = ColorPalette(
    "#fff8e8", "#fffefa", "#c89135", "#ecd297", "#b47d24", "#fffdf5",
    "#fffcf2", "#e2bf75", "#966415", "#f1dfb2", "#3b3121",
)
CORAL_PALETTE = ColorPalette(
    "#fff1ef", "#fffdfc", "#c9786d", "#ebbbb3", "#b96359", "#fff8f6",
    "#fff9f8", "#e3a79e", "#9f5048", "#f0cbc5", "#3d2927",
)


def render_text_pages(
    title: str, lines: list[str], palette: ColorPalette = BROWN_PALETTE
) -> list[bytes]:
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
    return render_modules(title, modules, palette)


def render_modules(
    title: str, modules: list[RenderModule], palette: ColorPalette = BROWN_PALETTE
) -> list[bytes]:
    title_font = ImageFont.truetype(FONT_PATH, TITLE_SIZE)
    module_title_font = ImageFont.truetype(FONT_PATH, MODULE_TITLE_SIZE)
    body_font = ImageFont.truetype(FONT_PATH, BODY_SIZE)
    max_width = IMAGE_WIDTH - CONTENT_MARGIN * 2 - 36
    title_lines = _wrap_text(title, title_font, max_width)
    header_top = CONTENT_MARGIN - 18
    header_height = _header_height(title_lines, title_font)
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
    content_top = header_top + header_height + 28
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
            title_lines,
            page,
            max(MIN_IMAGE_HEIGHT, content_top + _page_height(page, module_title_font, body_font) + CONTENT_MARGIN),
            header_height,
            title_font,
            module_title_font,
            body_font,
            palette,
        )
        for page in pages
    ]


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return [""]

    lines: list[str] = []
    current_line = ""
    for unit in _text_units(text):
        candidate = current_line + unit
        if current_line and _text_width(candidate, font) > max_width:
            lines.append(current_line)
            current_line = unit
        else:
            current_line = candidate
    if current_line:
        lines.append(current_line)
    return lines


def _text_units(text: str) -> list[str]:
    units: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if not _is_emoji(char):
            units.append(char)
            index += 1
            continue

        end = index + 1
        if _is_regional_indicator(char) and end < len(text) and _is_regional_indicator(text[end]):
            end += 1
        while end < len(text) and text[end] in "\ufe0e\ufe0f\u20e3":
            end += 1
        while end + 1 < len(text) and text[end] == "\u200d" and _is_emoji(text[end + 1]):
            end += 2
            while end < len(text) and text[end] in "\ufe0e\ufe0f\u20e3":
                end += 1
        units.append(text[index:end])
        index = end
    return units


def _is_emoji(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or codepoint
        in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}
    )


def _is_regional_indicator(char: str) -> bool:
    return 0x1F1E6 <= ord(char) <= 0x1F1FF


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> float:
    return sum(
        font.size if _is_emoji(unit[0]) else font.getlength(unit)
        for unit in _text_units(text)
    )


@lru_cache(maxsize=256)
def _emoji_image(emoji: str, size: int) -> Image.Image:
    emoji_font = ImageFont.truetype(EMOJI_FONT_PATH, EMOJI_FONT_SIZE)
    bbox = emoji_font.getbbox(emoji)
    image = Image.new("RGBA", (bbox[2] - bbox[0], bbox[3] - bbox[1]))
    ImageDraw.Draw(image).text(
        (-bbox[0], -bbox[1]), emoji, font=emoji_font, embedded_color=True
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _draw_text(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
) -> None:
    x, y = position
    for unit in _text_units(text):
        if _is_emoji(unit[0]):
            emoji = _emoji_image(unit, font.size)
            image.paste(emoji, (round(x), y), emoji)
            x += font.size
        else:
            draw.text((x, y), unit, font=font, fill=fill)
            x += font.getlength(unit)


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


def _header_height(title_lines: list[str], title_font: ImageFont.FreeTypeFont) -> int:
    return 30 + len(title_lines) * _line_height(title_font)


def _page_height(
    modules: list[RenderModule],
    module_title_font: ImageFont.FreeTypeFont,
    body_font: ImageFont.FreeTypeFont,
) -> int:
    return sum(
        _module_height(module, module_title_font, body_font) for module in modules
    ) + MODULE_GAP * max(0, len(modules) - 1)


def _render_page(
    title_lines: list[str],
    modules: list[RenderModule],
    image_height: int,
    header_height: int,
    title_font: ImageFont.FreeTypeFont,
    module_title_font: ImageFont.FreeTypeFont,
    body_font: ImageFont.FreeTypeFont,
    palette: ColorPalette,
) -> bytes:
    image = Image.new("RGB", (IMAGE_WIDTH, image_height), palette.background)
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (OUTER_MARGIN, OUTER_MARGIN, IMAGE_WIDTH - OUTER_MARGIN, image_height - OUTER_MARGIN),
        fill=palette.panel,
        outline=palette.border,
        width=4,
    )
    draw.rectangle(
        (OUTER_MARGIN + 12, OUTER_MARGIN + 12, IMAGE_WIDTH - OUTER_MARGIN - 12, image_height - OUTER_MARGIN - 12),
        outline=palette.inner_border,
        width=2,
    )
    header_top = CONTENT_MARGIN - 18
    draw.rounded_rectangle(
        (CONTENT_MARGIN, header_top, IMAGE_WIDTH - CONTENT_MARGIN, header_top + header_height),
        radius=8,
        fill=palette.header,
    )
    title_y = header_top + 15
    title_line_height = _line_height(title_font)
    for title_line in title_lines:
        title_width = _text_width(title_line, title_font)
        _draw_text(
            draw,
            image,
            (round((IMAGE_WIDTH - title_width) / 2), title_y),
            title_line,
            title_font,
            palette.header_text,
        )
        title_y += title_line_height

    y = header_top + header_height + 28
    line_height = _line_height(body_font)
    for module in modules:
        module_height = _module_height(module, module_title_font, body_font)
        draw.rounded_rectangle(
            (CONTENT_MARGIN, y, IMAGE_WIDTH - CONTENT_MARGIN, y + module_height),
            radius=8,
            fill=palette.module,
            outline=palette.module_border,
            width=2,
        )
        text_y = y + 18
        if module.title:
            _draw_text(
                draw,
                image,
                (CONTENT_MARGIN + 18, text_y),
                module.title,
                module_title_font,
                palette.module_title,
            )
            text_y += 52
            draw.line((CONTENT_MARGIN + 18, text_y - 10, IMAGE_WIDTH - CONTENT_MARGIN - 18, text_y - 10), fill=palette.divider, width=1)
        for line in module.lines or [""]:
            _draw_text(
                draw,
                image,
                (CONTENT_MARGIN + 18, text_y),
                line,
                body_font,
                palette.body_text,
            )
            text_y += line_height
        y += module_height + MODULE_GAP

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()