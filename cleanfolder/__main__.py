import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="CleanFolder")
    parser.add_argument("--preview", type=Path, metavar="FOLDER", help="화면 없이 정리 미리보기")
    arguments = parser.parse_args()
    if arguments.preview:
        from .service import Organizer

        preview = Organizer().preview(arguments.preview)
        for item in preview.files:
            print(f"{item.name} → {item.folder}/{item.name}")
        print(f"정리할 파일 {len(preview.files)}개 · 제외 {preview.skipped}개")
        return 0
    from .ui import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
