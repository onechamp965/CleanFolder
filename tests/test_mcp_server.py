import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP 선택 의존성을 설치해 주세요: pip install -e '.[mcp]'")
class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_four_tools_approval_organize_and_undo(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "Downloads"
            root.mkdir()
            (root / "report.pdf").write_text("report")
            (root / "setup.dmg").write_text("installer")
            (root / "existing").mkdir()
            (root / "existing/keep.txt").write_text("keep")
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "cleanfolder.mcp_server", "--allow", str(root), "--data-dir", str(base / "history")],
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    listed = (await session.list_tools()).tools
                    self.assertEqual({tool.name for tool in listed}, {
                        "scan_folder", "preview_organization", "organize_files", "undo_last_operation",
                    })
                    for tool in listed:
                        self.assertEqual(tool.annotations.readOnlyHint,
                                         tool.name in ("scan_folder", "preview_organization"))
                    denied = await session.call_tool("scan_folder", {"folder": str(base)})
                    self.assertTrue(denied.isError)
                    missing = await session.call_tool("trash", {"folder": str(root)})
                    self.assertTrue(missing.isError)
                    scan = await session.call_tool("scan_folder", {"folder": str(root)})
                    self.assertFalse(scan.isError)
                    self.assertEqual(self.payload(scan)["count"], 2)
                    preview = await session.call_tool("preview_organization", {"folder": str(root)})
                    token = self.payload(preview)["preview_id"]
                    denied = await session.call_tool("organize_files", {"preview_id": token})
                    self.assertTrue(denied.isError)
                    self.assertTrue((root / "report.pdf").exists())
                    organized = await session.call_tool("organize_files", {"preview_id": token, "approved": True})
                    self.assertFalse(organized.isError)
                    self.assertEqual(self.payload(organized)["completed"], 2)
                    self.assertTrue((root / "Installers/setup.dmg").exists())
                    replay = await session.call_tool("organize_files", {"preview_id": token, "approved": True})
                    self.assertTrue(replay.isError)
                    restored = await session.call_tool("undo_last_operation", {
                        "folder": str(root), "operation_id": self.payload(organized)["operation_id"], "approved": True,
                    })
                    self.assertFalse(restored.isError)
                    self.assertEqual(self.payload(restored)["completed"], 2)
            self.assertTrue((root / "report.pdf").exists())
            self.assertTrue((root / "setup.dmg").exists())
            self.assertEqual((root / "existing/keep.txt").read_text(), "keep")

    @staticmethod
    def payload(result):
        return result.structuredContent or json.loads(result.content[0].text)
