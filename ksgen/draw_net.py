"""Схемы сетей (задания 2–4) на изображениях коммутаторов из методички.

Коммутаторы — столбиком; связи — ортогональные: от порта вертикально в «полосу» над/под
коммутатором, по ней к вертикальному каналу (справа — связи между коммутаторами,
слева — к серверам и маршрутизаторам), по каналу к другому концу.
"""
import json

from PIL import Image, ImageDraw, ImageFont

from .common import EQUIPMENT, ROOT

FACE = json.loads((ROOT / "ksgen" / "faceplates.json").read_text())
FONT = ROOT / "fonts" / "LiberationSans-Regular.ttf"
LANE = 13          # шаг полос над/под коммутатором
CHAN = 14          # шаг вертикальных каналов
ICON_H = 96        # место под значок сервера по вертикали
INK = (0, 0, 0)
RED = (190, 0, 0)
BLUE = (20, 60, 170)


def font(size):
    return ImageFont.truetype(str(FONT), size)


class Diagram:
    def __init__(self):
        self.nodes = []      # dict(key, type, title, boxes)
        self.icons = []      # dict(key, kind, label, node)
        self.links = []      # dict(a, b, dashed, la, lb)
        self.cloud = None

    def node(self, key, ftype, title, boxes=None):
        self.nodes.append(dict(key=key, type=ftype, title=title, boxes=boxes or {}))

    def icon(self, key, kind, label, node):
        self.icons.append(dict(key=key, kind=kind, label=label, node=node))

    def link(self, a, b, dashed=False, la="", lb="", width=4):
        self.links.append(dict(a=a, b=b, dashed=dashed, la=la, lb=lb, width=width))

    # ------------------------------------------------------------------
    def render(self, path, legend=None):
        nodes = {n["key"]: n for n in self.nodes}
        icons = {i["key"]: i for i in self.icons}
        # полосы: сколько концов связей выходит вверх/вниз у каждого коммутатора
        lanes = {k: {"top": 0, "bottom": 0} for k in nodes}
        ends = []   # (link idx, end 'a'/'b', node, port, side, lane)
        for li, l in enumerate(self.links):
            for e in ("a", "b"):
                ref = l[e]
                if isinstance(ref, tuple):
                    nk, port = ref
                    side = FACE[nodes[nk]["type"]]["ports"][str(port)]["side"]
                    ends.append((li, e, nk, port, side, lanes[nk][side]))
                    lanes[nk][side] += 1
        icons_of = {k: [i for i in self.icons if i["node"] == k] for k in nodes}
        n_left = sum(1 for l in self.links if not (isinstance(l["a"], tuple) and isinstance(l["b"], tuple)))
        n_right = len(self.links) - n_left

        cloud_w = 260 if self.cloud else 0
        f_icon = font(19)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        icon_w = 120 + int(max([probe.textlength(i["label"], font=f_icon) for i in self.icons if i["kind"] != "router"] + [60]))
        x_left_chan = cloud_w + icon_w + 20
        x_plate = x_left_chan + n_left * CHAN + 30
        plate_w = max(FACE[n["type"]]["size"][0] for n in self.nodes)
        x_right_chan = x_plate + plate_w + 30
        width = x_right_chan + n_right * CHAN + 30

        # вертикальная раскладка
        pos = {}
        y = 20
        for n in self.nodes:
            k = n["key"]
            h = FACE[n["type"]]["size"][1]
            top = 34 + LANE * lanes[k]["top"] + 8
            bottom = LANE * lanes[k]["bottom"] + 30
            block = max(top + h + bottom, top + ICON_H * len(icons_of[k]) + 10)
            pos[k] = (x_plate, y + top)
            n["block"] = (y, y + block)
            y += block + 10
        legend_lines = _wrap(legend, font(20), width - 40) if legend else []
        height = y + 30 * len(legend_lines) + 20

        im = Image.new("RGB", (width, height), "white")
        d = ImageDraw.Draw(im)
        f_title = font(24)
        f_box = font(15)

        # коммутаторы
        for n in self.nodes:
            k = n["key"]
            x, yy = pos[k]
            face = Image.open(EQUIPMENT / FACE[n["type"]]["image"]).convert("RGB")
            im.paste(face, (x, yy))
            d.text((x, n["block"][0] + 4), n["title"], font=f_title, fill=INK, stroke_width=1, stroke_fill=INK)
            for port, (mode, vlan) in n["boxes"].items():
                pinfo = FACE[n["type"]]["ports"][str(port)]
                for box, text in ((pinfo.get("mode_box"), mode), (pinfo.get("vlan_box"), vlan)):
                    if box and text != "":
                        cx = x + (box[0] + box[2]) / 2
                        cy = yy + (box[1] + box[3]) / 2
                        d.text((cx, cy), str(text), font=f_box, fill=BLUE, anchor="mm")

        # значки слева от своего коммутатора
        ipos = {}
        for k, lst in icons_of.items():
            x, yy = pos[k]
            for j, ic in enumerate(lst):
                cy = yy + ICON_H * j + ICON_H // 2 - 10
                ipos[ic["key"]] = (cloud_w + icon_w - 10, cy)
                _icon(d, ic["kind"], cloud_w + icon_w - 60, cy, ic["label"], f_icon)

        def port_exit(nk, port):
            x, yy = pos[nk]
            info = FACE[nodes[nk]["type"]]
            r = info["ports"][str(port)]["rect"]
            cx = x + (r[0] + r[2]) / 2
            if info["ports"][str(port)]["side"] == "top":
                return (cx, yy + r[1]), yy, -1
            return (cx, yy + r[3]), yy + info["size"][1], 1

        lane_of = {(li, e): (nk, side, ln) for li, e, nk, port, side, ln in ends}
        right_k = left_k = 0
        bubbles = []
        for li, l in enumerate(self.links):
            pts_a = pts_b = None
            if isinstance(l["a"], tuple) and isinstance(l["b"], tuple):
                cxr = x_right_chan + CHAN * right_k
                right_k += 1
            else:
                cxr = x_left_chan + CHAN * (n_left - 1 - left_k)
                left_k += 1
            route = []
            for e in ("a", "b"):
                ref = l[e]
                if isinstance(ref, tuple):
                    nk, port = ref
                    (px, py), edge, sgn = port_exit(nk, port)
                    _, side, ln = lane_of[(li, e)]
                    ly = edge + sgn * (LANE * (ln + 1))
                    seg = [(px, py), (px, ly), (cxr, ly)]
                    lab = l["la"] if e == "a" else l["lb"]
                    if lab:
                        bubbles.append(((px, (py + edge) / 2), lab))
                else:
                    ix, iy = ipos[ref]
                    seg = [(ix, iy), (cxr, iy)]
                route.append(seg)
            pts = route[0] + list(reversed(route[1]))
            _poly(d, pts, l["width"], l["dashed"])
        for (bx, by), lab in bubbles:
            r = 13
            d.ellipse([bx - r, by - r, bx + r, by + r], fill="white", outline=RED, width=2)
            d.text((bx, by), lab, font=font(17), fill=RED, anchor="mm")

        if self.cloud:
            routers = [ipos[k] for k in self.cloud]
            cy = sum(p[1] for p in routers) / len(routers)
            cx = 120
            d.ellipse([cx - 100, cy - 45, cx + 100, cy + 45], outline=INK, width=3, fill=(245, 245, 255))
            d.text((cx, cy), "Internet", font=font(26), fill=INK, anchor="mm")
            for (x, yy) in routers:
                d.line([(cloud_w + icon_w - 86, yy), (cx + 100, cy)], fill=INK, width=3)

        for i, line in enumerate(legend_lines):
            d.text((20, height - 20 - 30 * (len(legend_lines) - i)), line, font=font(20), fill=INK)
        im.save(path)


def _poly(d, pts, width, dashed):
    if not dashed:
        d.line(pts, fill=INK, width=width, joint="curve")
        return
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        length = abs(x1 - x0) + abs(y1 - y0)
        step = 14
        k = 0
        while k < length:
            t0, t1 = k / length, min(k + 9, length) / length
            d.line([(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0), (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)],
                   fill=INK, width=width)
            k += step


def _icon(d, kind, x, cy, label, f):
    """Значок: сервер (корпус), маршрутизатор (шайба). Подпись слева."""
    if kind == "router":
        d.rounded_rectangle([x - 26, cy - 16, x + 26, cy + 16], radius=10, outline=INK, width=3, fill=(235, 225, 245))
        d.line([x - 12, cy, x + 12, cy], fill=INK, width=2)
        d.line([x, cy - 9, x, cy + 9], fill=INK, width=2)
    else:
        d.rectangle([x - 20, cy - 30, x + 20, cy + 30], outline=INK, width=3, fill=(240, 236, 220))
        for k in range(3):
            d.line([x - 13, cy - 20 + 9 * k, x + 13, cy - 20 + 9 * k], fill=INK, width=2)
        if kind == "db":
            d.ellipse([x - 9, cy + 6, x + 9, cy + 22], outline=INK, width=2, fill=(170, 200, 230))
    if kind == "router":
        d.text((x, cy - 20), label, font=f, fill=INK, anchor="md")
        return
    tw = d.textlength(label, font=f)
    d.text((x - 32 - tw, cy - 11), label, font=f, fill=INK)


def _wrap(text, f, width):
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if probe.textlength(t, font=f) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur]
