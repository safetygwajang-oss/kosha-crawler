"""크롤링 오케스트레이션"""
import time
from datetime import datetime
from .config import settings
from .session import build_session
from .api import KoshaAPI
from .downloader import save_thumbnail, save_file
from .storage import get_session, Media, MediaFile, is_media_seen, is_file_downloaded
from .utils import setup_logging
from .notifier import notify

log = setup_logging()


def crawl_page(api: KoshaAPI, page: int) -> dict:
    result = api.list_media(page=page)
    items = result.get("list", [])
    stats = {"new_media": 0, "new_files": 0, "skipped": 0, "errors": 0}

    with get_session() as db:
        for it in items:
            med_seq = it["medSeq"]
            title = it.get("medName", "")

            if is_media_seen(db, med_seq):
                stats["skipped"] += 1
                log.debug(f"skip: {med_seq} {title[:40]}")
                continue

            log.info(f"NEW [{med_seq}] {title}")

            # 썸네일
            thumb_path = None
            try:
                thumb_path = save_thumbnail(api, med_seq, it.get("medThumbnailPath", ""))
            except Exception as e:
                log.warning(f"  썸네일 실패: {e}")

            # 미디어 저장
            media = Media(
                med_seq=med_seq,
                title=title,
                description=it.get("medNote"),
                keyword=it.get("medKeyword"),
                reg_date=it.get("contsRegYmd"),
                pbls_no=it.get("contsPblsNo"),
                shp_nm=it.get("contsFbctnShpNm"),
                atcfl_no=it.get("contsAtcflNo"),
                thumbnail_path=thumb_path,
            )
            db.add(media)
            stats["new_media"] += 1

            # 첨부파일
            if it.get("contsAtcflNo"):
                try:
                    files = api.get_files(it["contsAtcflNo"])
                    for f in files:
                        if is_file_downloaded(db, f["atcflNo"], f["atcflSeq"], f.get("atcflSz")):
                            continue
                        try:
                            path, size = save_file(api, f)
                            db.add(MediaFile(
                                med_seq=med_seq,
                                atcfl_no=f["atcflNo"],
                                atcfl_seq=f["atcflSeq"],
                                original_name=f.get("orgnlAtchFileNm"),
                                saved_path=path,
                                size=size,
                            ))
                            stats["new_files"] += 1
                            log.info(f"    📎 {f.get('orgnlAtchFileNm')} ({size:,} B)")
                            time.sleep(settings.REQUEST_DELAY)
                        except Exception as e:
                            stats["errors"] += 1
                            log.error(f"    파일 실패: {f.get('orgnlAtchFileNm')} - {e}")
                except Exception as e:
                    stats["errors"] += 1
                    log.error(f"  첨부목록 실패: {e}")

            time.sleep(settings.REQUEST_DELAY)
        db.commit()

    return stats


def crawl(max_pages: int | None = None) -> dict:
    max_pages = max_pages or settings.MAX_PAGES
    started = datetime.now()
    log.info(f"===== 크롤링 시작 (max_pages={max_pages}) =====")

    session = build_session()
    api = KoshaAPI(session)
    total = {"new_media": 0, "new_files": 0, "skipped": 0, "errors": 0, "pages": 0}

    try:
        for page in range(1, max_pages + 1):
            log.info(f"--- Page {page} ---")
            stats = crawl_page(api, page)
            total["pages"] += 1
            for k in ["new_media", "new_files", "skipped", "errors"]:
                total[k] += stats[k]
            # 신규가 하나도 없는 페이지면 조기 종료 (증분 크롤링)
            if stats["new_media"] == 0 and page > 1:
                log.info(f"신규 없음 → 조기 종료 (page {page})")
                break
    finally:
        elapsed = (datetime.now() - started).total_seconds()
        log.info(
            f"===== 완료: {total['new_media']}건 신규, {total['new_files']}파일 다운, "
            f"{total['skipped']} 스킵, {total['errors']} 에러, {elapsed:.1f}s ====="
        )
        notify(f"[KOSHA] 신규 {total['new_media']} / 파일 {total['new_files']} / 에러 {total['errors']} ({elapsed:.0f}s)")

    return total
