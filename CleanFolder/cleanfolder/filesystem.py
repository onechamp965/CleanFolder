import os
import stat
import unicodedata
from pathlib import Path


class SafetyError(Exception):
    pass


def identity(path: Path) -> list[int]:
    information = path.lstat()
    return [information.st_dev, information.st_ino]


def regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except FileNotFoundError:
        return False


def verify_directory(path: Path, expected: list[int]) -> None:
    if not stat.S_ISDIR(path.lstat().st_mode) or identity(path) != expected:
        raise SafetyError(f"폴더가 변경되었습니다: {path}")


def verify_file(path: Path, expected: list[int]) -> None:
    if not regular_file(path) or identity(path) != expected:
        raise SafetyError(f"파일이 없거나 다른 파일로 바뀌었습니다: {path.name}")


def name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def available_name(parent: Path, name: str, reserved: set[str] | None = None) -> str:
    occupied = {name_key(entry.name) for entry in parent.iterdir()}
    occupied.update(reserved or ())
    candidate = name
    suffix = Path(name).suffix
    stem = name[:-len(suffix)] if suffix else name
    counter = 1
    while name_key(candidate) in occupied:
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def move_exclusive(
    source: Path, destination: Path, expected: list[int],
    source_parent: list[int] | None = None,
    destination_parent: list[int] | None = None,
) -> None:
    if os.name == "posix":
        source_descriptor = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            target_descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for descriptor, parent_identity in ((source_descriptor, source_parent), (target_descriptor, destination_parent)):
                    information = os.fstat(descriptor)
                    if parent_identity is not None and [information.st_dev, information.st_ino] != parent_identity:
                        raise SafetyError("파일을 담은 폴더가 변경되었습니다.")
                source_information = os.stat(source.name, dir_fd=source_descriptor, follow_symlinks=False)
                if not stat.S_ISREG(source_information.st_mode) or [source_information.st_dev, source_information.st_ino] != expected:
                    raise SafetyError(f"파일이 변경되었습니다: {source.name}")
                os.link(source.name, destination.name, src_dir_fd=source_descriptor,
                        dst_dir_fd=target_descriptor, follow_symlinks=False)
                try:
                    for descriptor, name in ((source_descriptor, source.name), (target_descriptor, destination.name)):
                        information = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                        if not stat.S_ISREG(information.st_mode) or [information.st_dev, information.st_ino] != expected:
                            raise SafetyError(f"파일이 변경되었습니다: {name}")
                    os.unlink(source.name, dir_fd=source_descriptor)
                except BaseException:
                    information = os.stat(destination.name, dir_fd=target_descriptor, follow_symlinks=False)
                    if stat.S_ISREG(information.st_mode) and [information.st_dev, information.st_ino] == expected:
                        os.unlink(destination.name, dir_fd=target_descriptor)
                    raise
            finally:
                os.close(target_descriptor)
        finally:
            os.close(source_descriptor)
        return
    if source_parent is not None:
        verify_directory(source.parent, source_parent)
    if destination_parent is not None:
        verify_directory(destination.parent, destination_parent)
    verify_file(source, expected)
    os.link(source, destination, follow_symlinks=False)
    try:
        verify_file(destination, expected)
        verify_file(source, expected)
        source.unlink()
    except BaseException:
        if regular_file(destination) and identity(destination) == expected:
            destination.unlink()
        raise
