"""Сборка РЗ: расчёт всех заданий → рисунки → docx."""
import itertools
from pathlib import Path

from docx.shared import Cm

from . import draw_plan, task1, task2, task3, task4
from .common import Student, load_variant
from .docx_kit import Doc
from .draw_net import Diagram
from .task3 import SERVER_VLAN, TRANSIT_VLAN

TASK1 = "Разработка структурированной кабельной системы этажа здания"
TASK2 = "Разработка базовой локальной вычислительной сети"
TASK3 = "Разработка локальной вычислительной сети на интеллектуальных коммутаторах"
TASK4 = "Организация отказоустойчивого подключения локальной сети к Internet со статической маршрутизацией"

TITLES = {"File-server-main": "Общий сервер отдела", "DB-server-main": "Сервер БД отдела"}


def solve(st: Student):
    v = load_variant(st)
    sks = task1.build(st, v)
    task1.assign_panels(sks)
    lan2 = task2.build(st, v, sks)
    lan3 = task3.build(st, v, sks, lan2)
    trunks = {}
    for a, b in itertools.combinations(sorted(sks.cc), 2):
        n = max(lan2.need_trunks.get((a, b), 0), lan3.need_trunks.get((a, b), 0), 4)
        start = len(sks.links)
        sks.add_links(a, b, n)
        trunks[a, b] = sks.links[start:]
    task2.finalize(lan2, sks, trunks)
    task3.finalize(lan3, lan2, trunks)
    vr = task4.build(st, lan3)
    return v, sks, lan2, lan3, vr


def ranges(socks):
    """«зона 2 (S-02-01 – S-02-12), зона 3 (S-03-01 – S-03-04)»"""
    out = []
    for z, grp in itertools.groupby(socks, key=lambda s: s.zone):
        grp = list(grp)
        ids = grp[0].id if len(grp) == 1 else f"{grp[0].id} – {grp[-1].id}"
        out.append(f"зона {z} ({ids})")
    return ", ".join(out)


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


def port_span(ports):
    return ports[0] if len(ports) == 1 else f"{ports[0]} – {ports[-1]}"


def build_all(st: Student, out: Path) -> list:
    """КМ-1…КМ-4 (каждая — со всеми предыдущими заданиями, как требует методичка) и полный РЗ."""
    out.mkdir(parents=True, exist_ok=True)
    img = out / "img"
    img.mkdir(exist_ok=True)
    solved = solve(st)
    v = solved[0]
    base = f"{st.group} {st.short.replace(' ', '_')}"
    files = []
    for k in range(1, 5):
        tasks = list(range(1, k + 1))
        files.append(_render(st, solved, img, tasks, out / f"{base} КМ-{k} ({'задания 1-' + str(k) if k > 1 else 'задание 1'}).docx"))
    files.append(_render(st, solved, img, [1, 2, 3, 4], out / f"{base} РЗ.docx", full=True))
    _, sks, lan2, lan3, vr = solved
    lens = [s.length for s in sks.all_sockets()]
    summary = dict(variant=v.key, plan=v.plan_title, cc=", ".join(sorted(sks.cc)), max_len=max(lens),
                   cost=lan3.cost, budget=v.budget, switches2=len(lan2.switches),
                   switches3=len(lan3.l2) + 1, extra4=bool(vr.extra), images=sorted(img.glob("*.png")))
    return files, summary


def _render(st, solved, img, tasks, path, full=False):
    v, sks, lan2, lan3, vr = solved
    D = Doc()
    _title(D, st, v, tasks, full)
    D.page_numbers(first_footer=f"Москва {st.year} г.", first_header=(
        "Федеральное государственное бюджетное образовательное учреждение",
        "высшего образования «Национальный исследовательский университет",
        "«Московский энергетический институт»",
        "Кафедра ВМСС"))
    if 1 in tasks:
        _task1(D, st, v, sks, img)
    if 2 in tasks:
        _task2(D, st, v, sks, lan2, img)
    if 3 in tasks:
        _task3(D, st, v, sks, lan2, lan3, img)
    if 4 in tasks:
        _task4(D, st, v, lan2, lan3, vr, img)
    D.save(path)
    return path


# ----------------------------------------------------------------------
def _title(D, st, v, tasks, full):
    """Титул по шаблону, принятому у Рыбинцева: шапка и «Москва» — в колонтитулах первой страницы."""
    for _ in range(6):
        D.p("", indent=False)
    for t in ("Расчетное задание", "ОСНОВЫ ПОСТРОЕНИЯ", "КОМПЬЮТЕРНЫХ СЕТЕЙ"):
        D.p(t, bold=True, align="center", indent=False, size=16)
    D.p("по курсу «Компьютерные сети»", bold=True, align="center", indent=False, size=16)
    if not full:
        D.p(f"Задани{'е' if len(tasks) == 1 else 'я'} {', '.join(map(str, tasks))}",
            align="center", indent=False)
    for _ in range(4):
        D.p("", indent=False)
    D.kv_table([("Выполнил", None), ("Студент", st.fio), ("Группа", st.group), ("Вариант", str(st.variant))])
    D.p("", indent=False)
    D.kv_table([("Принял", None), ("Преподаватель", st.teacher), ("Дата", "")])


EQUIP2 = [("1", "S12TF", "Коммутатор (Switch), 12 портов 10/100BASE-TX", 15),
          ("2", "S24TF", "Коммутатор (Switch), 24 порта 10/100BASE-TX", 20)]
EQUIP3 = [("1", "SS12TF-2TG-L2", "Интеллектуальный коммутатор 2-го уровня: 12 портов 10/100BASE-TX, "
                                 "2 порта 10/100/1000BASE-T, IEEE 802.1q (VLAN на основе портов)", 35),
          ("2", "SS24TF-2TG-L2", "Интеллектуальный коммутатор 2-го уровня: 24 порта 10/100BASE-TX, "
                                 "2 порта 10/100/1000BASE-T, IEEE 802.1q (VLAN на основе портов)", 55),
          ("3", "SS12TG-L3", "Интеллектуальный коммутатор 3-го уровня: 12 портов 10/100/1000BASE-T, "
                             "IEEE 802.1q, статическая маршрутизация", 45)]


def _equip_table(D, rows, title):
    D.table(title, ["№ п/п", "Обозначение", "Описание", "Стоимость, у.е."], rows,
            widths=[1.4, 3.6, 9.0, 2.5], align=["center", "center", "left", "center"])


# ----------------------------------------------------------------------
def _task1(D, st, v, sks, img):
    D.h1(f"Задание 1\n{TASK1}")
    D.p("**Цель задания:** формирование навыков разработки структурированной кабельной системы (СКС) "
        "этажа здания и оформления соответствующей эксплуатационной документации.")
    D.p(f"**Задание:** в соответствии с вариантом и конфигурацией зон подключения {v.plan_title} "
        "разработать СКС на витой паре категории 5е, удовлетворяющую исходным данным.")
    D.h2("Исходные данные для проектирования")
    D.table("Исходные данные", ["Вариант", "Конфигурация зон подключения", "Количество точек подключения в зонах",
                                "Размеры (L×W), м"],
            [(v.key, v.plan_title, ", ".join(map(str, v.points)), f"{v.L} × {v.W}")], widths=[2.5, 4.5, 6, 3.5])

    draw_plan.draw_plan(sks, img / "plan_zones.png", sockets=False)
    f_zones = D.figure(img / "plan_zones.png", f"Конфигурация зон подключения {v.plan_title}", 15)
    D.h2("Выполнение")

    names = sorted(sks.cc)
    zones_of = {c: [z for z in sorted(sks.zone_cc) if sks.zone_cc[z] == c] for c in names}
    D.p(f"Из допустимых мест размещения (рис. {f_zones}) выбрано {len(names)} {plural(len(names), "центр", "центра", "центров")} коммутации — "
        + ", ".join(names) + ". Места выбраны так, чтобы длина каждого статического соединения "
        f"не превышала 90 м, а суммарная длина кабеля была минимальной. Масштаб плана: "
        f"L = {v.L} м, W = {v.W} м.")
    D.bullets([f"ЦК {c}: зоны подключения {', '.join(map(str, zones_of[c]))};" for c in names[:-1]]
              + [f"ЦК {names[-1]}: зоны подключения {', '.join(map(str, zones_of[names[-1]]))}."])
    if sks.split:
        z, main, other, t = sks.split
        D.p(f"Чтобы число рабочих мест в каждом ЦК позволило уложиться в бюджет задания 3, зона {z} поделена: "
            f"{t} ближайших к ЦК {other} розеток подключены к нему, остальные — к ЦК {main}.")

    D.p("Точки подключения (розетки RJ45) равномерно распределены вдоль кабельных каналов, проложенных "
        "по внутренним границам зон подключения. Идентификатор розетки S-ZZ-NN: ZZ — номер зоны, "
        "NN — порядковый номер розетки в зоне. Каждый центр коммутации содержит коммутационные панели "
        "на 24 порта RJ45; идентификатор порта P-XNN-MM: X — центр коммутации, NN — номер панели, "
        "MM — номер порта.")
    rows = []
    for z in sorted(sks.sockets):
        ss = sks.sockets[z]
        ccs_z = sorted({x.cc for x in ss})
        ports = "; ".join(f"{p[0]} – {p[-1]}" if len(p) > 1 else p[0]
                          for p in ([x.port for x in ss if x.cc == c] for c in ccs_z))
        rows.append((z, len(ss), f"{ss[0].id} – {ss[-1].id}", ", ".join(ccs_z), ports))
    rows.append(("Итого", sum(len(s) for s in sks.sockets.values()), "", "", ""))
    D.table("Распределение точек подключения по зонам",
            ["Зона", "Число розеток", "Идентификаторы розеток", "ЦК", "Порты панелей"], rows,
            widths=[1.5, 2.3, 4.6, 1.3, 6.3])
    panels = []
    for c in names:
        n_sock = sum(1 for x in sks.all_sockets() if x.cc == c)
        n_link = sum(1 for l in sks.links if l.a.startswith(f"P-{c}") or l.b.startswith(f"P-{c}"))
        panels.append(f"ЦК {c}: {n_sock} {plural(n_sock, 'порт', 'порта', 'портов')} под розетки и {n_link} "
                      f"под соединения между ЦК — {sks.panels[c]} "
                      f"{plural(sks.panels[c], 'коммутационная панель', 'коммутационные панели', 'коммутационных панелей')} "
                      f"({', '.join(f'{c}{k:02d}' for k in range(1, sks.panels[c] + 1))});")
    panels[-1] = panels[-1][:-1] + "."
    D.p("Число коммутационных панелей:", keep=True)
    D.bullets(panels)
    D.p("Статические соединения между центрами коммутации заложены под магистральные связи "
        "коммутаторов, расположенных в разных ЦК (задания 2 и 3).")

    draw_plan.draw_plan(sks, img / "plan_sks.png")
    D.landscape(True)
    f_plan = D.figure(img / "plan_sks.png",
                      "План этажа с центрами коммутации, точками подключения и кабельными каналами", 25.5, 14.5)
    D.landscape(False)

    D.h2("Документация")
    lens = [s.length for s in sks.all_sockets()]
    D.p(f"Длина кабеля каждого статического соединения определена по плану (рис. {f_plan}) как длина "
        "трассы по кабельным каналам от розетки до центра коммутации с точностью до 1 м, увеличенная на 3 м "
        f"на прокладку по вертикали. Наименьшая длина — {min(lens)} м, наибольшая — {max(lens)} м, что не "
        "превышает 90 м, допустимых для статического соединения на витой паре.")
    rows, k = [], 0
    for z in sorted(sks.sockets):
        rows.append(("section", f"Соединения зоны подключения {z}"))
        for s in sks.sockets[z]:
            k += 1
            rows.append((f"S{k}", s.id, s.port, s.length))
    rows.append(("section", "Соединения между центрами коммутации"))
    for l in sks.links:
        k += 1
        rows.append((f"S{k}", l.a, l.b, l.length))
    D.table("Статические соединения СКС", ["№ соединения", "Идентификатор 1", "Идентификатор 2", "Длина, м"],
            rows, widths=[3.0, 4.2, 4.2, 3.0])


# ----------------------------------------------------------------------
def _task2(D, st, v, sks, lan2, img):
    D.h1(f"Задание 2\n{TASK2}")
    D.p("**Цель задания:** формирование навыков выбора состава комплекса технических средств и разработки "
        "отказоустойчивой структуры локальной вычислительной сети за счёт использования возможностей "
        "протокола покрывающего дерева (STP, стандарт IEEE 802.1d).")
    D.p("**Задание:** для СКС, разработанной в задании 1, на неинтеллектуальных коммутаторах разработать "
        "структуру и выбрать состав технических средств ЛВС отдела из четырёх рабочих групп (WG-1 – WG-4), "
        "у каждой из которых есть свой сервер; кроме того, есть общий сервер отдела и сервер базы данных "
        "отдела, доступ к которым нужен всем сотрудникам. Все интерфейсы — 100BASE-TX, единое адресное "
        "пространство 192.168.0.0/16. Отказ соединения между коммутаторами не должен приводить к потере "
        "доступа группы к общим серверам; число транзитных коммутаторов в штатном режиме — минимальное.")

    D.h2("Исходные данные для проектирования")
    D.table("Исходные данные", ["Вариант", "Количество сотрудников в группах", "Рост числа сотрудников (в каждой группе), %"],
            [(v.key, ", ".join(map(str, v.staff)), v.growth)], widths=[3, 7, 6.5])
    _equip_table(D, EQUIP2, "Параметры учебного сетевого оборудования")
    D.h2("Выбор необходимого оборудования")
    D.p(f"Число сотрудников каждой группы увеличивается на {v.growth} % с округлением вверх:", keep=True)
    D.table("Число сотрудников рабочих групп с учётом роста",
            ["Рабочая группа", "Сотрудников", f"С учётом роста {v.growth} %"],
            [(f"WG-{w}", v.staff[w - 1], v.users[w - 1]) for w in range(1, 5)]
            + [("Итого", sum(v.staff), sum(v.users))], widths=[4, 4, 5])

    D.p("Сотрудники каждой группы размещены по возможности в одной зоне и в зонах одного центра "
        "коммутации — так группе достаточно коммутаторов в одном ЦК:", keep=True)
    D.bullets([f"WG-{w} ({lan2.users[w - 1]} чел.): {ranges(lan2.placement[w])};" for w in range(1, 5)])
    spare = sum(len(s) for s in sks.sockets.values()) - sum(lan2.users)
    D.p(f"Свободными (резервными) {plural(spare, 'остаётся', 'остаются', 'остаются')} {spare} "
        f"{plural(spare, 'точка', 'точки', 'точек')} подключения.")

    D.p("На каждом коммутаторе рабочей группы резервируются два порта: для подключения к корневому "
        "коммутатору отдела и для резервной связи с коммутатором другой группы; сервер группы подключается "
        "к коммутатору своей группы. Общий сервер и сервер БД подключены к корневому коммутатору, к которому "
        "напрямую подключены все коммутаторы групп — в штатном режиме трафик к общим серверам проходит "
        "не более чем через один транзитный коммутатор (корневой).")
    rows = []
    for w in range(1, 5):
        sws = [a for a in lan2.access if a.wg == w]
        cost_w = sum(task2.TYPES[a.type][1] for a in sws)
        rows.append((f"WG-{w}", lan2.users[w - 1], ", ".join(f"{a.id} ({a.type}, ЦК {a.cc})" for a in sws), cost_w))
    c0 = task2.TYPES[lan2.core.type][1]
    rows.append(("Общие серверы", "—", f"{lan2.core.id} ({lan2.core.type}, ЦК {lan2.core.cc}) — корневой", c0))
    cost = sum(task2.TYPES[s.type][1] for s in lan2.switches)
    rows.append(("Итого", sum(lan2.users), f"{len(lan2.switches)} коммутаторов", cost))
    D.table("Подключение к сети сотрудников",
            ["Рабочая группа", "Рабочих мест с учётом роста", "Перечень оборудования", "Стоимость, у.е."],
            rows, widths=[2.8, 3.0, 8.0, 2.7], align=["center", "center", "left", "center"])

    D.h2("Разработка сети")
    D.p(f"Идентификаторы коммутаторов (ID) назначены так, что наименьший ID = 1 имеет коммутатор "
        f"{lan2.core.id}; по алгоритму STP он становится корневым мостом, все его порты — назначенные (Н). "
        "У коммутаторов групп порт, ведущий к корневому, — корневой (К). На резервных связях между "
        "коммутаторами групп оба конца имеют одинаковую стоимость пути до корня, поэтому назначенным "
        "становится порт коммутатора с меньшим ID, а порт коммутатора с большим ID блокируется (Б). "
        "При обрыве связи коммутатора группы с корневым заблокированный порт переходит в рабочее состояние, "
        "и доступ к общим серверам сохраняется через соседний коммутатор.")
    users = []
    for sw in lan2.access:
        ps = sorted(p for p, (t, r) in sw.ports.items() if t.startswith("P-"))
        if ps:
            users.append(f"{sw.id}: порты {port_span(ps)} — рабочие места WG-{sw.wg};")
    users[-1] = users[-1][:-1] + "."
    D.p("Рабочие места подключены к портам коммутаторов групп (на рисунке не показаны, чтобы не загромождать схему):", keep=True)
    D.bullets(users)
    dg = Diagram()
    for sw in lan2.switches:
        role = "корневой" if sw is lan2.core else f"WG-{sw.wg}"
        dg.node(sw.id, sw.type, f"{sw.id} (ID = {sw.bid}) — {role}, ЦК {sw.cc}")
    for s in lan2.servers:
        kind = "db" if s.name == "DB-server-main" else "server"
        dg.icon(s.name, kind, TITLES.get(s.name, s.title), s.sw.id)
    for l in lan2.links:
        dg.link((l.a.id, l.pa), (l.b.id, l.pb), dashed=not l.active, la=l.ra, lb=l.rb)
    for s in lan2.servers:
        dg.link((s.sw.id, s.port), s.name, width=2)
    dg.render(img / "lan2.png", legend="Сплошные линии — активная конфигурация STP, пунктир — заблокированная "
                                       "связь; К — корневой, Н — назначенный, Б — заблокированный порт")
    D.landscape(True)
    D.figure(img / "lan2.png", "Структура ЛВС с активной конфигурацией и ролями портов STP", 25.5, 15.0)
    D.landscape(False)

    D.h2("Документация")
    rows = [(i, sw.id, sw.type, sw.cc) for i, sw in enumerate(lan2.switches, 1)]
    D.table("Размещение оборудования по центрам коммутации",
            ["№ п/п", "Идентификатор оборудования", "Тип оборудования", "Идентификатор центра коммутации"],
            rows, widths=[1.5, 4.5, 5, 4])
    D.p("Серверы размещены в центрах коммутации рядом с коммутаторами, к которым подключены: "
        + "; ".join(f"{s.name} — ЦК {s.cc}" for s in lan2.servers) + ".")
    D.p("Связи коммутаторов, находящихся в разных центрах коммутации, проходят через статические соединения "
        "между ЦК (задание 1); скрещённый кабель (X) ставится с одной стороны, чтобы соединение "
        "коммутатор — коммутатор в целом было скрещённым.")
    _dyn(D, lan2.rows, "Динамические соединения")


def _dyn(D, rows, title, start=1):
    out, k = [], start - 1
    for r in rows:
        if r[0] == "section":
            out.append(r)
        else:
            k += 1
            out.append((f"D{k}",) + tuple(r))
    D.table(title, ["№ соединения", "Идентификатор 1", "Идентификатор 2", "Тип кабеля"], out,
            widths=[3.0, 4.5, 4.5, 3.0])
    return k


# ----------------------------------------------------------------------
def _net3(lan3, routers=False):
    dg = Diagram()
    sws = lan3.switches if routers else [sw for sw in lan3.switches if sw.id in lan3.snapshot]
    for sw in sws:
        ports = sw.ports if routers else lan3.snapshot[sw.id]
        boxes = {p: (mode, vlan) for p, (t, mode, vlan) in ports.items() if t}
        dg.node(sw.id, sw.type, f"{sw.id} — {sw.type}, ЦК {sw.cc}", boxes)
    for name, (sw, q, vlan) in lan3.servers.items():
        dg.icon(name, "db" if name == "DB-server-main" else "server", name, sw.id)
    if routers:
        for (sw, q), name in zip(lan3.router_at, ("R-01", "R-02")):
            dg.icon(name, "router", name, sw.id)
        dg.cloud = ["R-01", "R-02"]
    for sw, up, p in (lan3.trunks4 if routers else lan3.trunks):
        dg.link((sw.id, up), (lan3.l3.id, p))
    for name, (sw, q, _) in lan3.servers.items():
        dg.link((sw.id, q), name, width=2)
    if routers:
        for (sw, q), name in zip(lan3.router_at, ("R-01", "R-02")):
            dg.link((sw.id, q), name, width=3)
    return dg


IP_HEAD = ["№ п/п", "VLAN ID", "IP сети", "IP оборудования: пользователи", "IP оборудования: серверы",
           "IP-адрес модуля маршрутизации"]
IP_W = [1.2, 2.0, 3.3, 4.0, 3.4, 2.8]


def _ip_rows(st, lan3, vr=None):
    rows = []
    for i, vlan in enumerate(sorted(lan3.ip), 1):
        ip = lan3.ip[vlan]
        if vlan == SERVER_VLAN:
            rows.append((i, f"VLAN{vlan}", f"{ip['net']}/24", "–", f"{ip['common']}, {ip['db']}", ip["gw"]))
        else:
            rows.append((i, f"VLAN{vlan}", f"{ip['net']}/24", f"{ip['first']} – {ip['last']}", ip["server"], ip["gw"]))
    if vr:
        rows.append((len(rows) + 1, f"VLAN{TRANSIT_VLAN}", f"{task4.TRANSIT}.0/29", "–",
                     f"R-01: {vr.r1}, R-02: {vr.r2}, виртуальный: {vr.vip}", vr.l3))
    return rows


def _task3(D, st, v, sks, lan2, lan3, img):
    D.h1(f"Задание 3\n{TASK3}")
    D.p("**Цель задания:** формирование навыков выбора состава и разработки структуры комплекса технических "
        "средств локальной сети на коммутаторах, поддерживающих технологию виртуальных локальных сетей "
        "(VLAN) по стандарту IEEE 802.1q и статическую маршрутизацию.")
    D.p("**Задание:** на интеллектуальных коммутаторах (Smart Switch) построить ЛВС, в которой "
        "широковещательный трафик каждой рабочей группы изолирован от других групп, стоимостью не более "
        f"{v.budget} у.е.")

    D.h2("Исходные данные для проектирования")
    D.table("Исходные данные", ["Вариант", "Максимальная стоимость, у.е."], [(v.key, v.budget)], widths=[5, 7])
    _equip_table(D, EQUIP3, "Параметры учебного сетевого оборудования (SMART SWITCH)")
    D.h2("Выбор необходимого оборудования")
    D.p("Каждой рабочей группе выделена своя VLAN на основе портов; общие серверы отдела вынесены в "
        f"отдельную VLAN{SERVER_VLAN}. Маршрутизацию между VLAN выполняет модуль маршрутизации коммутатора "
        "третьего уровня. Рабочие места подключаются к портам 100BASE-TX, серверы — к портам 1000BASE-T.")
    rows = [(f"VLAN{vl}", f"WG-{w}" if w else "Общие серверы", a, b)
            for (vl, a, b), w in zip(lan3.need, [1, 2, 3, 4, 0])]
    rows.append(("Итого", "", sum(r[2] for r in rows), sum(r[3] for r in rows)))
    D.table("Необходимое число портов по VLAN",
            ["VLAN ID", "Назначение", "Портов 100BASE-TX", "Портов 1000BASE-T"], rows, widths=[3, 4.5, 3.5, 3.5])

    by = {}
    for sw in lan3.l2:
        by.setdefault((sw.type, sw.cc), 0)
        by[sw.type, sw.cc] += 1
    D.p("Коммутатор третьего уровня SS12TG-L3 (12 портов 1000BASE-T) обязателен — он маршрутизирует трафик "
        "между VLAN; к нему подключены общие серверы, магистрали от коммутаторов второго уровня и (в задании 4) "
        "два внешних маршрутизатора. Коммутаторы второго уровня выбраны по числу рабочих мест в каждом центре "
        "коммутации при минимальной стоимости; один гигабитный порт каждого из них — магистраль (T) к "
        "коммутатору третьего уровня, второй — под сервер группы.")
    if lan3.on_gig:
        D.p(f"{lan3.on_gig} {plural(lan3.on_gig, 'рабочее место подключено', 'рабочих места подключены', 'рабочих мест подключены')} к свободным портам 10/100/1000BASE-T — они совместимы "
            "с 100BASE-TX, это позволяет уложиться в заданную стоимость.")
    terms = " + ".join(f"{sum(1 for s in lan3.switches if s.type == t)}·{c}"
                       for t, (_, _, c) in task3.TYPES.items() if any(s.type == t for s in lan3.switches))
    verdict = "что не превышает" if lan3.cost <= v.budget else "что ПРЕВЫШАЕТ"
    D.p(f"Стоимость: {terms} = {lan3.cost} у.е., {verdict} заданных {v.budget} у.е.")
    D.p("Серверы размещены в центрах коммутации вместе с коммутаторами, к которым подключены:", keep=True)
    D.bullets([f"{n} — {sw.id}, порт {q}, ЦК {sw.cc};" for n, (sw, q, _) in lan3.servers.items()][:-1]
              + [f"{n} — {sw.id}, порт {q}, ЦК {sw.cc}." for n, (sw, q, _) in list(lan3.servers.items())[-1:]])

    D.landscape(True)
    D.h2("Разработка сети")
    D.p("Порты рабочих мест и серверов работают в режиме U (untagged) и принадлежат VLAN своей группы; "
        "магистральные порты между коммутаторами работают в режиме T (tagged) и передают кадры всех VLAN "
        "с метками IEEE 802.1q.")
    _net3(lan3).render(img / "lan3.png", legend="U — порт без меток (access), T — порт с метками 802.1q (trunk); "
                                                "в нижней строке — номер VLAN")
    D.figure(img / "lan3.png", "Структура ЛВС с VLAN на интеллектуальных коммутаторах", 25.5, 15.0)
    D.landscape(False)
    D.h2("Документация")
    rows = [(i, sw.id, sw.type, sw.cc) for i, sw in enumerate(lan3.switches, 1)]
    D.table("Размещение оборудования по центрам коммутации",
            ["№ п/п", "Идентификатор оборудования", "Тип оборудования", "Идентификатор центра коммутации"],
            rows, widths=[1.5, 4.5, 5, 4])
    D.p("Все порты 1000BASE-T поддерживают автоматическое определение типа кабеля (Auto MDI/MDI-X), поэтому "
        "все соединения выполняются прямым кабелем (||).")
    _dyn(D, lan3.rows, "Динамические соединения")

    D.p(f"Адреса сетей имеют вид 1xx.1yy.zz.0/24, где xx = {st.group_num:02d} — номер учебной группы, "
        f"yy = {st.journal:02d} — номер студента в журнале, zz — номер VLAN. В каждой VLAN адрес .1 — "
        "интерфейс модуля маршрутизации (шлюз по умолчанию), .2 — сервер группы, далее — рабочие места; "
        f"в VLAN{SERVER_VLAN}: .2 — общий сервер, .3 — сервер БД.")
    D.table("Распределение IP-адресов", IP_HEAD, _ip_rows(st, lan3), widths=IP_W, size=11, head_size=10)
    D.table("Таблица маршрутизации коммутатора 3-го уровня",
            ["IP-адрес сети назначения", "Маска сети", "IP-адрес следующего маршрутизатора",
             "Идентификатор порта модуля маршрутизации", "IP-адрес порта модуля маршрутизации"],
            task4.routes(lan3), widths=[3.2, 3.2, 3.4, 3.4, 3.3], size=11, head_size=10)


# ----------------------------------------------------------------------
def _task4(D, st, v, lan2, lan3, vr, img):
    D.h1(f"Задание 4\n{TASK4}")
    D.p("**Цель задания:** формирование навыков составления таблицы статической маршрутизации между VLAN "
        "с организацией отказоустойчивого подключения к сети Internet за счёт протокола VRRP при "
        "динамическом назначении IP-адресов пользователям.")
    D.p("**Задание:** для сети из задания 3 подключить два внешних маршрутизатора R-01 и R-02, образующих "
        f"по протоколу VRRP виртуальный маршрутизатор (сеть {task4.TRANSIT}.0/29), модифицировать таблицы "
        "IP-адресов и маршрутизации коммутатора 3-го уровня, задать параметры DHCP-серверов для VLAN.")

    D.h2("Выполнение")
    (s1, q1), (s2, q2) = lan3.router_at
    if vr.extra:
        ex = vr.extra
        D.p(f"В задании 3 все порты коммутатора {lan3.l3.id} заняты (иначе не уложиться в {v.budget} у.е.). "
            "В задании 4 стоимость не ограничена, поэтому для подключения маршрутизаторов добавлен коммутатор "
            f"{ex['switch'].id} ({ex['switch'].type}, ЦК {ex['switch'].cc}, 35 у.е.): его порт 14 — магистраль "
            f"(T) к порту {ex['l3port']} коммутатора {lan3.l3.id}, рабочее место, ранее подключённое к этому "
            f"порту, перенесено на порт 1 нового коммутатора.")
    D.p(f"Маршрутизаторы R-01 и R-02 подключены к портам {q1} и {q2} коммутатора {s1.id}, отнесённым к новой "
        f"VLAN{TRANSIT_VLAN}. Маршрутизатор с большим приоритетом (R-01) — основной (Master), R-02 — резервный "
        "(Backup); при отказе R-01 R-02 принимает на себя IP- и MAC-адрес виртуального маршрутизатора.")
    D.table("Параметры протокола VRRP", ["Параметр", "Значение"], [
        ("Идентификатор группы VRRP (VRID)", vr.vrid),
        ("Приоритет R-01 (Master)", vr.prio1),
        ("Приоритет R-02 (Backup)", vr.prio2),
        ("IP-адрес R-01", f"{vr.r1}/29"),
        ("IP-адрес R-02", f"{vr.r2}/29"),
        ("IP-адрес виртуального маршрутизатора", f"{vr.vip}/29"),
        ("MAC-адрес виртуального маршрутизатора", vr.mac),
        (f"IP-адрес модуля маршрутизации в VLAN{TRANSIT_VLAN}", f"{vr.l3}/29"),
    ], widths=[9, 6], align=["left", "center"])
    D.p(f"MAC-адрес виртуального маршрутизатора по стандарту VRRP — 00-00-5E-00-01-XX, где XX — VRID "
        f"в шестнадцатеричном виде ({vr.vrid} = {vr.vrid:02X}h).")

    _net3(lan3, routers=True).render(img / "lan4.png", legend="R-01, R-02 — внешние маршрутизаторы "
                                                              f"(VRRP, VLAN{TRANSIT_VLAN})")
    D.landscape(True)
    D.figure(img / "lan4.png", "Структура ЛВС с внешними маршрутизаторами", 25.5, 15.0)
    D.landscape(False)
    k = sum(1 for r in lan3.rows if r[0] != "section")
    add = []
    if vr.extra:
        ex = vr.extra
        add += [("section", f"Подключение коммутатора {ex['switch'].id} (вместо соединения {ex['socket_port']} – {ex['old']})"),
                (ex["socket_port"], ex["switch"].pid(1), "||"),
                (ex["switch"].pid(14), lan3.l3.pid(ex["l3port"]), "||")]
    add += [("section", "Подключение маршрутизаторов"),
            (s1.pid(q1), "R-01-01", "||"), (s2.pid(q2), "R-02-01", "||")]
    _dyn(D, add, "Динамические соединения (дополнение к таблице задания 3)", start=k + 1)

    D.p("Первый адрес каждой VLAN — шлюз по умолчанию: виртуальный интерфейс модуля маршрутизации "
        "коммутатора третьего уровня, настраивается на самом коммутаторе. Статические IP-адреса серверов "
        f"задаются на серверах. В VLAN{SERVER_VLAN} все адреса статические; в VLAN{TRANSIT_VLAN} DHCP не "
        "используется — у маршрутизаторов и модуля маршрутизации статические адреса.")
    D.table("Распределение IP-адресов (с учётом R-01, R-02)", IP_HEAD, _ip_rows(st, lan3, vr), widths=IP_W,
            size=11, head_size=10)
    D.p("Маршрут по умолчанию (0.0.0.0/0) направляет трафик в Internet на адрес виртуального "
        "маршрутизатора — так он не зависит от того, какой из R-01 и R-02 сейчас основной.")
    D.table("Таблица маршрутизации коммутатора 3-го уровня",
            ["IP-адрес сети назначения", "Маска сети", "IP-адрес следующего маршрутизатора",
             "Идентификатор порта модуля маршрутизации", "IP-адрес порта модуля маршрутизации"],
            task4.routes(lan3, vr), widths=[3.2, 3.2, 3.4, 3.4, 3.3], size=11, head_size=10)

    D.p("Пользователям каждой VLAN рабочих групп адреса выдаются динамически из диапазона, начиная с .3 "
        "(адреса .1 и .2 заняты шлюзом и сервером группы). Для VLAN50 и VLAN60 DHCP не нужен — адреса "
        "статические. В качестве DNS-сервера указан адрес виртуального маршрутизатора.")
    D.table("Параметры DHCP-серверов для VLAN",
            ["VLAN", "Диапазон IP-адресов", "Маска сети", "IP-адрес маршрутизатора", "IP-адрес сервера DNS"],
            task4.dhcp(lan3, vr), widths=[1.4, 5.4, 3.2, 3.3, 3.2], size=11, head_size=10)
