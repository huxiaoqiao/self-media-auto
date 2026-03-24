# -*- coding: utf-8 -*-
"""直接发送选题卡片，绕过编码问题"""
import sys
import json
import subprocess

# Fix encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

APP_ID = "cli_a930dedc42789cd1"
APP_SECRET = "WOjERqoJ8OhIwIthMS3NAcJAxFDvXK2X"
DEFAULT_RECECEIVE_ID = "ou_2da8e0f846c19c8fabebd6c6d82a8d6d"

def get_token():
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET})
    ], capture_output=True, text=True, encoding="utf-8")
    data = json.loads(result.stdout)
    return data.get("tenant_access_token", "")

def send_card(token, receive_id, card):
    payload = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False)
    }
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload)
    ], capture_output=True, text=True, encoding="utf-8")
    data = json.loads(result.stdout)
    return data.get("code") == 0

def build_topic_card(title, data_str, url, analysis, topic_id):
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "🔥 爆款选题推荐"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**📌 标题：** {title}\n\n**📊 数据：** {data_str}\n\n**🔗 原文：** {url}\n\n**💡 爆点分析：**\n{analysis}"}},
            {"tag": "hr"},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "lark_md", "content": "**🔍 解读此选题**"}, "type": "primary", "value": {"action": "insight", "topic_id": str(topic_id)}},
                {"tag": "button", "text": {"tag": "lark_md", "content": "**📋 换一批**"}, "type": "default", "value": {"action": "refresh", "topic_id": str(topic_id)}}
            ]}
        ]
    }

topics = [
    {
        "id": "1",
        "title": "腾讯上线 ima skill，知识管理终于可以🦞全自动了",
        "data": "阅读数 10W+ | 点赞 193 | 评论 47738 | 热度 13024",
        "url": "https://mp.weixin.qq.com/s?__biz=MzU4NTE1Mjg4MA==&mid=2247498110&idx=1&sn=46652ca78e67a74f2eb5f84d2157982f&chksm=fc84588b34f518c1273334461697123a14291907e25c558dcfd9900f93aefe65af01e3a80991&scene=0&xtrack=1#rd",
        "analysis": "腾讯ima是一款知识管理工具，接入AI后实现全自动知识采集、整理、归纳。工具类产品的AI赋能方向，用户痛点明确。"
    },
    {
        "id": "2",
        "title": "微信官方支持扫码接入OpenClaw了！附详细教程",
        "data": "阅读数 10W+ | 点赞 367 | 评论 33973 | 热度 12771",
        "url": "https://mp.weixin.qq.com/s?__biz=MzA4NzgzMjA4MQ==&mid=2453481779&idx=1&sn=5ab1bd7301be1b33487d006ff81db003&chksm=861042d7496a97a76766c440c546f20e2b0dfc68e750a383c820bdf2135507cbfeae117daf6e&scene=0&xtrack=1#rd",
        "analysis": "微信官方亲自下场支持OpenClaw接入，标志性事件！代表AI工具获平台官方认可，具有新闻性和话题性。"
    },
    {
        "id": "3",
        "title": "利好国产！远洋捕捞：超微创始人被捕，走私25亿美元英伟达GPU",
        "data": "阅读数 10W+ | 点赞 51 | 评论 61440 | 热度 10944",
        "url": "http://mp.weixin.qq.com/s?__biz=MzYyMTI5MjIyMA==&mid=2247487669&idx=1&sn=2e95012716ccd0ff29e50bf2fa038825&chksm=fe037bf586b8a940e3f457c1b7a4a0a3f21d5e3842b4abc9f6e8653a27c3d16f95af24075233&scene=126&sessionid=0#rd",
        "analysis": "涉及国家竞争、芯片走私、大厂创始人被抓，话题劲爆！评论数高达61440说明争议性极强。"
    },
    {
        "id": "4",
        "title": "我们用西游取经团实测 MiniMax M2.7，发现 AI 已经进化成这样了",
        "data": "阅读数 10W+ | 点赞 243 | 评论 52105 | 热度 10029",
        "url": "https://mp.weixin.qq.com/s?__biz=MzA5ODEzMjIyMA==&mid=2247732441&idx=1&sn=67de7b7564b1d23a09f2514299087adb&chksm=91c61085196926cfc99dda2ddc11415a388a238b494e068732e457ff5d03265a09f9ac1ad6cb&scene=0&xtrack=1#rd",
        "analysis": "MiniMax M2.7是最新大模型，用西游记IP做测评框架角度新颖。52105评论说明大家对国产大模型非常关注。"
    },
    {
        "id": "5",
        "title": "宇树科技：史上最奇怪的IPO公司",
        "data": "阅读数 10W+ | 点赞 103 | 评论 36476 | 热度 7319",
        "url": "https://mp.weixin.qq.com/s?__biz=MzkyNTY1MjE2OA==&mid=2247493493&idx=1&sn=3657974e1694cc05e531bb01bb0de6af&chksm=c03b4a5239d4ace32cdf5112e966494b24bbd61f4b401534cef216fa95e5278b090f62fb2a9d&scene=0&xtrack=1#rd",
        "analysis": "宇树科技是机器人明星公司，IPO本身有话题性。标题用最奇怪制造悬念感，36476评论说明大众对机器人行业关注度极高。"
    }
]

token = get_token()
if not token:
    print("Failed to get token")
    sys.exit(1)

for topic in topics:
    card = build_topic_card(topic["title"], topic["data"], topic["url"], topic["analysis"], topic["id"])
    success = send_card(token, DEFAULT_RECECEIVE_ID, card)
    print(f"Topic {topic['id']}: {'OK' if success else 'FAILED'}")

print("Done!")
