"""네이버 카페 업로드 (검증된 이중 인코딩 방식)

✅ 제목/본문 모두 이중 URL 인코딩
✅ urlencoded 방식으로 통일 (multipart 제거)
✅ 썸네일은 본문에 <img> 태그로 삽입 (KOSHA 원본 URL)
✅ 줄바꿈은 <br> 태그로 변환
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


# ============================================
# 🔧 인코딩 유틸 (검증된 방식)
# ============================================

def naver_double_encode(text: str) -> str:
    """네이버 카페 API 전용 이중 URL 인코딩"""
    if not text:
        return ""
    first = quote(text, safe='')
    second = quote(first, safe='')
    return second


def convert_newlines_to_br(text: str) -> str:
    """줄바꿈을 <br>로 변환 (네이버 카페 API가 \\n 무시함)"""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "<br>")
    return text


# ============================================
# 📝 본문 생성
# ============================================

def _build_content(media: Media, thumb_url: str = None) -> str:
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

    parts = []

    # 썸네일 이미지 (있으면 상단에)
    if thumb_url:
        parts.append(f"<p><img src='{thumb_url}' alt='썸네일' /></p>")

    parts.extend([
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
    ])
    return "\n".join(parts)


def _get_thumbnail_url(media: Media) -> str | None:
    """
    KOSHA 원본 썸네일 URL 반환
    - media 객체에 thumbnail_url 필드가 있으면 그거 사용
    - 없으면 med_seq로 KOSHA 썸네일 API URL 생성
    """
    # 우선순위 1: DB에 저장된 원본 URL
    if hasattr(media, 'thumbnail_url') and media.thumbnail_url:
        return media.thumbnail_url
    
    # 우선순위 2: med_seq 기반 KOSHA 썸네일 API
    if media.med_seq:
        return f"https://portal.kosha.or.kr/archive/cent-archive/master-arch/master-list4/viewThumbnail?medSeq={media.med_seq}"
    
    return None


# ============================================
# 🚀 업로드 (검증된 이중 인코딩 방식)
# ============================================

def upload_article(token_mgr: NaverTokenManager, media: Media) -> dict:
    """미디어 1건 업로드 - 이중 인코딩 방식"""
    token = token_mgr.get_token()

    # 원문 생성
    subject_raw = f"[KOSHA] {media.title or ''}"
    thumb_url = _get_thumbnail_url(media)
    content_raw = _build_content(media, thumb_url=thumb_url)

    # ⭐ 줄바꿈 → <br> 변환
    content_html = convert_newlines_to_br(content_raw)

    # ⭐ 이중 인코딩 (제목/본문 동일)
    subject_encoded = naver_double_encode(subject_raw)
    content_encoded = naver_double_encode(content_html)

    # body 조립
    body = f"subject={subject_encoded}&content={content_encoded}&openyn=true"

    log.info(f"  📤 업로드: {subject_raw[:50]}")
    if thumb_url:
        log.info(f"  🖼️  썸네일 URL: {thumb_url}")

    r = requests.post(
        settings.cafe_article_api,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body.encode("ascii"),  # ⭐ ASCII 인코딩이 핵심!
        timeout=60,
    )

    if r.status_code not in (200, 201):
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
