"""파일/썸네일 저장 로직"""
from .config import settings
from .api import KoshaAPI
from .utils import safe_filename


def save_thumbnail(api: KoshaAPI, med_seq: int, thumb_path: str) -> str | None:
    result = api.download_thumbnail(thumb_path)
    if not result:
        return None
    content, ext = result
    path = settings.THUMB_DIR / f"{med_seq}{ext}"
    path.write_bytes(content)
    return str(path)


def save_file(api: KoshaAPI, file_info: dict) -> tuple[str, int]:
    orig = file_info.get("orgnlAtchFileNm") or file_info.get("atcflOrginlNm", "unknown")
    save_path = settings.FILE_DIR / safe_filename(orig)
    content = api.download_file(file_info["atcflNo"], file_info["atcflSeq"])
    save_path.write_bytes(content)
    return str(save_path), len(content)
