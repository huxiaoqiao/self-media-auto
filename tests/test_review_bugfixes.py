import importlib
import importlib.util
import json
import types
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "scripts" / "workflow"
FEISHU_DIR = REPO_ROOT / "scripts" / "feishu"
INTEGRATIONS_DIR = REPO_ROOT / "scripts" / "modules" / "integrations"
POSTING_DIR = REPO_ROOT / "scripts" / "posting"


def import_fresh(module_name, extra_paths=()):
    for name in list(sys.modules):
        if name == module_name or name.startswith(f"{module_name}."):
            sys.modules.pop(name, None)
    if module_name == "workflow_controller":
        for name in list(sys.modules):
            if name == "scripts.feishu.send_feishu_card" or name.startswith("scripts.feishu.send_feishu_card."):
                sys.modules.pop(name, None)
    for path in reversed([str(p) for p in extra_paths]):
        if path not in sys.path:
            sys.path.insert(0, path)
    return importlib.import_module(module_name)


def import_fresh_file(module_name, file_path, extra_paths=()):
    for name in list(sys.modules):
        if name == module_name:
            sys.modules.pop(name, None)
    for path in reversed([str(p) for p in extra_paths]):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class WorkflowStartupTests(unittest.TestCase):
    def test_import_without_feishu_credentials_keeps_cli_usable(self):
        with mock.patch.dict(os.environ, {
            "FEISHU_APP_ID": "",
            "FEISHU_APP_SECRET": "",
            "FEISHU_RECEIVE_ID": "",
        }, clear=False):
            workflow = import_fresh("workflow_controller", [WORKFLOW_DIR])

        self.assertIsNone(workflow.build_url_preview_card)
        self.assertIsNone(workflow.build_rewrite_card)
        self.assertIsNone(workflow.send_card)
        self.assertIsNone(workflow.get_token)

    def test_from_video_uses_video_extractor_before_article_fallback(self):
        workflow = import_fresh("workflow_controller", [WORKFLOW_DIR])
        controller = workflow.SelfMediaController()

        with tempfile.TemporaryDirectory() as tmpdir:
            controller.workspace = tmpdir
            controller.session_file = str(Path(tmpdir) / ".workflow_state.json")

            with mock.patch.object(controller, "_extract_video_content", return_value="视频转写正文") as video_mock, \
                 mock.patch.object(controller, "_extract_article_content", return_value="网页正文") as article_mock, \
                 mock.patch.object(controller, "_generate_insight", return_value="解读"), \
                 mock.patch.object(workflow, "build_rewrite_card", None), \
                 mock.patch.object(workflow, "send_card", None), \
                 mock.patch.object(workflow, "get_token", None):
                controller.run_from_video("https://v.douyin.com/test")

        video_mock.assert_called_once_with("https://v.douyin.com/test")
        article_mock.assert_not_called()

    def test_from_video_falls_back_to_article_extractor_when_asr_empty(self):
        workflow = import_fresh("workflow_controller", [WORKFLOW_DIR])
        controller = workflow.SelfMediaController()

        with tempfile.TemporaryDirectory() as tmpdir:
            controller.workspace = tmpdir
            controller.session_file = str(Path(tmpdir) / ".workflow_state.json")

            with mock.patch.object(controller, "_extract_video_content", return_value=None), \
                 mock.patch.object(controller, "_extract_article_content", return_value="网页正文") as article_mock, \
                 mock.patch.object(controller, "_generate_insight", return_value="解读"), \
                 mock.patch.object(workflow, "build_rewrite_card", None), \
                 mock.patch.object(workflow, "send_card", None), \
                 mock.patch.object(workflow, "get_token", None):
                controller.run_from_video("https://example.com/video")

        article_mock.assert_called_once()


class FeishuServerPathTests(unittest.TestCase):
    def test_default_workdir_is_repo_root(self):
        with mock.patch.dict(os.environ, {
            "FEISHU_WORKDIR": "",
        }, clear=False):
            os.environ.pop("FEISHU_WORKDIR", None)
            server = import_fresh_file(
                "feishu_card_server_for_path_tests",
                FEISHU_DIR / "feishu-card-server.py",
                [FEISHU_DIR, REPO_ROOT, REPO_ROOT / "scripts" / "modules"],
            )

        self.assertEqual(Path(server.WORKDIR).resolve(), REPO_ROOT)

    def test_workflow_cmd_points_to_real_controller(self):
        server = import_fresh_file(
            "feishu_card_server_for_cmd_tests",
            FEISHU_DIR / "feishu-card-server.py",
            [FEISHU_DIR, REPO_ROOT, REPO_ROOT / "scripts" / "modules"],
        )

        cmd = server.build_workflow_cmd("status")

        self.assertEqual(Path(cmd[2]).resolve(), REPO_ROOT / "scripts" / "workflow" / "workflow_controller.py")
        self.assertEqual(cmd[:2], [sys.executable, "-u"])
        self.assertEqual(cmd[3], "status")

    def test_publish_button_uses_browser_mode(self):
        server = import_fresh_file(
            "feishu_card_server_for_publish_tests",
            FEISHU_DIR / "feishu-card-server.py",
            [FEISHU_DIR, REPO_ROOT, REPO_ROOT / "scripts" / "modules"],
        )

        seen = {}

        class DummyController:
            def run_post(self, method="api"):
                seen["method"] = method
                return True

        class FakeHandler:
            def __init__(self):
                self.messages = []

            def send_text(self, token, message):
                self.messages.append(message)

        with tempfile.TemporaryDirectory() as tmpdir:
            draft_file = Path(tmpdir) / "article.md"
            draft_file.write_text("# title\n\nbody", encoding="utf-8")
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text(f'{{"draft_file": "{str(draft_file).replace(chr(92), chr(92) + chr(92))}"}}', encoding="utf-8")

            fake_workflow = types.SimpleNamespace(SelfMediaController=DummyController)
            handler = FakeHandler()

            with mock.patch.object(server, "STATE_FILE", str(state_file)), \
                 mock.patch.object(server, "WORKDIR", tmpdir), \
                 mock.patch.object(server, "WORKFLOW_DIR", str(WORKFLOW_DIR)), \
                 mock.patch.dict(sys.modules, {"workflow_controller": fake_workflow}), \
                 mock.patch.object(server.os, "chdir"):
                server.FeishuHandler.run_post(handler, "token")

        self.assertEqual(seen["method"], "browser")
        self.assertTrue(any("浏览器模式" in message for message in handler.messages))


class FeishuImageNormalizationTests(unittest.TestCase):
    def test_extract_image_path_accepts_dict_and_string(self):
        server = import_fresh_file(
            "feishu_card_server_for_image_tests",
            FEISHU_DIR / "feishu-card-server.py",
            [FEISHU_DIR, REPO_ROOT, REPO_ROOT / "scripts" / "modules"],
        )

        self.assertEqual(server.extract_image_path({"path": "C:/tmp/a.png", "pos": "第1段"}), "C:/tmp/a.png")
        self.assertEqual(server.extract_image_path("C:/tmp/b.png"), "C:/tmp/b.png")
        self.assertEqual(server.extract_image_path({"pos": "missing"}), "")
        self.assertEqual(server.extract_image_path(None), "")

    def test_existing_image_paths_filters_dict_entries(self):
        server = import_fresh_file(
            "feishu_card_server_for_existing_image_tests",
            FEISHU_DIR / "feishu-card-server.py",
            [FEISHU_DIR, REPO_ROOT, REPO_ROOT / "scripts" / "modules"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            image = Path(tmpdir) / "image.png"
            image.write_bytes(b"png")
            entries = [{"path": str(image), "pos": "第1段"}, {"path": str(Path(tmpdir) / "missing.png")}]

            self.assertEqual(server.existing_image_paths(entries), [str(image)])


class XiaohuFormatterPathTests(unittest.TestCase):
    def test_formatter_points_to_existing_formatting_assets(self):
        module = import_fresh("xiaohu_formatter", [INTEGRATIONS_DIR])
        formatter = module.XiaohuFormatter({}, mock.Mock())

        self.assertEqual(formatter.xiaohu_dir.resolve(), REPO_ROOT / "scripts" / "formatting")
        self.assertTrue(formatter.format_script.exists())
        self.assertEqual(formatter.format_script.name, "format.py")
        self.assertGreater(len(formatter.list_themes()), 0)


class WechatClipboardTests(unittest.TestCase):
    def test_cf_html_offsets_use_utf8_byte_positions(self):
        script = r"""
import { prepareForWechatClipboard } from './scripts/formatting/html-sanitizer.ts';
const html = prepareForWechatClipboard('<h1>雷总大气</h1><p><strong>7亿tokens到手</strong>，我准备搞点事情。</p>');
const encoder = new TextEncoder();
const decoder = new TextDecoder();
const bytes = encoder.encode(html);
const get = (name) => Number(html.match(new RegExp(name + ':(\\d{10})'))[1]);
const startHtml = get('StartHTML');
const endHtml = get('EndHTML');
const startFragment = get('StartFragment');
const endFragment = get('EndFragment');
console.log(JSON.stringify({
  startsWithHtml: decoder.decode(bytes.slice(startHtml, startHtml + 6)) === '<html>',
  fragmentStart: decoder.decode(bytes.slice(startFragment, startFragment + 20)),
  fragmentEnd: decoder.decode(bytes.slice(endFragment - 18, endFragment)),
  endMatchesByteLength: endHtml === bytes.length,
  containsChinese: html.includes('雷总大气') && html.includes('我准备搞点事情'),
}));
"""
        result = subprocess.run(
            ["bun", "-e", script],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)

        self.assertTrue(payload["startsWithHtml"])
        self.assertEqual(payload["fragmentStart"], "<!--StartFragment-->")
        self.assertEqual(payload["fragmentEnd"], "<!--EndFragment-->")
        self.assertTrue(payload["endMatchesByteLength"])
        self.assertTrue(payload["containsChinese"])

    def test_windows_html_clipboard_uses_raw_utf8_bytes(self):
        source = (POSTING_DIR / "copy-to-clipboard.ts").read_text(encoding="utf-8")
        start = source.index("async function copyHtmlWindows")
        end = source.index("async function copyImageToClipboard")
        copy_html_windows = source[start:end]

        self.assertIn('RegisterClipboardFormat("HTML Format")', copy_html_windows)
        self.assertIn("[System.IO.File]::ReadAllBytes", copy_html_windows)
        self.assertIn("SetClipboardData(format, hGlobal)", copy_html_windows)
        self.assertIn("public static void SetHtml(byte[] bytes)", copy_html_windows)
        self.assertIn("[NativeClipboard]::SetHtml($bytes)", copy_html_windows)
        self.assertNotIn("[UIntPtr]($bytes.Length + 1)", copy_html_windows)
        self.assertNotIn("Clipboard]::SetText", copy_html_windows)
        self.assertNotIn("TextDataFormat]::Html", copy_html_windows)

    def test_browser_paste_verifies_chinese_text_integrity(self):
        source = (POSTING_DIR / "wechat-article.ts").read_text(encoding="utf-8")

        self.assertIn("expectedCjkSamples", source)
        self.assertIn("hasReplacementChars", source)
        self.assertIn("Body pasted with corrupted Chinese text", source)


class DiscoverySourceTests(unittest.TestCase):
    def test_source_to_provider_mapping(self):
        workflow = import_fresh("workflow_controller", [WORKFLOW_DIR])

        self.assertEqual(workflow.resolve_hot_article_provider("cimipa"), "cimi")
        self.assertEqual(workflow.resolve_hot_article_provider("cimi"), "cimi")
        self.assertEqual(workflow.resolve_hot_article_provider("paid"), "cimi")
        self.assertEqual(workflow.resolve_hot_article_provider("power-fee"), "cimi")
        self.assertEqual(workflow.resolve_hot_article_provider("free"), "jizhile")
        self.assertEqual(workflow.resolve_hot_article_provider("jizhile"), "jizhile")
        self.assertIsNone(workflow.resolve_hot_article_provider(None))
