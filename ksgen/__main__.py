"""python -m ksgen --fio "Рязанцев Иоанн Васильевич" --group А-12-23 --variant 17 [--journal 17] [--out build]"""
import argparse
from pathlib import Path

from .common import ROOT, Student
from .report import build_all


def main():
    ap = argparse.ArgumentParser(description="Генератор РЗ по курсу «Компьютерные сети»")
    ap.add_argument("--fio", required=True, help="Фамилия Имя Отчество полностью")
    ap.add_argument("--group", required=True, help="например А-12-23")
    ap.add_argument("--variant", type=int, required=True, help="номер варианта (две последние цифры)")
    ap.add_argument("--journal", type=int, help="номер в журнале группы (по умолчанию = вариант)")
    ap.add_argument("--teacher", default="Рыбинцев В.О.")
    ap.add_argument("--out", default=None, help="папка результата (по умолчанию build/<группа>/<вариант>)")
    a = ap.parse_args()
    st = Student(fio=" ".join(a.fio.split()), group=a.group.strip(), variant=a.variant,
                 journal=a.journal or a.variant, teacher=a.teacher)
    out = Path(a.out) if a.out else ROOT / "build" / st.group / f"{st.variant:02d}"
    files, summary = build_all(st, out)
    for path in files:
        print(path)
    if summary["cost"] > summary["budget"]:
        print(f"ВНИМАНИЕ: задание 3 — {summary['cost']} у.е. при бюджете {summary['budget']} у.е.")


if __name__ == "__main__":
    main()
