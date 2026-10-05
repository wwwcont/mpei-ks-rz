"""Задание 2: базовая ЛВС на неинтеллектуальных коммутаторах со STP."""
import itertools
from dataclasses import dataclass, field

from .common import Student, Variant
from .task1 import SKS

TYPES = {"S12TF": (12, 15), "S24TF": (24, 20)}   # портов, у.е.
PREFIX = {"S12TF": "S12", "S24TF": "S24"}
RESERVED = 2   # на каждом коммутаторе группы: порт к корневому + порт резервной связи


@dataclass
class Switch:
    id: str
    type: str
    cc: str
    bid: int
    wg: int = 0                                   # 0 — корневой коммутатор отдела
    ports: dict = field(default_factory=dict)     # порт → (что подключено, роль STP)

    @property
    def cap(self):
        return TYPES[self.type][0]

    def free(self):
        return [p for p in range(1, self.cap + 1) if p not in self.ports]

    def pid(self, p):
        return f"{self.id}-{p:02d}"


@dataclass
class SwLink:
    a: Switch
    pa: int
    b: Switch
    pb: int
    kind: str              # uplink / backup
    ra: str = ""           # роль порта STP на стороне a
    rb: str = ""
    via: tuple = ()        # порты панелей (на стороне a, на стороне b), если ЦК разные

    @property
    def active(self):
        return "Б" not in (self.ra, self.rb)


@dataclass
class Server:
    name: str
    title: str
    cc: str
    sw: Switch = None
    port: int = 0


@dataclass
class LAN2:
    users: list                    # с учётом роста по WG-1..4
    placement: dict                # wg → [Socket]
    core: Switch
    access: list
    links: list
    servers: list
    user_ports: dict               # Socket.id → (Switch, порт)
    rows: list = field(default_factory=list)   # таблица динамических соединений

    @property
    def switches(self):
        return [self.core] + self.access


def place_users(st: Student, v: Variant, sks: SKS) -> dict:
    """Сотрудники по зонам. Сначала — уложиться в бюджет задания 3 (он зависит от того, сколько
    сотрудников в каждом ЦК), затем — группа в одном ЦК и в меньшем числе зон."""
    from .task3 import cheapest
    users = v.users
    zones = sorted(sks.sockets)
    ccs = sorted(sks.cc)
    by_sig = {}    # (сотрудники по ЦК, ЦК серверов групп) → (лучший балл, [варианты])
    for zperm in itertools.permutations(zones):
        seq = [s for z in zperm for s in sks.sockets[z]]
        zstart = {}
        for i, s in enumerate(seq):
            zstart.setdefault(s.zone, i)
        for wperm in itertools.permutations(range(4)):
            for skip in range(16):
                pos, res, ok = 0, {}, True
                for k, w in enumerate(wperm):
                    if skip >> k & 1 and pos < len(seq) and zstart[seq[pos].zone] != pos:
                        nz = [zstart[z] for z in zperm if zstart[z] > pos]
                        pos = nz[0] if nz else len(seq)
                    part = seq[pos:pos + users[w]]
                    if len(part) < users[w]:
                        ok = False
                        break
                    res[w] = part
                    pos += users[w]
                if not ok:
                    continue
                score = 0
                ucc = dict.fromkeys(ccs, 0)
                srv = []
                for w in range(4):
                    cnt = {}
                    for s in res[w]:
                        cnt[s.cc] = cnt.get(s.cc, 0) + 1
                    ucc_w = cnt
                    for c, n in cnt.items():
                        ucc[c] += n
                    srv.append(max(sorted(cnt), key=lambda c: cnt[c]))
                    score += 1000 * (len(cnt) - 1) + 10 * (len({s.zone for s in res[w]}) - 1)
                sig = (tuple(ucc[c] for c in ccs), tuple(srv))
                cur = by_sig.get(sig)
                if cur is None or score < cur[0]:
                    by_sig[sig] = cur = (score, [])
                if score == cur[0] and len(cur[1]) < 200:
                    key = tuple(tuple(s.id for s in res[w]) for w in range(4))
                    cur[1].append((key, res))
    ranked = []
    for (ucc, srv), (score, items) in by_sig.items():
        top = cheapest(ccs, {c: n for c, n in zip(ccs, ucc) if n}, list(srv), v.budget)
        cost = top[0][0] if top else 10 ** 6
        no_reserve = not top or not top[0][4]
        ranked.append((cost > v.budget, no_reserve, score, cost, items))
    ranked.sort(key=lambda r: r[:4])
    best = ranked[0][:3]
    pool = dict(kv for r in ranked if r[:3] == best for kv in r[4])
    keys = sorted(pool)
    choice = pool[st.rng("placement").choice(keys)]
    return {w + 1: sorted(choice[w], key=lambda s: (s.zone, s.num)) for w in range(4)}


def _pick_switches(m):
    """Минимальный по стоимости набор коммутаторов на m портов (плюс резерв на каждом)."""
    best = None
    for k in (1, 2, 3):
        for combo in itertools.combinations_with_replacement(("S24TF", "S12TF"), k):
            capacity = sum(TYPES[t][0] - RESERVED for t in combo)
            cost = sum(TYPES[t][1] for t in combo)
            if capacity >= m and (best is None or (cost, k) < best[0]):
                best = ((cost, k), list(combo))
    return best[1]


def build(st: Student, v: Variant, sks: SKS) -> LAN2:
    placement = place_users(st, v, sks)
    rng = st.rng("lan2")

    # части групп по ЦК; сервер группы — в ЦК, где больше её сотрудников
    parts = []
    servers = []
    for w in range(1, 5):
        by_cc = {}
        for s in placement[w]:
            by_cc.setdefault(s.cc, []).append(s)
        main_cc = max(sorted(by_cc), key=lambda c: len(by_cc[c]))
        for cc in sorted(by_cc):
            parts.append((w, cc, by_cc[cc], cc == main_cc))
        servers.append(Server(f"WG-{w}-server", f"Сервер WG-{w}", main_cc))

    access, n = [], 1
    user_ports = {}
    for w, cc, socks, has_srv in parts:
        types = _pick_switches(len(socks) + has_srv)
        group = []
        for t in types:
            n += 1
            group.append(Switch(id=f"{PREFIX[t]}-{n:02d}", type=t, cc=cc, bid=n, wg=w))
        if has_srv:
            servers[w - 1].sw = group[0]
        # сотрудники — с порта 1 подряд, по коммутаторам группы
        queue = list(socks)
        for i, sw in enumerate(group):
            room = sw.cap - RESERVED - (1 if has_srv and i == 0 else 0)
            for p in range(1, room + 1):
                if not queue:
                    break
                s = queue.pop(0)
                sw.ports[p] = (s.port, "")
                user_ports[s.id] = (sw, p)
        access += group

    # корневой коммутатор — в ЦК, где больше коммутаторов групп
    cnt = {c: sum(1 for a in access if a.cc == c) for c in sks.cc}
    top = max(cnt.values())
    core_cc = rng.choice(sorted(c for c in cnt if cnt[c] == top))
    core_type = "S12TF" if len(access) + 2 <= 12 else "S24TF"
    core = Switch(id=f"{PREFIX[core_type]}-01", type=core_type, cc=core_cc, bid=1)
    common = [Server("File-server-main", "Общий сервер отдела", core_cc),
              Server("DB-server-main", "Сервер базы данных отдела", core_cc)]
    common[0].sw, common[0].port = core, core.cap - 1
    common[1].sw, common[1].port = core, core.cap
    core.ports[core.cap - 1] = (common[0].name, "Н")
    core.ports[core.cap] = (common[1].name, "Н")

    links = []
    for k, a in enumerate(access, 1):
        links.append(SwLink(a=a, pa=a.cap, b=core, pb=k, kind="uplink", ra="К", rb="Н"))

    # резервные связи: пары внутри ЦК, остаток — между ЦК; нечётный — к коммутатору со свободным портом
    singles = []
    for cc in sorted(sks.cc):
        group = [a for a in access if a.cc == cc]
        for i in range(0, len(group) - 1, 2):
            links.append(SwLink(a=group[i], pa=0, b=group[i + 1], pb=0, kind="backup"))
        if len(group) % 2:
            singles.append(group[-1])
    while len(singles) >= 2:
        links.append(SwLink(a=singles.pop(0), pa=0, b=singles.pop(0), pb=0, kind="backup"))
    if singles:
        x = singles[0]
        used = {}
        for a in access:
            used[a.id] = len(a.ports) + RESERVED + (1 if any(s.sw is a for s in servers) else 0)
        cands = [a for a in access if a is not x and used[a.id] < a.cap]
        cands.sort(key=lambda a: (a.cc != x.cc, -(a.cap - used[a.id]), a.bid))
        links.append(SwLink(a=x, pa=0, b=cands[0], pb=0, kind="backup"))

    # порты резервных связей — сверху вниз под портом к корневому; сервер группы — ниже них
    nxt = {a.id: a.cap - 1 for a in access}
    for l in links:
        if l.kind == "backup":
            l.pa, nxt[l.a.id] = nxt[l.a.id], nxt[l.a.id] - 1
            l.pb, nxt[l.b.id] = nxt[l.b.id], nxt[l.b.id] - 1
            lo, hi = (l.a, l.b) if l.a.bid < l.b.bid else (l.b, l.a)
            l.ra, l.rb = ("Н", "Б") if lo is l.a else ("Б", "Н")
    for s in servers:
        s.port = nxt[s.sw.id]
        nxt[s.sw.id] -= 1
        s.sw.ports[s.port] = (s.name, "")
    for l in links:
        l.a.ports[l.pa] = (l.b.pid(l.pb), l.ra)
        l.b.ports[l.pb] = (l.a.pid(l.pa), l.rb)
    for a in access:
        busy = [p for p, (t, r) in a.ports.items() if not r and not t.endswith(("-server", "-main"))]
        assert max(busy) < min(p for p, (t, r) in a.ports.items() if r or t.endswith(("-server", "-main"))), a.id

    # магистрали между ЦК — через статические соединения СКС
    need = {}
    for l in links:
        if l.a.cc != l.b.cc:
            key = tuple(sorted((l.a.cc, l.b.cc)))
            need[key] = need.get(key, 0) + 1
    lan = LAN2(users=v.users, placement=placement, core=core, access=access, links=links,
               servers=common + servers, user_ports=user_ports)
    lan.need_trunks = need
    return lan


def finalize(lan: LAN2, sks: SKS, trunks: dict):
    """После того как в СКС заведены статические соединения между ЦК — раздать их и собрать таблицу."""
    free = {k: list(v) for k, v in trunks.items()}
    for l in lan.links:
        if l.a.cc != l.b.cc:
            key = tuple(sorted((l.a.cc, l.b.cc)))
            link = free[key].pop(0)
            pa, pb = (link.a, link.b) if key[0] == l.a.cc else (link.b, link.a)
            l.via = (pa, pb)

    rows = []
    for w in range(1, 5):
        rows.append(("section", f"Рабочая группа WG-{w}"))
        for s in lan.placement[w]:
            sw, p = lan.user_ports[s.id]
            rows.append((s.port, sw.pid(p), "||"))
    rows.append(("section", "Соединения между оборудованием"))
    for l in sorted(lan.links, key=lambda l: (l.kind != "uplink", l.a.bid)):
        if l.via:
            rows.append((l.a.pid(l.pa), l.via[0], "X"))
            rows.append((l.via[1], l.b.pid(l.pb), "||"))
        else:
            rows.append((l.a.pid(l.pa), l.b.pid(l.pb), "X"))
    rows.append(("section", "Сервера"))
    for s in lan.servers:
        rows.append((s.name, s.sw.pid(s.port), "||"))
    lan.rows = rows
