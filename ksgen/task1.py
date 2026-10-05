"""Задание 1: СКС этажа — центры коммутации, розетки, кабельные каналы, панели, статические соединения."""
import itertools
from dataclasses import dataclass, field

from . import geom
from .common import Student, Variant, load_geometry

CHANNEL_INSET = 5      # px: кабельный канал идёт вдоль пунктира зоны, чуть внутри
CORNER_V = 9           # px: отступ розетки от угла на вертикальной стороне (подпись выше стрелки)
CORNER_H = 20          # px: на горизонтальной — подпись правее стрелки, не налезть на соседнюю сторону
SP_VERT = 6.5          # px: мин. шаг розеток на вертикальной стороне (подпись стоит горизонтально)
SP_HORZ = 19.0         # px: на горизонтальной — шире, чтобы подписи не налезали
MAX_LINK = 90          # м: предел длины статического соединения витой парой
VERT = 3               # м: запас на вертикальную прокладку
PANEL = 24             # портов RJ45 на коммутационной панели
CC_NAMES = "ABCD"


@dataclass
class Socket:
    zone: int
    num: int
    pos: tuple
    normal: tuple       # наружу, к стене зоны
    length: int = 0
    cc: str = ""
    port: str = ""      # P-A01-03

    @property
    def id(self):
        return f"S-{self.zone:02d}-{self.num:02d}"


@dataclass
class Link:
    a: str
    b: str
    length: int


@dataclass
class SKS:
    plan: geom.Plan
    plan_name: str
    cc: dict                    # имя → точка
    zone_cc: dict               # зона → имя ЦК
    channels: dict              # зона → контур канала
    exits: dict                 # зона → [трассы от канала до ЦК]
    sockets: dict               # зона → [Socket]
    cc_routes: dict = field(default_factory=dict)   # (A, B) → (трасса, длина м)
    panels: dict = field(default_factory=dict)      # имя ЦК → число панелей
    links: list = field(default_factory=list)       # статические соединения между ЦК
    _next: dict = field(default_factory=dict)       # следующий свободный порт панели
    split: tuple = None         # (зона, основной ЦК, второй ЦК, розеток ко второму) — если зона поделена

    def all_sockets(self):
        return [s for z in sorted(self.sockets) for s in self.sockets[z]]

    def take_port(self, cc):
        n = self._next.get(cc, 0)
        self._next[cc] = n + 1
        self.panels[cc] = max(self.panels.get(cc, 0), n // PANEL + 1)
        return f"P-{cc}{n // PANEL + 1:02d}-{n % PANEL + 1:02d}"

    def add_links(self, a, b, count):
        """Статические соединения между ЦК (под магистрали заданий 2–3)."""
        key = tuple(sorted((a, b)))
        _, length = self.cc_routes[key]
        for _ in range(count):
            self.links.append(Link(self.take_port(key[0]), self.take_port(key[1]), round(length) + VERT))


def _exit(plan, chan, zone, c, allow_zone):
    """Лучшая точка выхода из канала зоны к ЦК c: (трасса, длина)."""
    cands = list(chan)
    for a, b in geom.loop_edges(chan):
        if a[0] == b[0]:
            lo, hi = sorted((a[1], b[1]))
            cands.append((a[0], min(max(c[1], lo), hi)))
        else:
            lo, hi = sorted((a[0], b[0]))
            cands.append((min(max(c[0], lo), hi), a[1]))
    best = None
    for e in cands:
        pts, length = plan.route(e, c, allow=tuple(z for z in (zone, allow_zone) if z))
        if best is None or length < best[1]:
            best = (pts, length)
    return best


def build(st: Student, v: Variant) -> SKS:
    plan = geom.Plan(load_geometry(v.plan), v.L, v.W)
    chans = {z: geom.inset_loop(loop, CHANNEL_INSET) for z, loop in plan.zones.items()}
    perim = {z: geom.loop_perimeter(ch, plan) for z, ch in chans.items()}
    npts = dict(zip(range(1, 6), v.points))

    # выходы и оценки для каждой пары (зона, место ЦК)
    ex = {}
    for z in chans:
        for i, c in enumerate(plan.cc):
            ex[z, i] = _exit(plan, chans[z], z, c, plan.in_zone(*c))

    def zone_cost(z, i):
        r = ex[z, i][1]
        return r + perim[z] / 2 + VERT, npts[z] * (r + perim[z] / 4 + VERT)

    # перебор наборов мест ЦК (сначала по два, если длины не влезают — по три) и привязок зон к ЦК
    rng = st.rng("cc")
    options = []
    for k in (2, 3):
        for combo in itertools.combinations(range(len(plan.cc)), k):
            near = {z: [i for i in combo if zone_cost(z, i)[0] <= MAX_LINK - 2] for z in chans}
            if any(not near[z] for z in chans):
                continue
            for pick in itertools.product(*[near[z] for z in sorted(chans)]):
                assign = dict(zip(sorted(chans), pick))
                if set(assign.values()) != set(combo):
                    continue
                total = sum(zone_cost(z, assign[z])[1] for z in chans)
                options.append((total, combo, assign))
        if options:
            break
    if not options:   # ни один набор не укладывается в 90 м — берём с наименьшей наибольшей длиной
        for combo in itertools.combinations(range(len(plan.cc)), 2):
            assign = {z: min(combo, key=lambda i: zone_cost(z, i)[0]) for z in chans}
            worst = max(zone_cost(z, assign[z])[0] for z in chans)
            options.append((worst * 1e6, combo, assign))
    options.sort(key=lambda o: o[0])
    # от привязки зон к ЦК зависит, сколько сотрудников окажется в каждом ЦК, а от этого —
    # уложится ли задание 3 в бюджет: сначала варианты, где укладывается
    ranked = []
    for o in options[:60]:
        sock = {}
        for z, i in o[2].items():
            sock[i] = sock.get(i, 0) + npts[z]
        ranked.append((2 - _budget_ok(v, sock), o[0], o[1], o[2]))
    ranked.sort(key=lambda r: r[:2])

    def realize(combo, assign, split=None):
        """Собрать СКС; split = (зона, второй ЦК, сколько розеток к нему). None — если длины > 90 м."""
        order = sorted(combo, key=lambda i: (plan.cc[i][0], plan.cc[i][1]))
        name = {i: CC_NAMES[k] for k, i in enumerate(order)}
        sks = SKS(plan=plan, plan_name=v.plan, cc={name[i]: plan.cc[i] for i in combo},
                  zone_cc={z: name[assign[z]] for z in chans}, channels=chans,
                  exits={z: [ex[z, assign[z]][0]] for z in chans}, sockets={})
        srng = st.rng("sockets")
        for z in sorted(chans):
            sks.sockets[z] = _place_sockets(plan, chans[z], z, npts[z], ex[z, assign[z]], srng)
            for x in sks.sockets[z]:
                x.cc = sks.zone_cc[z]
        if split:
            z, j, t = split
            alt = {x.id: _length(plan, chans[z], x.pos, ex[z, j]) for x in sks.sockets[z]}
            moved = sorted(sks.sockets[z], key=lambda x: alt[x.id] - x.length)[:t]
            if any(alt[x.id] > MAX_LINK for x in moved):
                return None
            for x in moved:
                x.cc, x.length = name[j], alt[x.id]
            sks.exits[z].append(ex[z, j][0])
            sks.split = (z, name[assign[z]], name[j], t)
        for a_, b_ in itertools.combinations(sorted(sks.cc), 2):
            allow = tuple(x for x in (plan.in_zone(*sks.cc[a_]), plan.in_zone(*sks.cc[b_])) if x)
            sks.cc_routes[a_, b_] = plan.route(sks.cc[a_], sks.cc[b_], allow=allow)
        return sks

    if ranked[0][0]:
        # ни одна привязка целых зон не даёт уложиться в бюджет задания 3 — делим одну зону между двумя ЦК
        cands = []
        for _, total, combo, assign in ranked:
            base = {}
            for z, i in assign.items():
                base[i] = base.get(i, 0) + npts[z]
            for z in sorted(chans):
                for j in combo:
                    if j == assign[z]:
                        continue
                    for t in range(1, npts[z]):
                        sock = dict(base)
                        sock[assign[z]] -= t
                        sock[j] += t
                        lvl = _budget_ok(v, sock)
                        if lvl > 2 - ranked[0][0]:
                            cands.append((2 - lvl, total, t, combo, assign, (z, j, t)))
        cands.sort(key=lambda c: c[:3])
        for _, total, t, combo, assign, split in cands:
            sks = realize(combo, assign, split)
            if sks:
                return sks
    top = [r for r in ranked if r[0] == ranked[0][0] and r[1] <= ranked[0][1] * 1.12][:4]
    _, _, combo, assign = rng.choice(top)
    return realize(combo, assign)


def _length(plan, chan, pos, exit_):
    """Длина кабеля от розетки в pos до ЦК через выход exit_ = (трасса, длина трассы)."""
    perim = geom.loop_perimeter(chan, plan)
    s_exit, _ = geom.project_s(chan, plan, exit_[0][0])
    sp, _ = geom.project_s(chan, plan, pos)
    d = (sp - s_exit) % perim
    return max(round(min(d, perim - d) + exit_[1] + VERT), VERT + 1)


def _budget_ok(v: Variant, sockets_cc: dict) -> int:
    """Есть ли распределение сотрудников по ЦК (не больше розеток в ЦК), при котором
    самый дешёвый набор коммутаторов задания 3 укладывается в бюджет:
    2 — да, с портами под R-01/R-02 на L3; 1 — только без них; 0 — нет."""
    from .task3 import cheapest
    ccs = sorted(sockets_cc)
    total = sum(v.users)
    if len(ccs) != 2:
        return 2
    a, b = ccs
    best = 0
    for ua in range(max(0, total - sockets_cc[b]), min(sockets_cc[a], total) + 1):
        ub = total - ua
        big = a if ua >= ub else b
        top = cheapest(ccs, {c: n for c, n in ((a, ua), (b, ub)) if n}, [big] * 4, v.budget)
        if top and top[0][0] <= v.budget:
            best = max(best, 2 if top[0][4] else 1)
            if best == 2:
                break
    return best


def assign_panels(sks: SKS):
    """Порты панелей под розетки: в каждом ЦК подряд по зонам."""
    for z in sorted(sks.sockets):
        for s in sks.sockets[z]:
            s.port = sks.take_port(s.cc)


def _place_sockets(plan, chan, zone, n, exit_, rng):
    edges = geom.loop_edges(chan)
    e_pt = exit_[0][0]
    s_exit, _ = geom.project_s(chan, plan, e_pt)
    perim = geom.loop_perimeter(chan, plan)
    rlen = exit_[1]

    lens = [abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in edges]
    vert = [a[0] == b[0] for a, b in edges]
    scale = 1.0
    while True:
        cap = []
        for l, ve in zip(lens, vert):
            sp = (SP_VERT if ve else SP_HORZ) * scale
            usable = l - 2 * (CORNER_V if ve else CORNER_H)
            cap.append(int(usable // sp) + 1 if usable > 0 else 0)
        if sum(cap) >= n:
            break
        scale *= 0.85
    # раскладка пропорционально ёмкости сторон (метод наибольших остатков)
    tot = sum(cap)
    raw = [n * c / tot for c in cap]
    cnt = [min(int(r), c) for r, c in zip(raw, cap)]
    rest = sorted(range(len(cap)), key=lambda k: raw[k] - int(raw[k]), reverse=True)
    while sum(cnt) < n:
        for k in rest:
            if sum(cnt) < n and cnt[k] < cap[k]:
                cnt[k] += 1

    socks = []
    for k, ((a, b), m) in enumerate(zip(edges, cnt)):
        if not m:
            continue
        l = lens[k]
        c = CORNER_V if vert[k] else CORNER_H
        nx, ny = geom._inner_normal(a, b)
        for j in range(m):
            t = (c + (j + 0.5) * (l - 2 * c) / m) / l
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            socks.append(Socket(zone=zone, num=0, pos=p, normal=(-nx, -ny)))
    # нумерация от точки выхода к ЦК, в одну из сторон обхода
    cw = rng.random() < 0.5
    arcs = []
    for s in socks:
        sp, _ = geom.project_s(chan, plan, s.pos)
        d = (sp - s_exit) % perim
        arcs.append((d if cw else (perim - d) % perim, s, min(d, perim - d)))
    arcs.sort(key=lambda t: t[0])
    for i, (_, s, along) in enumerate(arcs, 1):
        s.num = i
        s.length = max(round(along + rlen + VERT), VERT + 1)
    return [t[1] for t in arcs]
