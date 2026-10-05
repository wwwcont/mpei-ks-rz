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
    def render(self, path, legend=None, columns=2):
        """Коммутаторы — сеткой в columns колонок (по строкам). Связи коммутатор — коммутатор идут по
        вертикальным каналам в промежутке между колонками, к значкам — по каналам у внешнего края колонки."""
        nodes = {n["key"]: n for n in self.nodes}
        col = {n["key"]: (i % columns if columns > 1 else 0) for i, n in enumerate(self.nodes)}
        row = {n["key"]: (i // columns if columns > 1 else i) for i, n in enumerate(self.nodes)}
        # полосы: сколько концов связей выходит вверх/вниз у каждого коммутатора
        lanes = {k: {"top": 0, "bottom": 0} for k in nodes}
        ends = []
        for li, l in enumerate(self.links):
            for e in ("a", "b"):
                ref = l[e]
                if isinstance(ref, tuple):
                    nk, port = ref
                    side = FACE[nodes[nk]["type"]]["ports"][str(port)]["side"]
                    ends.append((li, e, nk, port, side, lanes[nk][side]))
                    lanes[nk][side] += 1
        icons_of = {k: [i for i in self.icons if i["node"] == k] for k in nodes}
        icon_side = {i["key"]: col[i["node"]] for i in self.icons}   # 0 — слева, 1 — справа

        def is_sw(ref):
            return isinstance(ref, tuple)
        n_mid = sum(1 for l in self.links if is_sw(l["a"]) and is_sw(l["b"]))
        side_links = [l for l in self.links if not (is_sw(l["a"]) and is_sw(l["b"]))]

        def link_side(l):
            ref = l["b"] if is_sw(l["a"]) else l["a"]
            return icon_side[ref]
        n_left = sum(1 for l in side_links if link_side(l) == 0)
        n_right = len(side_links) - n_left

        f_icon = font(19)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

        def icons_w(side):
            labels = [probe.textlength(i["label"], font=f_icon) for i in self.icons
                      if icon_side[i["key"]] == side and i["kind"] != "router"]
            return 120 + int(max(labels + [60])) if any(icon_side[i["key"]] == side for i in self.icons) else 20
        cloud_w = 260 if self.cloud else 0
        left_w = cloud_w + icons_w(0)
        plate_w = max(FACE[n["type"]]["size"][0] for n in self.nodes)
        x_left_chan = left_w + 10
        x_col = [x_left_chan + n_left * CHAN + 30]
        x_mid_chan = x_col[0] + plate_w + 30
        if columns > 1:
            x_col.append(x_mid_chan + n_mid * CHAN + 30)
            x_right_chan = x_col[1] + plate_w + 30
        else:
            x_right_chan = x_mid_chan + n_mid * CHAN + 10
        x_right_icons = x_right_chan + n_right * CHAN + 30
        width = x_right_icons + (icons_w(1) if columns > 1 else 0) + 20

        # вертикальная раскладка по строкам
        pos = {}
        y = 20
        n_rows = max(row.values()) + 1
        for r in range(n_rows):
            keys = [k for k in nodes if row[k] == r]
            tops = {k: 34 + LANE * lanes[k]["top"] + 8 for k in keys}
            top = max(tops.values())
            block = 0
            for k in keys:
                h = FACE[nodes[k]["type"]]["size"][1]
                block = max(block, top + h + LANE * lanes[k]["bottom"] + 30, top + ICON_H * len(icons_of[k]) + 10)
            for k in keys:
                pos[k] = (x_col[col[k]], y + top)
                nodes[k]["block"] = (y, y + block)
            y += block + 10
        legend_lines = _wrap(legend, font(20), width - 40) if legend else []
        height = y + 30 * len(legend_lines) + 20

        im = Image.new("RGB", (width, height), "white")
        d = ImageDraw.Draw(im)
        f_title = font(24)
        f_box = font(15)

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
                        d.text((x + (box[0] + box[2]) / 2, yy + (box[1] + box[3]) / 2), str(text),
                               font=f_box, fill=BLUE, anchor="mm")

        # значки: у левой колонки — слева, у правой — справа
        ipos = {}
        for k, lst in icons_of.items():
            x, yy = pos[k]
            for j, ic in enumerate(lst):
                cy = yy + ICON_H * j + ICON_H // 2 - 10
                if icon_side[ic["key"]] == 0:
                    ix = left_w - 60
                    ipos[ic["key"]] = (ix + 50, cy)
                    _icon(d, ic["kind"], ix, cy, ic["label"], f_icon)
                else:
                    ix = x_right_icons + 40
                    ipos[ic["key"]] = (ix - 50, cy)
                    _icon(d, ic["kind"], ix, cy, ic["label"], f_icon, right=True)

        def port_exit(nk, port):
            x, yy = pos[nk]
            info = FACE[nodes[nk]["type"]]
            r = info["ports"][str(port)]["rect"]
            cx = x + (r[0] + r[2]) / 2
            if info["ports"][str(port)]["side"] == "top":
                return (cx, yy + r[1]), yy, -1
            return (cx, yy + r[3]), yy + info["size"][1], 1

        lane_of = {(li, e): (nk, side, ln) for li, e, nk, port, side, ln in ends}
        k_mid = k_left = k_right = 0
        bubbles = []
        for li, l in enumerate(self.links):
            if is_sw(l["a"]) and is_sw(l["b"]):
                cx = x_mid_chan + CHAN * k_mid
                k_mid += 1
            elif link_side(l) == 0:
                cx = x_left_chan + CHAN * (n_left - 1 - k_left)
                k_left += 1
            else:
                cx = x_right_chan + CHAN * k_right
                k_right += 1
            route = []
            for e in ("a", "b"):
                ref = l[e]
                if is_sw(ref):
                    nk, port = ref
                    (px, py), edge, sgn = port_exit(nk, port)
                    _, side, ln = lane_of[(li, e)]
                    ly = edge + sgn * (LANE * (ln + 1))
                    seg = [(px, py), (px, ly), (cx, ly)]
                    lab = l["la"] if e == "a" else l["lb"]
                    if lab:
                        bubbles.append(((px, (py + edge) / 2), lab))
                else:
                    ix, iy = ipos[ref]
                    seg = [(ix, iy), (cx, iy)]
                route.append(seg)
            _poly(d, route[0] + list(reversed(route[1])), l["width"], l["dashed"])
        role_color = {"К": (0, 130, 0), "Н": (120, 40, 160), "Б": RED}
        for (bx, by), lab in bubbles:
            r = 13
            c = role_color.get(lab, RED)
            d.ellipse([bx - r, by - r, bx + r, by + r], fill="white", outline=c, width=2)
            d.text((bx, by), lab, font=font(17), fill=c, anchor="mm")

        if self.cloud:
            routers = [ipos[k] for k in self.cloud]
            cy = sum(p[1] for p in routers) / len(routers)
            cx = 120
            d.ellipse([cx - 100, cy - 45, cx + 100, cy + 45], outline=INK, width=3, fill=(245, 245, 255))
            d.text((cx, cy), "Internet", font=font(26), fill=INK, anchor="mm")
            for (x, yy) in routers:
                d.line([(x - 76, yy), (cx + 100, cy)], fill=INK, width=3)

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


def _icon(d, kind, x, cy, label, f, right=False):
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
    d.text((x + 32 if right else x - 32 - tw, cy - 11), label, font=f, fill=INK)


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
