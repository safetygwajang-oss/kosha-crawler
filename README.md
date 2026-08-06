# KOSHA Crawler

한국산업안전보건공단(KOSHA) 자료실 OPS 게시물 자동 수집기.

## 기능
- 목록·썸네일·첨부파일 자동 수집
- SQLite 이력 관리로 **중복 다운로드 방지**
- **증분 크롤링**: 신규 없는 페이지에서 조기 종료
- 자동 재시도, 로깅, Slack/Teams 알림
- Docker · GitHub Actions · cron 모두 지원

## 빠른 시작

```bash
git clone <repo>
cd kosha-crawler
cp .env.example .env
pip install -r requirements.txt

# 1회 실행
python scripts/run_once.py

# 상주 스케줄러
python scripts/run_scheduler.py
```

## Docker 배포

```bash
docker compose up -d
docker compose logs -f
```

## 배포 옵션

| 방법 | 특징 |
|------|------|
| GitHub Actions | 서버 불필요, 무료 |
| Docker | 사내 서버, 완전 격리 |
| cron + venv | 심플, 기존 리눅스 서버 |

## 폴더 구조
```
data/
├── thumbnails/    # 썸네일 이미지
├── files/         # PDF 등 원본 첨부
└── kosha.db       # 이력 DB
logs/              # 월별 로그
```
