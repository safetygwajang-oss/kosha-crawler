"""카페 업로드만 실행 (크롤링 없이 pending 처리)"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kosha_crawler.cafe_uploader import upload_pending

if __name__ == "__main__":
    limit = int(os.getenv("UPLOAD_LIMIT", "30"))
    print(f"===== 카페 업로드 전용 실행 (limit={limit}) =====")
    result = upload_pending(limit=limit)
    print(f"===== 결과: {result} =====")
