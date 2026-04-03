#!/usr/bin/env python3
"""
飞书卡片事件轮询脚本
在 AGENTS.md 的流程中调用，检查用户是否有未处理的卡片按钮点击
"""

import json
import urllib.request
import sys


def poll_card_event():
    """检查卡片事件队列"""
    try:
        # 注意：服务器端定义的是 PUT 方法，不是 GET
        req = urllib.request.Request(
            "http://127.0.0.1:18799/feishu/poll",
            method='PUT',  # 明确指定 PUT 方法
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get('has_event'):
                action = result.get('action', '')
                message = result.get('message', '')
                # 清理 action 值可能的引号
                action = action.strip('"\'')
                return action, message
    except Exception as e:
        print(f"轮询异常: {e}", file=sys.stderr)
    return None, None


if __name__ == "__main__":
    action, message = poll_card_event()
    if action:
        print(f"ACTION:{action}")
        print(f"MESSAGE:{message}")
    else:
        print("NO_EVENT")
