"""네이버 OAuth 토큰 관리 (자동 갱신)"""
import json
import time
from pathlib import Path
import requests
from .config import settings
from .utils import setup_logging

log = setup_logging("naver_auth")


class NaverTokenManager:
    """Access Token을 캐시하고 만료 시 Refresh Token으로 자동 갱신"""

    def __init__(self):
        self.cache_path: Path = settings.NAVER_TOKEN_CACHE
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._load_cache()

    def _load_cache(self):
        if self.cache_path.exists():
            try:
                d = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._token = d.get("access_token")
                self._expires_at = d.get("expires_at", 0)
            except Exception:
                pass

    def _save_cache(self):
        self.cache_path.write_text(json.dumps({
            "access_token": self._token,
            "expires_at": self._expires_at,
        }), encoding="utf-8")

    def _refresh(self) -> str:
        log.info("네이버 access_token 재발급 중...")
        r = requests.post(
            settings.naver_token_url,
            params={
                "grant_type": "refresh_token",
                "client_id": settings.NAVER_CLIENT_ID,
                "client_secret": settings.NAVER_CLIENT_SECRET,
                "refresh_token": settings.NAVER_REFRESH_TOKEN,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if "access_token" not in data:
            raise RuntimeError(f"토큰 발급 실패: {data}")
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        self._save_cache()
        log.info("access_token 발급 완료")
        return self._token

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        return self._refresh()
