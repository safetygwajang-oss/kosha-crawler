"""네이버 카페에 크롤링 결과를 게시글로 업로드"""
import urllib.parse
from pathlib import Path
from datetime import datetime
import requests
from .config import settings
from .naver_auth import NaverTokenManager
from .storage import get_session, get_pending_uploads, Media
from .utils import setup_logging

log = setup_logging("cafe_uploader")


def _sanitize_for_ms949(text: str) -> str:
    """ms949(cp949)로 인코딩 불가능한 모든 문자(이모지 등)를 공백으로 대체.
    한 글자씩 encode 시도하는 방식으로 100% 안전.
    """
    if not text:
        return ""
    result = []
    for ch in text:
        try:
            ch.encode('ms949')
            result.append(ch)
        except UnicodeEncodeError:
            # 이모지 등 인코딩 불가 → 공백으로 대체
            result.append(' ')
    # 연속 공백 정리
    return ''.join(result)


def _build_content(media: Media) -> str:
    """게시글 HTML 본문 구성 (ms949 안전)"""
    reg = media.reg_date or ""
    reg_fmt = f"{reg[:4]}-{reg[4:6]}-{reg[6:8]}" if len(reg) == 8 else reg

    # 제목/설명 모두 sanitize (DB 원본에 이모지가 있을 수 있음)
    safe_title = _sanitize_for_ms949(media.title or "")
    safe_desc = _sanitize_for_ms949(media.description or "")
    safe_pbls = _sanitize_for_ms949(media.pbls_no or "")
    safe_shp = _sanitize_for_ms949(media.shp_nm or "")

    file_lines = []
    for f in media.files:
        safe_name = _sanitize_for_ms949(f.original_name or "")
        file_lines.append(f"- {safe_name} ({f.size:,} bytes)")
    files_block = "<br>".join(file_lines) if file_lines else "(첨부파일 없음)"

    parts = [
        f"<h3>{safe_title}</h3>",
        f"<p><b>등록일:</b> {reg_fmt}<br>",
        f"<b>발행번호:</b> {safe_pbls}<br>",
        f"<b>유형:</b> {safe_shp}</p>",
        "<hr>",
        f"<p>{safe_desc.replace(chr(10), '<br>')}</p>",
        "<hr>",
        f"<p><b>[첨부파일]</b><br>{files_block}</p>",
        f"<p><small>KOSHA 자동 수집 · {datetime.now():%Y-%m-%d %H:%M}</small></p>",
    ]
    return "\n".join(parts)


def upload_article(token_mgr: NaverTokenManager, media: Media) -> dict:
    """미디어 1건을 카페에 업로드"""
    token = token_mgr.get_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 네이버 카페 API는 ms949 인코딩 요구 → 이모지 제거 필수
    safe_title = _sanitize_for_ms949(media.title or "")
    raw_subject = f"[KOSHA] {safe_title}"
    raw_content = _build_content(media)

    # 최종 안전망 (혹시 몰라 한 번 더)
    safe_subject = _sanitize_for_ms949(raw_subject)
    safe_content = _sanitize_for_ms949(raw_content)

    subject = urllib.parse.quote(safe_subject, encoding="ms949")
    content = urllib.parse.quote(safe_content, encoding="ms949")

    data = {"subject": subject, "content": content}

    # 썸네일만 첨부 가능 (이미지 파일)
    files_payload = []
    opened_files = []
    if media.thumbnail_path and Path(media.thumbnail_path).exists():
        thumb_path = Path(media.thumbnail_path)
        fp = thumb_path.open("rb")
        opened_files.append(fp)
        mime = "image/png" if thumb_path.suffix == ".png" else "image/jpeg"
        files_payload.append(("image", (thumb_path.name, fp, mime, {"Expires": "0"})))

    try:
        r = requests.post(
            settings.cafe_article_api,
            headers=headers,
            data=data,
            files=files_payload or None,
            timeout=60,
        )
    finally:
        for fp in opened_files:
            fp.close()

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")

    resp = r.json()
    result = resp.get("message", {}).get("result", {})
    if not result:
        raise RuntimeError(f"응답 파싱 실패: {resp}")
    return result


def upload_pending(limit: int = 20) -> dict:
    """미업로드분을 배치 업로드"""
    if not settings.NAVER_UPLOAD_ENABLED:
        log.info("카페 업로드 비활성화(NAVER_UPLOAD_ENABLED=false)")
        return {"uploaded": 0, "errors": 0, "skipped": True}

    required = [
        settings.NAVER_CLIENT_ID, settings.NAVER_CLIENT_SECRET,
        settings.NAVER_REFRESH_TOKEN, settings.NAVER_CAFE_CLUB_ID,
        settings.NAVER_CAFE_MENU_ID
    ]
    if not all(required):
        log.error("네이버 카페 설정 누락 - .env 확인")
        return {"uploaded": 0, "errors": 0, "skipped": True}

    token_mgr = NaverTokenManager()
    stats = {"uploaded": 0, "errors": 0}

    with get_session() as db:
        pending = get_pending_uploads(db, limit=limit)
        log.info(f"업로드 대기: {len(pending)}건")

        for m in pending:
            try:
                result = upload_article(token_mgr, m)
                m.cafe_uploaded_at = datetime.utcnow()
                m.cafe_article_url = result.get("articleUrl")
                m.cafe_upload_error = None
                stats["uploaded"] += 1
                log.info(f"[OK] 업로드: [{m.med_seq}] {m.title[:40]} -> {m.cafe_article_url}")
            except Exception as e:
                m.cafe_upload_error = str(e)[:1000]
                stats["errors"] += 1
                log.error(f"[FAIL] [{m.med_seq}] {m.title[:40]} - {e}")
            db.commit()

    return stats
