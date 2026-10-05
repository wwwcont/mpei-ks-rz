"""Текст комментария бота с результатами (по $RUNNER_TEMP/student.json) → stdout."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

info = json.loads(Path(os.environ["RUNNER_TEMP"], "student.json").read_text())
repo = os.environ["GITHUB_REPOSITORY"]
branch = os.environ.get("RESULTS_BRANCH", "results")
base = f"https://github.com/{repo}/raw/{branch}/{quote(info['folder'])}"
tree = f"https://github.com/{repo}/tree/{branch}/{quote(info['folder'])}"
s = info["summary"]


def link(name):
    return f"{base}/{quote(name)}"


rows = []
for name in info["files"]:
    pdf = name[:-5] + ".pdf"
    if " КМ-" in name:
        k = name.split(" КМ-")[1][0]
        what = f"**КМ-{k}** — задани{'е 1' if k == '1' else 'я 1–' + k}"
    else:
        what = "**Полный РЗ** — задания 1–4"
    rows.append(f"| {what} | [docx]({link(name)}) | [pdf]({link(pdf)}) |")

ok_cost = "✅" if s["cost"] <= s["budget"] else "⚠️ больше бюджета"
lines = [
    f"## 📦 РЗ собран — вариант {info['variant']}, {info['fio']}",
    "",
    "| Что | Файл | Просмотр |",
    "| --- | --- | --- |",
    *rows,
    "",
    f"Все файлы и рисунки — [папка {info['folder']}]({tree}).",
    "",
    "**Что получилось**",
    f"- план {s['plan']}, центры коммутации {s['cc']}; самый длинный кабель — {s['max_len']} м (≤ 90 м ✅);",
    f"- задание 2: {s['switches2']} коммутаторов;",
    f"- задание 3: {s['switches3']} коммутаторов, {s['cost']} у.е. при бюджете {s['budget']} у.е. {ok_cost};",
    f"- IP-адреса — с номером в журнале **{info['journal']}** (1{info['group'].split('-')[1]}.1{info['journal']:02d}.zz.0/24)"
    + " — если номер другой, поправьте его в форме Issue.",
]
if s.get("extra4"):
    lines.append("- задание 4: на L3 не осталось портов под R-01/R-02 — добавлен коммутатор (в тексте объяснено).")
lines += [
    "",
    "**🧑‍🎓 Что сделать**",
    "1. Откройте docx в Word — он предложит обновить поля: соглашайтесь (это содержание).",
    "2. Перескажите общие абзацы своими словами (у всей группы они из одного шаблона); числа, таблицы и рисунки не трогайте.",
    f"3. Отправляйте по методичке: тема письма «{info['short']} {info['group']} Задания 1, 2» и т. п.; "
    "КМ-N уже содержит все предыдущие задания, как требует методичка. Адрес — в методичке.",
    "",
    "Пересобрать (поменяли ФИО, вариант, номер в журнале) — отредактируйте форму этого Issue или напишите `/пересобрать`.",
]
img = s.get("images", [])
if "plan_sks.png" in img:
    lines += ["", f"<details><summary>План СКС</summary>\n\n![план]({base}/img/plan_sks.png)\n</details>"]
sys.stdout.write("\n".join(lines) + "\n")
