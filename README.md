# KOSHA Crawler + Naver Cafe Auto-Post

한국산업안전보건공단(KOSHA) OPS 자료를 자동 수집하여 네이버 카페에 게시.

## 기능
- KOSHA 목록·썸네일·첨부파일 자동 수집
- SQLite 이력 관리 (중복 다운로드/업로드 방지)
- 네이버 카페 자동 게시
- 자동 재시도, 로깅, Slack 알림

## 빠른 시작

```bash
git clone <repo>
cd kosha-crawler
cp .env.example .env
# .env 파일에 NAVER_* 값 입력
pip install -r requirements.txt
python scripts/run_once.py
```

## GitHub Actions 배포
Settings → Secrets에 아래 등록:
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `NAVER_REFRESH_TOKEN`
- `SLACK_WEBHOOK_URL` (선택)
