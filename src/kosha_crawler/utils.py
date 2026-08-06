"""공용 유틸리티"""
import logging
from datetime import datetime
from .config import settings


def safe_filename(name: str) -> str:
    """파일 시스템에 안전한 이름으로 변환"""
    for ch in '<>:"/\\|?*\n\r\t':
        name = name.replace(ch, "_")
    return name.strip()[:200]  # 너무 긴 이름 방지


def setup_logging(name: str = "kosha") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log

    log.setLevel(settings.LOG_LEVEL)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

    fh = logging.FileHandler(
        settings.LOG_DIR / f"crawler_{datetime.now():%Y%m}.log",
        encoding="utf-8"
    )
    fh.setFormatter(fmt)
    log.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    return log
