"""네이버 카페에 크롤링 결과를 게시글로 업로드

✅ 검증된 인코딩 방식: 이중 URL 인코딩 (Double URL Encoding)
   - quote(quote(text, safe=''), safe='')
   - Content-Type: application/x-www-form-urlencoded
   - body는 문자열로 조립 후 UTF-8 바이트로 전송
   
   네이버 카페 서버가 MS949 환경이라 UTF-8 %인코딩 문자열(%EC%9D...)을
   한 번 더 %인코딩해서(%25EC%259D...) 보내면 서버가 두 번 디코딩하여
   원래 한글로 정상 복원됨.
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


def naver_double_encode(text: str) -> str:
    """네이버 카페 API용 이중 URL 인코딩.
    
    한글 → %EC%9D%B4... → %25EC%259D%25B4...
    네이버 서버가 두 번 디코딩하여 원래 한글로 복원.
    """
    if not text:
        return ""
    first = quote(text, safe='')
    second = quote(first, safe='')
    return second


def _build_content(media: Media) -> str:
    """게시글 HTML 본문 구성 (원본 한글 그대로 - 인코딩은 전송 직전에)"""
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
    """미디어 1건을 카페에 업로드.
    
    ✅ 검증된 방식: 이중 URL 인코딩 + 문자열 body + UTF-8 전송
    """
    token = token_mgr.get_token()

    # 원본 한글 텍스트 준비
    subject_raw = f"[KOSHA] {media.title or ''}"
    content_raw = _build_content(media)

    # 네이버 이중 인코딩 적용
    subject_encoded = naver_double_encode(subject_raw)
    content_encoded = naver_double_encode(content_raw)

    # 문자열 body 조립 (dict 사용 금지 - requests가 자동 인코딩 시도함)
    body = f"subject={subject_encoded}&content={content_encoded}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    r = requests.post(
        settings.cafe_article_api,
        headers=headers,
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
