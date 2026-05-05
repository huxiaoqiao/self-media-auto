import importlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "scripts" / "workflow"
FEISHU_DIR = REPO_ROOT / "scripts" / "feishu"
INTEGRATIONS_DIR = REPO_ROOT / "scripts" / "modules" / "integrations"


def import_fresh(module_name, extra_paths=()):
    for name in list(sys.modules):
        if name == module_name:
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
                 mock.patch.object(controller, "_generate_insight", return_value="解读"):
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
                 mock.patch.object(controller, "_generate_insight", return_value="解读"):
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
