"""네이버 카페 업로드 - 네이버 공식 문서 방식 준수

📖 참고: https://developers.naver.com/docs/login/cafe-api/cafe-api.md
📖 참고: github.com/naver/naver-openapi-guide

✅ multipart 방식일 때: subject/content = 단일 URL 인코딩, 이미지 필드명 = "0"
✅ urlencoded 방식일 때: subject/content = 이중 URL 인코딩
✅ 본문 줄바꿈은 <br> 태그
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

KOSHA_ARCHIVE_HOME = "https://portal.kosha.or.kr/archive/cent-archive/master-arch"


# ============================================
# 🔧 인코딩 유틸
# ============================================

def naver_double_encode(text: str) -> str:
    """이중 URL 인코딩 (urlencoded 방식용)"""
    if not text:
        return ""
    return quote(quote(text, safe=''), safe='')


def naver_single_encode(text: str) -> str:
    """단일 URL 인코딩 (multipart 방식용 - 네이버 공식 문서 기준)"""
    if not text:
        return ""
    return quote(text, safe='', encoding='utf-8')


def convert_newlines_to_br(text: str) -> str:
    """줄바꿈을 <br>로 변환"""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "<br>")
    return text


# ============================================
# 📝 본문 생성
# ============================================

def _build_content(media: Media) -> str:
    """게시글 본문 HTML (이미지는 multipart로 자동 삽입되므로 <img> 태그 X)"""
    reg = media.reg_date or ""
    reg_fmt = f"{reg[:4]}-{reg[4:6]}-{reg[6:8]}" if len(reg) == 8 else reg

    search_kw = quote(media.title or "", safe='')
    kosha_search = f"{KOSHA_ARCHIVE_HOME}?searchKeyword={search_kw}"

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
        f"<p>👉 <a href='{kosha_search}' target='_blank'><b>KOSHA에서 이 자료 검색하기</b></a></p>",
        "<hr>",
        f"<p><small>🤖 KOSHA 자동 수집 · {datetime.now():%Y-%m-%d %H:%M}</small></p>",
    ]
    return "\n".join(parts)


def _get_thumbnail_path(media: Media) -> Path | None:
    """DB에 저장된 썸네일 실물 파일 확인"""
    if not media.thumbnail_path:
        return None
    p = Path(media.thumbnail_path)
    if p.exists() and p.stat().st_size > 0:
        return p
    log.warning(f"  썸네일 실물 없음: {media.thumbnail_path}")
    return None


# ============================================
# 🚀 업로드 - 네이버 공식 문서 기반
# ============================================

def upload_article(token_mgr: NaverTokenManager, media: Media) -> dict:
    """미디어 1건 업로드
    - 썸네일 있음 → multipart + 단일인코딩 + 이미지필드명 "0"
    - 썸네일 없음 → urlencoded + 이중인코딩
    """
    token = token_mgr.get_token()

    subject_raw = f"[KOSHA] {media.title or ''}"
    content_raw = _build_content(media)
    content_html = convert_newlines_to_br(content_raw)

    thumb_path = _get_thumbnail_path(media)

    if thumb_path:
        # ✅ multipart 방식 (네이버 공식 자바 예제 준수)
        # - subject/content: 단일 URL 인코딩
        # - 이미지 필드명: "0" (네이버 공식)
        subject_enc = naver_single_encode(subject_raw)
        content_enc = naver_single_encode(content_html)

        mime = "image/png" if thumb_path.suffix.lower() == ".png" else "image/jpeg"
        with thumb_path.open("rb") as fp:
            img_bytes = fp.read()

        files = {
            "subject": (None, subject_enc),
            "content": (None, content_enc),
            "0": (thumb_path.name, img_bytes, mime),  # ⭐ 필드명 "0"
        }

        log.info(f"  📷 [multipart] 썸네일: {thumb_path.name} ({len(img_bytes):,} bytes)")

        r = requests.post(
            settings.cafe_article_api,
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            timeout=60,
        )
    else:
        # ✅ urlencoded 방식 (검증됨)
        # - subject/content: 이중 URL 인코딩
        subject_enc = naver_double_encode(subject_raw)
        content_enc = naver_double_encode(content_html)

        body = f"subject={subject_enc}&content={content_enc}&openyn=true"

        log.info(f"  📝 [urlencoded] 텍스트 전용")

        r = requests.post(
            settings.cafe_article_api,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=body.encode("ascii"),
            timeout=60,
        )

    log.info(f"  📤 제목: {subject_raw[:60]}")

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
