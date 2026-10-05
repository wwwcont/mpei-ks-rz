"""Issue «Мой РЗ» → сборка всех КМ и полного РЗ.

Читает форму Issue (ISSUE_BODY_FILE), собирает docx в OUT_DIR, пишет:
  $GITHUB_OUTPUT: ok=1|0, dir=<папка результата относительно OUT_DIR>, title=…
  $RUNNER_TEMP/student.json — данные для комментария (scripts/issue_comment.py)
При ошибке формы — текст ошибки в $RUNNER_TEMP/error.md и ok=0.
"""
import json
import os
import re
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ksgen.common import DATA, Student  # noqa: E402
from ksgen.report import build_all      # noqa: E402

FIELDS = {"ФИО": "fio", "Группа": "group", "Вариант": "variant", "Номер в журнале": "journal",
          "Преподаватель": "teacher"}


def parse(body: str) -> dict:
    out = {}
    for block in re.split(r"^###\s+", body, flags=re.M)[1:]:
        head, _, val = block.partition("\n")
        val = val.strip()
        if val in ("_No response_", "None"):
            val = ""
        if head.strip() in FIELDS:
            out[FIELDS[head.strip()]] = val
    return out


def output(**kw):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kw.items():
                f.write(f"{k}={v}\n")


def fail(msg):
    Path(os.environ.get("RUNNER_TEMP", "."), "error.md").write_text(msg)
    output(ok=0)
    print(msg)
    sys.exit(0)


def main():
    body = Path(os.environ["ISSUE_BODY_FILE"]).read_text()
    f = parse(body)
    fio = " ".join(f.get("fio", "").split())
    if len(fio.split()) < 2:
        fail("В поле **ФИО** нужны фамилия, имя и отчество полностью — они идут на титульный лист.")
    group = f.get("group", "").strip().replace("A", "А")
    if not (DATA / "variants" / f"{group}.yaml").exists():
        have = ", ".join(p.stem for p in sorted((DATA / "variants").glob("*.yaml")))
        fail(f"Таблицы вариантов для группы **{group or '—'}** пока нет (есть: {have}). "
             "Пришлите docx с вариантами вашей группы владельцу репо.")
    nums = re.findall(r"\d+", f.get("variant", ""))
    if not nums:
        fail("В поле **Вариант** нужен номер варианта, например `17` (из 12-17).")
    variant = int(nums[-1]) % 100
    j = re.search(r"\d+", f.get("journal", ""))
    journal = int(j.group()) if j else variant
    st = Student(fio=fio, group=group, variant=variant, journal=journal,
                 teacher=f.get("teacher") or "Рыбинцев В.О.")
    folder = f"{group}/{variant:02d} {st.short}"
    out = Path(os.environ.get("OUT_DIR", "out")) / folder
    try:
        files, summary = build_all(st, out)
    except SystemExit as e:
        fail(f"Не собралось: {e}")
    except Exception:
        fail("Генератор упал — напишите владельцу репо.\n\n```\n" + traceback.format_exc()[-3000:] + "\n```")
    info = dict(fio=fio, short=st.short, group=group, variant=st.variant_key, journal=journal,
                folder=folder, files=[p.name for p in files],
                summary={k: (v if k != "images" else [p.name for p in v]) for k, v in summary.items()})
    Path(os.environ.get("RUNNER_TEMP", "."), "student.json").write_text(json.dumps(info, ensure_ascii=False))
    output(ok=1, dir=folder)


if __name__ == "__main__":
    main()
