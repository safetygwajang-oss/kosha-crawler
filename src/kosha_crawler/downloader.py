"""파일/썸네일 저장 로직"""
import logging
from .config import settings
from .api import KoshaAPI
from .utils import safe_filename

log = logging.getLogger("kosha")


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

    log.info(f"    [DL] atcflNo={file_info.get('atcflNo')} "
             f"seq={file_info.get('atcflSeq')} "
             f"expected_size={file_info.get('atcflSz', '?')}")

    content = api.download_file(file_info["atcflNo"], file_info["atcflSeq"])

    log.info(f"    [DL] downloaded {len(content)} bytes, "
             f"preview={content[:80]!r}")

    save_path.write_bytes(content)
    return str(save_path), len(content)
