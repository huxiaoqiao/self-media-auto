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
