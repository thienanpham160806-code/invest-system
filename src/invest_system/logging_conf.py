"""Cau hinh log dung chung cho toan du an."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_FMT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"


def setup_logging(log_file: str | Path | None = "logs/app.log") -> None:
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    handlers: list[logging.Handler] = []
    # Chay bang pythonw.exe (chay ngam tren Windows) thi sys.stdout la None -
    # khi do chi ghi ra file.
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    logging.basicConfig(level=level, format=_FMT, handlers=handlers, force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
