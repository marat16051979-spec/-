"""Сборка статического демо для GitHub Pages.

    python tools/build_pages.py <папка-вывода>

Кладёт в папку: index.html, static/, app.zip (Python-код движка для Pyodide),
sample.csv (вымышленные данные) и .nojekyll.
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
SAMPLE = BACKEND / "tests" / "fixtures" / "sample.csv"


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)
    for f in (APP / "static").iterdir():
        if f.name == "index.html":
            shutil.copy2(f, out / "index.html")
        elif f.is_file():
            shutil.copy2(f, out / "static" / f.name)
    with zipfile.ZipFile(out / "app.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(APP.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            z.write(f, f.relative_to(BACKEND).as_posix())
    shutil.copy2(SAMPLE, out / "sample.csv")
    (out / ".nojekyll").write_text("")
    print(f"Готово: {out} ({sum(1 for _ in out.rglob('*'))} файлов)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(Path(sys.argv[1]).resolve())
