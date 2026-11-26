"""Командная строка для пакетной загрузки и прогона (ежедневный запуск по расписанию).

    python -m app.cli load путь/к/файлу.csv [--append]
    python -m app.cli run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import importer, services
from .db import make_engine, make_session_factory


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="antifraud")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_load = sub.add_parser("load", help="Загрузить CSV/XLSX и пересчитать")
    p_load.add_argument("file")
    p_load.add_argument("--append", action="store_true", help="Дополнить, а не заменить витрину")
    sub.add_parser("run", help="Пересчитать баллы по текущей витрине")
    args = ap.parse_args(argv)

    engine = make_engine()
    Session = make_session_factory(engine)
    services.init_db(engine, Session)
    with Session() as s:
        if args.cmd == "load":
            path = Path(args.file)
            cases, report = importer.parse_file(path.name, path.read_bytes())
            services.import_cases(s, cases, "append" if args.append else "replace")
            print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        run = services.recalculate(s, "cli")
        s.commit()
        print(f"Прогон {run.id}: дел {run.n_cases}, версия правил {run.ruleset_version}, ошибок {len(run.errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
