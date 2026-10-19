# 운영체제별 배포

각 운영체제에서 Python 가상환경을 만들고 `requirements-build.txt`를 설치합니다. 빌드 도구와 Qt 버전은 해당 파일에 고정합니다. macOS의 CPU 아키텍처와 최소 버전은 빌드 환경의 Python·Qt에 따라 결정됩니다.

## macOS

```bash
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python -m scripts.release macos
python -m scripts.verify_macos
```

결과는 `dist/macos/`에 저장됩니다. DMG를 기본 다운로드로 제공하고 ZIP은 대체 다운로드로 제공합니다. 두 파일을 모두 받을 필요는 없습니다.

이전 앱과 용량 비교:

```bash
python -m scripts.release macos --baseline dist/CleanFolder.app
```

기존 `python scripts/build_macos.py` 명령도 지원합니다.

## Windows

Windows PowerShell에서 실행합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-build.txt
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m scripts.release windows
```

결과는 `dist/windows/`에 저장됩니다. ZIP 전체를 풀고 `CleanFolder/CleanFolder.exe`를 실행합니다. 실행 파일만 따로 옮기면 안 됩니다.

Windows 빌드 경로는 준비되어 있으나, Windows에서 직접 빌드·실행 검증하기 전에는 정식 배포본으로 표시하지 않습니다. 현재 Windows 산출물은 설치 마법사가 아닌 포터블 ZIP을 대상으로 합니다.

## 배포 전 확인

- 테스트 전체 통과, 정리·미리보기·복구·휴지통·설정 실제 조작 확인
- Python이 별도로 설치되지 않은 컴퓨터에서 실행 확인
- 한글 파일 이름·긴 경로·이름 충돌·접근 권한 확인
- 기존 버전의 작업 기록과 설정을 읽고 복구할 수 있는지 확인
- macOS 서명·공증, Windows 코드 서명은 별도 절차로 진행
- 새 버전 설치본은 GitHub Releases, 소스는 저장소에 업로드

각 결과 폴더의 `size-report.json`은 심볼릭 링크 중복을 제외한 실제 파일 바이트 합계입니다. Finder·탐색기의 디스크 할당 용량과는 다를 수 있습니다. `SHA256SUMS.txt`로 배포 파일의 해시를 확인할 수 있습니다.

업로드용 소스 ZIP은 `python -m scripts.source_archive`로 만듭니다. 가상환경·빌드 결과·Git 기록은 포함하지 않으며 ZIP 최상위에 README와 프로젝트 파일이 놓입니다.
