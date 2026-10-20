"""Draws the app icon, the Android adaptive-icon pieces and the splash image from the lowercase "dawat" wordmark.
Only text in the OFL-licensed Outfit and Plus Jakarta Sans fonts (already in the app) on the brand navy: no other artwork.
Run: python scripts/make-assets.py   (needs Pillow)   Output: mobile/assets/*.png"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent.parent
fonts = root / 'node_modules' / '@expo-google-fonts'
OUT = root / 'assets'
OUT.mkdir(exist_ok=True)
NAVY = (0x21, 0x36, 0x4B, 255)
WHITE = (255, 255, 255, 255)
SKY = (0xA6, 0xD3, 0xF2, 255)
MARK = fonts / 'outfit' / '700Bold' / 'Outfit_700Bold.ttf'
TAG = fonts / 'plus-jakarta-sans' / '600SemiBold' / 'PlusJakartaSans_600SemiBold.ttf'


def fit_text(draw, text, font_path, target_w):
    """Largest font size whose text is at most target_w wide; returns (font, bbox)."""
    size = 50
    while True:
        f = ImageFont.truetype(str(font_path), size + 4)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] > target_w:
            break
        size += 4
    f = ImageFont.truetype(str(font_path), size)
    return f, draw.textbbox((0, 0), text, font=f)


def wordmark(canvas, width_frac, color, tagline=None, tag_color=SKY, center_y=0.5):
    d = ImageDraw.Draw(canvas)
    W, H = canvas.size
    f, b = fit_text(d, 'dawat', MARK, W * width_frac)
    w, h = b[2] - b[0], b[3] - b[1]
    y_block = h
    tf = tb = None
    gap = 0
    if tagline:
        tf = ImageFont.truetype(str(TAG), int(f.size * 0.22))
        tb = d.textbbox((0, 0), tagline, font=tf)
        gap = int(f.size * 0.12)
        y_block += gap + (tb[3] - tb[1])
    top = int(H * center_y - y_block / 2)
    d.text(((W - w) / 2 - b[0], top - b[1]), 'dawat', font=f, fill=color)
    if tagline:
        d.text(((W - (tb[2] - tb[0])) / 2 - tb[0], top + h + gap - tb[1]), tagline, font=tf, fill=tag_color)


# 1. icon: 1024 square, navy, wordmark (Play and iOS draw their own mask, so no transparency and no rounded corners)
icon = Image.new('RGBA', (1024, 1024), NAVY)
wordmark(icon, 0.70, WHITE)
icon.convert('RGB').save(OUT / 'icon.png')

# 2. adaptive foreground: transparent, wordmark inside the 66% safe circle (Android crops to a circle or squircle)
fg = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
wordmark(fg, 0.50, WHITE)
fg.save(OUT / 'adaptive-icon.png')

# 3. monochrome (Android 13 themed icons): the same shape in one colour
mono = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
wordmark(mono, 0.50, (0, 0, 0, 255))
mono.save(OUT / 'adaptive-icon-monochrome.png')

# 4. splash image: transparent, wordmark with the tagline; the navy fill comes from the plugin's backgroundColor
sp = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
wordmark(sp, 0.80, WHITE, tagline='Food, your way')
sp.save(OUT / 'splash-icon.png')
print('wrote', sorted(p.name for p in OUT.glob('*.png')))
