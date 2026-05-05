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
