from pathlib import Path

from .filesystem import SafetyError, identity, verify_directory


class PathAllowlist:
    def __init__(self, folders: list[Path]):
        if not folders:
            raise SafetyError("허용할 폴더를 하나 이상 지정해 주세요.")
        self._folders = {}
        for folder in folders:
            path = self._absolute(folder)
            lineage = (path, *path.parents)
            expected = {}
            for ancestor in lineage:
                expected[ancestor] = identity(ancestor)
                verify_directory(ancestor, expected[ancestor])
            self._folders[path] = expected

    @staticmethod
    def _absolute(folder: Path) -> Path:
        path = folder.expanduser()
        if not path.is_absolute() or ".." in path.parts:
            raise SafetyError("상위 경로 이동 없이 절대 경로를 지정해 주세요.")
        return path

    def validate(self, folder: Path) -> Path:
        path = self._absolute(folder)
        expected = self._folders.get(path)
        if expected is None:
            raise SafetyError("허용 목록에 등록된 폴더만 접근할 수 있습니다. 하위 폴더는 별도 등록이 필요합니다.")
        for ancestor, information in expected.items():
            verify_directory(ancestor, information)
        return path
