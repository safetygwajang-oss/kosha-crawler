"""재시도 자동화된 HTTP 세션"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import settings


def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504, 429],
        allowed_methods=["GET", "POST"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10))
    s.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
        "Origin": settings.BASE_URL,
        "Referer": f"{settings.BASE_URL}/archive/cent-archive/master-arch/master-list1?page=1&rowsPerPage=12",
    })
    return s
