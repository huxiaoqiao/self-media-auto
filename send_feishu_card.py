#!/usr/bin/env python3
"""
飞书交互卡片发送脚本
用法（CLI）:
  python send_feishu_card.py topic --title "标题" --data "数据" --url "链接" --analysis "分析" --id "ID"
  python send_feishu_card.py rewrite --title "标题" --insight "洞察" --id "ID"
  python send_feishu_card.py review --image "图路径" --title "标题" --content "内容" --tags "标签"
  python send_feishu_card.py archive --title "标题" --doc-url "链接" --id "ID" --date "日期"
  python send_feishu_card.py final --image "图路径" --title "标题" --content "内容" --tags "标签"

Python API:
  from send_feishu_card import send_topic_card, send_rewrite_card, send_review_card, send_archive_card, send_final_card
"""

import sys
import json
import subprocess
import argparse
from pathlib import Path
from typing import Optional

# ============ 飞书配置 ============
APP_ID = "cli_a930dedc42789cd1"
APP_SECRET = "WOjERqoJ8OhIwIthMS3NAcJAxFDvXK2X"
DEFAULT_RECEIVE_ID = "ou_2da8e0f846c19c8fabebd6c6d82a8d6d"

# ============ API 请求 ============

def get_token() -> str:
    """获取 tenant_access_token"""
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET})
    ], capture_output=True, text=True, encoding="utf-8")
    data = json.loads(result.stdout)
    token = data.get("tenant_access_token", "")
    if not token:
        raise Exception(f"获取token失败: {data}")
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
    ], capture_output=True, text=True, encoding="utf-8")
    
    data = json.loads(result.stdout)
    image_key = data.get("data", {}).get("image_key", "")
    if image_key:
        print(f"  ✅ 图片上传成功: {image_key}")
    else:
        print(f"  ⚠️ 图片上传失败: {data.get('msg', 'unknown error')}")
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
    ], capture_output=True, text=True, encoding="utf-8")
    
    data = json.loads(result.stdout)
    if data.get("code") == 0:
        print("  ✅ 卡片发送成功")
        return True
    else:
        print(f"  ❌ 卡片发送失败: {data.get('msg')}")
        return False


# ============ 卡片模板 ============

def build_topic_card(title: str, data_str: str, url: str, analysis: str, topic_id: str) -> dict:
    """选题卡片（单条）"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "purple", "title": {"tag": "plain_text", "content": "🚀 IP 爆款选题推荐"}},
        "elements": [
            {"tag": "markdown", "content": f"**🔥 [{topic_id}] {title}**\n📊 {data_str}\n💡 {analysis}\n🔗 [原文链接]({url})"},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": f"🔍 解读选题{topic_id}"}, "type": "primary", "value": f"{{\"action\":\"insight_topic\",\"id\":{topic_id}}}"}
            ]}
        ]
    }


def build_topic_list_card(topics: list, industry: str = "AI") -> dict:
    """
    批量选题卡片（多选题合一张卡）
    topics: list of dict, each with keys: id, title, data, url, analysis
    """
    elements = []
    
    # 顶部 Industry 标识
    elements.append({"tag": "markdown", "content": f"**🔥 AI赛道 · 爆款选题 TOP {len(topics)}**"})
    elements.append({"tag": "hr"})
    
    for i, topic in enumerate(topics):
        topic_id = topic.get("id", i + 1)
        title = topic.get("title", "")
        data = topic.get("data", "")
        url = topic.get("url", "")
        analysis = topic.get("analysis", "")
        
        elements.append({
            "tag": "markdown",
            "content": f"**🔥 [{topic_id}] {title}**\n📊 {data}\n💡 {analysis}\n🔗 [原文链接]({url})"
        })
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": f"🔍 解读选题{topic_id}"},
                "type": "primary",
                "value": f"insight_{topic_id}"
            }]
        })
        if i < len(topics) - 1:
            elements.append({"tag": "hr"})
    
    # 底部操作按钮
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "📋 换一批（查看剩余10个选题）"}, "type": "default", "value": "refresh"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 初始化（重置IP名称/行业赛道）"}, "type": "default", "value": "init"}
        ]
    })
    
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "purple", "title": {"tag": "plain_text", "content": "🚀 IP 爆款选题推荐 · AI赛道"}},
        "elements": elements
    }


def build_url_preview_card(title: str, author: str, source: str, summary: str, url: str, content_type: str, extra_info: str = "") -> dict:
    """内容预览卡"""
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
        "header": {"template": "yellow", "title": {"tag": "plain_text", "content": "✍️ 选题解读完成"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**📌 选题：** {title}\n\n**💡 解读洞察：**\n{insight}\n\n**🎯 建议：** 这个选题具有爆款潜质，建议进行 IP 化改写。"}},
            {"tag": "hr"},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": f"ID: {topic_id}"}]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "✍️ 开始改写"}, "type": "primary", "value": f"rewrite_{topic_id}"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "🔄 换一个"}, "type": "default", "value": f"skip_{topic_id}"}
            ]},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "💡 提示：如果按钮点击报错，请直接回复「开始改写+ID」来启动改写，例如：开始改写12"}]}
        ]
    }


def build_review_card(image_key: str, title: str, content: str, tags: str, review_id: str) -> dict:
    """审核卡片"""
    elements = []
    
    if image_key:
        elements.append({"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "封面图"}})
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "（无封面图）"}})
    
    elements.extend([
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**📌 标题：** {title}\n\n**✨ 亮点：**\n{content}\n\n**💡 标签：** {tags}"}},
        {"tag": "hr"},
        {"tag": "note", "elements": [{"tag": "plain_text", "content": f"ID: {review_id}"}]},
        {"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "✅ 通过"}, "type": "primary", "value": f"approve_{review_id}"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "✏️ 修改"}, "type": "default", "value": f"modify_{review_id}"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "❌ 重写"}, "type": "default", "value": f"rewrite_{review_id}"}
        ]},
        {"tag": "note", "elements": [{"tag": "plain_text", "content": "💡 提示：如果按钮点击报错，请直接回复对应指令，例如：通过、修改、重写"}]}
    ])
    
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"🎨 内容审核 - {title}"}},
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


def build_final_card(image_key: str, title: str, content: str, tags: str, review_id: str) -> dict:
    """最终稿卡片"""
    elements = []
    
    if image_key:
        elements.append({"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "封面图"}})
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "（无封面图）"}})

    elements.extend([
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**📝 完整文案：**\n\n{content}"}},
        {"tag": "hr"},
        {"tag": "note", "elements": [{"tag": "plain_text", "content": tags}]},
        {"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "📤 发布到公众号"}, "type": "primary", "value": f"post_{review_id}"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "📋 复制文案"}, "type": "default", "value": f"copy_{review_id}"}
        ]},
        {"tag": "note", "elements": [{"tag": "plain_text", "content": "💡 提示：如果按钮点击报错，请直接回复「发布」或「复制」来执行操作"}]}
    ])
    
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "green", "title": {"tag": "plain_text", "content": f"✅ 最终稿 - {title}"}},
        "elements": elements
    }


# ============ Python API ============

def send_topic_card(title: str, data_str: str, url: str, analysis: str, topic_id: str, receive_id: str = DEFAULT_RECEIVE_ID) -> bool:
    """发送选题卡片（单条，Python直接调用）"""
    print(f"📤 发送选题卡片: {title}")
    token = get_token()
    card = build_topic_card(title, data_str, url, analysis, topic_id)
    return send_card(token, receive_id, card)


def send_topic_list_card(topics: list, industry: str = "AI", receive_id: str = DEFAULT_RECEIVE_ID) -> bool:
    """发送批量选题卡片（多选题合一张卡，Python直接调用）"""
    print(f"📤 发送批量选题卡片: {len(topics)} 个选题")
    token = get_token()
    card = build_topic_list_card(topics, industry)
    return send_card(token, receive_id, card)


def send_url_preview_card(title: str, author: str, source: str, summary: str, url: str, content_type: str = "article", extra_info: str = "", receive_id: str = DEFAULT_RECEIVE_ID) -> bool:
    """发送内容预览卡"""
    print(f"📤 发送内容预览卡: {title}")
    token = get_token()
    card = build_url_preview_card(title, author, source, summary, url, content_type, extra_info)
    return send_card(token, receive_id, card)


def send_rewrite_card(title: str, insight: str, topic_id: str, receive_id: str = DEFAULT_RECEIVE_ID) -> bool:
    """发送改写确认卡"""
    print(f"📤 发送改写确认卡: {title}")
    token = get_token()
    card = build_rewrite_card(title, insight, topic_id)
    return send_card(token, receive_id, card)


def send_review_card(image_key: str, title: str, content: str, tags: str, review_id: str, receive_id: str = DEFAULT_RECEIVE_ID) -> bool:
    """发送审核卡片"""
    print(f"📤 发送审核卡片: {title}")
    token = get_token()
    card = build_review_card(image_key, title, content, tags, review_id)
    return send_card(token, receive_id, card)


def send_archive_card(title: str, doc_url: str, topic_id: str, date: str, receive_id: str = DEFAULT_RECEIVE_ID) -> bool:
    """发送归档确认卡"""
    print(f"📤 发送归档确认卡: {title}")
    token = get_token()
    card = build_archive_card(title, doc_url, topic_id, date)
    return send_card(token, receive_id, card)


def send_final_card(image_key: str, title: str, content: str, tags: str, review_id: str, receive_id: str = DEFAULT_RECEIVE_ID) -> bool:
    """发送最终稿卡片"""
    print(f"📤 发送最终稿卡片: {title}")
    token = get_token()
    card = build_final_card(image_key, title, content, tags, review_id)
    return send_card(token, receive_id, card)


def upload_image_file(image_path: str) -> str:
    """上传图片并返回 image_key（外部调用）"""
    token = get_token()
    return upload_image(token, image_path)


# ============ CLI 入口 ============

def main():
    parser = argparse.ArgumentParser(description='飞书卡片发送', formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest='card_type', help='卡片类型')
    
    # topic
    p = subparsers.add_parser('topic', help='选题卡片')
    p.add_argument('--title', required=True, help='标题')
    p.add_argument('--data', required=True, help='数据字符串')
    p.add_argument('--url', required=True, help='原文链接')
    p.add_argument('--analysis', required=True, help='爆点分析')
    p.add_argument('--id', required=True, help='选题ID')
    
    # rewrite
    p = subparsers.add_parser('rewrite', help='改写确认卡')
    p.add_argument('--title', required=True, help='标题')
    p.add_argument('--insight', required=True, help='解读洞察')
    p.add_argument('--id', required=True, help='选题ID')
    
    # url_preview
    p = subparsers.add_parser('url_preview', help='内容预览卡')
    p.add_argument('--title', required=True, help='标题')
    p.add_argument('--author', required=True, help='作者')
    p.add_argument('--source', required=True, help='来源')
    p.add_argument('--content-preview', required=True, help='内容预览')
    p.add_argument('--url', required=True, help='链接')
    p.add_argument('--type', default='article', help='类型: article/video')
    p.add_argument('--extra', default='', help='额外信息')
    
    # review
    p = subparsers.add_parser('review', help='审核卡片')
    p.add_argument('--image', default='', help='封面图路径')
    p.add_argument('--title', required=True, help='标题')
    p.add_argument('--content', required=True, help='文案内容')
    p.add_argument('--tags', required=True, help='标签')
    p.add_argument('--review-id', default='', help='审核ID')
    
    # archive
    p = subparsers.add_parser('archive', help='归档确认卡')
    p.add_argument('--title', required=True, help='标题')
    p.add_argument('--doc-url', required=True, help='文档链接')
    p.add_argument('--id', required=True, help='选题ID')
    p.add_argument('--date', required=True, help='日期')
    
    # final
    p = subparsers.add_parser('final', help='最终稿卡片')
    p.add_argument('--image', default='', help='封面图路径')
    p.add_argument('--title', required=True, help='标题')
    p.add_argument('--content', required=True, help='文案内容')
    p.add_argument('--tags', required=True, help='标签')
    p.add_argument('--review-id', default='', help='审核ID')
    
    args = parser.parse_args()
    
    if not args.card_type:
        parser.print_help()
        sys.exit(1)
    
    print(f"📤 飞书卡片发送 - 类型: {args.card_type}")
    
    # 获取 token
    print("🔑 获取访问令牌...")
    token = get_token()
    print(f"  ✅ Token: {token[:20]}...")
    
    import time
    review_id = args.review_id if hasattr(args, 'review_id') and args.review_id else time.strftime("%m%d%H%M%S")
    
    if args.card_type == "topic":
        # topic_id 传入时必须是全局唯一ID（1-15），用于精确定位 candidates 数组索引
        card = build_topic_card(args.title, args.data, args.url, args.analysis, args.id)
        
    elif args.card_type == "rewrite":
        card = build_rewrite_card(args.title, args.insight, args.id)
        
    elif args.card_type == "url_preview":
        card = build_url_preview_card(args.title, args.author, args.source, args.content_preview, args.url, args.type, args.extra)
        
    elif args.card_type == "review":
        image_key = upload_image(token, args.image) if args.image else ""
        card = build_review_card(image_key, args.title, args.content, args.tags, review_id)
        
    elif args.card_type == "archive":
        card = build_archive_card(args.title, args.doc_url, args.id, args.date)
        
    elif args.card_type == "final":
        image_key = upload_image(token, args.image) if args.image else ""
        card = build_final_card(image_key, args.title, args.content, args.tags, review_id)
    
    success = send_card(token, DEFAULT_RECEIVE_ID, card)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
