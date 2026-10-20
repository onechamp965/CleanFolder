# MCP 사용 안내

CleanFolder의 검사·미리보기·정리·복구를 MCP 클라이언트에서 호출할 수 있습니다. GUI와 같은 Core를 사용하며 MCP SDK는 선택 설치입니다. 데스크톱 앱을 설치하는 것만으로 MCP 서버가 자동 설정되지는 않습니다.

## 설치·실행

프로젝트 폴더의 Python 가상환경에서 실행합니다. SDK 1.x를 사용합니다([공식 문서](https://py.sdk.modelcontextprotocol.io/v1/)).

```bash
python -m pip install -e '.[mcp]'
python -m cleanfolder.mcp_server --allow "$HOME/Downloads"
```

서버는 **stdio**로 통신합니다. `--allow`는 필수이며 여러 번 지정할 수 있습니다. 등록한 폴더 자체만 허용하며 하위 폴더는 자동 허용하지 않습니다. 절대 경로를 사용하고 `..`·심볼릭 링크 경로는 거부합니다. 허용 폴더가 교체되면 서버를 다시 시작해 등록해야 합니다.

## 클라이언트 설정

Python 경로와 폴더 경로를 실제 절대 경로로 바꾸세요.

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

## 제공 도구

| Tool | 입력·동작 |
| --- | --- |
| `scan_folder` | `folder`: 최상위 파일 목록과 `latest_operation_id` 조회 |
| `preview_organization` | `folder`, 선택적 `include_names`: 정확한 파일 이름 목록으로 대상 선택, 생략하면 전체 |
| `organize_files` | `preview_id`, `approved: true`: 저장된 미리보기 그대로 실행 |
| `undo_last_operation` | `folder`, `operation_id`, `approved: true`: 승인한 최근 작업 복구 |

삭제·휴지통 이동 도구는 제공하지 않습니다. 설치 파일을 휴지통으로 보내는 기능은 GUI에서만 제공합니다.

## 승인과 미리보기

**조회 → 미리보기 → 이동 목록을 사용자에게 표시 → 명시적 승인 → 정리** 순서로 호출합니다.

- 미리보기 ID는 5분 유효하며 승인된 실행을 시도하면 소모됩니다. 서버 재시작 후에도 다시 미리보기 해야 합니다.
- `approved`는 클라이언트가 승인을 받았다는 표시입니다. 실제 사용자 확인 UI는 클라이언트에서 구현해야 합니다.
- 복구도 승인 후 호출합니다. `operation_id`는 정리 결과 또는 조회 결과에서 얻습니다.
- 파일·대상 폴더·분류 설정이 바뀌면 다시 미리보기 해야 합니다. 이후 추가된 파일은 다음 정리 대상입니다.
- MCP 정리는 항상 새 분류 폴더를 만듭니다. 기존 폴더 내부는 조회·수정하지 않으며, 복구만 기록된 폴더의 기록된 파일에 접근합니다.

## 작업 기록

기본 기록·설정은 GUI와 공유합니다. GUI와 MCP에서 서로의 정리를 복구할 수 있으며 동시 변경은 공통 잠금으로 차단합니다.

- macOS: `~/Library/Application Support/CleanFolder/`
- Windows: `%LOCALAPPDATA%/CleanFolder/`
- 테스트 기록 격리: `--data-dir /absolute/path/test-history`

## MCP Inspector

Node.js 22.19 이상이 설치되어 있으면 프로젝트 폴더에서 실행합니다([Inspector 안내](https://github.com/modelcontextprotocol/inspector)). Inspector가 서버를 실행하므로 별도 서버를 켤 필요는 없습니다.

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m cleanfolder.mcp_server --allow "$HOME/Downloads"
```

stdio 연결에서 **Tools → List Tools**로 네 개 도구를 확인합니다. 처음에는 테스트 폴더를 허용하고 아래 순서로 확인하세요.

1. 조회와 미리보기를 호출합니다.
2. 반환된 ID로 승인 없는 정리가 거부되는지 확인합니다.
3. 승인 후 정리와 복구를 확인합니다.
4. 미등록 경로와 소모된 미리보기 ID가 거부되는지 확인합니다.

같은 연결에서 진행해야 미리보기 ID가 유지됩니다. Inspector가 실행되는 동안 터미널을 열어 두고, 종료할 때는 Control+C를 누릅니다.

### 포트가 이미 사용 중인 경우

다른 포트로 실행할 수 있습니다.

```bash
CLIENT_PORT=6284 MCP_SANDBOX_PORT=6285 MCP_APP_ORIGIN_PORT=6288 npx @modelcontextprotocol/inspector .venv/bin/python -m cleanfolder.mcp_server --allow "$HOME/Downloads"
```

포트 설정은 [Inspector 공식 설정](https://github.com/modelcontextprotocol/inspector/blob/main/docs/environment-variables.md)을 참고하세요.

[README로 돌아가기](../README.md)
