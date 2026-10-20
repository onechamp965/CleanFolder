# MCP 변경 단위

기존 저장소에는 staged/unstaged 변경과 미추적 Core/UI/배포 파일이 이미 있습니다. 아래는 이번 MCP 작업을 검토·커밋할 때의 논리적 구분이며, 실제 커밋이나 인덱스 변경은 수행하지 않습니다. 기존 구조 분리 작업을 먼저 검토하고 포함할 파일을 선택하세요. `git add .`로 기존 작업을 함께 포함하지 않도록 주의합니다.

## 1. 공통 Core

권장 메시지: `refactor(core): share top-level scanning and validate operation state`

- `cleanfolder/core/service.py`: 공통 `scan`, 미리보기의 기존 분류 폴더 재사용 옵션, 결과의 작업 ID, 실행 시 디스크 설정 검증, 복구할 최신 작업 ID 검증
- `cleanfolder/core/path_validator.py`: 기본 거부, 정확한 허용 폴더, 심볼릭 링크·상위 이동 거부, 폴더·상위 경로 교체 감지
- `tests/test_architecture.py`: GUI·MCP SDK 없이 Core 실행 확인
- `tests/test_service.py`: 다른 인스턴스의 설정 변경 후 오래된 GUI 미리보기 실행 차단

검증: 기존 `test_service`, `test_settings`, `test_architecture` 테스트.

## 2. MCP 인터페이스

권장 메시지: `feat(mcp): add allowlisted preview-first organization tools`

- `cleanfolder/mcp_server/`: stdio 진입점과 네 개 Tool, 서버 내 미리보기 보관·만료·소모, 정확한 이름으로 대상 선택
- `pyproject.toml`: MCP 선택 의존성·실행 명령 추가
- `tests/test_mcp_tools.py`, `tests/test_mcp_server.py`: 경로 제한·선택·승인·변경 감지·재시작 후 복구·실제 stdio 통신

검증: `python -m unittest tests.test_mcp_tools tests.test_mcp_server -v`.

## 3. GUI 회귀 검증

권장 메시지: `test(desktop): cover shared GUI and MCP undo history`

- `tests/test_ui.py`: GUI에서 MCP 정리 복구, MCP에서 GUI 정리 복구
- 기존 미리보기·파일 선택·설치 파일 휴지통·취소·설정·복구 테스트 유지

검증: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`.

## 4. 사용 안내

권장 메시지: `docs: document MCP setup approval and Inspector workflow`

- `README.md`: 소개·기능·설치·실행·사용법 중심으로 간소화, MCP 설정·Inspector·테스트 안내
- `docs/architecture.md`: 의존성 방향과 승인·경로·기록 정책
- `docs/mcp-changes.md`: 변경 단위와 검증 방법

현재 배포 앱 버전과 사용자 데이터 형식·저장 위치는 유지합니다. 이 작업은 설치본 재빌드·릴리스·Git 커밋을 포함하지 않습니다.

## 검증 결과 (2026-10-20)

- macOS, Python 3.13.11, PySide6 6.12.0, MCP SDK 1.30.0에서 전체 110개 테스트 통과(건너뛴 테스트 없음)
- 실제 stdio 클라이언트에서 네 개 Tool, 미등록 경로·삭제 Tool·승인 없는 실행·토큰 재사용 거부, 정리·복구 확인
- PySide6 offscreen 회귀 테스트에서 파일 선택·휴지통·취소·설정·복구와 GUI↔MCP 상호 복구 확인
- MCP Inspector CLI에서 `tools/list --strict`, `scan_folder`, `preview_organization` 호출 성공; 기존 폴더 내부 파일 유지 확인
- README의 MCP 선택 설치와 `cleanfolder-mcp` 실행 진입점 확인
- Windows 실행·배포 앱 재빌드와 Inspector 웹 화면의 수동 조작은 이번 검증에 포함하지 않음
