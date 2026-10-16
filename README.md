# CleanFolder

선택한 폴더의 파일을 종류별로 정리하는 macOS 우선 데스크톱 앱입니다. 정리 전 미리보기와 최근 작업 복구를 제공합니다.

## 주요 기능

- 최상위 파일만 검사하고 정리 전 이동 위치 표시
- 파일 종류별 분류 및 파일명 충돌 시 새 이름 생성
- 설치 파일 선택 후 운영체제 휴지통으로 이동
- 앱 재실행 후에도 유지되는 작업 기록과 **원래대로 돌리기**
- 복구 시 앱이 만든 빈 분류 폴더 제거
- 전용 앱 아이콘 및 밝은 화면·어두운 화면에 맞춰 표시되는 버튼·탭 아이콘
- 사이드바 탐색, 파일 수·용량 요약, 정리할 파일이 없을 때의 상태 안내

## 분류 기준

확장자의 대소문자를 구분하지 않습니다. 대표 확장자는 다음과 같으며 전체 목록은 `cleanfolder/categories.py`에 있습니다.

| 분류 | 확장자 |
| --- | --- |
| Word | `.doc`, `.docx`, `.docm`, `.odt` |
| PowerPoint | `.ppt`, `.pptx`, `.pptm`, `.odp` |
| Excel | `.xls`, `.xlsx`, `.xlsm`, `.csv`, `.ods` |
| PDF | `.pdf` |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.heic`, `.svg`, `.avif` |
| Videos | `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm` |
| Audio | `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg` |
| Archives | `.zip`, `.rar`, `.7z`, `.tar`, `.gz`, `.bz2`, `.xz` |
| Installers | `.dmg`, `.pkg`, `.msi`, `.exe`, `.iso` |
| Code | `.py`, `.js`, `.ts`, `.java`, `.swift`, `.html`, `.css`, `.json`, `.yaml` |
| Text | `.txt`, `.md`, `.rtf`, `.log`, `.rst`, `.tex` |
| Others | 확장자가 없거나 위 기준에 해당하지 않는 파일 |

## 안전 정책

- 선택한 폴더의 바로 아래 일반 파일만 대상으로 합니다. 기존 폴더, 앱 번들, 숨김 파일, 심볼릭 링크는 제외합니다.
- 기존 폴더 내부를 검사하거나 수정하지 않습니다. `Images`가 이미 있으면 `Images (1)`처럼 새 분류 폴더를 만듭니다. 반복 정리에서도 동일합니다.
- 기존 파일을 덮어쓰지 않습니다. 복구 위치에 같은 이름이 있으면 `report (1).pdf`처럼 새 이름으로 복구합니다.
- 미리보기 이후 변경된 파일이나 폴더는 확인 후 다시 미리보기 해야 합니다. 이후 추가된 파일은 다음 정리 때 처리합니다.
- 설치 파일은 자동 삭제하지 않습니다. 설치 파일 탭에는 최상위 설치 파일과 앱의 기록으로 확인된 정리 파일만 표시합니다. 기존 설치 파일 폴더는 탐색하지 않습니다.
- 선택한 설치 파일은 영구 삭제 대신 휴지통으로 이동합니다. 휴지통으로 보낸 파일은 Finder에서 복원하며, 정리 복구 대상에서는 제외합니다.
- 복구는 선택한 폴더의 최근 미복구 작업부터 수행합니다. 없어지거나 다른 파일로 교체된 항목은 건너뛰고 알립니다. 일부 복구에 실패하면 같은 작업을 다시 시도할 수 있습니다.
- 이동 전에 기록을 저장합니다. 이동 중 중단된 작업도 복구 대상이며, 기록 파일은 보관해야 합니다. macOS 기록 위치는 `~/Library/Application Support/CleanFolder/`입니다.
- APFS 등 하드 링크를 지원하는 로컬 파일시스템을 사용합니다. 하드 링크를 사용할 수 없는 볼륨에서는 파일을 이동하지 않고 오류를 표시합니다.

## 설치 및 실행

### 배포 앱 사용

GitHub Releases에 첨부된 Mac에 맞는 `.dmg` 또는 앱 전용 `.zip`을 다운로드합니다. `Code → Download ZIP`은 개발용 소스입니다.

- **AppleSilicon**: M1·M2·M3·M4 등 Apple Silicon Mac
- **Intel**: Intel Mac에서 별도로 빌드한 배포 파일
- DMG를 열어 `CleanFolder.app`을 `Applications`로 끌어 놓고 실행합니다.
- 설치 화면에서는 앱이 왼쪽, `Applications`가 오른쪽에 표시되며 화살표를 따라 드래그하면 됩니다.
- 앱 전용 ZIP은 압축을 푼 뒤 `CleanFolder.app`을 응용 프로그램 폴더로 옮깁니다.
- 배포 앱에는 Python과 필요한 라이브러리가 포함됩니다.
- Apple 개발자 인증서 서명·공증을 거치지 않은 빌드는 macOS에서 실행이 차단될 수 있습니다.

### 소스로 실행

Python 3.10 이상과 macOS 데스크톱 환경이 필요합니다.

```bash
cd CleanFolder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m cleanfolder
```

화면 없이 미리보기만 확인할 수도 있습니다.

```bash
python -m cleanfolder --preview ~/Downloads
```

테스트 실행:

```bash
python -m unittest discover -s tests -v
```

### macOS 앱 빌드

빌드할 Mac에서 다음 명령을 실행합니다. 해당 Mac의 CPU 아키텍처용 앱을 생성합니다.

```bash
python -m pip install -r requirements-build.txt
python scripts/build_macos.py
```

`dist/`에 아이콘이 적용된 `CleanFolder.app`, 배포용 ZIP, 설치용 DMG가 생성됩니다. 배포 파일은 GitHub의 **Releases → Draft a new release → Attach binaries**에 첨부합니다. 일반 사용자가 바로 찾을 수 있도록 Releases를 안내합니다.

## 사용 방법

1. **폴더 선택**으로 정리할 폴더를 고릅니다.
2. **정리 미리보기**에서 파일과 이동 위치를 확인한 뒤 **정리하기**를 누릅니다.
3. 필요하면 **설치 파일** 탭에서 파일을 체크하고 **선택한 파일을 휴지통으로**를 누릅니다.
4. **작업 기록**에서 이력을 확인하고 **원래대로 돌리기**로 최근 정리를 복구합니다.
5. Finder에서 파일을 변경했다면 **다시 미리보기**로 갱신합니다.

## 기술 스택

- Python 3.10+
- PySide6 / Qt Widgets: 운영체제 기본 스타일, 백그라운드 파일 작업
- Send2Trash: 운영체제 휴지통 이동
- JSON: 작업별 기록, 임시 파일을 이용한 원자적 저장
- unittest: 파일 정리·복구·안전 정책 및 화면 동작 테스트
