"""DB 상태 진단 스크립트"""
import sys
from pathlib import Path
sys.path.insert(0, "src")

from kosha_crawler.storage import get_session, Media, MediaFile
from kosha_crawler.config import settings

print(f"=" * 60)
print(f"DB_PATH: {settings.DB_PATH}")
print(f"DB 파일 존재: {Path(settings.DB_PATH).exists()}")
if Path(settings.DB_PATH).exists():
    print(f"DB 파일 크기: {Path(settings.DB_PATH).stat().st_size:,} bytes")
print(f"=" * 60)

with get_session() as db:
    total = db.query(Media).count()
    pending = db.query(Media).filter(Media.cafe_uploaded_at.is_(None)).count()
    uploaded = db.query(Media).filter(Media.cafe_uploaded_at.isnot(None)).count()
    with_error = db.query(Media).filter(Media.cafe_upload_error.isnot(None)).count()
    
    print(f"\n📊 Media 통계")
    print(f"  전체:           {total}건")
    print(f"  카페 미업로드:  {pending}건 (재시도 대상)")
    print(f"  카페 업로드완료: {uploaded}건")
    print(f"  에러 이력 있음:  {with_error}건")
    
    print(f"\n📁 File 통계")
    file_count = db.query(MediaFile).count()
    print(f"  전체 파일: {file_count}건")
    
    print(f"\n🔍 최근 Media 10건 상세")
    recent = db.query(Media).order_by(Media.crawled_at.desc()).limit(10).all()
    for m in recent:
        status = "✅업로드" if m.cafe_uploaded_at else ("❌에러" if m.cafe_upload_error else "⏳대기")
        err_preview = (m.cafe_upload_error or "")[:60]
        print(f"  [{m.med_seq}] {status} | {m.title[:40]}")
        if err_preview:
            print(f"        └ err: {err_preview}")
