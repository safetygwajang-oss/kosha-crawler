"""네이버 카페에 크롤링 결과를 게시글로 업로드"""
import time
import urllib.parse
from pathlib import Path
from datetime import datetime
import requests
from .config import settings
from .naver_auth import NaverTokenManager
from .storage import get_session, get_pending_uploads, Media
from .utils import setup_logging

log = setup_logging("cafe_uploader")

# 네이버 카페 연속 등록 차단 회피용 - 글 사이 대기 시간(초)
UPLOAD_INTERVAL_SEC = 20
# 429/403 등 실패 시 추가 대기(초)
FAILURE_BACKOFF_SEC = 60


def _naver_double_encode(text: str) -> str:
    """네이버 카페 API 전용 이중 URL 인코딩.
    
    핵심: UTF-8로 두 번 URL 인코딩해야 네이버가 정상 디코딩함.
    예: '경력' -> '%EA%B2%BD%EB%A0%A5' -> '%25EA%25B2%25BD%25EB%25A0%25A5'
    """
    if not text:
        return ""
    first = urllib.parse.quote(text, safe='', encoding='utf-8')
    second = urllib.parse.quote(first, safe='')
    return second


def _build_content(media: Media) -> str:
    """게시글 HTML 본문 구성 (원본 한글 그대로 - 인코딩은 상위에서)"""
    reg = media.reg_date or ""
    reg_fmt = f"{reg[:4]}-{reg[4:6]}-{reg[6:8]}" if len(reg) == 8 else reg

    file_lines = []
    for f in media.files:
        file_lines.append(f"- {f.original_name} ({f.size:,} bytes)")
    files_block = "<br>".join(file_lines) if file_lines else "(첨부파일 없음)"

    desc = (media.description or "").replace(chr(10), '<br>')

    parts = [
        f"<h3>{media.title or ''}</h3>",
        f"<p><b>등록일:</b> {reg_fmt}<br>",
        f"<b>발행번호:</b> {media.pbls_no or ''}<br>",
        f"<b>유형:</b> {media.shp_nm or ''}</p>",
        "<hr>",
        f"<p>{desc}</p>",
        "<hr>",
        f"<p><b>[첨부파일]</b><br>{files_block}</p>",
        f"<p><small>KOSHA 자동 수집 · {datetime.now():%Y-%m-%d %H:%M}</small></p>",
    ]
    return "\n".join(parts)


def upload_article(token_mgr: NaverTokenManager, media: Media) -> dict:
    """미디어 1건을 카페에 업로드 (네이버 이중 URL 인코딩 적용)"""
    token = token_mgr.get_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 원본 한글 그대로 준비
    raw_subject = f"[KOSHA] {media.title or ''}"
    raw_content = _build_content(media)

    # 🔑 네이버 이중 URL 인코딩 (UTF-8, 두 번)
    subject = _naver_double_encode(raw_subject)
    content = _naver_double_encode(raw_content)

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
    # 네이버 응답 안에 error가 있는지도 체크 (200이어도 error일 수 있음)
    msg = resp.get("message", {})
    if msg.get("status") and msg.get("status") != "200":
        err = msg.get("error", {})
        raise RuntimeError(f"API error: {err.get('message', str(resp))}")

    result = msg.get("result", {})
    if not result:
        raise RuntimeError(f"응답 파싱 실패: {resp}")
    return result


def upload_pending(limit: int = 20) -> dict:
    """미업로드분을 배치 업로드 (연속 등록 방지 delay 포함)"""
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

                # 마지막 글이 아니면 연속 등록 방지 대기
                if idx < len(pending) - 1:
                    log.info(f"  ...다음 글 업로드까지 {UPLOAD_INTERVAL_SEC}초 대기")
                    time.sleep(UPLOAD_INTERVAL_SEC)

            except Exception as e:
                m.cafe_upload_error = str(e)[:1000]
                stats["errors"] += 1
                title_preview = (m.title or "")[:40]
                log.error(f"[FAIL] ({idx+1}/{len(pending)}) [{m.med_seq}] {title_preview} - {e}")
                db.commit()

                # 실패 시 더 오래 대기 (네이버 차단 회피)
                if "연속으로 등록" in str(e) or "403" in str(e) or "429" in str(e):
                    log.warning(f"  네이버 차단 감지 - {FAILURE_BACKOFF_SEC}초 대기")
                    time.sleep(FAILURE_BACKOFF_SEC)
                elif idx < len(pending) - 1:
                    time.sleep(UPLOAD_INTERVAL_SEC)

    log.info(f"===== 업로드 완료: 성공 {stats['uploaded']}, 실패 {stats['errors']} =====")
    return stats
