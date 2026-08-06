"""파일/썸네일 다운로드 상태 진단

- data/files/ 실제 파일 존재 여부, 크기 확인
- data/thumbnails/ 실제 이미지 존재 여부, 크기 확인
- DB File 레코드와 실제 파일 매칭 확인
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kosha_crawler.storage import get_session, Media, File as DbFile

DATA_DIR = Path("data")
FILES_DIR = DATA_DIR / "files"
THUMBS_DIR = DATA_DIR / "thumbnails"


def main():
    print("=" * 70)
    print("파일/썸네일 진단")
    print("=" * 70)

    # 폴더 실물 확인
    print(f"\n[data/files/]")
    if FILES_DIR.exists():
        files = list(FILES_DIR.iterdir())
        print(f"  파일 개수: {len(files)}")
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        print(f"  총 용량: {total_size:,} bytes")
        for f in files[:10]:
            if f.is_file():
                print(f"  - {f.name} ({f.stat().st_size:,} bytes)")
        if len(files) > 10:
            print(f"  ... 외 {len(files)-10}개")
    else:
        print("  ❌ 폴더 없음!")

    print(f"\n[data/thumbnails/]")
    if THUMBS_DIR.exists():
        thumbs = list(THUMBS_DIR.iterdir())
        print(f"  파일 개수: {len(thumbs)}")
        total_size = sum(f.stat().st_size for f in thumbs if f.is_file())
        print(f"  총 용량: {total_size:,} bytes")
        for f in thumbs[:10]:
            if f.is_file():
                print(f"  - {f.name} ({f.stat().st_size:,} bytes)")
        if len(thumbs) > 10:
            print(f"  ... 외 {len(thumbs)-10}개")
    else:
        print("  ❌ 폴더 없음!")

    # DB와 실물 대조
    print(f"\n[DB ↔ 실물 대조 - 최근 미디어 5건]")
    with get_session() as db:
        medias = db.query(Media).order_by(Media.med_seq.desc()).limit(5).all()
        for m in medias:
            print(f"\n  [{m.med_seq}] {(m.title or '')[:40]}")
            print(f"    thumbnail_path DB값: {m.thumbnail_path}")
            if m.thumbnail_path:
                p = Path(m.thumbnail_path)
                if p.exists():
                    print(f"    ✅ 썸네일 실물 존재: {p.stat().st_size:,} bytes")
                else:
                    print(f"    ❌ 썸네일 실물 없음")

            for f in m.files:
                print(f"    파일: {f.original_name}")
                print(f"      local_path DB값: {f.local_path}")
                print(f"      DB size 필드: {f.size}")
                if f.local_path:
                    p = Path(f.local_path)
                    if p.exists():
                        print(f"      ✅ 실물 존재: {p.stat().st_size:,} bytes")
                    else:
                        print(f"      ❌ 실물 없음")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
