#!/usr/bin/env python3
"""
飞书交互卡片发送脚本（纯 Python 版）
用法：python3 send_feishu_card.py <card_type> <params...>

card_type:
  topic_list  - 选题列表卡片
  rewrite     - 改写确认卡
  review      - 审核卡片
  archive     - 归档确认卡
  final       - 最终稿卡片
"""

import sys
import json
import subprocess
import argparse
import re
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ============ 飞书配置 ============
APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
DEFAULT_RECEIVE_ID = os.getenv("FEISHU_RECEIVE_ID")
if not APP_ID or not APP_SECRET:
    raise ValueError("FEISHU_APP_ID and FEISHU_APP_SECRET environment variables are required")

# ============ API 请求 ============

def get_token():
    """获取 tenant_access_token"""
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET})
    ], capture_output=True, encoding="utf-8", errors="replace")
    data = json.loads(result.stdout)
    token = data.get("tenant_access_token", "")
    if not token:
        raise Exception(f"获取 token 失败：{data}")
    return token


def upload_image(token: str, image_path: str) -> str:
    """上传图片并返回 image_key"""
    if not image_path or not Path(image_path).exists():
        return ""

    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/im/v1/images",
        "-H", f"Authorization: Bearer {token}",
        "-F", "image_type=message",
        "-F", f"image=@{image_path}"
    ], capture_output=True, text=True)

    data = json.loads(result.stdout)
    image_key = data.get("data", {}).get("image_key", "")
    if image_key:
        print(f"  ✅ 图片上传成功：{image_key}")
    else:
        print(f"  ⚠️ 图片上传失败：{data.get('msg', 'unknown error')}")
    return image_key


def send_card(token: str, receive_id: str, card: dict) -> bool:
    """发送交互卡片"""
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
    ], capture_output=True, encoding="utf-8", errors="replace")

    data = json.loads(result.stdout)
    if data.get("code") == 0:
        print("  ✅ 卡片发送成功")
        return True
    else:
        print(f"  ❌ 卡片发送失败：{data.get('msg')}")
        return False


# ============ 卡片模板 ============

def _format_topic_data(t: dict) -> str:
    """根据可用字段自动格式化选题数据行"""
    parts = []
    if t.get('author'):
        parts.append("👤 " + str(t['author']))
    if t.get('likes') is not None:
        parts.append("👍 " + str(t['likes']) + " 赞")
    if t.get('comments') is not None:
        parts.append("💬 " + str(t['comments']) + " 评论")
    if t.get('score') is not None:
        parts.append("🔥 " + str(t['score']) + " 热度")
    return " | ".join(parts) if parts else "暂无数据"


def _format_topic_analysis(t: dict) -> str:
    """根据可用字段自动生成爆点解读"""
    if t.get('analysis'):
        return str(t['analysis'])
    title = str(t.get('title', ''))
    if t.get('score') and int(t.get('score', 0)) > 10000:
        return "热度爆表，全网刷屏"
    if '源码' in title or '代码' in title or 'Source' in title:
        return "源码泄露引爆开发者圈，技术圈必看"
    if '开源' in title or 'Open' in title:
        return "开源项目再掀热潮，社区关注度高"
    if 'AI' in title and ('超越' in title or '吊打' in title or '碾压' in title):
        return "AI 模型横评，对比强烈引发讨论"
    return "爆款选题，值得深入解读"


def build_topic_list_card(topics: list, industry: str = "") -> dict:
    """选题集合卡片 - 一次展示多个选题"""
    elements = []
    elements.append({"tag": "markdown", "content": f"**🔥 {industry}赛道 · 今日爆款选题 TOP {len(topics)}**"})
    elements.append({"tag": "hr"})

    for i, t in enumerate(topics):
        topic_num = i + 1
        title = str(t.get('title', '未知选题')).strip()
        topic_url = t.get('url', '') or t.get('id', '')
        if title.startswith('http'):
            title = f"选题 {topic_num}"
        guid = t.get('guid', str(topic_num))
        data_str = _format_topic_data(t)
        analysis_str = _format_topic_analysis(t)

        elements.append({
            "tag": "markdown",
            "content": f"**🔥 [{topic_num}] {title}**\n📊 {data_str}\n💡 {analysis_str}\n🔗 [原文链接]({topic_url})"
        })
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": f"🔍 解读选题 {topic_num}"},
                "type": "primary",
                "value": f"insight_{guid}"
            }]
        })
        if i < len(topics) - 1:
            elements.append({"tag": "hr"})

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "📋 换一批（查看更多爆款选题）"}, "type": "default", "value": "next"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 初始化（重置 IP 名称/行业赛道）"}, "type": "default", "value": "init"}
        ]
    })
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "💡 点击上方按钮选择选题，或直接发送序号 1-5 选择"}]
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "purple", "title": {"tag": "plain_text", "content": f"🚀 IP 爆款选题推荐 · {industry}赛道"}},
        "elements": elements
    }


def build_url_preview_card(title: str, author: str, source: str, summary: str, url: str, content_type: str, extra_info: str = "") -> dict:
    """内容预览卡 - 用户发送链接后的确认卡片"""
    type_emoji = "📝" if content_type == "article" else "🎬"
    type_label = "文章" if content_type == "article" else "视频"

    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "purple", "title": {"tag": "plain_text", "content": f"{type_emoji} 检测到 {type_label} - 待确认"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**📌 标题：** {title}\n\n**✍️ 作者：** {author}\n\n**📢 来源：** {source}"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**📋 内容概要：**\n{summary}"}},
            {"tag": "hr"},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": extra_info}]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "✍️ 开始改写"}, "type": "primary", "value": f"rewrite_url_{content_type}"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "❌ 算了"}, "type": "default", "value": "cancel_url"}
            ]},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "⚠️ 按钮异常时，请直接发送文字指令：发送「改写」开始改写，发送「算了」结束"}]}
        ]
    }


def build_rewrite_card(title: str, insight: str, topic_id: str) -> dict:
    """改写确认卡"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "purple", "title": {"tag": "plain_text", "content": "📝 选题解读完成"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 选题：** {title}\n\n**💡 解读：**\n{insight}"}},
            {"tag": "hr"},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": f"ID: {topic_id}"}]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "✍️ 开始改写"}, "type": "primary", "value": f"rewrite_{topic_id}"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "🔄 换一个"}, "type": "default", "value": "next_new"}
            ]}
        ]
    }


def build_review_card(image_key: str, title: str, content: str, tags: str, review_id: str, template: str = "blue", header_title: str = None) -> dict:
    """审核卡片"""
    CHUNK_SIZE = 800
    paragraphs = []
    if content:
        for i in range(0, len(content), CHUNK_SIZE):
            chunk = content[i:i+CHUNK_SIZE]
            paragraphs.append({"tag": "div", "text": {"tag": "lark_md", "content": chunk}})

    now_str = time.strftime('%H:%M:%S')
    elements = []
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"**🔥 标题：** {title}\n\n**🏷️ 标签：** {tags}"}
    })
    elements.extend(paragraphs)
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"更新时间：{now_str}"}]
    })
    elements.append({
        "tag": "action",
        "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "✅ 通过"}, "type": "primary", "value": f"approve_{review_id}"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "✏️ 修改"}, "type": "default", "value": f"modify_{review_id}"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "❌ 重写"}, "type": "default", "value": f"rewrite_{review_id}"}
        ]
    })

    hdr = header_title if header_title else "📋 内容审核"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": template, "title": {"tag": "plain_text", "content": hdr}},
        "elements": elements
    }


def build_archive_card(title: str, doc_url: str, topic_id: str, date: str) -> dict:
    """归档确认卡"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "green", "title": {"tag": "plain_text", "content": "📁 二创完成，已归档"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**📌 标题：** {title}\n\n**✅ 状态：** 已完成 IP 化改写并保存到飞书文档\n\n**📂 位置：** 爆款 IP 二创/{date}"}},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "📁 查看文档"}, "type": "primary", "multi_url": {"url": doc_url}},
                {"tag": "button", "text": {"tag": "plain_text", "content": "✏️ 调整内容"}, "type": "default", "value": f"edit_{topic_id}"}
            ]}
        ]
    }


def build_final_card(image_key: str, title: str, content: str, tags: str, review_id: str, article_image_keys=None, deai_notes: str = None) -> dict:
    """最终稿卡片
    
    Args:
        deai_notes: Optional[str], Natural Chinese Protocol 祛AI处理改动说明
    """
    elements = []

    if image_key:
        elements.append({"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "封面图"}})
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "（无封面图）"}})

    content_clean = re.sub(r'^#+\s*', '', content, flags=re.MULTILINE).strip() if content else ""

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"**🔥 标题：** {title}"}
    })

    if content_clean:
        main_text = content_clean[:2000] + ("..." if len(content_clean) > 2000 else "")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": main_text}})

    if article_image_keys:
        elements.append({"tag": "hr"})
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"🖼️ 文章包含 {len(article_image_keys)} 张专业配图，已插入相应段落"}]})

    # 🔍 祛 AI 味说明区块
    if deai_notes:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🔍 Natural Chinese Protocol · 祛AI处理说明**\n\n{deai_notes}"}
        })

    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": tags}]})
    elements.append({
        "tag": "action",
        "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "📤 发布到公众号"}, "type": "primary", "value": f"post_{review_id}"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "📋 复制文案"}, "type": "default", "value": f"copy_{review_id}"}
        ]
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "green", "title": {"tag": "plain_text", "content": "🎉 最终稿"}},
        "elements": elements
    }


# ============ CLI 入口 ============

def main():
    if len(sys.argv) < 2:
        print("用法：python3 send_feishu_card.py <card_type> <params...>")
        print("card_type: topic_list | rewrite | review | archive | final")
        sys.exit(1)

    card_type = sys.argv[1]

    print(f"📤 飞书卡片发送 - 类型：{card_type}")

    # 获取 token
    print("🔑 获取访问令牌...")
    token = get_token()
    print(f"  ✅ Token: {token[:20]}...")

    # 解析参数并构建卡片
    review_id = time.strftime("%m%d%H%M%S")
    receive_id = DEFAULT_RECEIVE_ID

    if card_type == "topic_list":
        # topic_list INDUSTRY JSON_DATA
        industry = sys.argv[2] if len(sys.argv) > 2 else ""
        json_data = sys.argv[3] if len(sys.argv) > 3 else "[]"
        topics = json.loads(json_data)
        card = build_topic_list_card(topics, industry)

    elif card_type == "rewrite":
        # rewrite TITLE INSIGHT TOPIC_ID
        title, insight, topic_id = sys.argv[2:5]
        card = build_rewrite_card(title, insight, topic_id)

    elif card_type == "url_preview":
        # url_preview TITLE AUTHOR SOURCE CONTENT_PREVIEW URL CONTENT_TYPE [EXTRA_INFO]
        title, author, source, content_preview, url = sys.argv[2:7]
        content_type = sys.argv[7] if len(sys.argv) > 7 else "article"
        extra_info = sys.argv[8] if len(sys.argv) > 8 else ""
        card = build_url_preview_card(title, author, source, content_preview, url, content_type, extra_info)

    elif card_type == "review":
        # review IMAGE_PATH TITLE CONTENT TAGS [COVER_KEY]
        # IMAGE_PATH: 封面图路径
        # 可选额外参数：经过的插图路径（用于追加发送）
        image_path, title, content, tags = sys.argv[2:6]
        extra_images = sys.argv[6:]  # 额外的插图路径
        print(f"🖼️ 处理图片：{image_path}")
        image_key = upload_image(token, image_path) if image_path else ""
        card = build_review_card(image_key, title, content, tags, review_id)

        # 发送主卡片
        print(f"📨 发送到：{receive_id}")
        success = send_card(token, receive_id, card)

        # 发送插图（作为追加消息）
        if extra_images:
            time.sleep(0.5)  # 稍微延迟确保卡片先收到
            for idx, img_path in enumerate(extra_images):
                if os.path.exists(img_path):
                    img_key = upload_image(token, img_path)
                    if img_key:
                        caption = f"📸 插图{idx+1}" if idx > 0 else "📸 插图"
                        # 发送插图作为独立图片消息
                        from urllib.request import Request
                        import urllib.error
                        img_data = json.dumps({
                            "receive_id": receive_id,
                            "msg_type": "image",
                            "content": json.dumps({"image_key": img_key})
                        }).encode('utf-8')
                        img_req = Request(
                            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                            data=img_data,
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {token}"
                            },
                            method='POST'
                        )
                        try:
                            with urllib.request.urlopen(img_req, timeout=10) as resp:
                                result = json.loads(resp.read().decode('utf-8'))
                                if result.get('code') == 0:
                                    print(f"  ✅ 插图{idx+1} 发送成功")
                                else:
                                    print(f"  ⚠️ 插图{idx+1} 发送失败：{result.get('msg')}")
                        except Exception as e:
                            print(f"  ⚠️ 插图{idx+1} 发送异常：{e}")
        sys.exit(0 if success else 1)
        return  # 确保不重复执行

    elif card_type == "archive":
        # archive TITLE DOC_URL TOPIC_ID
        title, doc_url, topic_id = sys.argv[2:5]
        date = time.strftime("%Y-%m-%d")
        card = build_archive_card(title, doc_url, topic_id, date)

    elif card_type == "final":
        # final IMAGE_PATH TITLE CONTENT TAGS
        image_path, title, content, tags = sys.argv[2:6]
        print(f"🖼️ 处理图片：{image_path}")
        image_key = upload_image(token, image_path) if image_path else ""
        card = build_final_card(image_key, title, content, tags, review_id)

    else:
        print(f"❌ 未知卡片类型：{card_type}")
        print("支持的类型：topic | rewrite | review | archive | final")
        sys.exit(1)

    # 发送卡片
    print(f"📨 发送到：{receive_id}")
    success = send_card(token, receive_id, card)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
