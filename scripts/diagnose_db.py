"""DB 상태 진단 스크립트"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from kosha_crawler.storage import get_session, Media, MediaFile
from kosha_crawler.config import settings

print("=" * 70)
print(f"DB_PATH: {settings.DB_PATH}")
db_path = Path(settings.DB_PATH)
print(f"DB 파일 존재: {db_path.exists()}")
if db_path.exists():
    print(f"DB 파일 크기: {db_path.stat().st_size:,} bytes")
print("=" * 70)

with get_session() as db:
    total = db.query(Media).count()
    pending = db.query(Media).filter(Media.cafe_uploaded_at.is_(None)).count()
    uploaded = db.query(Media).filter(Media.cafe_uploaded_at.isnot(None)).count()
    with_error = db.query(Media).filter(Media.cafe_upload_error.isnot(None)).count()

    print(f"\n[Media 통계]")
    print(f"  전체:            {total}건")
    print(f"  카페 미업로드:   {pending}건 (재시도 대상)")
    print(f"  카페 업로드완료: {uploaded}건")
    print(f"  에러 이력 있음:  {with_error}건")

    file_count = db.query(MediaFile).count()
    print(f"\n[File 통계]")
    print(f"  전체 파일: {file_count}건")

    print(f"\n[최근 Media 10건]")
    recent = db.query(Media).order_by(Media.crawled_at.desc()).limit(10).all()
    for m in recent:
        if m.cafe_uploaded_at:
            status = "[OK]"
        elif m.cafe_upload_error:
            status = "[ERR]"
        else:
            status = "[WAIT]"
        title = (m.title or "")[:45]
        print(f"  [{m.med_seq}] {status} {title}")
        if m.cafe_upload_error:
            err = m.cafe_upload_error[:80]
            print(f"         └ {err}")

    print("=" * 70)
