# 구조

```text
cleanfolder/
  __main__.py          GUI·미리보기 진입점
  core/                분류, 안전한 이동, 복구, 기록, 설정
  desktop/             공통 PySide6 화면·위젯·아이콘·테마
  platforms/           운영체제별 데이터 경로·안내
  assets/              공통 디자인 원본과 앱 아이콘
packaging/
  hooks/               사용하지 않는 Qt 플러그인 수집 방지
  macos/               macOS 앱·DMG 설정
  windows/             Windows 실행 파일 설정
scripts/               아이콘 생성·빌드·용량 보고서
tests/                 핵심 기능·화면·설정·구조 테스트
```

## 의존성 방향

- `desktop`은 `core`를 호출합니다. `core`는 화면 모듈이나 PySide6를 가져오지 않습니다.
- `platforms`는 GUI 없이 운영체제별 경로와 안내를 제공합니다.
- 안전한 파일 이동과 잠금은 기존 구현을 유지합니다. POSIX와 Windows 처리를 무리하게 통합하지 않습니다.
- 빌드 도구와 배포 설정은 앱 실행 코드에 포함되지 않습니다.

## 기존 사용자 데이터

작업 기록·설정의 JSON 형식과 저장 위치를 유지합니다. 구조 변경을 위해 사용자 파일을 옮기거나 기록을 초기화하지 않습니다.

- macOS: `~/Library/Application Support/CleanFolder/`
- Windows: `%LOCALAPPDATA%/CleanFolder/`
- 설정: 해당 폴더 안의 `preferences/settings.json`

## 경량화 원칙

- 실행 의존성은 Qt Widgets·SVG를 포함하는 `PySide6-Essentials`와 `Send2Trash`입니다.
- 빌드 훅에서 PDF 이미지 플러그인과 Qt 가상 키보드 플러그인을 제외합니다. 이들이 끌어오는 PDF·QML·Quick 구성의 불필요한 수집을 방지합니다.
- 한국어·영어 Qt 번역만 유지합니다. 시스템 기본 입력기·한글 입력·운영체제 파일 선택 창은 제거하지 않습니다.
- 파일의 PDF·이미지·영상 분류는 확장자 기준이므로 문서 렌더러나 영상 재생기가 필요하지 않습니다. 파일 분류 기능은 그대로 유지합니다.
- 디자인 원본·다른 운영체제의 아이콘은 배포 앱의 공통 리소스에 중복해서 넣지 않습니다.
- 서명 후 바이너리를 임의로 삭제하지 않습니다. UPX나 강제 바이너리 압축을 사용하지 않습니다.
- 빌드마다 실제 파일 크기와 SHA-256을 저장합니다. 용량과 실행 가능 여부를 함께 검증합니다.

참고: [Qt 패키지 구성](https://doc.qt.io/qtforpython-6/gettingstarted/package_details.html), [PyInstaller 빌드 훅](https://pyinstaller.org/en/stable/hooks.html).
