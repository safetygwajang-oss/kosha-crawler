"""네이버 카페 업로드 (이미지 첨부 + KOSHA 원본 링크)

✅ 인코딩: 이중 URL 인코딩 (검증됨)
✅ 이미지 첨부: KOSHA 썸네일을 즉시 다운로드해 image 필드로 multipart 전송
✅ PDF 등 파일: 본문에 KOSHA 원본 링크 삽입 (네이버 API는 이미지만 지원)
"""
import time
import tempfile
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

# KOSHA 원본 상세 페이지 URL 템플릿 (med_seq 기반)
# 실제 KOSHA 사이트 구조에 맞게 필요시 조정
KOSHA_DETAIL_URL = "https://www.kosha.or.kr/kosha/report/medFocData.do?medSeq={med_seq}"

# 네이버 카페 이미지 첨부 제한
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif"}


def naver_double_encode(text: str) -> str:
    """네이버 카페 API용 이중 URL 인코딩 (검증됨)"""
    if not text:
        return ""
    return quote(quote(text, safe=''), safe='')


def _download_thumbnail(media: Media) -> Path | None:
    """KOSHA 썸네일을 임시 파일로 즉시 다운로드.
    성공 시 파일 경로 반환, 실패 시 None.
    호출자가 사용 후 파일 삭제 책임.
    """
    if not media.thumbnail_url:
        return None

    try:
        # 절대 URL 조립
        url = media.thumbnail_url
        if url.startswith("/"):
            url = settings.KOSHA_BASE_URL.rstrip("/") + url

        r = requests.get(url, timeout=30, stream=True)
        if r.status_code != 200:
            log.warning(f"  썸네일 다운로드 실패 HTTP {r.status_code}: {url}")
            return None

        # 확장자 추출 (Content-Type 우선, URL suffix 보조)
        ct = r.headers.get("Content-Type", "").lower()
        if "png" in ct:
            ext = ".png"
        elif "gif" in ct:
            ext = ".gif"
        else:
            ext = ".jpg"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        size = 0
        for chunk in r.iter_content(8192):
            tmp.write(chunk)
            size += len(chunk)
            if size > MAX_IMAGE_SIZE:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                log.warning(f"  썸네일 크기 초과({size}): {url}")
                return None
        tmp.close()

        if size == 0:
            Path(tmp.name).unlink(missing_ok=True)
            return None

        log.info(f"  썸네일 다운로드 완료: {size:,} bytes ({ext})")
        return Path(tmp.name)

    except Exception as e:
        log.warning(f"  썸네일 다운로드 예외: {e}")
        return None


def _build_content(media: Media) -> str:
    """게시글 본문 HTML (원본 링크 포함)"""
    reg = media.reg_date or ""
    reg_fmt = f"{reg[:4]}-{reg[4:6]}-{reg[6:8]}" if len(reg) == 8 else reg

    # KOSHA 원본 페이지 링크
    kosha_link = KOSHA_DETAIL_URL.format(med_seq=media.med_seq)

    # 파일 목록 (KOSHA 원본에서 다운로드 안내)
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
        f"<b>📂 유형:</b> {media.shp_nm or ''}",
        f"</p>",
        "<hr>",
        f"<p>{desc}</p>",
        "<hr>",
        f"<p><b>📥 첨부파일 다운로드</b><br>",
        f"{files_block}<br><br>",
        f"👉 <a href='{kosha_link}' target='_blank'><b>KOSHA 원본 페이지에서 다운로드</b></a><br>",
        f"<small>({kosha_link})</small>",
        f"</p>",
        "<hr>",
        f"<p><small>🤖 KOSHA 자동 수집 · {datetime.now():%Y-%m-%d %H:%M}</small></p>",
    ]
    return "\n".join(parts)


def upload_article(token_mgr: NaverTokenManager, media: Media) -> dict:
    """미디어 1건을 카페에 업로드 (이미지 첨부 시도)"""
    token = token_mgr.get_token()

    subject_raw = f"[KOSHA] {media.title or ''}"
    content_raw = _build_content(media)

    subject_encoded = naver_double_encode(subject_raw)
    content_encoded = naver_double_encode(content_raw)

    # 썸네일 즉시 다운로드 시도
    thumb_path = _download_thumbnail(media)

    try:
        if thumb_path and thumb_path.exists():
            # multipart로 이미지 첨부
            mime = "image/png" if thumb_path.suffix.lower() == ".png" else "image/jpeg"
            with thumb_path.open("rb") as fp:
                files = {
                    "subject": (None, subject_encoded),
                    "content": (None, content_encoded),
                    "image": (thumb_path.name, fp.read(), mime, {"Expires": "0"}),
                }
                r = requests.post(
                    settings.cafe_article_api,
                    headers={"Authorization": f"Bearer {token}"},
                    files=files,
                    timeout=60,
                )
        else:
            # 이미지 없이 form-urlencoded
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
    finally:
        # 임시 파일 정리
        if thumb_path:
            try:
                thumb_path.unlink(missing_ok=True)
            except Exception:
                pass

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
