"""Задание 3: ЛВС на интеллектуальных коммутаторах с VLAN и статической маршрутизацией (L3)."""
import itertools
from dataclasses import dataclass, field

from .common import Student, Variant
from .task1 import SKS
from .task2 import LAN2

# порты 100BASE-TX, порты 1000BASE-T, у.е.
TYPES = {
    "SS24TF-2TG-L2": (24, 2, 55),
    "SS12TF-2TG-L2": (12, 2, 35),
    "SS12TG-L3": (0, 12, 45),
}
PREFIX = {"SS24TF-2TG-L2": "SS24", "SS12TF-2TG-L2": "SS12", "SS12TG-L3": "L3"}
ROUTER_PORTS = 2       # на L3 под R-01 и R-02 (задание 4)
SERVER_VLAN = 50
TRANSIT_VLAN = 60


@dataclass
class SSwitch:
    id: str
    type: str
    cc: str
    ports: dict = field(default_factory=dict)    # порт → (что подключено, режим U/T, VLAN)

    @property
    def fast(self):
        return TYPES[self.type][0]

    @property
    def cap(self):
        return TYPES[self.type][0] + TYPES[self.type][1]

    @property
    def gig(self):
        return list(range(self.fast + 1, self.cap + 1))

    def pid(self, p):
        return f"{self.id}-{p:02d}"


@dataclass
class LAN3:
    l3: SSwitch
    l2: list
    cost: int
    budget: int
    vlans: dict             # wg → VLAN ID (10, 20, …)
    need: list              # [(VLAN, 100BASE-TX, 1000BASE-T)]
    user_ports: dict        # Socket.id → (SSwitch, порт)
    servers: dict           # имя → (SSwitch, порт, VLAN)
    trunks: list            # [(L2, порт L2, порт L3)]
    on_gig: int = 0         # сотрудников на портах 1000BASE-T
    ip: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    router_ports: list = field(default_factory=list)

    @property
    def switches(self):
        return [self.l3] + self.l2


def _feasible(cfg, l3_cc, users_cc, servers_cc, reserve=ROUTER_PORTS):
    """Проверка набора: хватает ли портов. cfg: ЦК → [типы L2]."""
    n_l2 = sum(len(t) for t in cfg.values())
    l3_free = 12 - n_l2 - reserve
    if l3_free < 2:          # общий сервер и сервер БД — на L3
        return False
    l3_free -= 2
    gig = {cc: sum(TYPES[t][1] - 1 for t in ts) for cc, ts in cfg.items()}
    gig[l3_cc] = gig.get(l3_cc, 0) + l3_free
    fast = {cc: sum(TYPES[t][0] for t in ts) for cc, ts in cfg.items()}
    # серверы групп — на гигабитные порты в своём ЦК, иначе в любом
    for cc in servers_cc:
        if gig.get(cc, 0) > 0:
            gig[cc] -= 1
        else:
            spare = [c for c in gig if gig[c] > 0]
            if not spare:
                return False
            gig[spare[0]] -= 1
    for cc, u in users_cc.items():
        if u > fast.get(cc, 0) + gig.get(cc, 0):
            return False
    return True


def cheapest(ccs, users_cc, srv_cc, budget=None):
    """Все самые дешёвые допустимые наборы: [(стоимость, число L2, ЦК для L3, {ЦК: [типы L2]}, резерв)].
    Порты под R-01/R-02 резервируются, если с ними укладываемся в бюджет (или бюджет не задан)."""
    top = _cheapest(ccs, users_cc, srv_cc, ROUTER_PORTS)
    if budget is not None and (not top or top[0][0] > budget):
        alt = _cheapest(ccs, users_cc, srv_cc, 0)
        if alt and (not top or alt[0][0] < top[0][0]):
            return alt
    return top


def _cheapest(ccs, users_cc, srv_cc, reserve):
    key = (tuple(ccs), tuple(sorted(users_cc.items())), tuple(srv_cc), reserve)
    if key in _CACHE:
        return _CACHE[key]
    opts = [("SS24TF-2TG-L2",) * a + ("SS12TF-2TG-L2",) * b for a in range(5) for b in range(5)]
    options = []
    for l3_cc in ccs:
        for combo in itertools.product(*[opts] * len(ccs)):
            cfg = dict(zip(ccs, combo))
            if not _feasible(cfg, l3_cc, users_cc, srv_cc, reserve):
                continue
            cost = 45 + sum(TYPES[t][2] for ts in cfg.values() for t in ts)
            options.append((cost, sum(len(t) for t in combo), l3_cc, cfg, reserve))
    options.sort(key=lambda o: (o[0], o[1]))
    top = [o for o in options if o[:2] == options[0][:2]]
    _CACHE[key] = top
    return top


_CACHE = {}


def build(st: Student, v: Variant, sks: SKS, lan2: LAN2) -> LAN3:
    vlans = {w: 10 * w for w in range(1, 5)}
    users_cc = {}
    for w, socks in lan2.placement.items():
        for s in socks:
            users_cc[s.cc] = users_cc.get(s.cc, 0) + 1
    srv_cc = [s.cc for s in lan2.servers if s.name.startswith("Server-WG")]
    ccs = sorted(sks.cc)

    top = cheapest(ccs, users_cc, srv_cc, v.budget)
    cost, _, l3_cc, cfg, reserve = st.rng("lan3").choice(top)

    l3 = SSwitch(id="L3-01", type="SS12TG-L3", cc=l3_cc)
    l2, n = [], 1
    for cc in ccs:
        for t in cfg[cc]:
            n += 1
            l2.append(SSwitch(id=f"{PREFIX[t]}-{n:02d}", type=t, cc=cc))

    # L3: 1–2 общие серверы, сверху вниз — магистрали к L2, ниже — маршрутизаторы R-01/R-02
    servers = {}
    l3.ports[1] = ("CommonServer", "U", SERVER_VLAN)
    l3.ports[2] = ("DB-Server", "U", SERVER_VLAN)
    servers["CommonServer"] = (l3, 1, SERVER_VLAN)
    servers["DB-Server"] = (l3, 2, SERVER_VLAN)
    trunks = []
    p = 12
    for sw in l2:
        up = sw.cap  # последний гигабитный порт L2 — магистраль
        sw.ports[up] = (l3.pid(p), "T", "")
        l3.ports[p] = (sw.pid(up), "T", "")
        trunks.append((sw, up, p))
        p -= 1
    router_ports = [p - 1, p] if reserve else []
    for rp in router_ports:
        l3.ports[rp] = ("", "U", TRANSIT_VLAN)   # имена — в задании 4

    def free_gig(sw):
        return [q for q in (sw.gig if sw is not l3 else range(1, 13)) if q not in sw.ports]

    # серверы групп — на свободный гигабитный порт L2 в своём ЦК (или на L3)
    for s in lan2.servers:
        if not s.name.startswith("Server-WG"):
            continue
        w = int(s.name[-1])
        cand = [sw for sw in l2 if sw.cc == s.cc and free_gig(sw)]
        cand += [l3] if l3.cc == s.cc and free_gig(l3) else []
        cand += [sw for sw in l2 if free_gig(sw)] + ([l3] if free_gig(l3) else [])
        sw = cand[0]
        q = free_gig(sw)[0]
        sw.ports[q] = (s.name, "U", vlans[w])
        servers[s.name] = (sw, q, vlans[w])

    # сотрудники: в каждом ЦК — подряд по группам на порты 100BASE-TX, остаток — на гигабитные
    user_ports, on_gig = {}, 0
    for cc in ccs:
        slots = []
        for sw in [x for x in l2 if x.cc == cc]:
            slots += [(sw, q) for q in range(1, sw.fast + 1) if q not in sw.ports]
        for sw in [x for x in l2 if x.cc == cc] + ([l3] if l3.cc == cc else []):
            slots += [(sw, q) for q in free_gig(sw)]
        for w in range(1, 5):
            for s in lan2.placement[w]:
                if s.cc != cc:
                    continue
                sw, q = slots.pop(0)
                if q > sw.fast:
                    on_gig += 1
                sw.ports[q] = (s.port, "U", vlans[w])
                user_ports[s.id] = (sw, q)

    need = [(vlans[w], lan2.users[w - 1], 1) for w in range(1, 5)] + [(SERVER_VLAN, 0, 2)]
    lan = LAN3(l3=l3, l2=l2, cost=cost, budget=v.budget, vlans=vlans, need=need,
               user_ports=user_ports, servers=servers, trunks=trunks, on_gig=on_gig,
               router_ports=router_ports)
    lan.need_trunks = {}
    for sw in l2:
        if sw.cc != l3.cc:
            key = tuple(sorted((sw.cc, l3.cc)))
            lan.need_trunks[key] = lan.need_trunks.get(key, 0) + 1
    _ip_plan(st, lan2, lan)
    return lan


def net(st: Student, vlan: int) -> str:
    return f"1{st.group_num:02d}.1{st.journal:02d}.{vlan}"


def _ip_plan(st, lan2, lan):
    """Адреса: .1 — интерфейс L3 (шлюз VLAN), .2 — сервер группы, дальше сотрудники."""
    ip = {}
    for w in range(1, 5):
        v = lan.vlans[w]
        n = lan2.users[w - 1]
        ip[v] = dict(net=f"{net(st, v)}.0", prefix=24, gw=f"{net(st, v)}.1",
                     server=f"{net(st, v)}.2", first=f"{net(st, v)}.3", last=f"{net(st, v)}.{n + 2}",
                     range=(f"{net(st, v)}.1", f"{net(st, v)}.{n + 2}"), users=n)
    v = SERVER_VLAN
    ip[v] = dict(net=f"{net(st, v)}.0", prefix=24, gw=f"{net(st, v)}.1",
                 common=f"{net(st, v)}.2", db=f"{net(st, v)}.3",
                 range=(f"{net(st, v)}.1", f"{net(st, v)}.3"), users=0)
    lan.ip = ip


def finalize(lan: LAN3, lan2: LAN2, trunks: dict):
    free = {k: list(v) for k, v in trunks.items()}
    rows = []
    for w in range(1, 5):
        rows.append(("section", f"Рабочая группа WG-{w} (VLAN{lan.vlans[w]})"))
        for s in lan2.placement[w]:
            sw, q = lan.user_ports[s.id]
            rows.append((s.port, sw.pid(q), "||"))
    rows.append(("section", "Соединения между оборудованием"))
    lan.via = {}
    for sw, up, p in lan.trunks:
        if sw.cc != lan.l3.cc:
            key = tuple(sorted((sw.cc, lan.l3.cc)))
            link = free[key].pop(0)
            pa, pb = (link.a, link.b) if key[0] == sw.cc else (link.b, link.a)
            rows.append((sw.pid(up), pa, "X"))
            rows.append((pb, lan.l3.pid(p), "||"))
            lan.via[sw.id] = (pa, pb)
        else:
            rows.append((sw.pid(up), lan.l3.pid(p), "X"))
    rows.append(("section", "Подключение серверов"))
    for name, (sw, q, _) in lan.servers.items():
        rows.append((sw.pid(q), name, "||"))
    lan.rows = rows
