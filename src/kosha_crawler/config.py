"""환경설정 - .env 파일에서 로드"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ---- KOSHA API ----
    BASE_URL: str = "https://portal.kosha.or.kr"
    LIST_PATH: str = "/api/portal24/bizV/p/VCPDG01007/selectMediaList"
    FILE_LIST_PATH: str = "/api/portal24/bizA/p/files/getFileList"
    DOWNLOAD_PATH: str = "/api/portal24/bizA/p/files/download"

    # ---- 크롤링 옵션 ----
    SHP_CD: str = "12"
    ROWS_PER_PAGE: int = 12
    MAX_PAGES: int = 5
    REQUEST_DELAY: float = 0.3
    REQUEST_TIMEOUT: int = 30
    DOWNLOAD_TIMEOUT: int = 120

    # ---- 저장 경로 ----
    DATA_DIR: Path = Path("data")
    THUMB_DIR: Path = Path("data/thumbnails")
    FILE_DIR: Path = Path("data/files")
    LOG_DIR: Path = Path("logs")
    DB_PATH: Path = Path("data/kosha.db")

    # ---- 스케줄 ----
    CRON_HOUR: int = 6
    CRON_MINUTE: int = 0
    TIMEZONE: str = "Asia/Seoul"

    # ---- 네이버 카페 ----
    NAVER_CLIENT_ID: str = ""
    NAVER_CLIENT_SECRET: str = ""
    NAVER_REFRESH_TOKEN: str = ""
    NAVER_CAFE_CLUB_ID: str = ""
    NAVER_CAFE_MENU_ID: str = ""
    NAVER_UPLOAD_ENABLED: bool = False
    NAVER_TOKEN_CACHE: Path = Path("data/.naver_token.json")

    # ---- 알림 (선택) ----
    SLACK_WEBHOOK_URL: str = ""
    TEAMS_WEBHOOK_URL: str = ""

    # ---- 로깅 ----
    LOG_LEVEL: str = "INFO"

    @property
    def list_api(self) -> str:
        return f"{self.BASE_URL}{self.LIST_PATH}"

    @property
    def file_list_api(self) -> str:
        return f"{self.BASE_URL}{self.FILE_LIST_PATH}"

    @property
    def download_api(self) -> str:
        return f"{self.BASE_URL}{self.DOWNLOAD_PATH}"

    @property
    def cafe_article_api(self) -> str:
        return f"https://openapi.naver.com/v1/cafe/{self.NAVER_CAFE_CLUB_ID}/menu/{self.NAVER_CAFE_MENU_ID}/articles"

    @property
    def naver_token_url(self) -> str:
        return "https://nid.naver.com/oauth2.0/token"

    def ensure_dirs(self):
        for d in [self.DATA_DIR, self.THUMB_DIR, self.FILE_DIR, self.LOG_DIR]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
