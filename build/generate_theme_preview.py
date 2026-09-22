"""生成 cm2xl 浅色主题改善前后对比预览图。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cm2xl_theme_preview.png"

OLD = {
    "page": "#F5F4EF",
    "card": "#FAFAF7",
    "border": "#E2E8F0",
    "hint": "#F0FDFA",
    "entry_bg": "#F5F4EF",
    "entry_border": "#E5E7EB",
    "checkbox_border": "#E5E7EB",
    "text": "#1F2937",
    "subtle": "#64748B",
    "accent": "#0F766E",
    "nav": "#115E59",
    "btn_muted": "#64748B",
}

NEW = {
    "page": "#E4E2DA",
    "card": "#F0EEE6",
    "border": "#B8BFC8",
    "hint": "#D9EDE8",
    "entry_bg": "#FAFAF8",
    "entry_border": "#9CA8B6",
    "checkbox_border": "#7B8794",
    "text": "#1A2332",
    "subtle": "#52606D",
    "accent": "#0F766E",
    "nav": "#115E59",
    "btn_muted": "#5B6775",
}


def _font(size: int, bold: bool = False):
    candidates = [
        Path(r"C:\Windows\Fonts\msyhbd.ttc") if bold else Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhl.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size, index=0)
            except OSError:
                continue
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Segoe UI"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex(rgb: str):
    rgb = rgb.lstrip("#")
    return tuple(int(rgb[i : i + 2], 16) for i in (0, 2, 4))


def _draw_panel(draw: ImageDraw.ImageDraw, x0: int, y0: int, w: int, h: int, pal: dict, title: str):
    f_title = _font(18, True)
    f_h = _font(14, True)
    f_b = _font(12)
    f_s = _font(11)

    draw.rectangle((x0, y0, x0 + w, y0 + h), fill=_hex(pal["page"]))
    draw.text((x0 + 16, y0 + 12), title, fill=_hex(pal["text"]), font=f_title)

    nav_w = 150
    draw.rectangle((x0 + 12, y0 + 44, x0 + 12 + nav_w, y0 + h - 12), fill=_hex(pal["nav"]))
    draw.text((x0 + 24, y0 + 58), "cm2xl", fill=(255, 255, 255), font=f_h)
    draw.rectangle((x0 + 18, y0 + 108, x0 + 12 + nav_w - 6, y0 + 142), fill=_hex(pal["accent"]))
    draw.text((x0 + 28, y0 + 116), "PCDMIS导出", fill=(255, 255, 255), font=f_b)

    cx = x0 + nav_w + 28
    cw = w - nav_w - 40
    draw.text((cx, y0 + 52), "PCDMIS 按需 Excel 测量报告", fill=_hex(pal["text"]), font=f_h)
    draw.text((cx, y0 + 74), "v1.0.5 · 测到一半也能出表", fill=_hex(pal["subtle"]), font=f_s)

    card_y = y0 + 98
    card_h = 250
    draw.rounded_rectangle((cx, card_y, cx + cw, card_y + card_h), radius=14, fill=_hex(pal["card"]), outline=_hex(pal["border"]), width=2)
    draw.text((cx + 16, card_y + 14), "导出 Excel", fill=_hex(pal["text"]), font=f_h)
    draw.text((cx + 16, card_y + 36), "读取当前已测数据，生成 PC-DMIS 列格式报告", fill=_hex(pal["subtle"]), font=f_s)

    entry_y = card_y + 62
    draw.text((cx + 16, entry_y), "输出目录", fill=_hex(pal["text"]), font=f_b)
    draw.rounded_rectangle((cx + 88, entry_y - 2, cx + cw - 90, entry_y + 24), radius=8, fill=_hex(pal["entry_bg"]), outline=_hex(pal["entry_border"]), width=1)
    draw.text((cx + 98, entry_y + 2), "C:\\Users\\...\\cm2xl\\reports", fill=_hex(pal["subtle"]), font=f_s)
    draw.rounded_rectangle((cx + cw - 78, entry_y - 2, cx + cw - 16, entry_y + 24), radius=8, fill=_hex(pal["btn_muted"]))
    draw.text((cx + cw - 68, entry_y + 4), "浏览", fill=(255, 255, 255), font=f_s)

    cb_y = entry_y + 40
    for i, label in enumerate(("仅报告窗口数据", "仅 Mark 命令")):
        bx = cx + 16 + i * 170
        draw.rounded_rectangle((bx, cb_y, bx + 18, cb_y + 18), radius=4, fill=_hex(pal["entry_bg"]), outline=_hex(pal["checkbox_border"]), width=2)
        if i == 0:
            draw.line((bx + 4, cb_y + 9, bx + 8, cb_y + 13), fill=_hex(pal["accent"]), width=2)
            draw.line((bx + 8, cb_y + 13, bx + 14, cb_y + 5), fill=_hex(pal["accent"]), width=2)
        draw.text((bx + 26, cb_y + 1), label, fill=_hex(pal["text"]), font=f_b)

    btn_y = cb_y + 36
    draw.rounded_rectangle((cx + 16, btn_y, cx + 168, btn_y + 36), radius=10, fill=_hex(pal["accent"]))
    draw.text((cx + 36, btn_y + 10), "一键导出 Excel", fill=(255, 255, 255), font=f_h)

    card2_y = card_y + card_h + 14
    card2_h = 120
    draw.rounded_rectangle((cx, card2_y, cx + cw, card2_y + card2_h), radius=14, fill=_hex(pal["card"]), outline=_hex(pal["border"]), width=2)
    draw.text((cx + 16, card2_y + 14), "出货检测表填入", fill=_hex(pal["text"]), font=f_h)
    cb2_y = card2_y + 44
    draw.rounded_rectangle((cx + 16, cb2_y, cx + 34, cb2_y + 18), radius=4, fill=_hex(pal["entry_bg"]), outline=_hex(pal["checkbox_border"]), width=2)
    draw.line((cx + 20, cb2_y + 9, cx + 24, cb2_y + 13), fill=_hex(pal["accent"]), width=2)
    draw.line((cx + 24, cb2_y + 13, cx + 30, cb2_y + 5), fill=_hex(pal["accent"]), width=2)
    draw.text((cx + 42, cb2_y + 1), "接着上次结果填入", fill=_hex(pal["text"]), font=f_b)
    draw.text((cx + 190, cb2_y + 1), "上次结果：无", fill=_hex(pal["subtle"]), font=f_s)

    foot_y = y0 + h - 34
    draw.rounded_rectangle((cx, foot_y, cx + cw, foot_y + 28), radius=10, fill=_hex(pal["card"]), outline=_hex(pal["border"]), width=1)
    draw.text((cx + 12, foot_y + 7), "PC-DMIS: 未连接", fill=_hex(pal["subtle"]), font=f_s)
    draw.text((cx + cw - 52, foot_y + 7), "就绪", fill=_hex(pal["text"]), font=f_b)


def main():
    panel_w, panel_h = 520, 620
    gap = 24
    margin = 20
    img_w = margin * 2 + panel_w * 2 + gap
    img_h = margin * 2 + panel_h + 36
    img = Image.new("RGB", (img_w, img_h), "#D1D5DB")
    draw = ImageDraw.Draw(img)

    draw.text((margin, margin - 2), "cm2xl 浅色主题对比预览（左：当前 / 右：改善后）", fill="#111827", font=_font(16, True))

    y = margin + 28
    _draw_panel(draw, margin, y, panel_w, panel_h, OLD, "当前（偏白、边框弱）")
    _draw_panel(draw, margin + panel_w + gap, y, panel_w, panel_h, NEW, "改善后（暖灰纸感、对比更清晰）")

    img.save(OUT, format="PNG")
    print(OUT)


if __name__ == "__main__":
    main()
