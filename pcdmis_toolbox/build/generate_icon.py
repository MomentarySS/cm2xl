"""
build/generate_icon.py
======================
生成 cm2xl.ico — 程序化图标，多尺寸bundled in .ico format。
运行: python build/generate_icon.py
输出: pcdmis_toolbox/cm2xl.ico
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

ACCENT      = "#0F766E"   # 深青绿
ACCENT_LITE = "#14B8A6"   # 亮青绿
PRIMARY     = "#115E59"   # 主色
BG          = "#F5F4EF"   # 暖灰背景
WHITE       = "#FFFFFF"

OUT_PATH = Path(__file__).parent.parent / "cm2xl.ico"
SIZES = [256, 128, 64, 48, 32, 16]  # 递减，ICO 支持多尺寸


def _font(size: int) -> ImageFont.FreeTypeFont:
    """加载 Segoe UI 粗体，没有则回退到默认"""
    try:
        return ImageFont.truetype("C:\\Windows\\Fonts\\segui.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _make_layer(size: int) -> Image.Image:
    """生成单层图标图片"""
    # 画布
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角矩形背景
    r = size // 5  # 圆角半径
    pad = size // 16  # 内边距

    # 外发光/描边：用浅色先画大圆角矩形作光晕
    outer = size // 32
    draw.rounded_rectangle(
        [pad - outer, pad - outer, size - pad + outer, size - pad + outer],
        radius=r + outer,
        fill=(*_hex(ACCENT_LITE), 60)
    )

    # 主体背景
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=r,
        fill=_hex(ACCENT)
    )

    # 内层渐变叠加（底部略暗，模拟立体感）
    inner_pad = pad + size // 16
    inner_h = size - inner_pad * 2
    for i in range(inner_h // 4):
        alpha = int(30 * (1 - i / (inner_h // 4)))
        y_bottom = size - inner_pad - i
        draw.line(
            [(inner_pad, y_bottom), (size - inner_pad, y_bottom)],
            fill=(0, 0, 0, alpha),
            width=1
        )

    # 字母 "c" — 用比背景稍亮的填充
    letter = "c"
    # 计算字体大小：让字母占图标高度的约 60%
    letter_size = int(size * 0.52)
    font = _font(letter_size)

    # 测量文字边界
    bb = draw.textbbox((0, 0), letter, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]

    # 居中偏移
    tx = (size - tw) // 2 - bb[0]
    ty = (size - th) // 2 - bb[1]

    # 阴影
    sh_off = size // 32
    draw.text((tx + sh_off, ty + sh_off), letter, font=font, fill=(0, 0, 0, 90))

    # 主文字（亮青绿 vs 暖白）
    draw.text((tx, ty), letter, font=font, fill=_hex(ACCENT_LITE))

    # 小标记 "2xl" — 缩小字号放在右下角（仅大尺寸）
    if size >= 64:
        sub_size = max(letter_size // 3, size // 8)
        sub_font = _font(sub_size)
        sub_text = "2xl"
        sb = draw.textbbox((0, 0), sub_text, font=sub_font)
        sw = sb[2] - sb[0]
        # 放右下，内边距
        sx = size - pad - sw - size // 32
        sy = size - pad - (sb[3] - sb[1]) - size // 32
        draw.text((sx, sy), sub_text, font=sub_font, fill=_hex(ACCENT_LITE))

    return img


def _hex(hex_str: str) -> tuple:
    """#RRGGBB → (R, G, B)"""
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def generate_ico(out_path: Path, sizes: list[int]) -> None:
    """生成多尺寸 .ico 文件"""
    layers = [_make_layer(s) for s in sizes]

    # 保存 ICO：PIL 直接支持 .ico 多尺寸
    out_path.parent.mkdir(parents=True, exist_ok=True)
    layers[0].save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=layers[1:]
    )
    print(f"✅ 生成: {out_path}  (尺寸: {sizes})")


if __name__ == "__main__":
    generate_ico(OUT_PATH, SIZES)
