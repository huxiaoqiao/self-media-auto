#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send topics 11-15 as single batch card."""
import sys, json, os
sys.path.insert(0, r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto")
from send_feishu_card import get_token, send_card

topics = [
    {"id": "11", "title": "好莱坞导演对AI的恐慌，大概需要LibTV这样的产品来解决", "data": "👁️ 阅读: 33251 | 👍 赞: 242 | 🔥 热度: 6005", "url": "https://mp.weixin.qq.com/s?__biz=MzU2Njg0OTEyNQ==&mid=2247492129&idx=1&sn=a8ff63e930d2de8fc03db452b72b6642", "analysis": "AI工具解决好莱坞导演焦虑，产品角度"},
    {"id": "12", "title": "OpenCLI：万物皆可 CLI", "data": "👁️ 阅读: 20762 | 👍 赞: 417 | 🔥 热度: 8564", "url": "https://mp.weixin.qq.com/s?__biz=MzA4NzgzMjA4MQ==&mid=2453481700&idx=1&sn=377e4c26de698584d065dff8e6a675bf", "analysis": "OpenCLI工具，开发者热点，技术教程"},
    {"id": "13", "title": "我们用「西游取经团」实测 MiniMax M2.7 ，发现 AI 已经进化成这样了？", "data": "👁️ 阅读: 52105 | 👍 赞: 243 | 🔥 热度: 10029", "url": "https://mp.weixin.qq.com/s?__biz=MzA5ODEzMjIyMA==&mid=2247732441&idx=1&sn=67de7b7564b1d23a09f2514299087adb", "analysis": "MiniMax M2.7实测，AI进化速度，产品对比"},
    {"id": "14", "title": "龙虾终于有安全版了，还能一键装、直接用！", "data": "👁️ 阅读: 27669 | 👍 赞: 90 | 🔥 热度: 5339", "url": "https://mp.weixin.qq.com/s?__biz=MzI3NTkyMjA4NA==&mid=2247521337&idx=1&sn=22618a6d812f01b23322a70899734b29", "analysis": "OpenClaw安全版，一键安装，实用教程"},
    {"id": "15", "title": "AI 球球直播呼吁脑机接口开源，海外 KOL 疯狂艾特马斯克，疑似 X 宕机？", "data": "👁️ 阅读: 13322 | 👍 赞: 64 | 🔥 热度: 3407", "url": "https://mp.weixin.qq.com/s?__biz=MzYyMTY1NDA0Nw==&mid=2247515803&idx=1&sn=50a21b1edab6fb6a872d10a1060ab540", "analysis": "AI直播热点，脑机接口，海外KOL联动"}
]

STATE_FILE = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\.workflow_state.json"
try:
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)
    state['last_candidates'] = topics
    state['candidates_page_index'] = 2
    state['candidates_page_size'] = 5
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("✅ Saved to state")
except Exception as e:
    print(f"⚠️ {e}")

token = get_token()
card = {
    "config": {"wide_screen_mode": True},
    "header": {"template": "purple", "title": {"tag": "plain_text", "content": "🚀 IP 爆款选题推荐 · AI赛道"}},
    "elements": [
        {"tag": "markdown", "content": "**🔥 AI赛道 · 今日爆款选题 TOP 5（第二批）**"},
        {"tag": "hr"},
    ]
}

for i, t in enumerate(topics):
    topic_num = int(t['id'])
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
        {"tag": "button", "text": {"tag": "plain_text", "content": "📋 换一批（查看最后5个选题）"}, "type": "default", "value": "next"},
        {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 初始化（重置IP名称/行业赛道）"}, "type": "default", "value": "init"}
    ]
})
card["elements"].append({
    "tag": "note",
    "elements": [{"tag": "plain_text", "content": "💡 点击上方按钮选择选题，或直接发送序号 11-15 选择"}]
})

result = send_card(token, "ou_2da8e0f846c19c8fabebd6c6d82a8d6d", card)
print(f"结果: {result}")
