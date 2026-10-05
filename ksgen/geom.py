"""Геометрия плана этажа: контуры зон, ортогональные трассы, длины в метрах.

Координаты — пиксели исходного JPG плана (geometry.json). Масштаб по осям свой:
bbox здания соответствует L × W метров.
"""
import numpy as np
from PIL import Image, ImageDraw


class Plan:
    def __init__(self, geo: dict, L: float, W: float):
        self.geo = geo
        x0, y0, x1, y1 = geo["bbox"]
        self.sx = L / (x1 - x0)
        self.sy = W / (y1 - y0)
        self.zones = {int(k): union_loop(v) for k, v in geo["zones"].items()}
        self.zone_rects = {int(k): v for k, v in geo["zones"].items()}
        self.cc = [tuple(p) for p in geo["cc"]]
        # маска здания: внутри наружной стены, с отступом от неё
        w = x1 + 10
        h = y1 + 10
        self.mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(self.mask).polygon([tuple(p) for p in geo["outline"]], fill=255)
        self.inb = np.array(self.mask) > 0
        self.mw, self.mh = w, h
        # карта зон (с отступом 3 px внутрь от пунктира): номер зоны или 0
        self.zmap = np.zeros((h, w), np.int16)
        for z, rects in self.zone_rects.items():
            for r in rects:
                self.zmap[r[1] + 3:r[3] - 2, r[0] + 3:r[2] - 2] = z

    # ---- метрика ----
    def dist(self, a, b) -> float:
        return abs(a[0] - b[0]) * self.sx + abs(a[1] - b[1]) * self.sy

    def path_len(self, pts) -> float:
        return sum(self.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))

    def inside(self, x, y) -> bool:
        x, y = int(round(x)), int(round(y))
        return 0 <= x < self.mw and 0 <= y < self.mh and self.inb[y, x]

    def in_zone(self, x, y):
        x, y = int(round(x)), int(round(y))
        z = int(self.zmap[y, x]) if 0 <= x < self.mw and 0 <= y < self.mh else 0
        return z or None

    def seg_cost(self, a, b, allow=()):
        """Длина осевого отрезка + число пикселей вне здания и внутри чужих зон."""
        x0, y0 = int(round(a[0])), int(round(a[1]))
        x1, y1 = int(round(b[0])), int(round(b[1]))
        if x0 == x1:
            lo, hi = sorted((y0, y1))
            ins = self.inb[lo:hi + 1, x0] if 0 <= x0 < self.mw else np.zeros(0, bool)
            zs = self.zmap[lo:hi + 1, x0] if 0 <= x0 < self.mw else np.zeros(0, int)
            n = hi - lo + 1
        else:
            lo, hi = sorted((x0, x1))
            ins = self.inb[y0, lo:hi + 1] if 0 <= y0 < self.mh else np.zeros(0, bool)
            zs = self.zmap[y0, lo:hi + 1] if 0 <= y0 < self.mh else np.zeros(0, int)
            n = hi - lo + 1
        bad = n - int(ins.sum())
        inzone = int(((zs > 0) & ~np.isin(zs, list(allow) or [0])).sum())
        return self.dist(a, b), bad, inzone

    def route(self, a, b, allow=()):
        """Ортогональная трасса a→b внутри здания (≤ 3 отрезков), по возможности в обход чужих зон."""
        a = (round(a[0]), round(a[1]))
        b = (round(b[0]), round(b[1]))
        cands = [[a, (b[0], a[1]), b], [a, (a[0], b[1]), b]]
        x0, y0, x1, y1 = self.geo["bbox"]
        for x in range(x0 + 4, x1 - 3, 4):
            cands.append([a, (x, a[1]), (x, b[1]), b])
        for y in range(y0 + 4, y1 - 3, 4):
            cands.append([a, (a[0], y), (b[0], y), b])
        best = None
        for c in cands:
            pts = [p for i, p in enumerate(c) if i == 0 or p != c[i - 1]]
            length = bad = inzone = 0
            for i in range(len(pts) - 1):
                l, bd, iz = self.seg_cost(pts[i], pts[i + 1], allow)
                length += l
                bad += bd
                inzone += iz
            score = (bad > 0, inzone * 0.5 + length, len(pts))
            if best is None or score < best[0]:
                best = (score, pts, length)
        return best[1], best[2]


def union_loop(rects):
    """Контур объединения прямоугольников (ортогональный многоугольник), обход по часовой стрелке
    в экранных координатах (y вниз). Возвращает список вершин без повтора первой."""
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})

    def cell_in(i, j):
        if i < 0 or j < 0 or i >= len(xs) - 1 or j >= len(ys) - 1:
            return False
        cx = (xs[i] + xs[i + 1]) / 2
        cy = (ys[j] + ys[j + 1]) / 2
        return any(r[0] < cx < r[2] and r[1] < cy < r[3] for r in rects)

    # направленные рёбра границы: внутренность справа при обходе по часовой (y вниз)
    edges = {}
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            if not cell_in(i, j):
                continue
            x0, x1, y0, y1 = xs[i], xs[i + 1], ys[j], ys[j + 1]
            if not cell_in(i, j - 1):
                edges[(x0, y0)] = edges.get((x0, y0), []) + [(x1, y0)]   # верх: слева направо
            if not cell_in(i + 1, j):
                edges[(x1, y0)] = edges.get((x1, y0), []) + [(x1, y1)]   # право: вниз
            if not cell_in(i, j + 1):
                edges[(x1, y1)] = edges.get((x1, y1), []) + [(x0, y1)]   # низ: справа налево
            if not cell_in(i - 1, j):
                edges[(x0, y1)] = edges.get((x0, y1), []) + [(x0, y0)]   # лево: вверх
    start = min(edges)  # верхний левый
    loop = [start]
    cur = start
    while True:
        nxt = edges[cur].pop()
        if nxt == start:
            break
        loop.append(nxt)
        cur = nxt
    # убрать вершины на прямой
    out = []
    n = len(loop)
    for k in range(n):
        p, c, q = loop[k - 1], loop[k], loop[(k + 1) % n]
        if (p[0] == c[0] == q[0]) or (p[1] == c[1] == q[1]):
            continue
        out.append(c)
    return out


def inset_loop(loop, d):
    """Сдвиг ортогонального контура внутрь на d (обход по часовой, y вниз → внутренность справа)."""
    n = len(loop)
    out = []
    for k in range(n):
        p, c, q = loop[k - 1], loop[k], loop[(k + 1) % n]
        n1 = _inner_normal(p, c)
        n2 = _inner_normal(c, q)
        out.append((c[0] + d * (n1[0] + n2[0]), c[1] + d * (n1[1] + n2[1])))
    return out


def _inner_normal(a, b):
    dx = (b[0] > a[0]) - (b[0] < a[0])
    dy = (b[1] > a[1]) - (b[1] < a[1])
    return (-dy, dx)  # поворот направо в экранных координатах


def loop_edges(loop):
    n = len(loop)
    return [(loop[k], loop[(k + 1) % n]) for k in range(n)]


def point_at(loop_pts, plan, s):
    """Точка контура на расстоянии s метров от вершины 0 (по обходу), и номер ребра."""
    edges = loop_edges(loop_pts)
    total = sum(plan.dist(a, b) for a, b in edges)
    s %= total
    for k, (a, b) in enumerate(edges):
        l = plan.dist(a, b)
        if s <= l or k == len(edges) - 1:
            t = s / l if l else 0
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), k
        s -= l
    raise AssertionError


def loop_perimeter(loop_pts, plan):
    return sum(plan.dist(a, b) for a, b in loop_edges(loop_pts))


def project_s(loop_pts, plan, p):
    """Ближайшая к p точка контура: (s в метрах от вершины 0, точка)."""
    best = None
    s0 = 0.0
    for a, b in loop_edges(loop_pts):
        l = plan.dist(a, b)
        if a[0] == b[0]:
            lo, hi = sorted((a[1], b[1]))
            q = (a[0], min(max(p[1], lo), hi))
        else:
            lo, hi = sorted((a[0], b[0]))
            q = (min(max(p[0], lo), hi), a[1])
        d = plan.dist(p, q)
        if best is None or d < best[0]:
            best = (d, s0 + plan.dist(a, q), q)
        s0 += l
    return best[1], best[2]
