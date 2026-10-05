"""Общие данные: студент, вариант, детерминированный генератор случайных чисел."""
import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "plans"
EQUIPMENT = ROOT / "docs" / "source" / "equipment"
DATA = ROOT / "data"


@dataclass
class Student:
    fio: str          # полностью: «Рязанцев Иоанн Васильевич»
    group: str        # «А-12-23»
    variant: int      # номер варианта (обычно = номер в журнале)
    journal: int      # номер в журнале — для IP-адресов 1xx.1yy.zz.0
    teacher: str = "Рыбинцев В.О."
    year: int = 2026

    @property
    def group_num(self) -> int:
        return int(re.search(r"-(\d+)-", self.group).group(1))

    @property
    def variant_key(self) -> str:
        return f"{self.group_num}-{self.variant:02d}"

    @property
    def short(self) -> str:
        parts = self.fio.split()
        return parts[0] + " " + "".join(p[0] + "." for p in parts[1:])

    def rng(self, tag: str) -> random.Random:
        """Свой генератор на каждое решение: правка одного места не меняет остальные."""
        h = hashlib.sha256(f"{self.fio}|{self.group}|{self.variant}|{tag}".encode()).hexdigest()
        return random.Random(int(h, 16))


@dataclass
class Variant:
    key: str
    plan: str             # «U3», «T7»
    points: list          # точки подключения в зонах 1..5
    staff: list           # сотрудники WG-1..WG-4
    growth: int           # рост, %
    budget: int           # макс. стоимость для задания 3, у.е.
    L: int
    W: int

    @property
    def plan_title(self) -> str:
        return f"{self.plan[0]}-{self.plan[1:]}"

    @property
    def users(self) -> list:
        """Сотрудники с учётом роста, округление вверх."""
        return [-(-s * (100 + self.growth) // 100) for s in self.staff]


def load_variant(st: Student) -> Variant:
    path = DATA / "variants" / f"{st.group}.yaml"
    if not path.exists():
        raise SystemExit(f"нет таблицы вариантов {path.relative_to(ROOT)}")
    table = yaml.safe_load(path.read_text())
    if st.variant_key not in table:
        raise SystemExit(f"варианта {st.variant_key} нет в {path.relative_to(ROOT)}")
    return Variant(key=st.variant_key, **table[st.variant_key])


def load_geometry(plan: str) -> dict:
    return json.loads((PLANS / "geometry.json").read_text())[plan]
