#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send new batch (topics 6-10) as single batch card."""
import sys, json, os
sys.path.insert(0, r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto")
from send_feishu_card import get_token, send_card

topics = [
    {"id": "6", "title": "微信官方接入龙虾，我顺手给接上了 Claude Code。已开源", "data": "👁️ 阅读: 34541 | 👍 赞: 374 | 🔥 热度: 12932", "url": "https://mp.weixin.qq.com/s?__biz=MzA4NzgzMjA4MQ==&mid=2453481779&idx=1&sn=5ab1bd7301be1b33487d006ff81db003", "analysis": "OpenClaw + Claude Code 实战，教程类内容"},
    {"id": "7", "title": "腾讯上线 ima skill，知识管理终于可以全自动了", "data": "👁️ 阅读: 47738 | 👍 赞: 193 | 🔥 热度: 13024", "url": "https://mp.weixin.qq.com/s?__biz=MzU4NTE1Mjg4MA==&mid=2247498110&idx=1&sn=46652ca78e67a74f2eb5f84d2157982f", "analysis": "腾讯ima知识管理，AI效率工具，实用性强"},
    {"id": "8", "title": "突发！微信一键扫码就能接入原版 OpenClaw 了！", "data": "👁️ 阅读: 12160 | 👍 赞: 63 | 🔥 热度: 4048", "url": "https://mp.weixin.qq.com/s?__biz=Mzk0NzQzOTczOA==&mid=2247523631&idx=1&sn=b33f707806a7ef10c75834a6f5a249d4", "analysis": "OpenClaw 微信接入，热点事件"},
    {"id": "9", "title": "飞书 aily，让我看到了 OPC 真正需要的 Agent", "data": "👁️ 阅读: 16460 | 👍 赞: 57 | 🔥 热度: 3976", "url": "https://mp.weixin.qq.com/s?__biz=MzYyMTY1NDA0Nw==&mid=2247515869&idx=1&sn=63e3ff3742f867f29424b4861694bbb8", "analysis": "飞书AI Agent，产品分析角度"},
    {"id": "10", "title": "Rabbit又行了？油管大V改口，将发第二款AI硬件", "data": "👁️ 阅读: 52807 | 👍 赞: 375 | 🔥 热度: 9186", "url": "https://mp.weixin.qq.com/s?__biz=MjM5OTQzMTAxOA==&mid=2450418285&idx=1&sn=3684a6cfa610d963949df58444e64c31", "analysis": "Rabbit AI硬件，科技热点，大V观点"}
]

# Save to state
STATE_FILE = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\.workflow_state.json"
try:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
    else:
        state = {}
    state['last_candidates'] = topics
    state['candidates_page_index'] = 2
    state['candidates_page_size'] = 5
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("✅ Candidates saved to state")
except Exception as e:
    print(f"⚠️ Failed to save: {e}")

# Build card
token = get_token()
card = {
    "config": {"wide_screen_mode": True},
    "header": {"template": "purple", "title": {"tag": "plain_text", "content": "🚀 IP 爆款选题推荐 · AI赛道"}},
    "elements": [
        {"tag": "markdown", "content": "**🔥 AI赛道 · 今日爆款选题 TOP 5（续）**"},
        {"tag": "hr"},
    ]
}

for i, t in enumerate(topics):
    topic_num = i + 6  # 6,7,8,9,10
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
    "elements": [{"tag": "plain_text", "content": "💡 点击上方按钮选择选题，或直接发送序号 6-10 选择"}]
})

result = send_card(token, "ou_2da8e0f846c19c8fabebd6c6d82a8d6d", card)
print(f"结果: {result}")
