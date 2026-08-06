"""네이버 카페 업로드 (썸네일 이미지 첨부 + KOSHA 원본 링크)

✅ 인코딩: 이중 URL 인코딩 (urlencoded / multipart 모두 동일)
✅ 이미지: DB의 thumbnail_path 로컬 파일을 image 필드로 multipart 전송
✅ 파일: 본문에 KOSHA 자료실 검색 링크 삽입 (네이버 API가 이미지만 지원)
"""
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import requests
from .config import settings
from .naver_auth import NaverTokenManager
from .storage import get_session, get_pending_uploads, Media
from .utils import setup_logging

log = setup_logging("cafe_uploader")

UPLOAD_INTERVAL_SEC = 25
FAILURE_BACKOFF_SEC = 60

# KOSHA 자료실
KOSHA_ARCHIVE_HOME = "https://portal.kosha.or.kr/archive/cent-archive/master-arch"


def naver_double_encode(text: str) -> str:
    """네이버 카페 API용 이중 URL 인코딩 (검증됨)"""
    if not text:
        return ""
    return quote(quote(text, safe=''), safe='')


def _build_content(media: Media) -> str:
    """게시글 본문 HTML"""
    reg = media.reg_date or ""
    reg_fmt = f"{reg[:4]}-{reg[4:6]}-{reg[6:8]}" if len(reg) == 8 else reg

    # KOSHA 자료실 검색 링크 (제목으로 검색)
    search_kw = quote(media.title or "", safe='')
    kosha_search = f"{KOSHA_ARCHIVE_HOME}?searchKeyword={search_kw}"

    file_lines = []
    for f in media.files:
        file_lines.append(f"📎 {f.original_name}")
    files_block = "<br>".join(file_lines) if file_lines else "(첨부파일 없음)"

    desc = (media.description or "").replace(chr(10), '<br>')

    parts = [
        f"<h3>{media.title or ''}</h3>",
        f"<p>",
        f"<b>📅 등록일:</b> {reg_fmt}<br>",
        f"<b>📄 발행번호:</b> {media.pbls_no or ''}<br>",
        f"<b>📂 유형:</b> {media.shp_nm or ''}<br>",
        f"<b>🔖 자료번호:</b> {media.med_seq}",
        f"</p>",
        "<hr>",
        f"<p>{desc}</p>",
        "<hr>",
        f"<p><b>📥 첨부파일 (KOSHA 원본에서 다운로드)</b><br>",
        f"{files_block}</p>",
        f"<p>👉 <a href='{kosha_search}' target='_blank'><b>KOSHA에서 이 자료 검색하기</b></a><br>",
        f"👉 <a href='{KOSHA_ARCHIVE_HOME}' target='_blank'>KOSHA 안전보건자료실 바로가기</a></p>",
        "<hr>",
        f"<p><small>🤖 KOSHA 자동 수집 · {datetime.now():%Y-%m-%d %H:%M}</small></p>",
    ]
    return "\n".join(parts)


def _get_thumbnail_path(media: Media) -> Path | None:
    """DB에 저장된 썸네일 경로에서 실물 확인"""
    if not media.thumbnail_path:
        return None
    p = Path(media.thumbnail_path)
    if p.exists() and p.stat().st_size > 0:
        return p
    log.warning(f"  썸네일 실물 없음: {media.thumbnail_path}")
    return None


def upload_article(token_mgr: NaverTokenManager, media: Media) -> dict:
    """미디어 1건 업로드 - 썸네일 있으면 image 첨부, 없으면 텍스트만"""
    token = token_mgr.get_token()

    subject_raw = f"[KOSHA] {media.title or ''}"
    content_raw = _build_content(media)

    # 이중 인코딩 (multipart / urlencoded 모두 동일하게 적용)
    subject_encoded = naver_double_encode(subject_raw)
    content_encoded = naver_double_encode(content_raw)

    thumb_path = _get_thumbnail_path(media)

    if thumb_path:
        # multipart with image: 이중 인코딩된 ASCII 문자열을 그대로 전송
        mime = "image/png" if thumb_path.suffix.lower() == ".png" else "image/jpeg"
        with thumb_path.open("rb") as fp:
            img_bytes = fp.read()
        files = {
            "subject": (None, subject_encoded),
            "content": (None, content_encoded),
            "image": (thumb_path.name, img_bytes, mime, {"Expires": "0"}),
        }
        log.info(f"  📷 썸네일 첨부: {thumb_path.name} ({len(img_bytes):,} bytes)")
        r = requests.post(
            settings.cafe_article_api,
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            timeout=60,
        )
    else:
        # urlencoded: 이중 인코딩
        body = f"subject={subject_encoded}&content={content_encoded}"
        r = requests.post(
            settings.cafe_article_api,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=body.encode("utf-8"),
            timeout=60,
        )

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")

    resp = r.json()
    msg = resp.get("message", {})
    if msg.get("status") and str(msg.get("status")) != "200":
        err = msg.get("error", {})
        raise RuntimeError(f"API error: {err.get('message', str(resp))}")

    result = msg.get("result", {})
    if not result:
        raise RuntimeError(f"응답 파싱 실패: {resp}")
    return result


def upload_pending(limit: int = 20) -> dict:
    if not settings.NAVER_UPLOAD_ENABLED:
        log.info("카페 업로드 비활성화")
        return {"uploaded": 0, "errors": 0, "skipped": True}

    required = [
        settings.NAVER_CLIENT_ID, settings.NAVER_CLIENT_SECRET,
        settings.NAVER_REFRESH_TOKEN, settings.NAVER_CAFE_CLUB_ID,
        settings.NAVER_CAFE_MENU_ID
    ]
    if not all(required):
        log.error("네이버 카페 설정 누락")
        return {"uploaded": 0, "errors": 0, "skipped": True}

    token_mgr = NaverTokenManager()
    stats = {"uploaded": 0, "errors": 0}

    with get_session() as db:
        pending = get_pending_uploads(db, limit=limit)
        log.info(f"업로드 대기: {len(pending)}건 (간격 {UPLOAD_INTERVAL_SEC}s)")

        for idx, m in enumerate(pending):
            try:
                result = upload_article(token_mgr, m)
                m.cafe_uploaded_at = datetime.utcnow()
                m.cafe_article_url = result.get("articleUrl")
                m.cafe_upload_error = None
                stats["uploaded"] += 1
                title_preview = (m.title or "")[:40]
                log.info(f"[OK] ({idx+1}/{len(pending)}) [{m.med_seq}] {title_preview} -> {m.cafe_article_url}")
                db.commit()

                if idx < len(pending) - 1:
                    log.info(f"  ...다음 글까지 {UPLOAD_INTERVAL_SEC}초 대기")
                    time.sleep(UPLOAD_INTERVAL_SEC)

            except Exception as e:
                m.cafe_upload_error = str(e)[:1000]
                stats["errors"] += 1
                title_preview = (m.title or "")[:40]
                log.error(f"[FAIL] ({idx+1}/{len(pending)}) [{m.med_seq}] {title_preview} - {e}")
                db.commit()

                if "연속으로 등록" in str(e) or "403" in str(e) or "429" in str(e):
                    log.warning(f"  네이버 차단 감지 - {FAILURE_BACKOFF_SEC}초 대기")
                    time.sleep(FAILURE_BACKOFF_SEC)
                elif idx < len(pending) - 1:
                    time.sleep(UPLOAD_INTERVAL_SEC)

    log.info(f"===== 업로드 완료: 성공 {stats['uploaded']}, 실패 {stats['errors']} =====")
    return stats
