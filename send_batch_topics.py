#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发送批量选题卡片（5个选题在一张卡上）"""
import sys
sys.path.insert(0, r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto")

from send_feishu_card import send_topic_list_card, get_token, send_card

topics = [
    {
        "id": "1",
        "title": "微信原生支持各种 OpenClaw 龙虾接入，附教程",
        "data": "👁️ 阅读: 11367 | 👍 赞: 67 | 🔥 热度: 3175",
        "url": "https://mp.weixin.qq.com/s?__biz=MzYyMTY1NDA0Nw==&mid=2247515925&idx=1&sn=a81c761213e7c47f03bfd5e3b3e2ee92",
        "analysis": "OpenClaw 龙虾自动化工具 + 微信生态接入，实用教程类内容"
    },
    {
        "id": "2",
        "title": "这只叫做「JVS」的龙虾，在自动帮我经营小红书了",
        "data": "👁️ 阅读: 11248 | 👍 赞: 64 | 🔥 热度: 3278",
        "url": "https://mp.weixin.qq.com/s?__biz=MzkxMzUyODQ3OA==&mid=2247491339&idx=1&sn=54daa030f0411c1dfca17c54b73f7035",
        "analysis": "AI自动化运营小红书，JVS系统实战案例"
    },
    {
        "id": "3",
        "title": "宇树科技：史上最奇怪的IPO公司",
        "data": "👁️ 阅读: 36476 | 👍 赞: 103 | 🔥 热度: 7319",
        "url": "https://mp.weixin.qq.com/s?__biz=MzkyNTY1MjE2OA==&mid=2247493493&idx=1&sn=3657974e1694cc05e531bb01bb0de6af",
        "analysis": "宇树科技IPO，机器人赛道热点，财经分析角度"
    },
    {
        "id": "4",
        "title": "北京早高峰，用千问叫了辆车，我回不到过去了",
        "data": "👁️ 阅读: 21897 | 👍 赞: 114 | 🔥 热度: 3644",
        "url": "https://mp.weixin.qq.com/s?__biz=MzU2Njg0OTEyNQ==&mid=2247492201&idx=1&sn=07f48f41afedd5ae38bcf6b31e1c7f9f",
        "analysis": "千问AI打车体验，情感故事+AI应用落地"
    },
    {
        "id": "5",
        "title": "腾讯上线 ima skill，知识管理终于可以全自动了",
        "data": "👁️ 阅读: 47738 | 👍 赞: 193 | 🔥 热度: 13024",
        "url": "https://mp.weixin.qq.com/s?__biz=MzU4NTE1Mjg4MA==&mid=2247498110&idx=1&sn=46652ca78e67a74f2eb5f84d2157982f",
        "analysis": "腾讯ima知识管理工具，AI效率提升，实用性强"
    }
]

if __name__ == "__main__":
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
        card["elements"].append({
            "tag": "markdown",
            "content": f"**🔥 [{t['id']}] {t['title']}**\n📊 {t['data']}\n💡 {t['analysis']}\n🔗 [原文链接]({t['url']})"
        })
        card["elements"].append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": f"🔍 解读选题 {t['id']}"},
                "type": "primary",
                "value": f"insight_{t['id']}"
            }]
        })
        if i < len(topics) - 1:
            card["elements"].append({"tag": "hr"})

    # 底部操作按钮（带说明）
    card["elements"].append({"tag": "hr"})
    card["elements"].append({
        "tag": "action",
        "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "📋 换一批（查看更多爆款选题）"}, "type": "default", "value": "next"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 初始化（重置IP名称/行业赛道）"}, "type": "default", "value": "init"}
        ]
    })
    # 提示
    card["elements"].append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "💡 点击上方按钮选择选题，或直接发送序号 1-5 选择"}]
    })

    result = send_card(token, "ou_2da8e0f846c19c8fabebd6c6d82a8d6d", card)
    print(f"结果: {result}")
