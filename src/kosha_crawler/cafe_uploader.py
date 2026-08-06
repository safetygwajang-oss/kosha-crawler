"""네이버 카페에 크롤링 결과를 게시글로 업로드

인코딩 방식: 네이버 공식 문서 + Python 성공 사례 기반
- urllib.parse.quote()로 UTF-8 URL 인코딩
- data를 dict가 아닌 문자열로 조립 (requests dict 자동 인코딩 회피)
- 첨부파일이 있으면 multipart, 없으면 x-www-form-urlencoded
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

# 네이버 카페 연속 등록 차단 회피용 - 글 사이 대기 시간(초)
UPLOAD_INTERVAL_SEC = 25
# 실패 시 추가 대기(초)
FAILURE_BACKOFF_SEC = 60


def _build_content(media: Media) -> str:
    """게시글 HTML 본문 구성 (원본 한글 그대로)"""
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


def _post_without_image(url: str, token: str, subject: str, content: str) -> requests.Response:
    """이미지 첨부 없이 게시글 등록 (application/x-www-form-urlencoded).
    
    ✅ 네이버 공식 방식:
    1. quote()로 한글 → UTF-8 URL 인코딩 (%EC%9D%B4...)
    2. dict가 아닌 문자열로 body 조립
    3. .encode('utf-8')로 바이트 전송
    """
    encoded_subject = quote(subject)
    encoded_content = quote(content)
    body = f"subject={encoded_subject}&content={encoded_content}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return requests.post(
        url,
        headers=headers,
        data=body.encode("utf-8"),
        timeout=60,
    )


def _post_with_image(url: str, token: str, subject: str, content: str,
                     thumb_path: Path) -> requests.Response:
    """이미지 첨부 있는 게시글 등록 (multipart/form-data).
    
    multipart일 때는 requests가 각 필드를 UTF-8로 넣으므로
    subject/content는 quote()로 미리 URL 인코딩한 문자열을 전달.
    """
    encoded_subject = quote(subject)
    encoded_content = quote(content)

    headers = {"Authorization": f"Bearer {token}"}

    mime = "image/png" if thumb_path.suffix.lower() == ".png" else "image/jpeg"
    with thumb_path.open("rb") as fp:
        files = {
            "subject": (None, encoded_subject),
            "content": (None, encoded_content),
            "image": (thumb_path.name, fp.read(), mime),
        }
        return requests.post(url, headers=headers, files=files, timeout=60)


def upload_article(token_mgr: NaverTokenManager, media: Media) -> dict:
    """미디어 1건을 카페에 업로드."""
    token = token_mgr.get_token()

    subject = f"[KOSHA] {media.title or ''}"
    content = _build_content(media)

    # 첨부 이미지 유무에 따라 다른 방식 사용
    has_thumb = bool(media.thumbnail_path and Path(media.thumbnail_path).exists())

    if has_thumb:
        r = _post_with_image(
            settings.cafe_article_api, token, subject, content,
            Path(media.thumbnail_path)
        )
    else:
        r = _post_without_image(
            settings.cafe_article_api, token, subject, content
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
