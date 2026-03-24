#!/usr/bin/env python3
"""
检查待处理的卡片事件并返回路由指令
在每次响应开头调用，根据待处理事件返回要执行的动作
"""
import sys
import os
import json

ACTION_FILE = '/tmp/feishu_card_action.txt'

def check_pending_action():
    """检查待处理事件并返回 action_type, action_value"""
    if not os.path.exists(ACTION_FILE):
        return None, None
    
    try:
        with open(ACTION_FILE, 'r') as f:
            content = f.read().strip()
        
        if not content:
            return None, None
        
        try:
            event_data = json.loads(content)
            action_type = event_data.get('action_type', 'unknown')
            action_value = event_data.get('action_value', '')
        except:
            # 旧格式兼容
            parts = content.split('|', 1)
            if len(parts) != 2:
                return None, None
            action_value = parts[0].strip()
            # 从 action_value 解析类型
            if '_' in action_value:
                action_type = action_value.split('_', 1)[0]
            else:
                action_type = action_value
        
        return action_type, action_value
    except Exception as e:
        print(f"检查待处理事件失败: {e}", file=sys.stderr)
        return None, None

def clear_pending_action():
    """清除待处理事件"""
    try:
        if os.path.exists(ACTION_FILE):
            os.remove(ACTION_FILE)
    except:
        pass

if __name__ == '__main__':
    action_type, action_value = check_pending_action()
    
    if action_type is None:
        print("NO_PENDING_ACTION")
        sys.exit(0)
    
    # 打印路由指令（供主程序解析）
    print(f"ACTION_TYPE={action_type}")
    print(f"ACTION_VALUE={action_value}")
    
    # 路由建议
    if action_type == 'next':
        print("ROUTE=discovery")
    elif action_type == 'insight':
        print("ROUTE=from-article")
    elif action_type == 'skip':
        print("ROUTE=discovery")
    elif action_type == 'review':
        print("ROUTE=review")
    elif action_type == 'post':
        print("ROUTE=post")
    elif action_type == 'copy':
        print("ROUTE=copy")
    elif action_type == 'edit':
        print("ROUTE=edit")
    else:
        print(f"ROUTE=unknown:{action_type}")
