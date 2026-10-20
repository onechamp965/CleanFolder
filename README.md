# CleanFolder

선택한 폴더의 파일을 종류별로 정리하는 PySide6 데스크톱 앱입니다. GUI와 MCP 서버가 같은 Core의 검사·분류·이동·작업 기록·복구 기능을 사용합니다.

현재 macOS 배포 앱은 **1.4.0**입니다. 이 저장소의 MCP 기능은 소스로 실행합니다. [변경 이력](CHANGELOG.md) · [배포 안내](docs/distribution.md) · [구조 설명](docs/architecture.md)

## 기능

- 선택한 폴더 바로 아래의 일반 파일만 검사하고 이동 위치 미리보기
- 정리할 파일 선택, 확장자별 분류, 이름 충돌 시 새 이름 생성
- 기존 폴더·앱 번들·숨김 파일·심볼릭 링크 제외
- 작업 기록 저장 및 **원래대로 돌리기**, 복구 시 덮어쓰기 방지
- 설치 파일 선택 후 운영체제 휴지통으로 이동: GUI에서만 제공
- 분류 규칙·제외 항목·시작 폴더·밝은/어두운 화면 설정
- MCP: 허용 경로 조회, 승인할 정리 미리보기, 정리, 최근 작업 복구

## 설치·실행

배포 앱은 GitHub Releases의 DMG 또는 앱 ZIP을 받습니다. 1.4.0 설치본은 Apple Silicon·macOS 14 이상용입니다. DMG에서 `CleanFolder.app`을 `Applications`로 옮겨 실행합니다. Python 설치는 필요 없습니다. 서명·공증되지 않은 앱은 macOS에서 실행이 차단될 수 있습니다.

소스로 실행하려면 Python 3.10 이상이 필요합니다.

```bash
cd CleanFolder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m cleanfolder
```

화면 없이 미리보기: `python -m cleanfolder --preview ~/Downloads`

## 사용법

1. **폴더 선택**으로 정리할 폴더를 고릅니다.
2. **정리 미리보기**에서 남겨둘 파일의 체크를 해제하고 이동 위치를 확인합니다.
3. **선택한 N개 정리**를 누릅니다. 기존 이름이 있으면 새 분류 폴더나 파일 이름을 만듭니다.
4. **작업 기록 → 원래대로 돌리기**로 최근 미복구 작업부터 복구합니다.
5. 설치 파일은 **설치 파일** 탭에서 직접 선택하고 **선택한 파일을 휴지통으로**를 누릅니다. 휴지통으로 보낸 파일은 운영체제 휴지통에서 복원합니다.
6. **설정**에서 분류 규칙·폴더 이름·제외 항목 등을 저장합니다. 미리보기의 체크 해제는 현재 폴더에서만 유지되며 앱 재실행·폴더 변경 시 초기화됩니다.

기본 정리는 새 분류 폴더를 만듭니다. GUI에서 재사용을 켜면 기록으로 확인된 앱 생성 폴더만 재사용합니다. MCP 정리는 이 설정과 관계없이 항상 새 폴더를 만들며 기존 폴더 내부를 조회·수정하지 않습니다. 복구만 기록된 분류 폴더의 기록된 파일에 접근하고, 해당 작업이 만든 빈 폴더를 제거합니다.

미리보기 이후 파일·대상 폴더·분류 설정이 바뀌면 다시 미리보기 해야 합니다. 이후 추가된 파일은 다음 정리 대상입니다. 하드 링크를 지원하는 로컬 파일시스템이 필요하며, 미지원 볼륨에서는 이동하지 않고 오류를 알립니다.

## MCP 실행·설정

MCP는 선택 설치이며 GUI와 Core는 MCP SDK 없이도 동작합니다. SDK 1.x를 사용합니다([공식 문서](https://py.sdk.modelcontextprotocol.io/v1/)).

```bash
python -m pip install -e '.[mcp]'
python -m cleanfolder.mcp_server --allow "$HOME/Downloads"
```

서버는 **stdio**로 통신합니다. `--allow`는 필수이며 여러 번 지정할 수 있습니다. 등록한 폴더 자체만 허용하며 하위 폴더는 자동 허용하지 않습니다. 절대 경로를 사용하고 `..`·심볼릭 링크 경로는 거부합니다. 허용 폴더가 교체되면 서버를 다시 시작해 등록해야 합니다.

MCP 클라이언트 설정 예시입니다. Python 경로와 폴더 경로를 실제 절대 경로로 바꾸세요.

```json
{
  "mcpServers": {
    "cleanfolder": {
      "command": "/absolute/path/CleanFolder/.venv/bin/python",
      "args": ["-m", "cleanfolder.mcp_server", "--allow", "/Users/you/Downloads"]
    }
  }
}
```

제공하는 Tool은 다음 네 개뿐이며 삭제·휴지통 이동 Tool은 없습니다.

| Tool | 입력·동작 |
| --- | --- |
| `scan_folder` | `folder`: 최상위 파일 목록과 `latest_operation_id` 조회 |
| `preview_organization` | `folder`, 선택적 `include_names`: 정확한 파일 이름 목록으로 대상 선택, 생략하면 전체 |
| `organize_files` | `preview_id`, `approved: true`: 저장된 미리보기 그대로 실행 |
| `undo_last_operation` | `folder`, `operation_id`, `approved: true`: 승인한 최근 작업 복구 |

클라이언트는 **조회 → 미리보기 → 이동 목록을 사용자에게 표시 → 명시적 승인 → 정리** 순서로 호출합니다. 미리보기 ID는 5분 유효하며 승인된 실행을 시도하면 소모됩니다. 서버 재시작 후에도 다시 미리보기 해야 합니다. `approved`는 클라이언트가 승인을 받았다는 표시이므로, 실제 사용자 확인 UI는 클라이언트에서 구현해야 합니다. 복구도 승인 후 호출하며 `operation_id`는 정리 결과 또는 조회 결과에서 얻습니다.

기본 작업 기록·설정은 GUI와 공유합니다(macOS: `~/Library/Application Support/CleanFolder/`, Windows: `%LOCALAPPDATA%/CleanFolder/`). GUI와 MCP에서 서로의 정리를 복구할 수 있고 동시 변경은 공통 잠금으로 차단합니다. 테스트 시 `--data-dir /absolute/path/test-history`로 기록을 격리할 수 있습니다.

### MCP Inspector

Node.js 22.19 이상이 설치되어 있으면 프로젝트 폴더에서 실행합니다([Inspector 안내](https://github.com/modelcontextprotocol/inspector)). Inspector가 서버를 실행하므로 별도 서버를 켤 필요는 없습니다.

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m cleanfolder.mcp_server --allow "$HOME/Downloads"
```

Inspector의 stdio 연결에서 **Tools → List Tools**로 네 개 Tool을 확인합니다. 테스트 폴더를 허용한 뒤 조회·미리보기를 호출하고, 반환된 ID로 승인 없는 정리가 거부되는지, 승인 후 정리·복구가 되는지 확인합니다. 미등록 경로와 소모된 미리보기 ID도 거부되어야 합니다. 같은 연결에서 진행해야 미리보기 ID가 유지됩니다.

## 테스트

```bash
python -m pip install -e '.[mcp]'
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Core 안전 정책·설정, MCP 경로 제한·승인·만료·stdio 통신, GUI 정리·선택·휴지통·복구와 GUI↔MCP 복구를 검사합니다. MCP SDK가 없으면 stdio 통합 테스트는 건너뜁니다. 커밋하기 좋은 변경 단위는 [MCP 변경 안내](docs/mcp-changes.md)에 정리했습니다.
