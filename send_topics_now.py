#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send current topics as batch card via card server."""
import sys
sys.path.insert(0, r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto")
from send_feishu_card import get_token, send_card

topics = [
    {"id": "1", "title": "微信原生支持各种 OpenClaw 龙虾接入，附教程", "data": "👁️ 阅读: 11367 | 👍 赞: 67 | 🔥 热度: 3175", "url": "https://mp.weixin.qq.com/s?__biz=MzYyMTY1NDA0Nw==&mid=2247515925&idx=1&sn=a81c761213e7c47f03bfd5e3b3e2ee92", "analysis": "OpenClaw 龙虾自动化工具 + 微信生态接入，实用教程类"},
    {"id": "2", "title": "这只叫做「JVS」的龙虾，在自动帮我经营小红书了", "data": "👁️ 阅读: 11248 | 👍 赞: 64 | 🔥 热度: 3278", "url": "https://mp.weixin.qq.com/s?__biz=MzkxMzUyODQ3OA==&mid=2247491339&idx=1&sn=54daa030f0411c1dfca17c54b73f7035", "analysis": "AI自动化运营小红书，JVS系统实战案例"},
    {"id": "3", "title": "宇树科技：史上\"最奇怪\"的IPO公司", "data": "👁️ 阅读: 36476 | 👍 赞: 103 | 🔥 热度: 7319", "url": "https://mp.weixin.qq.com/s?__biz=MzkyNTY1MjE2OA==&mid=2247493493&idx=1&sn=3657974e1694cc05e531bb01bb0de6af", "analysis": "宇树科技IPO，机器人赛道热点，财经分析角度"},
    {"id": "4", "title": "北京早高峰，用千问叫了辆车，我回不到过去了", "data": "👁️ 阅读: 21897 | 👍 赞: 114 | 🔥 热度: 3644", "url": "https://mp.weixin.qq.com/s?__biz=MzU2Njg0OTEyNQ==&mid=2247492201&idx=1&sn=07f48f41afedd5ae38bcf6b31e1c7f9f", "analysis": "千问AI打车体验，情感故事+AI应用落地"},
    {"id": "5", "title": "利好国产，远洋捕捞，超微创始人被捕，向中国走私25亿美元的英伟达GPU", "data": "👁️ 阅读: 61440 | 👍 赞: 51 | 🔥 热度: 10944", "url": "http://mp.weixin.qq.com/s?__biz=MzYyMTI5MjIyMA==&mid=2247487669&idx=1&sn=2e95012716ccd0ff29e50bf2fa038825", "analysis": "科技财经热点，GPU走私事件，话题性强"}
]

token = get_token()
card = {
    "config": {"wide_screen_mode": True},
    "header": {"template": "purple", "title": {"tag": "plain_text", "content": "🚀 IP 爆款选题推荐 · AI赛道"}},
    "elements": [
        {"tag": "markdown", "content": "**🔥 AI赛道 · 今日爆款选题 TOP 5**"},
        {"tag": "hr"},
    ]
}

for i, t in enumerate(topics):
    topic_num = i + 1
    card["elements"].append({
        "tag": "markdown",
        "content": f"**🔥 [{topic_num}] {t['title']}**\n📊 {t['data']}\n💡 {t['analysis']}\n🔗 [原文链接]({t['url']})"
    })
    card["elements"].append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": f"🔍 解读选题 {topic_num}"},
            "type": "primary",
            "value": f"insight_{topic_num}"
        }]
    })
    if i < len(topics) - 1:
        card["elements"].append({"tag": "hr"})

card["elements"].append({"tag": "hr"})
card["elements"].append({
    "tag": "action",
    "actions": [
        {"tag": "button", "text": {"tag": "plain_text", "content": "📋 换一批（查看更多爆款选题）"}, "type": "default", "value": "next"},
        {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 初始化（重置IP名称/行业赛道）"}, "type": "default", "value": "init"}
    ]
})
card["elements"].append({
    "tag": "note",
    "elements": [{"tag": "plain_text", "content": "💡 点击上方按钮选择选题，或直接发送序号 1-5 选择"}]
})

# Also save candidates to state file so button clicks work correctly
import json, os
STATE_FILE = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\.workflow_state.json"
try:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
    else:
        state = {}
    state['last_candidates'] = topics
    state['candidates_page_index'] = 1
    state['candidates_page_size'] = 5
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("✅ Candidates saved to state")
except Exception as e:
    print(f"⚠️ Failed to save candidates: {e}")

result = send_card(token, "ou_2da8e0f846c19c8fabebd6c6d82a8d6d", card)
print(f"结果: {result}")
