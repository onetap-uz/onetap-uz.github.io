# Контакт в цвете темы: фото в рамке цвета каждой темы визитки.
#
#   python theme-vcards.py javokhir     (папка визитки; "." — страница автора)
#
# Из index.html берутся фото (CONFIG.photo.page), темы (CONFIG.themes) и имя
# файла контакта (CONFIG.contacts.vcfUrl). Сам контакт — тот, что выгружен
# через ?export и лежит рядом: скрипт меняет в нём только PHOTO и пишет по
# файлу на тему. Первая тема сохраняется под исходным именем, остальные —
# с -id на конце (javokhir-ergashev-emerald.vcf). Страница выбирает файл
# по теме, которую выбрал посетитель.
#
# Нужны Python 3 с Pillow и numpy:  pip install pillow numpy

import base64
import io
import math
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

OUT = 320          # сторона фото в контакте, px — как у прежнего vcard-фото
SS = 3             # рисуем крупнее и уменьшаем: ровные края кругов
QUALITY = 86

# Доли стороны квадрата. Телефон обрезает фото контакта кругом радиусом 0.5,
# поэтому всё важное — внутри него: фото, цветная рамка и тонкое внешнее кольцо.
R_LINE, LINE_W = 0.468, 0.006
R_RING = 0.432
R_PHOTO = 0.414


def hex_rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def read_config(page):
    photo = re.search(r"page:\s*'data:image/\w+;base64,([^']+)'", page)
    vcf = re.search(r"vcfUrl:\s*'([^']+)'", page)
    block = re.search(r"themes:\s*\[(.*?)\n\s*\]", page, re.S)
    if not (photo and vcf and block):
        sys.exit('В index.html не нашлось photo.page, contacts.vcfUrl или themes')
    themes = []
    for line in block.group(1).splitlines():
        pairs = dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", line))
        if 'id' in pairs:
            themes.append(pairs)
    return base64.b64decode(photo.group(1)), vcf.group(1), themes


def gradient(t, stops):
    """t в [0,1] (массив) -> цвета по списку равномерных опорных цветов."""
    stops = [hex_rgb(s) for s in stops]
    pos = np.clip(t, 0, 1) * (len(stops) - 1)
    i = np.minimum(pos.astype(int), len(stops) - 2)
    f = (pos - i)[..., None]
    a = np.stack(stops)[i]
    b = np.stack(stops)[i + 1]
    return a * (1 - f) + b * f


def compose(photo_bytes, th):
    S = OUT * SS
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float64) + 0.5
    dx, dy = xx - S / 2, yy - S / 2
    r = np.hypot(dx, dy) / S
    neon = 'accent' in th
    main = th['accent'] if neon else th['gold']

    # фон: вертикальный градиент темы + мягкое свечение акцента за фото
    img = gradient(yy / S, [th['bg2'], th['bg']])
    glow = (0.26 if th.get('scheme') != 'light' else 0.18) * np.clip(1 - r / 0.5, 0, 1) ** 1.6
    img = img * (1 - glow[..., None]) + hex_rgb(main) * glow[..., None]

    # тонкое внешнее кольцо, как на странице
    line = (np.abs(r - R_LINE) < LINE_W / 2)[..., None] * 0.55
    img = img * (1 - line) + hex_rgb(main) * line

    # рамка: у золотых тем — диагональный градиент, у неоновых — круговой
    if neon:
        ang = (np.arctan2(dx, -dy) / (2 * math.pi)) % 1
        ring = gradient(ang, [th['accent'], th['accent2'], th['accent3'], th['accent']])
    else:
        k = math.radians(150)                       # как linear-gradient(150deg)
        proj = (dx * math.sin(k) - dy * math.cos(k)) / (2 * R_RING * S) + 0.5
        ring = gradient(proj, [th['goldSoft'], th['gold'], th['goldDeep'], th['goldSoft']])
    in_ring = (r <= R_RING)[..., None]
    img = np.where(in_ring, ring, img)

    canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB')

    # фото кругом внутри рамки
    d = round(2 * R_PHOTO * S)
    face = Image.open(io.BytesIO(photo_bytes)).convert('RGB').resize((d, d), Image.LANCZOS)
    mask = Image.fromarray(((np.hypot(*(np.mgrid[0:d, 0:d] + 0.5 - d / 2)) <= d / 2) * 255).astype(np.uint8), 'L')
    off = (S - d) // 2
    canvas.paste(face, (off, off), mask)

    out = io.BytesIO()
    canvas.resize((OUT, OUT), Image.LANCZOS).save(out, 'JPEG', quality=QUALITY, optimize=True)
    return out.getvalue()


def fold(line):
    """Как fold() на странице: строки по 75 символов, продолжение — с пробела."""
    if len(line) <= 75 or not line.isascii():   # не-ASCII не режем, как и страница
        return line
    parts = [line[:75]] + [' ' + line[i:i + 74] for i in range(75, len(line), 74)]
    return '\r\n'.join(parts)


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    page = (folder / 'index.html').read_text(encoding='utf-8')
    photo, vcf_name, themes = read_config(page)
    base = folder / vcf_name
    if not base.exists():
        sys.exit(f'Нет файла {base}: сначала выгрузите контакт через ?export')

    lines = base.read_bytes().decode('utf-8').replace('\r\n ', '').split('\r\n')
    lines = [l for l in lines if l and not l.startswith('PHOTO')]
    at = lines.index('END:VCARD')

    for n, th in enumerate(themes):
        jpeg = base64.b64encode(compose(photo, th)).decode('ascii')
        card = lines[:at] + ['PHOTO;ENCODING=b;TYPE=JPEG:' + jpeg] + lines[at:]
        name = vcf_name if n == 0 else re.sub(r'\.vcf$', f"-{th['id']}.vcf", vcf_name, flags=re.I)
        (folder / name).write_bytes(('\r\n'.join(fold(l) for l in card) + '\r\n').encode('utf-8'))
        print(f"{th['id']:10} -> {folder / name}  ({len(jpeg) * 3 // 4 // 1024} КБ фото)")


if __name__ == '__main__':
    main()
