"""크롤링 없이 업로드만 재시도"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kosha_crawler import upload_pending

if __name__ == "__main__":
    result = upload_pending(limit=50)
    print(result)
