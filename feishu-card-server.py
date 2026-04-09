#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Feishu Card Server - Handles card button events and sends interactive cards."""

import sys, io
# Only wrap if running in a context that needs it (not in exec tool environment)
if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # If wrapping fails, use original stdout

import json
import subprocess
import urllib.request
import urllib.error
import os
import re
import time
import threading
import socket
import sys
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import uuid
import queue
import requests
import certifi
import httpx
from dotenv import load_dotenv

# 修复 Windows 环境下 requests SSL CA 证书问题
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()

# ==================== 统一日志配置 ====================
from utils.logger_config import get_card_server_logger, init_logging

# 初始化日志系统(清理旧日志 + 创建日志目录)
init_logging(log_prefix='card_server')

# 获取 logger
logger = get_card_server_logger()

# 加载环境变量
load_dotenv()

# Global cache for topic mapping (GUID -> Topic Dict)
# This prevents ID collisions across different batches/pages
TOPIC_MAP = {}

# Thread lock for protecting TOPIC_MAP concurrent access
TOPIC_MAP_LOCK = threading.RLock()

# Thread lock for protecting STATE_FILE concurrent access
STATE_FILE_LOCK = threading.RLock()

# Feishu App Config (from environment variables with fallback)
APP_ID = os.getenv("FEISHU_APP_ID", "cli_a930dedc42789cd1")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "WOjERqoJ8OhIwIthMS3NAcJAxFDvXK2X")
DEFAULT_RECEIVE_ID = os.getenv("FEISHU_RECEIVE_ID", "ou_2da8e0f846c19c8fabebd6c6d82a8d6d")
WORKDIR = os.getenv("FEISHU_WORKDIR", r"C:\Users\Administrator\.openclaw\skills\self-media-auto")
STATE_FILE = WORKDIR + r"/.workflow_state.json"

# ==================== 全局底层引擎组件 ====================
PROCESSED_ACTIONS = {}  # 全局请求防抖去重锁
TOKEN_CACHE = {"token": "", "expire": 0} # 飞书 Token 缓存
MESSAGE_QUEUE = queue.Queue() # 异步消息队列引擎,实现"UI 秒回"

def get_global_token():
    """Shared token fetcher for all threads with cache."""
    global TOKEN_CACHE
    now = time.time()
    if TOKEN_CACHE.get("token") and TOKEN_CACHE.get("expire", 0) > now:
        return TOKEN_CACHE["token"]

    try:
        req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            token = data.get('tenant_access_token', '')
            if token:
                TOKEN_CACHE["token"] = token
                TOKEN_CACHE["expire"] = now + data.get('expire', 7200) - 120
                logger.info(f"[AUTH] Global token updated. Expires in {data.get('expire')}s")
                return token
    except Exception as e:
        logger.error(f"[ERROR] get_global_token failed: {e}")
    return ""

def message_sender_worker():
    """Clean, independent worker thread handling async message delivery."""
    logger.info("[QUEUE] Independent message sender worker started.")
    while True:
        try:
            msg = MESSAGE_QUEUE.get()
            token = get_global_token()
            if not token:
                logger.error("[QUEUE] Sender worker: Failed to get token")
                MESSAGE_QUEUE.task_done()
                continue

            target_id = DEFAULT_RECEIVE_ID
            logger.debug(f"[ASYNC_SEND] Sending {msg['type']} to {target_id}...")
            payload = {
                "receive_id": target_id,
                "msg_type": "text" if msg["type"] == "text" else "interactive",
                "content": json.dumps({"text": msg["content"]} if msg["type"] == "text" else msg["content"], ensure_ascii=False)
            }
            req = urllib.request.Request(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))
                if resp_data.get("code") != 0:
                    logger.error(f"[FEISHU] Message send failed: {resp_data.get('msg')}")
                else:
                    logger.debug(f"[ASYNC_DONE] Successfully sent {msg['type']}")

            MESSAGE_QUEUE.task_done()
        except Exception as e:
            logger.error(f"[QUEUE] Sender worker failed: {e}")
            time.sleep(1)

# Start background queue worker
threading.Thread(target=message_sender_worker, daemon=True).start()
# =========================================================


def load_persistent_map():
    """Load TOPIC_MAP from persistent state file on startup."""
    global TOPIC_MAP
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
            persisted = state.get('topic_map', {})
            if persisted:
                with TOPIC_MAP_LOCK:
                    TOPIC_MAP.update(persisted)
                print(f"[INIT] Loaded {len(TOPIC_MAP)} persistent topic mappings from state file.")
                # 启动时自动清理过期数据
                cleanup_expired_map(max_age_days=3)
    except Exception as e:
        print(f"[WARN] Failed to load persistent topic map: {e}")


def save_persistent_map():
    """Save the current TOPIC_MAP to persistent state file."""
    if not os.path.exists(STATE_FILE):
        return
    try:
        # Read current state first to avoid overwriting other keys
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        with TOPIC_MAP_LOCK:
            state['topic_map'] = TOPIC_MAP.copy()

        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        # print(f"[DEBUG] TOPIC_MAP persisted to {STATE_FILE}")
    except Exception as e:
        print(f"[WARN] Failed to persist topic map: {e}")


def cleanup_expired_map(max_age_days=3):
    """清理超过指定天数(默认 3 天)的 topic 映射"""
    global TOPIC_MAP
    cutoff = time.time() - (max_age_days * 24 * 60 * 60)
    with TOPIC_MAP_LOCK:
        expired_keys = [k for k, v in TOPIC_MAP.items()
                   if v.get('created_at', 0) < cutoff]
        for k in expired_keys:
            TOPIC_MAP.pop(k, None)
        if expired_keys:
            print(f"[CLEANUP] Removed {len(expired_keys)} expired topics (older than {max_age_days} days)")
            save_persistent_map()
        else:
            print(f"[CLEANUP] No expired topics to remove (retaining {len(TOPIC_MAP)} items)")


# Initialize on import/startup
load_persistent_map()


class FeishuHandler(BaseHTTPRequestHandler):

    # def log_message(self, format, *args):
    #     pass  # Suppress all logs

    # ===== HTTP Routes =====

    def do_GET(self):
        import urllib.parse
        logger.info("[HTTP] GET request: path=%s", self.path)
        if self.path.startswith("/feishu"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            challenge = params.get('challenge', [''])[0]
            if challenge:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"challenge": challenge}).encode('utf-8'))
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"code":0}')
        elif self.path.startswith("/trigger"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            trigger_type = params.get('type', ['discovery'])[0]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if trigger_type == 'discovery':
                threading.Thread(target=self.run_discovery_and_send_cards, args=(self.get_token(),)).start()
                self.wfile.write(json.dumps({"code": 0, "msg": "discovery triggered"}).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({"code": 1, "msg": "unknown trigger type"}).encode('utf-8'))
        else:
            logger.warning("[HTTP] GET request not found: path=%s", self.path)
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        logger.info("[HTTP] POST request: path=%s", self.path)
        if self.path != "/feishu/callback":
            self.send_response(404)
            self.end_headers()
            return

        print(f"\n[HTTP] 📥 收到 POST 请求: {self.path}", flush=True)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            data = json.loads(body)
        except:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        # 回调鉴权处理 (URL Verification)
        if data.get('type') == 'url_verification' or data.get('challenge'):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"challenge": data.get('challenge', '')}).encode('utf-8'))
            return

        # 检查是否是卡片操作事件 (card.action.trigger)
        event_header = data.get('header', {})
        event_type = event_header.get('event_type') or data.get('type')

        # 兼容两种常见格式:飞书 1.0 事件头和 2.0 嵌套结构
        action_value = data.get('action', {}).get('value')
        event_body = data.get('event', {})

        if not action_value:
            # 尝试从老版 event 结构中提取
            action_value = event_body.get('action', {}).get('value')

        if action_value:
            logger.info("[EVENT] Card action detected: action_value=%s", str(action_value)[:50])

            # 动态身份提取:识别是谁点击了按钮
            operator_obj = data.get('operator', {})
            open_id = operator_obj.get('open_id') or event_body.get('user', {}).get('open_id')
            if open_id:
                global DEFAULT_RECEIVE_ID
                if DEFAULT_RECEIVE_ID != open_id:
                    logger.info(f"[AUTH] Switching message target to user: {open_id}")
                    DEFAULT_RECEIVE_ID = open_id
            # 🚀 解决 200672: 飞书卡片返回格式极其严格
            # 必须提供合规的 toast 字典,并且增加 Content-Length 防止底层网关截断
            resp_data = {
                "toast": {
                    "type": "info",
                    "content": "指令已下达,正在极速拉取中...",
                    "i18n": {
                        "zh_cn": "指令已下达,正在极速拉取中..."
                    }
                }
            }
            resp_body = json.dumps(resp_data).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

            # 此时响应已发送,Feishu 将确认接收,后台线程继续工作
            threading.Thread(target=self.handle_card_action, args=(action_value,)).start()
            return

        # 检查是否是文本消息并包含 URL
        if event_type == 'im.message.receive_v1':
            message = data.get('event', {}).get('message', {})
            msg_type = message.get('message_type')
            if msg_type == 'text':
                try:
                    content_json = json.loads(message.get('content', '{}'))
                    text = content_json.get('text', '')
                    urls = re.findall(r'(https?://[^\s]+)', text)
                    if urls:
                        url = urls[0]
                        # 立即回复接收确认
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(json.dumps({"code": 0, "msg": "success"}).encode('utf-8'))

                        def process_url(u):
                            time.sleep(0.5)  # 稍微延迟,确保前端响应完成
                            token = self.get_token()
                            self.send_text(token, "收到链接,正在解析,请稍后(预计1-2分钟)...")
                            self.update_topic_context_by_id(token, u)
                            # 后台长耗时任务,直接对接 insight 流程
                            self.run_insight_and_send_card(token, f"insight_{u}")

                        # start thread
                        threading.Thread(target=process_url, args=(url,)).start()
                        return
                except Exception as e:
                    print(f"[WARN] Failed to parse im.message.receive_v1 text: {e}", flush=True)

        # 如果不是按钮点击或没匹配上,返回通用成功
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"code": 0, "msg": "success"}).encode('utf-8'))

    # ===== Feishu API =====

    def get_token(self):
        return get_global_token()

    def send_card(self, token, card):
        logger.debug("[FEISHU] Queuing interactive card")
        MESSAGE_QUEUE.put({"type": "card", "content": card})
        return True

    def send_image_preview(self, token, image_path, caption=""):
        logger.debug("[FEISHU] Sending image preview: path=%s, caption=%s", image_path, caption[:30] if caption else "none")
        if not image_path or not os.path.exists(image_path):
            logger.warning("[FEISHU] Image not found: path=%s", image_path)
            print(f"[WARN] Image not found: {image_path}")
            return
        try:
            token_data = json.loads(subprocess.run([
                'curl', '-s', '-X', 'POST',
                'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                '-H', 'Content-Type: application/json',
                '-d', json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET})
            ], capture_output=True, text=True).stdout)
            feishu_token = token_data.get("tenant_access_token", "")
            if not feishu_token:
                return

            upload_result = subprocess.run([
                'curl', '-s', '-X', 'POST',
                'https://open.feishu.cn/open-apis/im/v1/images',
                '-H', f'Authorization: Bearer {feishu_token}',
                '-F', 'image_type=message',
                '-F', f'image=@{image_path}'
            ], capture_output=True, text=True).stdout
            upload_data = json.loads(upload_result)
            image_key = upload_data.get("data", {}).get("image_key", "")
            if not image_key:
                logger.error("[FEISHU] Image upload failed: no image_key in response")
                return
            logger.info("[FEISHU] Image uploaded: image_key=%s", image_key[:20])

            if caption:
                template = "blue" if "插图" in caption else "purple"
                card_content = {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "template": template,
                        "title": {"tag": "plain_text", "content": caption}
                    },
                    "elements": [
                        {"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": caption}}
                    ]
                }
                payload = {
                    "receive_id": DEFAULT_RECEIVE_ID,
                    "msg_type": "interactive",
                    "content": json.dumps(card_content, ensure_ascii=False)
                }
            else:
                payload = {
                    "receive_id": DEFAULT_RECEIVE_ID,
                    "msg_type": "image",
                    "content": json.dumps({"image_key": image_key})
                }
            req = urllib.request.Request(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {feishu_token}"},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                if result.get('code') == 0:
                    logger.info("[FEISHU] Image preview sent: image_key=%s", image_key[:20])
                    print(f"[DEBUG] Image preview sent: {image_key}")
                else:
                    logger.warning("[FEISHU] Image send failed: code=%s, msg=%s", result.get('code'), result.get('msg'))
                    print(f"[WARN] Send image failed: {result.get('msg')}")
        except Exception as e:
            logger.error("[FEISHU] send_image_preview exception: %s", e, exc_info=True)
            print(f"[ERROR] send_image_preview failed: {e}")

    def send_text(self, token, text):
        logger.debug("[FEISHU] Queuing text message: length=%d", len(text))
        MESSAGE_QUEUE.put({"type": "text", "content": text})
        return True

    def send_source_selection_card(self, token, industry=None):
        """Send a card to let user choose hot topic source (paid vs free)."""
        industry_text = f" · {industry}赛道" if industry else ""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": f"🔍 请选择选题获取方式{industry_text}"}
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"**💡 两种选题获取方式,请根据您的需求和预算选择:**\n\n"
                },
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "💰 付费 API vs 🆓 免费抓取"}
                    ]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "markdown",
                    "content": f"**方式一:次幂数据 API(付费)**\n"
                        "✅ 数据来源:微信公众号\n"
                        "✅ 更精准的垂直领域爆文\n"
                        "✅ 包含详细的阅读数、点赞数等指标\n"
                        f"✅ 支持行业分类筛选{f':{industry}' if industry else ''}\n"
                        "⚠️ 需要有效的次幂 API 账号\n"
                },
                {
                    "tag": "action",
                    "actions": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "💰 使用付费 API(推荐)"},
                        "type": "primary",
                        "value": f"select_source_cimipa_{industry}" if industry else "select_source_cimipa"
                    }]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "markdown",
                    "content": f"**方式二:微博/头条/百度(免费)**\n"
                        "✅ 完全免费,无需 API 账号\n"
                        "✅ 覆盖全网热点(微博、今日头条、百度搜索)\n"
                        "✅ 适合追踪泛热点、社会新闻\n"
                        f"✅ 支持关键词过滤{f':{industry}' if industry else ''}\n"
                        "⚠️ 数据指标相对简化\n"
                },
                {
                    "tag": "action",
                    "actions": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🆓 使用免费抓取"},
                        "type": "default",
                        "value": f"select_source_free_{industry}" if industry else "select_source_free"
                    }]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "💡 您可以随时切换选择方式,系统会记住您的选择偏好"}
                    ]
                }
            ]
        }
        return self.send_card(token, card)

    def update_topic_context_by_id(self, token, topic_id):
        logger.info("[STATE] Updating topic context: topic_id=%s", str(topic_id)[:50])
        try:
            with STATE_FILE_LOCK:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)

            topic_id_str = str(topic_id).strip()
            updated = False

            # 1. 优先从全局映射中通过 GUID 查找
            with TOPIC_MAP_LOCK:
                if topic_id_str in TOPIC_MAP:
                    selected = TOPIC_MAP[topic_id_str]
                    state['topic_context'] = {
                        'id': selected.get('id', ''),
                        'title': selected.get('title', ''),
                        'source': selected.get('source', ''),
                        'author': selected.get('author', ''),
                        'score': selected.get('score', '')
                    }
                    updated = True
                    print(f"[DEBUG] Updated topic_context via TOPIC_MAP GUID {topic_id_str}: {selected.get('title', '')[:50]}", flush=True)

            # 2. 如果 GUID 没中,且不是 URL,则尝试作为数字索引查找 (向上兼容老卡片)
            if not updated and not topic_id_str.startswith('http'):
                candidates = state.get('last_candidates', [])
                try:
                    # Handle "insight_1" or "1"
                    raw_id = topic_id_str.split('_')[-1]
                    numeric_id = int(raw_id)
                    if 0 < numeric_id <= len(candidates):
                        selected = candidates[numeric_id - 1]
                        state['topic_context'] = {
                            'id': selected.get('id', ''),
                            'title': selected.get('title', ''),
                            'source': selected.get('source', ''),
                            'author': selected.get('author', ''),
                            'score': selected.get('score', '')
                        }
                        updated = True
                        print(f"[DEBUG] Updated topic_context via index {numeric_id}: {selected.get('title', '')[:50]}", flush=True)
                except (ValueError, IndexError):
                    pass

            # 3. 如果还是没中,且是 URL
            if not updated and topic_id_str.startswith('http'):
                state['topic_context'] = {
                    'id': topic_id_str,
                    'title': topic_id_str.split('?')[0][-30:],
                    'source': 'custom',
                    'author': ''
                }
                updated = True
                print(f"[DEBUG] Updated topic_context to URL: {topic_id_str[:50]}", flush=True)

            if not updated:
                print(f"[DEBUG] Topic ID {topic_id_str} could not be resolved, keeping existing context", flush=True)

            if updated:
                self.save_state(state)
        except Exception as e:
            print(f"[ERROR] update_topic_context_by_id failed: {e}", flush=True)

    def save_state(self, state):
        logger.debug("[STATE] Saving workflow state: keys=%s", list(state.keys()))
        try:
            with STATE_FILE_LOCK:
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] save_state failed: {e}", flush=True)
            import traceback
            traceback.print_exc()

    # ===== Card Action Router =====

    def handle_card_action(self, action_value, token=None):
        """Route card button actions to appropriate handlers."""
        import re  # Must be at function top to avoid "local variable re" bug
        logger.info("[ROUTE] Card action received: action_value=%s", str(action_value)[:50])
        try:
            # 防抖去重:10秒内相同的操作直接忽略
            now = time.time()
            if action_value in PROCESSED_ACTIONS and now - PROCESSED_ACTIONS.get(action_value, 0) < 10:
                logger.info(f"[ASYNC_SKIP] Ignoring duplicate action: {action_value}")
                return
            PROCESSED_ACTIONS[action_value] = now

            logger.debug("[ROUTE] Raw action_value: %s", repr(action_value))
            print(f"[DEBUG] handle_card_action: {repr(action_value)}", flush=True)
            token = self.get_token()

            # Strip common garbled quote chars and whitespaces
            if isinstance(action_value, str):
                for q in '"\'铐牢笼非':
                    action_value = action_value.strip(q)
                action_value = action_value.strip()

            # Fix for JSON string action_value: try to parse it properly
            if isinstance(action_value, str) and ('{' in action_value or action_value.startswith('\\{')):
                try:
                    # Clean up escaped characters first
                    clean_val = action_value.replace('\\"', '"').replace('\\\\', '\\')
                    # Try to parse as JSON
                    parsed = json.loads(clean_val)
                    if isinstance(parsed, dict):
                        raw_action = parsed.get('action', '')
                        raw_id = str(parsed.get('id', '')) if parsed.get('id') is not None else ''
                        # raw_action like "insight_topic" -> extract base action
                        if '_' in raw_action:
                            action_value = raw_action  # e.g. "insight_topic"
                        else:
                            action_value = f"{raw_action}_{raw_id}" if raw_id else raw_action
                        logger.info("[ROUTE] Parsed JSON action: action_value=%s", action_value[:50])
                        print(f"[DEBUG] Parsed JSON action_value: {action_value}", flush=True)
                        # Skip the regex path below
                        parts = action_value.split('_', 1)
                        action_type = parts[0] if parts else 'unknown'
                        topic_id = parts[1] if len(parts) > 1 else None
                        if action_type == 'insight':
                            if topic_id:
                                self.update_topic_context_by_id(token, topic_id)
                            threading.Thread(target=self.run_insight_and_send_card, args=(token, action_value)).start()
                            return
                        # ... handle other types similarly or fall through
                except Exception as e:
                    print(f"[WARN] JSON parse failed: {e}", flush=True)
                    # Fall through to regex-based parsing

            logger.debug("[ROUTE] Cleaned action_value: %s", str(action_value)[:50])
            # Robust splitting: handle cases where action_value might still have leftover quotes or escapes
            if isinstance(action_value, str):
                action_value = action_value.replace('"', '').replace('\\', '').strip()

            parts = action_value.split('_', 1)
            action_type = parts[0] if parts else 'unknown'

            if action_type == 'next':
                logger.info("[ROUTE] Action: next_batch - sending new topics")
                self.send_text(token, "🔍 正在为您检索下一批爆款选题...\n\n(预计 15-30 秒)")
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token,)).start()
            elif action_type == 'pre_discovery':
                logger.info("[ROUTE] Action: pre_discovery - sending source selection card")
                # 用户触发预发现流程,发送选择卡片
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    industry = state.get('industry')
                except:
                    industry = None
                self.send_text(token, "🔍 正在为您准备选题方式选择,请稍候...\n\n(预计 5-10 秒)")
                threading.Thread(target=self.send_source_selection_card, args=(token, industry)).start()
            elif action_type == 'select_source':
                # 用户选择了热点来源方式
                # action_value like "select_source_cimipa" or "select_source_free" or "select_source_cimipa_AI"
                parts_extended = action_value.split('_')
                source = 'cimipa' if 'cimipa' in parts_extended else 'free'
                source_name = '次幂数据 API' if source == 'cimipa' else '免费热点抓取'
                # 提取行业关键词(如果有)
                industry = None
                if len(parts_extended) > 3:
                    industry = parts_extended[3]
                logger.info("[ROUTE] Action: select_source - source=%s, industry=%s", source_name, industry)
                self.send_text(token, f"🔍 正在使用 [{source_name}] 为您检索爆款选题...{f' (行业:{industry})' if industry else ''}\n\n(预计 15-30 秒)")
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token, source, industry)).start()
            elif action_type == 'insight':
                topic_id = parts[1] if len(parts) > 1 else None
                logger.info("[ROUTE] Action: insight - topic_id=%s", topic_id[:30] if topic_id else "none")
                if topic_id:
                    self.update_topic_context_by_id(token, topic_id)
                self.send_text(token, "🧠 正在对该选题进行深度爆点分析与 IP 切入点规划...\n\n(预计 20-40 秒)")
                threading.Thread(target=self.run_insight_and_send_card, args=(token, action_value)).start()
            elif action_type == 'skip':
                logger.info("[ROUTE] Action: skip - fetching new topics")
                self.send_text(token, "⏩ 正在跳过并检索新选题...")
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token,)).start()
            elif action_type == 'refresh':
                logger.info("[ROUTE] Action: refresh - refreshing topic pool")
                self.send_text(token, "🔄 正在刷新爆款库...")
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token,)).start()
            elif action_type == 'init':
                logger.info("[ROUTE] Action: init - sending init guide")
                threading.Thread(target=self.run_init_and_send_card, args=(token,)).start()
            elif action_type == 'rewrite':
                logger.info("[ROUTE] Action: rewrite - repurpose request")
                self.send_text(token, "📝 正在为您进行 IP 化改写,生成脚本与长文...\n\n(预计 1-2 分钟,请稍候)")
                threading.Thread(target=self.run_repurpose_and_send_card, args=(token, action_value)).start()
            elif action_type == 'approve':
                logger.info("[ROUTE] Action: approve - tracking approval")
                threading.Thread(target=self.run_approve_and_track, args=(token, action_value)).start()
            elif action_type == 'modify':
                logger.info("[ROUTE] Action: modify - modifying content")
                threading.Thread(target=self.run_modify_and_send_card, args=(token, action_value)).start()
            elif action_type == 'rescript':
                logger.info("[ROUTE] Action: rescript - rescripting")
                threading.Thread(target=self.run_rescript_and_send_card, args=(token, action_value)).start()
            elif action_type == 'rearticle':
                logger.info("[ROUTE] Action: rearticle - re-articling")
                threading.Thread(target=self.run_rearticle_and_send_card, args=(token, action_value)).start()
            elif action_type.startswith('post'):
                logger.info("[ROUTE] Action: post - publishing to WeChat")
                self.send_text(token, "🚀 正在将内容同步至公众号草稿箱...")
                threading.Thread(target=self.run_post, args=(token,)).start()
            elif action_type == 'copy':
                logger.info("[ROUTE] Action: copy - sending copy guide")
                self.send_copy_guide(token)
            elif action_type.startswith('retry_visual_'):
                mtype = action_type.replace('retry_visual_', '')
                logger.info("[ROUTE] Action: retry_visual - model=%s", mtype)
                self.send_text(token, f"🔄 正在尝试使用 [{mtype}] 引擎重新绘图,请稍候...")
                threading.Thread(target=self._run_workflow_async, args=(token, ['python', '-u', 'workflow_controller.py', 'visuals', '--model', mtype])).start()
            else:
                logger.warning("[ROUTE] Unknown action_type: action_type=%s", action_type)
                print(f"[DEBUG] Unknown action_type: {action_type}", flush=True)
        except Exception as e:
            logger.error("[ROUTE] handle_card_action exception: %s", e, exc_info=True)
            print(f"[ERROR] handle_card_action failed: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def _run_workflow_async(self, token, cmd):
        """核心异步执行引擎:负责运行工作流并实时捕捉输出推送飞书"""
        try:
            print(f"\n[EXEC] 🚀 启动子进程: {' '.join(cmd)}", flush=True)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )

            full_output = []
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if not line:
                    continue

                clean_line = line.strip()
                if clean_line:
                    logger.debug("[EXEC] Workflow output: %s", clean_line[:100])
                    print(f"[workflow] {clean_line}", flush=True)
                    full_output.append(clean_line)

                    # 绝对稳健协议解析:[FEISHU_PREVIEW] TYPE=XXX PATH=YYY
                    if "[FEISHU_PREVIEW]" in clean_line:
                        logger.info("[EXEC] FEISHU_PREVIEW detected: %s", clean_line[:100])
                        try:
                            # 1. 提取 PATH= 之后的部分
                            if "PATH=" in clean_line:
                                # 彻底清洗:先去掉两端空格,再去掉可能存在的引号
                                raw_path = clean_line.split("PATH=")[1].strip()
                                # 针对 Windows 终端黏连问题:如果路径后面跟着其他协议标记,截断它
                                if " [FEISHU" in raw_path:
                                    raw_path = raw_path.split(" [FEISHU")[0].strip()

                                # 处理引号
                                clean_path = raw_path.replace('"', '').replace("'", "")

                                # 2. 如果是相对路径,强制转绝对
                                if not os.path.isabs(clean_path):
                                    if "assets" in clean_path:
                                        # 针对可能的 assets 前缀偏移
                                        as_idx = clean_path.find("assets")
                                        clean_path = os.path.join(WORKDIR, clean_path[as_idx:])
                                    else:
                                        clean_path = os.path.join(WORKDIR, clean_path)

                                # 3. 规范化斜杠 (Windows 兼容性)
                                clean_path = os.path.normpath(clean_path)

                                if os.path.exists(clean_path):
                                    print(f"[DEBUG] 🚀 物理校验成功: {clean_path}", flush=True)
                                    if "TYPE=COVER" in clean_line:
                                        self.send_image_preview(token, clean_path, "🖼️ 封面图已就绪")
                                    elif "TYPE=ILLUS" in clean_line:
                                        import re
                                        m = re.search(r'INDEX=(\d+)', clean_line)
                                        idx = m.group(1) if m else "?"
                                        self.send_image_preview(token, clean_path, f"🖼️ 插图 {idx} 已就绪")
                                    else:
                                        self.send_image_preview(token, clean_path, "🖼️ 图片已就绪")
                                else:
                                    print(f"[DEBUG] ⚠️ 路径指向的文件不存在: {clean_path}", flush=True)
                        except Exception as pe:
                            print(f"[DEBUG] ❌ 协议解析捕获异常: {pe}", flush=True)

                    # 状态监控协议
                    elif "[FEISHU_STATUS]" in clean_line:
                        try:
                            status_msg = clean_line.split("FEISHU_STATUS]")[-1].strip().replace('"', '').replace("'", "")
                            if "ERR=" in status_msg or "WARN=" in status_msg:
                                self.send_text(token, f"🔔 {status_msg}")
                            elif "DONE=" in status_msg:
                                # 任务结束最后推一个总结
                                pass
                        except: pass

            process.wait()
            output_str = "\n".join(full_output)

            # 如果是视觉任务结束,触发最终确认卡片
            if 'visuals' in str(cmd):
                self._send_visual_completion_card(token)

        except Exception as e:
            print(f"[ERROR] _run_workflow_async failed: {e}", flush=True)
            self.send_text(token, f"⚠️ 后台执行引擎异常: {str(e)[:100]}")

    def _send_visual_completion_card(self, token):
        """视觉任务结束后的收尾工作:合并状态发送总卡片"""
        try:
            import time; time.sleep(1) # 等待文件同步
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            title = state.get("topic_context", {}).get("title", "内容预览")
            draft = state.get("draft_file", "")
            cover = state.get("cover_image", "")
            illus = state.get("article_images", [])

            c_key = self.upload_to_feishu(cover) if cover and os.path.exists(cover) else ""
            i_keys = [self.upload_to_feishu(p) for p in illus if os.path.exists(p)]

            content = ""
            if draft and os.path.exists(draft):
                with open(draft, "r", encoding="utf-8") as f:
                    content = f.read()[:500] + "..."

            card = self.build_final_card(c_key, title, content, "高清渲染|Baoyu风格", "final_01", i_keys, deai_notes=None)
            self.send_card(token, card)
        except Exception as e:
            print(f"[ERROR] final completion failed: {e}")

    # ===== Action Handlers =====

    def run_init_and_send_card(self, token):
        logger.info("[INIT] Sending initialization guide")
        try:
            print("[DEBUG] run_init_and_send_card starting", flush=True)
            init_text = (
                "🔔 **IP 爆款制造机 - 初始化**\n\n"
                "请告诉我以下信息来完成配置:\n\n"
                "**1️⃣ IP 名称**\n"
                "您想用哪个名字作为内容品牌?(例如:胡老板、科技君)\n\n"
                "**2️⃣ 行业赛道**\n"
                "请从以下 45 个行业中选择您的定位:\n\n"
                "1.小绿书 2.育儿 3.科技 4.体育健身 5.财经\n"
                "6.美食 7.医疗 8.娱乐 9.情感 10.历史\n"
                "11.军事国际 12.美妆时尚 13.文化 14.汽车 15.游戏\n"
                "16.旅游 17.房产 18.健康养生 19.职场 20.摄影\n"
                "21.资讯热点 22.教育 23.开发者 24.影视 25.美妆\n"
                "26.生活 27.数码 28.媒体 29.宠物 30.三农\n"
                "31.星座命理 32.搞笑 33.动漫 34.家居 35.科学\n"
                "36.商业营销 37.个人成长 38.壁纸头像 39.法律 40.民生\n"
                "41.文案 42.体制 43.文摘 44.AI 45.其它\n\n"
                "请直接回复,例如:\n"
                "IP名称:胡老板\n"
                "行业:4"
            )
            self.send_text(token, init_text)
        except Exception as e:
            print(f"[ERROR] run_init_and_send_card failed: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def run_discovery_and_send_cards(self, token, source='cimipa', industry=None):
        """Run discovery and send topic cards."""
        try:
            logger.info("[DISCOVERY] Starting topic discovery: source=%s, industry=%s", source, industry)
            print("[DEBUG] run_discovery_and_send_cards starting", flush=True)
            os.chdir(WORKDIR)

            # Check if there's a cached page of candidates
            use_refresh = True
            current_start_num = 1
            state = None
            try:
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    candidates = state.get('last_candidates', [])
                    page_index = state.get('candidates_page_index', 0)
                    page_size = state.get('candidates_page_size', 5)
                    # 关键优化:当缓存中还有数据时,直接从缓存读取,不调用 workflow_controller
                    if candidates and page_index * page_size < len(candidates):
                        state['candidates_page_index'] = page_index + 1
                        with open(STATE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(state, f, ensure_ascii=False)
                        use_refresh = False
                        # 直接从缓存中取当前页的数据
                        start_idx = page_index * page_size
                        end_idx = start_idx + page_size
                        topics = candidates[start_idx:end_idx]
                        current_start_num = start_idx + 1
                        logger.info("[DISCOVERY] Using cached candidates: page_index=%d, total=%d, showing %d-%d",
                                   page_index + 1, len(candidates), start_idx + 1, end_idx)
            except Exception as e:
                logger.warning("[DISCOVERY] Failed to check cached candidates: %s", e)
                pass

            if use_refresh:
                # 缓存已空,需要调用 API 获取新一批数据
                last_id = state.get('cimi_last_id', '') if state else ''
                cmd = ['python', '-u', 'workflow_controller.py', 'discovery', '--refresh', '--source', source]
                if industry:
                    cmd.extend(['--keyword', industry])
                if last_id:
                    cmd.extend(['--last_id', last_id])
                    print(f"[DEBUG] Reaching end of cache. Fetching next page from API with last_id: {last_id}", flush=True)

                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'

                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90, encoding='utf-8', errors='replace', env=env)
                output = result.stdout
                print(f"[DEBUG] command output length: {len(output)}", flush=True)

                topics = self.parse_discovery_output(output)
                print(f"[DEBUG] parsed topics count: {len(topics)}", flush=True)

            if topics:
                # Save candidates to state file only if it's a fresh discovery
                if use_refresh:
                    try:
                        with open(STATE_FILE, 'r', encoding='utf-8') as f:
                            state = json.load(f)
                        state['last_candidates'] = topics
                        state['candidates'] = topics  # 关键修复:同时保存 candidates 字段,供 workflow_controller.py next 命令读取
                        state['candidates_page_index'] = 1
                        state['candidates_page_size'] = 5
                        with open(STATE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(state, f, ensure_ascii=False, indent=2)
                        print(f"[DEBUG] Saved {len(topics)} fresh candidates to state", flush=True)
                    except Exception as e:
                        print(f"[WARN] Failed to save candidates to state: {e}", flush=True)

                    # 关键修复:确保强制刷新时,即使解析了15条,也只往飞书卡片中推送第一页的数量(5条)
                    topics = topics[:5]
                    current_start_num = 1

                # ALWAYS send as batch card
                batch_card = self.build_topic_list_card(topics, industry or "AI", start_num=current_start_num)
                self.send_card(token, batch_card)
            else:
                if use_refresh:
                    print(f"[DEBUG] No topics parsed, output preview: {output[:500]}", flush=True)
                self.send_text(token, "⚠️ 获取选题失败,请稍后重试或手动发'选题'获取")
        except Exception as e:
            print(f"[ERROR] run_discovery_and_send_cards failed: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.send_text(token, f"⚠️ 操作失败: {str(e)[:100]}")

    def parse_discovery_output(self, output):
        logger.debug("[PARSE] Starting to parse discovery output: length=%d", len(output))
        """Parse topic data from workflow output.
        Returns list of dicts with keys: id (URL), title, source, author, score, data (display string), analysis.
        """
        topics = []

        # 🎯 优先解析结构化 JSON,这是 100% 准确的
        import re as _re
        json_match = _re.search(r'\[DATA_JSON\]:\s*(\[.*\])', output)
        if json_match:
            try:
                json_data = json.loads(json_match.group(1))
                logger.info(f"[PARSE] Successfully parsed {len(json_data)} topics from RAW JSON")
                for item in json_data:
                    # 获取核心参数
                    guid = item.get('guid', str(uuid.uuid4())[:8])
                    item['guid'] = guid
                    item['created_at'] = time.time()

                    # 规范化所需的值保证后续卡片拼接安全
                    item['author'] = item.get('author', '未知资源')
                    item['likes'] = str(item.get('likes', '0'))
                    item['comments'] = str(item.get('comments', item.get('reads', '0')))
                    item['score'] = str(item.get('score', '0'))

                    # 重新对齐一句话解读字段
                    if 'analysis' not in item:
                        item['analysis'] = item.get('topic_insight', item.get('digest', '爆款选题'))

                    # 组装展示字符串 (Fallback 用)
                    item['data'] = f"阅读: {item['comments']} | 赞: {item['likes']} | 热度: {item['score']}"

                    with TOPIC_MAP_LOCK:
                        TOPIC_MAP[guid] = item
                    topics.append(item)
                save_persistent_map()
                return topics
            except Exception as e:
                logger.warning(f"[WARN] Failed to parse DATA_JSON: {e}")

        # Strip ANSI color codes from entire output first
        ansi_escape = _re.compile(r'\x1b\[[0-9;]*m')
        clean_output = ansi_escape.sub('', output)

        lines = clean_output.split('\n')
        current_topic = None

        for line in lines:
            # Match pattern: 1. [source] [title](URL)
            topic_match = re.match(r'^\d+\.\s*\[([^\]]*)\]\s*\[(.+?)\]\((https?://[^\)]+)\)', line)
            if topic_match:
                source = topic_match.group(1).strip()
                title = topic_match.group(2).strip()
                url = topic_match.group(3).strip()
                current_topic = {
                    'id': url,
                    'title': title,
                    'source': source,
                    'author': '',
                    'score': '',
                    'data': '',
                    'analysis': '爆款选题'
                }
                continue

            # Extract metrics: 👤 author | 👁️ 阅读: xxx | 👍 赞: xxx | 🔥 热度: xxx
            if current_topic:
                author_match = re.search(r'👤\s*([^\s|]+)', line)
                if author_match and not current_topic.get('author'):
                    current_topic['author'] = author_match.group(1).strip()

                read_match = re.search(r'阅读[:\s]*([\d万+]+)', line)
                like_match = re.search(r'赞[赞:\s]*([\d万+]+)', line)
                heat_match = re.search(r'热度[:\s]*([\d万+]+)', line)

                data_parts = []
                score_val = 0
                if read_match:
                    val = read_match.group(1)
                    data_parts.append(f"阅读: {val}")
                    try: score_val += int(val.replace('万', '')) * 10000 if '万' in val else int(val)
                    except: pass
                if like_match:
                    val = like_match.group(1)
                    data_parts.append(f"赞: {val}")
                    try: score_val += int(val.replace('万', '')) * 1000 if '万' in val else int(val)
                    except: pass
                if heat_match:
                    val = heat_match.group(1)
                    data_parts.append(f"热度: {val}")
                    try: score_val += int(val.replace('万', '')) * 100 if '万' in val else int(val)
                    except: pass

                if data_parts:
                    current_topic['data'] = ' | '.join(data_parts)
                    current_topic['score'] = str(score_val)

                    # 关键革新:生成全局唯一 ID 并加入映射
                    guid = str(uuid.uuid4())[:8] # 取 8 位 UUID
                    current_topic['guid'] = guid
                    current_topic['created_at'] = time.time()  # 添加时间戳用于过期清理
                    with TOPIC_MAP_LOCK:
                        TOPIC_MAP[guid] = current_topic

                    topics.append(current_topic)
                    current_topic = None

        # Persist the new mappings to disk immediately
        save_persistent_map()
        return topics

    def build_topic_card(self, title, data_str, url, analysis, topic_id):
        """Build single topic selection card."""
        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": "🔥 新一期选题推送"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 选题:** {title}\n\n**📊 数据:** {data_str}\n\n**🔗 原文:** [{url}]({url})\n\n**💡 爆点:** {analysis}"}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"ID: {topic_id}"}]},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "🔍 解读此选题"}, "type": "primary", "value": f"insight_{topic_id}"},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "🔄 换一批"}, "type": "default", "value": "next"}
                ]}
            ]
        }

    def build_topic_list_card(self, topics, industry="AI", start_num=1):
        """Build batch topic card (all topics in one card).
        topics: list of dicts with keys: id(str), title, data, url, analysis, source, author, score
        """
        elements = []
        elements.append({"tag": "markdown", "content": f"**🔥 {industry}赛道 · 今日爆款选题 TOP {len(topics) * 3 if len(topics) == 5 and start_num == 1 else len(topics)}**"})
        elements.append({"tag": "hr"})

        for i, t in enumerate(topics):
            topic_num = start_num + i

            # 提取干净的标题和 URL
            title = str(t.get('title', '未知选题')).strip()
            topic_url = t.get('url', '') or t.get('id', '')

            # 防御性:如果标题看起来像 URL,尝试使用截断
            if title.startswith('http'):
                title = f"精选选题 {topic_num}"

            # 提取 GUID
            guid = t.get('guid', str(topic_num))

            # 提取精确的渲染数据实现第二版视觉要求
            author = str(t.get('author', '未知'))
            likes = str(t.get('likes', ''))
            comments = str(t.get('comments', t.get('reads', '')))
            heat = str(t.get('score', ''))

            # 组装富文本数据行
            rich_parts = [f"👤 {author}"]
            if likes and likes != "0" and likes.lower() != 'none': rich_parts.append(f"👍 {likes} 赞")
            if comments and comments != "0" and comments.lower() != 'none': rich_parts.append(f"💬 {comments} 评论")
            if heat and heat != "0" and heat.lower() != 'none': rich_parts.append(f"🔥 {heat} 热度")

            if len(rich_parts) >= 1:
                metrics_str = " | ".join(rich_parts)
            else:
                metrics_str = " | ".join(rich_parts) if rich_parts else t.get('data', '暂无热度数据')

            # 确保一句话解读存在
            analysis = str(t.get('analysis', t.get('digest', t.get('topic_insight', '该选题具有较大爆款潜质')))).strip()

            # 使用 GUID 作为按钮值,彻底解决 ID 冲突
            elements.append({
                "tag": "markdown",
                "content": f"**🔥 [{topic_num}] {title}**\n📊 {metrics_str}\n💡 {analysis}\n🔗 [原文链接]({topic_url})"
            })
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": f"🔍 解读选题 {topic_num}"},
                    "type": "primary",
                    "value": f"insight_{guid}" # 绑定 GUID
                }]
            })
            if i < len(topics) - 1:
                elements.append({"tag": "hr"})

        # Bottom action buttons (with descriptions)
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "action",
            "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "📋 换一批(查看更多爆款选题)"}, "type": "default", "value": "next"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 初始化(重置IP名称/行业赛道)"}, "type": "default", "value": "init"}
            ]
        })
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "💡 点击上方按钮选择选题,或直接发送序号 1-5 选择"}]
        })

        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": "purple", "title": {"tag": "plain_text", "content": f"🚀 IP 爆款选题推荐 · {industry}赛道"}},
            "elements": elements
        }

    def run_insight_and_send_card(self, token, action_value):
        """Analyze topic and send rewrite confirm card."""
        try:
            print("[DEBUG] run_insight_and_send_card starting", flush=True)
            os.chdir(WORKDIR)

            with STATE_FILE_LOCK:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            topic_ctx = state.get('topic_context', {})
            title = topic_ctx.get('title', '未知选题')
            url = topic_ctx.get('id', '')
            author = topic_ctx.get('author', '')
            score = topic_ctx.get('score', '')

            # Fetch article content using Controller's browser engine
            raw_content = ""
            if url:
                try:
                    # Import Controller dynamicially to access its powerful extraction
                    sys.path.insert(0, WORKDIR)
                    from workflow_controller import SelfMediaController
                    controller = SelfMediaController()
                    print(f"[DEBUG] Fetching content using Controller's engine: {url}", flush=True)
                    raw_content = controller._extract_article_content(url)
                    if not raw_content:
                        print(f"[WARN] Controller extraction returned empty, fallback to basic titles", flush=True)
                except Exception as e:
                    print(f"[WARN] Failed to fetch article using controller: {e}", flush=True)

            # Call LLM for insight
            insight_text = ""
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if raw_content and api_key:
                prompt = (
                    f"你是一个资深自媒体爆款策划顾问。请分析以下选题的爆款潜力:\n\n"
                    f"选题标题:{title}\n原文作者:{author}\n热度指数:{score}\n\n"
                    f"原文内容摘要:{raw_content[:1000]}\n\n"
                    f"请从以下四个维度分析(每条不超过50字):\n"
                    f"1. 【核心情绪】核心情绪是什么?为何能引发传播?\n"
                    f"2. 【IP切入点】从这个IP应该从哪个差异化角度切入?\n"
                    f"3. 【可借鉴点】哪些爆点元素值得借鉴?\n"
                    f"4. 【风险提示】有无敏感话题风险?\n\n"
                    f"直接输出分析结论,不要车轱辘话。"
                )
                try:
                    req_data = json.dumps({
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 600
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        "https://api.deepseek.com/v1/chat/completions",
                        data=req_data,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        insight_text = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if insight_text:
                            insight_text = insight_text.strip()
                except Exception as e:
                    print(f"[WARN] LLM insight failed: {e}", flush=True)

            if not insight_text:
                insight_text = f"🔥 **选题:** {title}\n\n热度指数:{score}\n\n请确认是否值得投入 IP 化改写。"

            # Update state
            topic_id_str = action_value.split('_', 1)[1] if '_' in action_value else 'new'
            state['topic_context'] = topic_ctx
            state['current_step'] = 'waiting_for_rewrite_confirm'
            with STATE_FILE_LOCK:
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False)

            # Send rewrite confirm card
            card = self.build_rewrite_card(title, insight_text, topic_id_str)
            self.send_card(token, card)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_text(token, f"⚠️ 解读失败: {str(e)[:100]}")

    def build_rewrite_card(self, title, insight, topic_id):
        """Build rewrite confirm card."""
        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": "purple", "title": {"tag": "plain_text", "content": "📝 选题解读完成"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 选题:** {title}\n\n**💡 解读:**\n{insight}"}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"ID: {topic_id}"}]},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "✍️ 开始改写"}, "type": "primary", "value": f"rewrite_{topic_id}"},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "🔄 换一个"}, "type": "default", "value": "next_new"}
                ]}
            ]
        }

    def run_repurpose_and_send_card(self, token, action_value):
        """Run repurpose - generate script + article, send two review cards."""
        logger.info("[REPURPOSE] Starting content repurpose: action_value=%s", str(action_value)[:50])
        try:
            os.chdir(WORKDIR)
            start_time = time.time()

            # 1. 强力净化:改写前彻底清理旧状态,并同步到磁盘,切断旧数据引用路径
            try:
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state_to_clean = json.load(f)
                    state_to_clean['draft_file'] = None
                    state_to_clean['video_script'] = None
                    # 保存这个"干净"的状态,防止脚本读到旧值
                    with open(STATE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(state_to_clean, f, ensure_ascii=False, indent=2)
                    print(f"[DEBUG] [{time.strftime('%H:%M:%S')}] Cleared old draft paths in state file.", flush=True)
            except Exception as e:
                print(f"[WARN] Failed to clean state: {e}", flush=True)

            # 2. 准备执行参数 - 关键优化:直接导入 SelfMediaController 调用,避免 subprocess 开销
            topic_id = action_value.split('_', 1)[1] if '_' in action_value else action_value
            # 还原真实 ID
            if topic_id in ['script_01', 'article_01']:
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        temp_state = json.load(f)
                    real_id = temp_state.get('topic_context', {}).get('id')
                    if real_id: topic_id = real_id
                except: pass

            # 关键优化:直接导入并调用,避免 subprocess 启动开销(约 1-2 秒)
            sys.path.insert(0, WORKDIR)
            from workflow_controller import SelfMediaController
            controller = SelfMediaController()

            print(f"[DEBUG] Executing repurpose using direct call (ID: {topic_id[:30]}...)", flush=True)
            process_start = time.time()

            # 直接调用 run_repurpose 方法,传入 topic_id
            controller.run_repurpose(str(topic_id))

            process_duration = time.time() - process_start
            print(f"[DEBUG] Repurpose completed in {process_duration:.2f}s", flush=True)

            # 3. 载入状态,并进行文件"新鲜度"校验
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            draft_file = state.get('draft_file', '')
            script_file = state.get('video_script', '')
            deai_notes = state.get('deai_notes', None)

            # 如果路径依然为空,或者文件修改时间在启动之前,说明没写成功
            def is_file_fresh(path, threshold_time):
                if not path or not os.path.exists(path): return False
                return os.path.getmtime(path) >= threshold_time

            if not is_file_fresh(draft_file, start_time) and not is_file_fresh(script_file, start_time):
                print(f"[ERROR] Stale files detected. Start: {start_time}, Draft: {os.path.getmtime(draft_file) if draft_file and os.path.exists(draft_file) else 'N/A'}", flush=True)
                self.send_text(token, "⚠️ 检测到生成文件失效,请尝试重试按钮。")
                return

            # 6. 读取新生成的内容
            title = state.get('topic_context', {}).get('title', '内容')
            article_full = ""
            if draft_file and os.path.exists(draft_file):
                try:
                    with open(draft_file, 'r', encoding='utf-8') as f:
                        raw = f.read()
                    article_full = re.sub(r'^#+\s*', '', raw, flags=re.MULTILINE).strip()
                except: pass
            if not article_full:
                article_full = "(未生成文章)"

            script_full = ""
            if script_file and os.path.exists(script_file):
                try:
                    with open(script_file, 'r', encoding='utf-8') as f:
                        script_full = f.read().strip()
                except Exception:
                    pass
            if not script_full:
                script_full = "(未生成脚本)"

            generate_script = os.getenv("GENERATE_VIDEO_SCRIPT", "FALSE").upper() == "TRUE"

            if generate_script:
                self.send_text(token, "✨ 改写完成,请分别审核【脚本】和【文章】...")

                script_card = self.build_review_card_v2(
                    cover_path="",
                    title=f"🎬 短视频脚本 | {title}",
                    content=script_full,
                    tags="脚本",
                    review_id="script_01",
                    template="orange",
                    header_title="🎬 脚本审核",
                    deai_notes=deai_notes
                )
                self.send_card(token, script_card)
            else:
                self.send_text(token, "✨ 改写完成,请审核【文章】...")

            article_card = self.build_review_card_v2(
                cover_path="",
                title=f"📖 深度长文 | {title}",
                content=article_full,
                tags="文章",
                review_id="article_01",
                template="blue",
                header_title="📖 文章审核",
                deai_notes=deai_notes
            )
            self.send_card(token, article_card)

        except Exception as e:
            self.send_text(token, f"⚠️ 改写失败: {str(e)[:100]}")

    def build_review_card_v2(self, cover_path, title, content, tags, review_id, template="blue", header_title=None, deai_notes=None):
        """Build review card with anti-fake labels and timestamps.
        
        Args:
            deai_notes: Optional[str], Natural Chinese Protocol 祛AI处理改动说明
        """
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
            "text": {"tag": "lark_md", "content": f"**🔥 标题:** {title}\n\n**🏷️ 标签:** {tags}"}
        })
        elements.extend(paragraphs)

        # 🔍 祛 AI 味说明区块（Natural Chinese Protocol 处理结果）
        if deai_notes:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**🔍 Natural Chinese Protocol · 祛AI处理说明**\n\n{deai_notes}"}
            })

        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"更新时间: {now_str}"}]
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

    def run_modify_and_send_card(self, token, action_value):
        """User clicked modify - ask what to change."""
        parts = action_value.split('_', 1)
        if len(parts) < 2:
            self.send_text(token, "⚠️ 无法识别修改目标,请重新操作")
            return
        target = parts[1]

        if target.startswith('script_'):
            kind = "🎬 脚本"
            file_key = "video_script"
        elif target.startswith('article_'):
            kind = "📖 文章"
            file_key = "draft_file"
        else:
            self.send_text(token, "⚠️ 未知修改目标")
            return

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        file_path = state.get(file_key, '')
        current_content = ""
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    current_content = f.read()
            except Exception:
                pass

        guide_msg = (
            f"✏️ 您选择了修改【{kind}】。\n\n"
            f"当前内容预览(前200字):\n"
            f"```{current_content[:200]}```\n\n"
            f"请直接告诉我您想怎么修改,例如:\n"
            f"• \"把开头改得更吸引人\"\n"
            f"• \"第三段加一个金句\"\n"
            f"• \"语言风格更口语化\"\n\n"
            f"我收到后会重新生成该【{kind}】。"
        )
        self.send_text(token, guide_msg)

    def run_rescript_and_send_card(self, token, action_value):
        """Regenerate script only, keep article."""
        self.send_text(token, "🔄 正在重新生成【脚本】,请稍候...\n(脚本已保留,内容将重新生成)")
        os.chdir(WORKDIR)

        # 关键优化:直接导入并调用,避免 subprocess 启动开销(约 1-2 秒)
        # 注:workflow_controller 的 --script-only 标志实际未实现,此处调用与完整 repurpose 等价
        sys.path.insert(0, WORKDIR)
        from workflow_controller import SelfMediaController
        controller = SelfMediaController()

        print(f"[DEBUG] Executing repurpose (script mode) using direct call", flush=True)
        process_start = time.time()

        controller.run_repurpose(None)

        process_duration = time.time() - process_start
        print(f"[DEBUG] Repurpose completed in {process_duration:.2f}s", flush=True)

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        title = state.get('topic_context', {}).get('title', '内容')
        script_file = state.get('video_script', '')
        article_file = state.get('draft_file', '')

        script_full = ""
        if script_file and os.path.exists(script_file):
            try:
                with open(script_file, 'r', encoding='utf-8') as f:
                    script_full = f.read().strip()
            except Exception:
                pass
        if not script_full:
            script_full = "(未生成脚本)"

        article_full = ""
        if article_file and os.path.exists(article_file):
            try:
                with open(article_file, 'r', encoding='utf-8') as f:
                    raw = f.read()
                raw = re.sub(r'^#+\s*', '', raw, flags=re.MULTILINE)
                article_full = raw.strip()
            except Exception:
                pass
        if not article_full:
            article_full = "(未生成文章)"

        self.send_text(token, "✨ 脚本已重新生成,请审核新版本...")

        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"🎬 短视频脚本 | {title}",
            content=script_full, tags="脚本(已重写)",
            review_id="script_01", template="orange", header_title="🎬 脚本审核(新版)"
        ))
        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"📖 深度长文 | {title}",
            content=article_full, tags="文章(未变)",
            review_id="article_01", template="blue", header_title="📖 文章审核"
        ))

    def run_rearticle_and_send_card(self, token, action_value):
        """Regenerate article only, keep script."""
        self.send_text(token, "🔄 正在重新生成【文章】,请稍候...\n(文章将重新生成,脚本已保留)")
        os.chdir(WORKDIR)

        # 关键优化:直接导入并调用,避免 subprocess 启动开销(约 1-2 秒)
        # 注:workflow_controller 的 --article-only 标志实际未实现,此处调用与完整 repurpose 等价
        sys.path.insert(0, WORKDIR)
        from workflow_controller import SelfMediaController
        controller = SelfMediaController()

        print(f"[DEBUG] Executing repurpose (article mode) using direct call", flush=True)
        process_start = time.time()

        controller.run_repurpose(None)

        process_duration = time.time() - process_start
        print(f"[DEBUG] Repurpose completed in {process_duration:.2f}s", flush=True)

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        title = state.get('topic_context', {}).get('title', '内容')
        script_file = state.get('video_script', '')
        article_file = state.get('draft_file', '')

        article_full = ""
        if article_file and os.path.exists(article_file):
            try:
                with open(article_file, 'r', encoding='utf-8') as f:
                    raw = f.read()
                raw = re.sub(r'^#+\s*', '', raw, flags=re.MULTILINE)
                article_full = raw.strip()
            except Exception:
                pass
        if not article_full:
            article_full = "(未生成文章)"


        script_full = ""
        if script_file and os.path.exists(script_file):
            try:
                with open(script_file, 'r', encoding='utf-8') as f:
                    script_full = f.read().strip()
            except Exception:
                pass
        if not script_full:
            script_full = "(未生成脚本)"

        self.send_text(token, "✨ 文章已重新生成,请审核新版本...")

        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"🎬 短视频脚本 | {title}",
            content=script_full, tags="脚本(未变)",
            review_id="script_01", template="orange", header_title="🎬 脚本审核"
        ))
        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"📖 深度长文 | {title}",
            content=article_full, tags="文章(已重写)",
            review_id="article_01", template="blue", header_title="📖 文章审核(新版)"
        ))

    def run_approve_and_track(self, token, action_value):
        logger.info("[APPROVE] Processing approval: action_value=%s", action_value)
        """Handle approve button - track approvals, trigger visuals when both approved."""
        parts = action_value.split('_', 1)
        if len(parts) < 2:
            self.send_text(token, "⚠️ 无法识别通过目标")
            return

        target = parts[1]
        if target.startswith('script_'):
            kind = "🎬 脚本"
            flag_key = "script_approved"
        elif target.startswith('article_'):
            kind = "📖 文章"
            flag_key = "article_approved"
        else:
            self.send_text(token, "⚠️ 未知通过目标")
            return

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        generate_script = os.getenv("GENERATE_VIDEO_SCRIPT", "FALSE").upper() == "TRUE"

        # 检查视觉工程是否真正在运行中(防止重复点击)
        # 注意:必须用 is_generating_cover 判断,不能用 *_approved 标志判断
        # 因为 *_approved 只表示用户点过通过,不代表当前有进程在跑
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            current_state = json.load(f)

        if current_state.get('is_generating_cover', False):
            print("[DEBUG] Visual generation already in progress, skipping duplicate click", flush=True)
            self.send_text(token, "⏳ 视觉工程已在运行中,请稍候...")
            return

        state[flag_key] = True
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        # 检查是否两个都已完成
        all_approved = False
        if generate_script:
            if state.get('script_approved') and state.get('article_approved'):
                all_approved = True
        else:
            if state.get('article_approved'):
                all_approved = True

        if all_approved:
            msg = "🎉 脚本 + 文章均已审核完成!\n\n🎨 正在启动视觉工程:分析内容、生成封面图与文章插图...\n\n(预计 1-2 分钟,请稍候)" if generate_script else "🎉 文章已审核完成!\n\n🎨 正在启动视觉工程:分析内容、生成封面图与文章插图...\n\n(预计 1-2 分钟,请稍候)"
            self.send_text(token, msg)
            time.sleep(1)
            state['script_approved'] = False
            state['article_approved'] = False
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            self.run_final_and_send_card(token)
        else:
            rem = "还剩 1 项确认后将自动进入视觉工程阶段。" if generate_script else ""
            self.send_text(token, f"✅ 【{kind}】已确认通过。\n\n{rem}")

    def run_final_and_send_card(self, token, model='seedream'):
        """Generate visuals and send final publish card."""
        import re  # Import at function top to avoid conditional import issues
        try:
            # Mutex guard
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                guard_state = json.load(f)
            if guard_state.get('is_generating_cover', False):
                print("[DEBUG] Visual generation already in progress, skipping", flush=True)
                self.send_text(token, "⏳ 封面图正在生成中,请稍候...")
                return
            guard_state['is_generating_cover'] = True
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(guard_state, f, ensure_ascii=False, indent=2)

            self.send_text(token, "🖼️ 正在生成封面图,请稍候...")

            os.chdir(WORKDIR)
            cmd = ['python', 'workflow_controller.py', 'visuals', '--model', model]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1
            )

            img_count = 0
            any_image_generated = False
            for line in proc.stdout:
                clean_line = line.strip()
                if not clean_line:
                    continue
                print(f"[visuals] {clean_line}", flush=True)

                if "[FEISHU_PREVIEW]" in clean_line:
                    try:
                        if "PATH=" in clean_line:
                            raw_path = clean_line.split("PATH=")[1].strip()
                            if " [FEISHU" in raw_path:
                                raw_path = raw_path.split(" [FEISHU")[0].strip()
                            clean_path = raw_path.replace('"', '').replace("'", "")

                            if not os.path.isabs(clean_path):
                                if "assets" in clean_path:
                                    as_idx = clean_path.find("assets")
                                    clean_path = os.path.join(WORKDIR, clean_path[as_idx:])
                                else:
                                    clean_path = os.path.join(WORKDIR, clean_path)

                            clean_path = os.path.normpath(clean_path)

                            if os.path.exists(clean_path):
                                img_count += 1
                                any_image_generated = True
                                if "TYPE=COVER" in clean_line:
                                    self.send_image_preview(token, clean_path, "🖼️ 封面图已就绪")
                                elif "TYPE=ILLUS" in clean_line:
                                    m = re.search(r'INDEX=(\d+)', clean_line)
                                    idx = m.group(1) if m else "?"
                                    self.send_image_preview(token, clean_path, f"🖼️ 插图 {idx} 已就绪")
                                else:
                                    self.send_image_preview(token, clean_path, "🖼️ 图片已就绪")
                    except Exception as pe:
                        print(f"[DEBUG] ❌ 协议解析捕获异常: {pe}", flush=True)

                elif "[FEISHU_STATUS]" in clean_line:
                    try:
                        status_msg = clean_line.split("FEISHU_STATUS]")[-1].strip().replace('"', '').replace("'", "")
                        if "ERR=" in status_msg or "WARN=" in status_msg:
                            self.send_text(token, f"🔔 {status_msg}")
                    except: pass

            proc.wait()

            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            title = state.get('topic_context', {}).get('title', '内容')
            draft_file = state.get('draft_file', '')
            cover_path = state.get('cover_image', '')

            content = ""
            if draft_file and os.path.exists(draft_file):
                with open(draft_file, 'r', encoding='utf-8') as f:
                    raw = f.read()
                raw = re.sub(r'^#+\s*', '', raw, flags=re.MULTILINE)
                content = raw.strip()

            if not any_image_generated:
                print("[WARN] No images generated this run (SafeSearch or API error), skipping to final card", flush=True)
                self.send_text(token, "⚠️ 封面图生成失败(API欠费或风控),跳过视觉工程,直接进入最终稿...")
                # Reset guard flag so user can retry later
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        cleanup = json.load(f)
                    cleanup['is_generating_cover'] = False
                    self.save_state(cleanup)
                except Exception: pass

            # 2. Upload images to Feishu (Cover + Illustrations)
            image_key = ""
            if cover_path and os.path.exists(cover_path):
                image_key = self.upload_to_feishu(cover_path)

            article_image_keys = []
            article_images = state.get('article_images', [])
            if article_images:
                self.send_text(token, f"📤 正在上传 {len(article_images)} 张插图到预览...")
                for p in article_images:
                    if os.path.exists(p):
                        key = self.upload_to_feishu(p)
                        if key: article_image_keys.append(key)

            # 3. Build and send final card
            deai_notes = state.get('deai_notes', None)
            card = self.build_final_card(image_key, title, content, "AI|迭代|成长", "final_01", article_image_keys, deai_notes=deai_notes)
            self.send_card(token, card)

            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                cleanup = json.load(f)
            cleanup['is_generating_cover'] = False
            # 重置审核标志,允许下一轮审核流程正常进行
            cleanup['script_approved'] = False
            cleanup['article_approved'] = False
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cleanup, f, ensure_ascii=False, indent=2)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_text(token, f"⚠️ 生成最终稿失败: {str(e)[:100]}")
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    cleanup = json.load(f)
                cleanup['is_generating_cover'] = False
                # 重置审核标志,允许下一轮审核流程正常进行
                cleanup['script_approved'] = False
                cleanup['article_approved'] = False
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cleanup, f, ensure_ascii=False, indent=2)
            except:
                pass

    def upload_to_feishu(self, path):
        """Helper to upload image to Feishu and return image_key."""
        try:
            token_data = json.loads(subprocess.run([
                'curl', '-s', '-X', 'POST',
                'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                '-H', 'Content-Type: application/json',
                '-d', json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET})
            ], capture_output=True, text=True).stdout)
            feishu_token = token_data.get("tenant_access_token", "")

            upload_result = subprocess.run([
                'curl', '-s', '-X', 'POST',
                'https://open.feishu.cn/open-apis/im/v1/images',
                '-H', f'Authorization: Bearer {feishu_token}',
                '-F', 'image_type=message',
                '-F', f'image=@{path}'
            ], capture_output=True, text=True).stdout
            upload_data = json.loads(upload_result)
            return upload_data.get("data", {}).get("image_key", "")
        except Exception as e:
            print(f"[WARN] Upload failed for {path}: {e}", flush=True)
            return ""

    def build_final_card(self, image_key, title, content, tags, review_id, article_image_keys=None, deai_notes=None):
        """Build final publish card with cover and multiple illustrations.
        
        Args:
            deai_notes: Optional[str], 祛AI味处理改动说明，如不传则不显示该区块
        """
        elements = []

        # Cover
        if image_key:
            elements.append({"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "封面图"}})

        content_clean = re.sub(r'^#+\s*', '', content, flags=re.MULTILINE).strip() if content else ""

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🔥 标题：** {title}"}
        })

        if content_clean:
            main_text = content_clean[:2000] + ("..." if len(content_clean) > 2000 else "")
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": main_text}})

        # 🎨 插图预览已通过"成一张发一张"模式独立发出，最终稿保持简洁
        if article_image_keys:
            elements.append({"tag": "hr"})
            elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"🖼️ 文章包含 {len(article_image_keys)} 张专业配图，已插入相应段落"}]})

        # 🔍 祛 AI 味说明区块（Natural Chinese Protocol 处理结果）
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

    def run_post(self, token):
        """Trigger post workflow using API mode (no browser)."""
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            draft_file = state.get('draft_file')
            if not draft_file:
                self.send_text(token, "⚠️ 未找到可发布的草稿,请先完成改写流程")
                return
            if not os.path.exists(draft_file):
                self.send_text(token, f"⚠️ 草稿文件不存在: {draft_file}\n请重新执行改写流程")
                return

            self.send_text(token, "🚀 正在启动 API 模式批量发布,请稍候...")

            os.chdir(WORKDIR)
            sys.path.insert(0, WORKDIR)
            from workflow_controller import SelfMediaController
            controller = SelfMediaController()

            ok = controller.run_post(method="api")
            if ok:
                self.send_text(token, "🎉 发布完成!请前往公众号后台确认草稿")
            else:
                # 读取最新一篇发布日志文件,发给用户看具体错误
                import glob as _glob
                log_dir = os.path.join(WORKDIR, 'logs')
                logs = sorted(_glob.glob(os.path.join(log_dir, 'post_*.log')), key=os.path.getmtime, reverse=True)
                err_detail = ""
                if logs:
                    try:
                        with open(logs[0], 'r', encoding='utf-8') as f:
                            content = f.read()
                        err_detail = "\n💡 错误详情:\n" + content[-800:]
                    except Exception:
                        pass
                self.send_text(token, f"⚠️ 发布失败{err_detail}\n如问题持续请检查公众号后台IP白名单设置")
        except Exception as e:
            self.send_text(token, f"⚠️ 发布失败: {str(e)[:100]}")

    def send_copy_guide(self, token):
        logger.debug("[COPY] Sending copy guide")
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            draft_file = state.get('draft_file', '')
            content = ""
            if draft_file and os.path.exists(draft_file):
                with open(draft_file, 'r', encoding='utf-8') as f:
                    raw = f.read()
                content = re.sub(r'^#+\s*', '', raw, flags=re.MULTILINE).strip()
        except:
            content = ""

        self.send_text(token, f"📋 以下是可复制文案:\n\n{content[:4000]}")


def main():
    import os
    import sys
    import atexit
    import subprocess
    import time
    logger.info("[SERVER] Starting Feishu card server (PID: %d)", os.getpid())

    # 1. 强力互斥并支持"新陈代谢":启动新实例时,自动杀掉旧实例
    lock_file = ".feishu_server_lock"

    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                old_pid = f.read().strip()
            if old_pid and old_pid != str(os.getpid()):
                print(f"\n[🔄 自动重启] 发现旧卡服务器正在运行 (PID: {old_pid})。", flush=True)
                print(f"正在尝试关闭旧实例并更新代码...", flush=True)
                # 使用 taskkill 强制杀掉旧进程 (Windows 兼容)
                subprocess.run(["taskkill", "/F", "/PID", old_pid], capture_output=True)
                time.sleep(0.5) # 等待释放
        except Exception as e:
            print(f"[WARN] 清理旧实例失败: {e}", flush=True)

        # 无论如何尝试删除旧锁,为新启动腾位子
        try: os.remove(lock_file)
        except: pass

    try:
        # 创建新的锁文件
        fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)

        # 注册退出清理逻辑
        def cleanup_lock():
            if os.path.exists(lock_file):
                try: os.remove(lock_file)
                except: pass
        atexit.register(cleanup_lock)

    except FileExistsError:
        # 万一极短时间内有竞争,提示一下
        print(f"\n[⚠️  启动受阻] 系统极短时间内有两次启动请求,请稍后重试。")
        sys.exit(1)

    # 2. 端口启动 (固定 18799)
    port = 18799
    try:
        server = HTTPServer(('127.0.0.1', port), FeishuHandler)
        print(f"\n✨ 飞书卡片服务器已就绪 (PID: {os.getpid()})")
        print(f"监听地址: http://127.0.0.1:{port}")
        print(f"Webhook入口: /feishu/callback | 触发入口: /trigger\n")
        server.serve_forever()
    except OSError as e:
        if e.errno == 98 or e.errno == 10048:
            print(f"\n[❌ 端口占用] {port} 仍然被占用。")
            print(f"请手动运行: taskkill /F /IM python.exe 清理。\n")
        else:
            print(f"[ERROR] 启动失败: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(lock_file):
            try: os.remove(lock_file)
            except: pass


if __name__ == '__main__':
    main()

