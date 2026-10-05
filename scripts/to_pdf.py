"""docx → PDF через LibreOffice (UNO) с обновлением содержания и полей.

Запускать питоном, в котором есть модуль uno:
  Ubuntu: sudo apt-get install libreoffice-writer python3-uno  → python3 scripts/to_pdf.py файлы…
  macOS:  /Applications/LibreOffice.app/Contents/Resources/python scripts/to_pdf.py файлы…
Сам поднимает soffice в фоне и гасит его в конце. PDF кладётся рядом с docx.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def soffice_bin():
    for c in ("soffice", "libreoffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if shutil.which(c) or os.path.exists(c):
            return shutil.which(c) or c
    raise SystemExit("не найден soffice")


def main(paths):
    profile = tempfile.mkdtemp(prefix="lo-profile-")
    port = 2002 + os.getpid() % 1000
    proc = subprocess.Popen([soffice_bin(), "--headless", "--invisible", "--norestore", "--nologo",
                             f"-env:UserInstallation=file://{profile}",
                             f"--accept=socket,host=127.0.0.1,port={port};urp;"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        for _ in range(120):
            try:
                ctx = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise SystemExit("soffice не поднялся")
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        for p in paths:
            p = Path(p).resolve()
            doc = desktop.loadComponentFromURL(p.as_uri(), "_blank", 0, (prop("Hidden", True),))
            try:
                for _ in range(2):   # второй проход — номера страниц после появления содержания
                    idx = doc.getDocumentIndexes()
                    for i in range(idx.getCount()):
                        idx.getByIndex(i).update()
                    doc.getTextFields().refresh()
                doc.storeToURL(p.with_suffix(".pdf").as_uri(), (prop("FilterName", "writer_pdf_Export"),))
                print(p.with_suffix(".pdf"))
            finally:
                doc.close(True)
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:])
