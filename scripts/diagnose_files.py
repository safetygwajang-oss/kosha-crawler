"""파일/썸네일 다운로드 상태 진단 + Media 모델 필드 자동 탐지"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import inspect
from kosha_crawler.storage import get_session, Media


def main():
    print("=" * 70)
    print("Media 모델 컬럼 목록 (실제 DB 스키마)")
    print("=" * 70)
    mapper = inspect(Media)
    for col in mapper.columns:
        print(f"  - {col.name}  ({col.type})")

    print("\n" + "=" * 70)
    print("최근 Media 5건 - 모든 필드값 출력")
    print("=" * 70)

    with get_session() as db:
        medias = db.query(Media).order_by(Media.med_seq.desc()).limit(5).all()
        for m in medias:
            print(f"\n[{m.med_seq}] {(m.title or '')[:50]}")
            for col in mapper.columns:
                val = getattr(m, col.name, None)
                if val is None or val == "":
                    continue
                sval = str(val)
                if len(sval) > 150:
                    sval = sval[:150] + "..."
                print(f"    {col.name}: {sval}")

            # 파일 목록
            if hasattr(m, "files") and m.files:
                print(f"    [files: {len(m.files)}개]")
                for f in m.files[:3]:
                    print(f"      - {f.original_name}")
                    for attr in ["local_path", "download_url", "url", "size", "atcfl_no"]:
                        if hasattr(f, attr):
                            v = getattr(f, attr)
                            if v:
                                print(f"        {attr}: {str(v)[:120]}")

    # 실물 파일 재확인
    print("\n" + "=" * 70)
    print("실물 파일 존재 여부")
    print("=" * 70)
    for folder_name in ["files", "thumbnails"]:
        folder = Path("data") / folder_name
        print(f"\n[data/{folder_name}/]")
        if not folder.exists():
            print("  ❌ 폴더 없음")
            continue
        items = [p for p in folder.iterdir() if p.is_file()]
        print(f"  파일 개수: {len(items)}")
        for p in items[:5]:
            print(f"    - {p.name} ({p.stat().st_size:,} bytes)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
