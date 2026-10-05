"""Рисунки задания 1: план этажа с центрами коммутации, розетками и кабельными каналами."""
from PIL import Image, ImageDraw, ImageFont

from .common import PLANS, ROOT
from .task1 import CHANNEL_INSET, SKS

K = 3                    # увеличение исходного плана
FONT = ROOT / "fonts" / "LiberationSans-Regular.ttf"
INK = (0, 0, 0)
CHAN = (20, 60, 170)
CCRED = (190, 0, 0)


def font(size):
    return ImageFont.truetype(str(FONT), size)


def _base(sks: SKS):
    im = Image.open(PLANS / f"{sks.plan_name}.jpg").convert("RGB")
    return im.resize((im.width * K, im.height * K), Image.LANCZOS)


def _sc(p):
    return (p[0] * K, p[1] * K)


def _cc_marker(d, sks, f):
    for name, p in sks.cc.items():
        x, y = _sc(p)
        r = 22
        d.rectangle([x - r, y - r, x + r, y + r], outline=CCRED, width=5)
        d.line([x - r, y - r, x + r, y + r], fill=CCRED, width=4)
        d.line([x - r, y + r, x + r, y - r], fill=CCRED, width=4)
        d.text((x + r + 6, y - r - 4), name, font=f, fill=CCRED, stroke_width=1, stroke_fill=CCRED)


def draw_plan(sks: SKS, path, sockets=True):
    """Рис.: конфигурация зон (sockets=False) или полный план СКС."""
    im = _base(sks)
    d = ImageDraw.Draw(im)
    if not sockets:
        im.save(path)
        return
    small = font(15)
    for z, chan in sks.channels.items():
        pts = [_sc(p) for p in chan] + [_sc(chan[0])]
        d.line(pts, fill=CHAN, width=4, joint="curve")
        for route in sks.exits[z]:
            d.line([_sc(p) for p in route], fill=CHAN, width=4, joint="curve")
    for (a, b), (pts, _) in sks.cc_routes.items():
        d.line([_sc(p) for p in pts], fill=CCRED, width=3, joint="curve")
    for z, socks in sks.sockets.items():
        for s in socks:
            x, y = _sc(s.pos)
            nx, ny = s.normal
            ln = CHANNEL_INSET * K - 2
            ex, ey = x + nx * ln, y + ny * ln
            d.line([x, y, ex, ey], fill=INK, width=2)
            # наконечник
            if nx:
                d.polygon([(ex, ey), (ex - nx * 6, ey - 4), (ex - nx * 6, ey + 4)], fill=INK)
            else:
                d.polygon([(ex, ey), (ex - 4, ey - ny * 6), (ex + 4, ey - ny * 6)], fill=INK)
            label = s.id
            tw = d.textlength(label, font=small)
            if nx < 0:
                tx, ty = x + 3, y - 17
            elif nx > 0:
                tx, ty = x - tw - 3, y - 17
            elif ny < 0:
                tx, ty = x + 4, y + 3
            else:
                tx, ty = x + 4, y - 19
            d.text((tx, ty), label, font=small, fill=INK)
    _cc_marker(d, sks, font(30))
    im.save(path)
