#!/usr/bin/env python3
"""
Self-media-auto 入口脚本
实际逻辑在 scripts/workflow/workflow_controller.py
"""
import os, sys

skill_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(skill_dir, "scripts", "workflow"))
os.chdir(skill_dir)

from workflow_controller import main
main()
