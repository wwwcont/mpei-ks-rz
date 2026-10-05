"""Задание 4: отказоустойчивое подключение к Internet — VRRP (R-01, R-02), маршрутизация на L3, DHCP."""
from dataclasses import dataclass

from .common import Student
from .task3 import LAN3, SERVER_VLAN, TRANSIT_VLAN, SSwitch

TRANSIT = "172.31.1"     # сеть 172.31.1.0/29 по заданию


@dataclass
class VRRP:
    vrid: int
    prio1: int
    prio2: int
    vip: str
    r1: str
    r2: str
    l3: str
    mac: str
    extra: dict = None      # добавленный коммутатор, если на L3 не осталось портов


def build(st: Student, lan3: LAN3) -> VRRP:
    rng = st.rng("vrrp")
    vrid = rng.randint(1, 30)
    prio1 = rng.choice([110, 120, 150, 200, 250])
    v = VRRP(vrid=vrid, prio1=prio1, prio2=100,
             vip=f"{TRANSIT}.1", r1=f"{TRANSIT}.2", r2=f"{TRANSIT}.3", l3=f"{TRANSIT}.6",
             mac=f"00-00-5E-00-01-{vrid:02X}")
    # состояние задания 3 — для его рисунка
    lan3.snapshot = {sw.id: dict(sw.ports) for sw in lan3.switches}
    lan3.trunks4 = list(lan3.trunks)
    l3 = lan3.l3
    if not lan3.router_ports:
        free = [q for q in range(1, 13) if q not in l3.ports]
        if len(free) >= 2:
            lan3.router_ports = free[:2]
    if lan3.router_ports:
        lan3.router_at = [(l3, lan3.router_ports[0]), (l3, lan3.router_ports[1])]
    else:
        v.extra = _extend(lan3)
    for (sw, q), name in zip(lan3.router_at, ("R-01", "R-02")):
        sw.ports[q] = (name, "U", TRANSIT_VLAN)
    return v


def _extend(lan3: LAN3):
    """Бюджет задания 3 не оставил портов на L3: в задании 4 (стоимость не ограничена) добавляется
    SS12TF-2TG-L2 — магистралью на место одного рабочего места L3, которое переносится на него."""
    l3 = lan3.l3
    q = next((q for q in range(1, 13) if l3.ports.get(q, ("",))[0].startswith("P-")), None)
    if q is None:
        raise SystemExit("задание 4: на L3 нет ни свободного порта, ни рабочего места для переноса")
    sid = next(k for k, (sw, port) in lan3.user_ports.items() if sw is l3 and port == q)
    name, mode, vlan = l3.ports[q]
    new = SSwitch(id=f"SS12-{len(lan3.l2) + 2:02d}", type="SS12TF-2TG-L2", cc=l3.cc)
    new.ports[1] = (name, "U", vlan)
    new.ports[14] = (l3.pid(q), "T", "")
    l3.ports[q] = (new.pid(14), "T", "")
    lan3.user_ports[sid] = (new, 1)
    lan3.l2.append(new)
    lan3.trunks4.append((new, 14, q))
    lan3.router_at = [(new, 11), (new, 12)]
    return dict(switch=new, l3port=q, socket_port=name, old=l3.pid(q))


def routes(lan3: LAN3, vr: VRRP = None):
    """Таблица маршрутизации L3: (сеть, маска, следующий маршрутизатор, порт, IP порта)."""
    rows = []
    for vlan in sorted(lan3.ip):
        ip = lan3.ip[vlan]
        rows.append((ip["net"], "255.255.255.0", "—", f"VLAN{vlan}", ip["gw"]))
    if vr:
        rows.append((f"{TRANSIT}.0", "255.255.255.248", "—", f"VLAN{TRANSIT_VLAN}", vr.l3))
        rows.append(("0.0.0.0", "0.0.0.0", vr.vip, f"VLAN{TRANSIT_VLAN}", vr.l3))
    return rows


def dhcp(lan3: LAN3, vr: VRRP):
    rows = []
    for vlan in sorted(lan3.ip):
        ip = lan3.ip[vlan]
        if vlan == SERVER_VLAN:
            rows.append((str(vlan), "— (статические адреса)", "255.255.255.0", ip["gw"], vr.vip))
        else:
            rows.append((str(vlan), f"{ip['first']} – {ip['last']}", "255.255.255.0", ip["gw"], vr.vip))
    return rows
