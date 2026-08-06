"""1회 실행 (cron / GitHub Actions / 수동)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kosha_crawler import crawl

if __name__ == "__main__":
    result = crawl()
    print(result)
