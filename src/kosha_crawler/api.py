"""KOSHA API 래퍼"""
from typing import Any
import requests
from .config import settings


class KoshaAPI:
    def __init__(self, session: requests.Session):
        self.s = session

    def list_media(self, page: int = 1, rows: int | None = None) -> dict[str, Any]:
        payload = {
            "shpCd": settings.SHP_CD,
            "searchCondition": "all",
            "searchValue": None,
            "ascDesc": "desc",
            "page": page,
            "rowsPerPage": rows or settings.ROWS_PER_PAGE,
        }
        r = self.s.post(settings.list_api, json=payload, timeout=settings.REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json().get("payload", {})

    def get_files(self, atcfl_no: str) -> list[dict]:
        payload = {
            "fileId": atcfl_no,
            "fileUploadType": "02",
            "atcflTaskColNm": "lastFile",
            "atcflSeTaskComCdNm": "Y",
        }
        r = self.s.post(settings.file_list_api, json=payload, timeout=settings.REQUEST_TIMEOUT)
        r.raise_for_status()
        payload_data = r.json().get("payload", {})
        if isinstance(payload_data, dict):
            return payload_data.get("list", [])
        return payload_data or []

    def download_file(self, atcfl_no: str, atcfl_seq: int) -> bytes:
        payload = {"atcflNo": atcfl_no, "atcflSeq": atcfl_seq}
        r = self.s.post(settings.download_api, json=payload, timeout=settings.DOWNLOAD_TIMEOUT)
        r.raise_for_status()
        return r.content

    def download_thumbnail(self, thumb_path: str) -> tuple[bytes, str] | None:
        if not thumb_path:
            return None
        r = self.s.get(settings.BASE_URL + thumb_path, timeout=settings.REQUEST_TIMEOUT)
        if r.status_code == 200 and len(r.content) > 100:
            ct = r.headers.get("Content-Type", "")
            ext = ".png" if "png" in ct else ".gif" if "gif" in ct else ".jpg"
            return r.content, ext
        return None
