#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Feishu Card Server - Handles card button events and sends interactive cards."""

import json
import subprocess
import urllib.request
import urllib.error
import os
import re
import time
import threading
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
import uuid
import queue
import sys
from dotenv import load_dotenv
load_dotenv() # 🎯 加载本地环境变量，确保 OpenAI/DeepSeek API Key 可用

# 全局组件
TOPIC_MAP = {}
PROCESSED_ACTIONS = {}  # 全局请求去重锁
TOKEN_CACHE = {"token": "", "expire": 0} # 🎯 Token 缓存
MESSAGE_QUEUE = queue.Queue() # 🎯 异步消息队列，实现 UI 秒回

# Feishu App Config (from environment variables with fallback)
APP_ID = os.getenv("FEISHU_APP_ID", "cli_a930dedc42789cd1")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "WOjERqoJ8OhIwIthMS3NAcJAxFDvXK2X")
DEFAULT_RECEIVE_ID = os.getenv("FEISHU_RECEIVE_ID", "ou_2da8e0f846c19c8fabebd6c6d82a8d6d")
WORKDIR = os.getenv("FEISHU_WORKDIR", r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto")
STATE_FILE = WORKDIR + r"/.workflow_state.json"


# ===== Global Messaging Engine (Async) =====

def get_global_token():
    """Shared token fetcher for all threads."""
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
                print(f"[AUTH] Global token updated. Expires in {data.get('expire')}s", flush=True)
                return token
    except Exception as e:
        print(f"[ERROR] get_global_token failed: {e}", flush=True)
    return ""

def message_sender_worker():
    """Clean, independent worker thread without class/self dependencies."""
    print("[DEBUG] Independent message sender worker started.", flush=True)
    while True:
        try:
            msg = MESSAGE_QUEUE.get()
            token = get_global_token()
            if not token: 
                print("[ERROR] Sender worker: Failed to get token", flush=True)
                MESSAGE_QUEUE.task_done()
                continue
            
            print(f"[ASYNC_SEND] Sending {msg['type']} to {DEFAULT_RECEIVE_ID}...", flush=True)
            payload = {
                "receive_id": DEFAULT_RECEIVE_ID,
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
                    print(f"[ERROR] Feishu API send failed: {resp_data.get('msg')}", flush=True)
                else:
                    print(f"[ASYNC_DONE] Successfully sent {msg['type']}", flush=True)
            
            MESSAGE_QUEUE.task_done()
        except Exception as e:
            print(f"[ERROR] Sender worker failed: {e}", flush=True)
            time.sleep(1)

# ==========================================

class FeishuHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Suppress all logs

    # ===== HTTP Routes =====

    def do_GET(self):
        import urllib.parse
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
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Standard Feishu Webhook handler - returns 200 FAST and processes async."""
        if self.path != "/feishu/callback":
            self.send_response(404); self.end_headers(); return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        # print(f"[DEBUG] Webhook Body: {body[:300]}...", flush=True)

        # 🔑 飞书 Webhook 验证（url_verification）：必须返回 challenge
        try:
            body_data = json.loads(body)
            if body_data.get('type') == 'url_verification' and body_data.get('challenge'):
                challenge = body_data.get('challenge')
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"challenge": challenge}).encode('utf-8'))
                print(f"[VERIFY] Webhook verification passed, challenge returned: {challenge[:20]}...", flush=True)
                return
        except Exception as e:
            print(f"[WARN] Failed to parse body for verification: {e}", flush=True)

        # 🎯 极其重要：立即响应 200 OK，防止飞书认为超时并重试 (报错 200671)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"code": 0, "msg": "success"}).encode('utf-8'))
        
        # 将解析和逻辑放在子线程运行，不再阻塞 HTTP 连接
        try:
            data = json.loads(body)
            # print(f"[DEBUG] Parsed data type: {data.get('type')}", flush=True)
            threading.Thread(target=self.async_action_processor, args=(data,)).start()
        except Exception as e:
            print(f"[ERROR] Body parse failed: {e}", flush=True)

    def async_action_processor(self, data):
        """Background worker with deduplication logic."""
        try:
            # 1. Verification handled by do_POST if needed, but here we focus on actions
            if data.get('type') == 'url_verification' or data.get('challenge'):
                return

            event = data.get('event', {})
            message = event.get('message', {})
            content_str = message.get('content', '{}')
            try: content = json.loads(content_str)
            except: content = {}

            # 提取 action_value
            action_value = None
            actions = content.get('actions', [])
            for act in actions:
                if act.get('tag') == 'button' and act.get('value'):
                    action_value = act.get('value'); break
            if not action_value:
                for el in content.get('elements', []):
                    if el.get('tag') == 'action':
                        for act in el.get('actions', []):
                            if act.get('tag') == 'button' and act.get('value'):
                                action_value = act.get('value'); break
            if not action_value:
                action_value = event.get('action', {}).get('value')

            if not action_value:
                return

            # 🎯 极其重要：动态提取用户的 OpenID，确保消息发回给点按钮的人，而不是老旧的写死 ID
            operator_obj = event.get('operator', {})
            open_id = operator_obj.get('open_id') or event.get('user', {}).get('open_id')
            
            if open_id:
                global DEFAULT_RECEIVE_ID
                if DEFAULT_RECEIVE_ID != open_id:
                    print(f"[AUTH] Switching message target to user: {open_id}", flush=True)
                    DEFAULT_RECEIVE_ID = open_id

            # 2. 去重校验：10秒内只跑一次
            import time
            now = time.time()
            if action_value in PROCESSED_ACTIONS and now - PROCESSED_ACTIONS[action_value] < 10:
                print(f"[ASYNC_SKIP] Ignoring duplicate: {action_value}", flush=True)
                return
            
            PROCESSED_ACTIONS[action_value] = now
            print(f"[ASYNC_ACTION] Processing: {action_value}", flush=True)
            
            # 3. 真正耗时的逻辑开始
            self.handle_card_action(action_value)
            
        except Exception as e:
            print(f"[ERROR] async_action_processor failed: {e}", flush=True)

    # ===== Feishu API =====

    def get_token(self):
        """Bridge to global token engine."""
        return get_global_token()

    def send_text(self, token, text):
        """Queue text message for async delivery (super fast UI)."""
        MESSAGE_QUEUE.put({"type": "text", "content": text})
        return True

    def send_card(self, token, card):
        """Queue card for async delivery."""
        MESSAGE_QUEUE.put({"type": "card", "content": card})
        return True

    def update_topic_context_by_id(self, token, topic_id):
        """Update workflow state with selected topic using global index in last_candidates."""
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            topic_id_str = str(topic_id).strip()
            candidates = state.get("last_candidates", []) or []

            # Use global index into last_candidates (stable, not dependent on in-memory guid)
            numeric_id = None
            try:
                raw_id = topic_id_str.split("_")[-1]
                numeric_id = int(raw_id)
            except ValueError:
                pass

            updated = False
            if numeric_id is not None and 0 <= numeric_id < len(candidates):
                selected = candidates[numeric_id]
                state["topic_context"] = {
                    "id": selected.get("id", ""),
                    "title": selected.get("title", ""),
                    "source": selected.get("source", ""),
                    "author": selected.get("author", ""),
                    "score": selected.get("score", "")
                }
                updated = True
                print(f"[DEBUG] Updated topic_context via global index {numeric_id}: {selected.get('title', '')[:50]}", flush=True)
            elif topic_id_str.startswith("http"):
                state["topic_context"] = {
                    "id": topic_id_str,
                    "title": topic_id_str.split("?")[0][-30:],
                    "source": "custom",
                    "author": ""
                }
                updated = True
                print(f"[DEBUG] Updated topic_context to URL: {topic_id_str[:50]}", flush=True)
            else:
                print(f"[DEBUG] Topic index {numeric_id} out of range (0-{len(candidates)-1}), keeping existing", flush=True)

            if updated:
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                self.send_response_ok()
            else:
                self.send_response(400, "Topic not found")
        except Exception as e:
            print(f"[ERROR] update_topic_context_by_id failed: {e}", flush=True)
            import traceback
            traceback.print_exc()

    # ===== Card Action Router =====

    def handle_card_action(self, action_value):
        """Route card button actions to appropriate handlers."""
        try:
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
                    import re
                    # Clean up escaped characters first
                    clean_val = action_value.replace('\\"', '"').replace('\\\\', '\\')
                    # Try to parse as JSON
                    parsed = json.loads(clean_val)
                    if isinstance(parsed, dict):
                        raw_action = parsed.get('action', '')
                        raw_id = str(parsed.get('id', '')) if parsed.get('id') is not None else ''
                        # Always use raw_action + raw_id format, e.g. "insight_topic_1"
                        if raw_id:
                            action_value = f"{raw_action}_{raw_id}"
                        else:
                            action_value = raw_action
                        print(f"[DEBUG] Parsed JSON action_value: {action_value}", flush=True)
                        # Skip the regex path below
                        parts = action_value.split('_', 1)
                        action_type = parts[0] if parts else 'unknown'
                        topic_id = parts[1] if len(parts) > 1 else None
                        if action_type == 'insight':
                            if topic_id:
                                self.update_topic_context_by_id(token, topic_id)
                            threading.Thread(target=self.run_insight_and_send_card, args=(token, action_value)).start()
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"code": 0, "msg": "success"}).encode('utf-8'))
                            return
                        # ... handle other types similarly or fall through
                except Exception as e:
                    print(f"[WARN] JSON parse failed: {e}", flush=True)
                    # Fall through to regex-based parsing

            # Robust splitting: handle cases where action_value might still have leftover quotes or escapes
            if isinstance(action_value, str):
                action_value = action_value.replace('"', '').replace('\\', '').strip()

            parts = action_value.split('_', 1)
            action_type = parts[0] if parts else 'unknown'

            if action_type == 'next':
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token, 'next')).start()
            elif action_type == 'insight':
                topic_id = parts[1] if len(parts) > 1 else None
                if topic_id:
                    self.update_topic_context_by_id(token, topic_id)
                threading.Thread(target=self.send_text, args=(token, "🔍 正在进行深度解读，请稍候... (预计 20-40 秒)")).start()
                threading.Thread(target=self.run_insight_and_send_card, args=(token, action_value)).start()
            elif action_type == 'skip':
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token, 'next')).start()
            elif action_type == 'refresh':
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token, 'refresh')).start()
            elif action_type == 'init':
                threading.Thread(target=self.run_init_and_send_card, args=(token,)).start()
            elif action_type == 'rewrite':
                threading.Thread(target=self.send_text, args=(token, "📝 正在为您进行 IP 化改写，请稍候... (预计 1-2 分钟)")).start()
                threading.Thread(target=self.run_repurpose_and_send_card, args=(token, action_value)).start()
            elif action_type == 'approve':
                threading.Thread(target=self.run_approve_and_track, args=(token, action_value)).start()
            elif action_type == 'modify':
                threading.Thread(target=self.send_text, args=(token, "⚙️ 正在为您应用修改建议，请稍候...")).start()
                threading.Thread(target=self.run_modify_and_send_card, args=(token, action_value)).start()
            elif action_type == 'rescript':
                threading.Thread(target=self.send_text, args=(token, "🔄 正在为您重新生成视频脚本...")).start()
                threading.Thread(target=self.run_rescript_and_send_card, args=(token, action_value)).start()
            elif action_type == 'rearticle':
                threading.Thread(target=self.send_text, args=(token, "🔄 正在为您重新生成深度文章...")).start()
                threading.Thread(target=self.run_rearticle_and_send_card, args=(token, action_value)).start()
            elif action_type.startswith('post'):
                threading.Thread(target=self.send_text, args=(token, "🚀 正在为您推送到公众号草稿箱...")).start()
                threading.Thread(target=self.run_post, args=(token,)).start()
                return
            elif action_type == 'revisuals':
                # 🎯 提供强力手动重置：用户点击该按钮即可强制清除生成锁
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    state['is_generating_cover'] = False
                    with open(STATE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)
                except: pass
                threading.Thread(target=self.run_final_and_send_card, args=(token,)).start()
            elif action_type == 'copy':
                self.send_copy_guide(token)
            else:
                self.send_text(token, f"收到未知操作: {action_type}，请直接告诉我您想做什么")
        except Exception as e:
            print(f"[ERROR] handle_card_action failed: {e}", flush=True)
            import traceback
            traceback.print_exc()

    # ===== Action Handlers =====

    def run_init_and_send_card(self, token):
        """Send initialization guide card."""
        try:
            print("[DEBUG] run_init_and_send_card starting", flush=True)
            init_text = (
                "🔔 **IP 爆款制造机 - 初始化**\n\n"
                "请告诉我以下信息来完成配置：\n\n"
                "**1️⃣ IP 名称**\n"
                "您想用哪个名字作为内容品牌？（例如：胡老板、科技君）\n\n"
                "**2️⃣ 行业赛道**\n"
                "请从以下 45 个行业中选择您的定位：\n\n"
                "1.小绿书 2.育儿 3.科技 4.体育健身 5.财经\n"
                "6.美食 7.医疗 8.娱乐 9.情感 10.历史\n"
                "11.军事国际 12.美妆时尚 13.文化 14.汽车 15.游戏\n"
                "16.旅游 17.房产 18.健康养生 19.职场 20.摄影\n"
                "21.资讯热点 22.教育 23.开发者 24.影视 25.美妆\n"
                "26.生活 27.数码 28.媒体 29.宠物 30.三农\n"
                "31.星座命理 32.搞笑 33.动漫 34.家居 35.科学\n"
                "36.商业营销 37.个人成长 38.壁纸头像 39.法律 40.民生\n"
                "41.文案 42.体制 43.文摘 44.AI 45.其它\n\n"
                "请直接回复，例如：\n"
                "IP名称：胡老板\n"
                "行业：4"
            )
            self.send_text(token, init_text)
        except Exception as e:
            print(f"[ERROR] run_init_and_send_card failed: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def run_discovery_and_send_cards(self, token, action_value='discovery'):
        """Run discovery or next, and send topic aggregated card."""
        try:
            print(f"[DEBUG] run_discovery_and_send_cards starting, action={action_value}", flush=True)
            os.chdir(WORKDIR)

            if action_value == 'next':
                cmd = ['python', 'workflow_controller.py', 'next']
            elif action_value == 'refresh':
                # 读取 last_id 用于分页请求
                refresh_last_id = None
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        st = json.load(f)
                    refresh_last_id = st.get('last_id')
                    if refresh_last_id:
                        print(f"[DEBUG] [refresh] found last_id in state: {refresh_last_id}", flush=True)
                except Exception as e:
                    print(f"[WARN] [refresh] failed to read last_id from state: {e}", flush=True)
                if refresh_last_id:
                    cmd = ['python', 'workflow_controller.py', 'discovery', '--refresh', '--last-id', refresh_last_id]
                else:
                    cmd = ['python', 'workflow_controller.py', 'discovery', '--refresh']
            else:
                cmd = ['python', 'workflow_controller.py', 'discovery']

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            output = result.stdout
            print(f"[DEBUG] command output length: {len(output)}", flush=True)

            topics = self.parse_discovery_output(output)
            print(f"[DEBUG] parsed topics count: {len(topics)}", flush=True)

            # === FIX: For 'next' action, always read from state file as source of truth ===
            # stdout parsing can fail; state file is always correct
            if action_value == 'next':
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    state_candidates = state.get('last_candidates', [])
                    page_idx = state.get('candidates_page_index', 0)
                    page_size = state.get('candidates_page_size', 5)
                    total = len(state_candidates)
                    start = page_idx * page_size
                    end = start + page_size
                    topics = state_candidates[start:end]
                    print(f"[DEBUG] [next] read from state: page_idx={page_idx}, showing topics {start+1}-{min(end, total)} of {total}", flush=True)
                    if not topics:
                        # all consumed, do a refresh - re-read state AFTER discovery ran
                        action_value = 'refresh'
                        print(f"[DEBUG] [next] all candidates consumed, triggering refresh", flush=True)
                        # Re-read state file (discovery with last_id already ran and saved new candidates)
                        try:
                            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                                state_after = json.load(f)
                            state_candidates = state_after.get('last_candidates', [])
                            page_idx = state_after.get('candidates_page_index', 0)
                            page_size = state_after.get('candidates_page_size', 5)
                            total = len(state_candidates)
                            start = page_idx * page_size
                            end = start + page_size
                            topics = state_candidates[start:end]
                            print(f"[DEBUG] [next] after refresh: page_idx={page_idx}, showing topics {start+1}-{min(end, total)} of {total}", flush=True)
                        except Exception as e:
                            print(f"[WARN] [next] failed to re-read state after refresh: {e}", flush=True)
                            topics = []
                except Exception as e:
                    print(f"[WARN] [next] failed to read state: {e}, falling back to discovery", flush=True)
                    topics = []
                    action_value = 'refresh'

            if topics:
                # Save candidates to state file only if it's a fresh discovery
                use_refresh = (action_value == 'refresh')
                if use_refresh:
                    try:
                        with open(STATE_FILE, 'r', encoding='utf-8') as f:
                            state = json.load(f)
                        state['last_candidates'] = topics
                        state['candidates_page_index'] = 1
                        state['candidates_page_size'] = 5
                        with open(STATE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(state, f, ensure_ascii=False, indent=2)
                        print(f"[DEBUG] Saved {len(topics)} fresh candidates to state", flush=True)
                    except Exception as e:
                        print(f"[WARN] Failed to save candidates to state: {e}", flush=True)

                # ALWAYS send as batch card (pass page_offset so buttons use global index)
                page_offset = 0
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        s = json.load(f)
                    page_idx = s.get('candidates_page_index', 0)
                    page_size = s.get('candidates_page_size', 5)
                    # candidates_page_index: 0=showing page1 after fresh discovery, 1=showing page2 after first next, etc.
                    page_offset = page_idx * page_size
                except Exception:
                    page_offset = 0
                batch_card = self.build_topic_list_card(topics, "AI", page_offset)
                self.send_card(token, batch_card)
            else:
                print(f"[DEBUG] No topics parsed, output preview: {output[:500]}", flush=True)
                self.send_text(token, "⚠️ 获取选题失败，请稍后重试或手动发'选题'获取")
        except Exception as e:
            print(f"[ERROR] run_discovery_and_send_cards failed: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.send_text(token, f"⚠️ 操作失败: {str(e)[:100]}")

    def parse_discovery_output(self, output):
        """Parse topic data from workflow output.
        Prioritizes structured JSON if available, falls back to re parsing.
        """
        topics = []
        
        # 🎯 优先解析结构化 JSON，这是 100% 准确的
        json_match = re.search(r'\[DATA_JSON\]:\s*(\[.*\])', output)
        if json_match:
            try:
                json_data = json.loads(json_match.group(1))
                print(f"[DEBUG] Successfully parsed {len(json_data)} topics from RAW JSON", flush=True)
                for item in json_data:
                    # 确保字段齐备
                    guid = item.get('guid', str(uuid.uuid4())[:8])
                    item['guid'] = guid
                    # 处理显示用的 data 字符串
                    read_str = str(item.get('comments', '0'))
                    like_str = str(item.get('likes', '0'))
                    heat_str = str(item.get('score', '0'))
                    item['data'] = f"阅读: {read_str} | 赞: {like_str} | 热度: {heat_str}"
                    # 注册到全局映射
                    TOPIC_MAP[guid] = item
                    topics.append(item)
                return topics
            except Exception as e:
                print(f"[WARN] Failed to parse DATA_JSON: {e}", flush=True)

        # 降级方案：旧的正则表达式解析（逐行扫描）
        lines = output.split('\n')
        current_topic = None
        for line in lines:
            topic_match = re.match(r'^\d+\.\s*\[([^\]]*)\]\s*\[(.+?)\]\((https?://[^\)]+)\)', line)
            if topic_match:
                source = topic_match.group(1).strip(); title = topic_match.group(2).strip(); url = topic_match.group(3).strip()
                current_topic = {'id': url, 'title': title, 'source': source, 'author': '', 'score': '', 'data': '', 'analysis': '爆款选题'}
                continue

            if current_topic:
                author_match = re.search(r'👤\s*([^\s|]+)', line)
                if author_match and not current_topic.get('author'): current_topic['author'] = author_match.group(1).strip()
                read_match = re.search(r'阅读[:\s]*([\d万+]+)', line); like_match = re.search(r'赞[赞:\s]*([\d万+]+)', line); heat_match = re.search(r'热度[:\s]*([\d万+]+)', line)
                data_parts = []; score_val = 0
                if read_match:
                    val = read_match.group(1); data_parts.append(f"阅读: {val}")
                    try: score_val += int(val.replace('万', '')) * 10000 if '万' in val else int(val)
                    except: pass
                if like_match:
                    val = like_match.group(1); data_parts.append(f"赞: {val}")
                    try: score_val += int(val.replace('万', '')) * 1000 if '万' in val else int(val)
                    except: pass
                if heat_match:
                    val = heat_match.group(1); data_parts.append(f"热度: {val}")
                    try: score_val += int(val.replace('万', '')) * 100 if '万' in val else int(val)
                    except: pass

                if data_parts:
                    current_topic['data'] = ' | '.join(data_parts); current_topic['score'] = str(score_val)
                    guid = str(uuid.uuid4())[:8]; current_topic['guid'] = guid; TOPIC_MAP[guid] = current_topic
                    topics.append(current_topic); current_topic = None
        return topics

    def build_topic_card(self, title, data_str, url, analysis, topic_id):
        """Build single topic selection card."""
        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": "🔥 新一期选题推送"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 选题：** {title}\n\n**📊 数据：** {data_str}\n\n**🔗 原文：** {url}\n\n**💡 爆点：** {analysis}"}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"ID: {topic_id}"}]},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "🔍 解读此选题"}, "type": "primary", "value": f"insight_{topic_id}"},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "🔄 换一批"}, "type": "default", "value": "next"}
                ]}
            ]
        }

    def build_topic_list_card(self, topics, industry="AI", page_offset=0):
        """Build batch topic card (all topics in one card).
        topics: list of dicts with keys: id(str), title, data, url, analysis, source, author, score
        """
        elements = []
        elements.append({"tag": "markdown", "content": f"**🔥 {industry}赛道 · 今日爆款选题 TOP {len(topics)}**"})
        elements.append({"tag": "hr"})

        for i, t in enumerate(topics):
            # 序号用 i+1（纯数字）
            topic_num = i + 1
            
            # 提取干净的标题和 URL
            title = str(t.get('title', '未知选题')).strip()
            topic_url = t.get('url', '') or t.get('id', '')

            # 防御性：如果标题看起来像 URL，尝试使用 data 或截断
            if title.startswith('http'):
                title = f"选题 {topic_num}"

            # 使用 base64(url) 作为按钮值，URL 唯一且稳定，彻底避免 index/guid 混淆
            import base64
            button_id = base64.b64encode(topic_url.encode('utf-8')).decode('utf-8')
            display_num = i + 1  # 1-indexed for display

            elements.append({
                "tag": "markdown",
                "content": f"**🔥 [{display_num}] {title}**\n📊 {t.get('data', '')}\n💡 {t.get('analysis', '爆款选题')}\n🔗 [原文链接]({topic_url})"
            })
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": f"🔍 解读选题 {display_num}"},
                    "type": "primary",
                    "value": f"insight_{button_id}"
                }]
            })
            if i < len(topics) - 1:
                elements.append({"tag": "hr"})

        # Bottom action buttons (with descriptions)
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "action",
            "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "📋 换一批（查看更多爆款选题）"}, "type": "default", "value": "next"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 初始化（重置IP名称/行业赛道）"}, "type": "default", "value": "init"}
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

    def run_insight_and_send_card(self, token, action_value):
        """Analyze topic and send rewrite confirm card."""
        try:
            print("[DEBUG] run_insight_and_send_card starting", flush=True)
            os.chdir(WORKDIR)

            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # FIX: Extract topic URL from action_value and look up the correct topic
            # Button value format: insight_{base64_url} or insight_{guid} (backward compat)
            topic_id_str = action_value.split('_', 1)[1] if '_' in action_value else 'new'
            candidates = state.get('last_candidates', [])
            selected_topic = None

            # Try URL lookup first (primary method after fix)
            import base64
            try:
                decoded_url = base64.b64decode(topic_id_str.encode('utf-8')).decode('utf-8')
                for c in candidates:
                    if c.get('id') == decoded_url or c.get('url') == decoded_url:
                        selected_topic = c
                        print(f"[DEBUG] [insight] matched by URL: {decoded_url[:50]}...", flush=True)
                        break
            except Exception:
                pass

            # Fallback: try guid lookup
            if not selected_topic:
                for c in candidates:
                    if c.get('guid') == topic_id_str:
                        selected_topic = c
                        print(f"[DEBUG] [insight] matched by guid: {topic_id_str}", flush=True)
                        break

            # Last fallback: topic_context
            if not selected_topic:
                print(f"[WARN] [insight] no match for '{topic_id_str}', falling back to topic_context", flush=True)
                selected_topic = state.get('topic_context', {})

            title = selected_topic.get('title', '未知选题')
            url = selected_topic.get('id', '') or selected_topic.get('url', '')
            author = selected_topic.get('author', '')
            score = selected_topic.get('score', '')

            # Update topic_context with the newly selected topic
            state['topic_context'] = selected_topic
            # Also update candidates so repurpose can find it by URL later
            state['last_candidates'] = candidates
            state['current_step'] = 'waiting_for_rewrite_confirm'

            # Fetch article content
            raw_content = ""
            if url:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        html = resp.read().decode('utf-8', errors='replace')
                        match = re.search(r'id="js_content"[^>]*>(.*?)</div>', html, re.DOTALL)
                        if match:
                            raw_content = re.sub(r'<[^>]+>', '', match.group(1))
                        else:
                            raw_content = re.sub(r'<[^>]+>', '', html)[:2000]
                except Exception as e:
                    print(f"[WARN] Failed to fetch article: {e}", flush=True)

            # Call LLM for insight
            insight_text = ""
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if raw_content and api_key:
                prompt = (
                    f"你是一个资深自媒体爆款策划顾问。请分析以下选题的爆款潜力：\n\n"
                    f"选题标题：{title}\n原文作者：{author}\n热度指数：{score}\n\n"
                    f"原文内容摘要：{raw_content[:1000]}\n\n"
                    f"请从以下四个维度分析（每条不超过50字）：\n"
                    f"1. 【核心情绪】核心情绪是什么？为何能引发传播？\n"
                    f"2. 【IP切入点】从这个IP应该从哪个差异化角度切入？\n"
                    f"3. 【可借鉴点】哪些爆点元素值得借鉴？\n"
                    f"4. 【风险提示】有无敏感话题风险？\n\n"
                    f"直接输出分析结论，不要车轱辘话。"
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
                insight_text = f"🔥 **选题：** {title}\n\n热度指数：{score}\n\n请确认是否值得投入 IP 化改写。"

            # Update state
            topic_id_str = action_value.split('_', 1)[1] if '_' in action_value else 'new'
            state['current_step'] = 'waiting_for_rewrite_confirm'
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False)

            # Send rewrite confirm card - pass base64(url) so rewrite button is unambiguous
            import base64
            topic_url_b64 = base64.b64encode(url.encode('utf-8')).decode('utf-8') if url else ''
            card = self.build_rewrite_card(title, insight_text, topic_url_b64)
            self.send_card(token, card)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_text(token, f"⚠️ 解读失败: {str(e)[:100]}")

    def build_rewrite_card(self, title, insight, topic_url_b64):
        """Build rewrite confirm card. topic_url_b64 is base64-encoded topic URL."""
        import base64
        try:
            decoded_url = base64.b64decode(topic_url_b64.encode('utf-8')).decode('utf-8')
            display_url = decoded_url[:40] + '...' if len(decoded_url) > 40 else decoded_url
        except:
            display_url = topic_url_b64
        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": "purple", "title": {"tag": "plain_text", "content": "📝 选题解读完成"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 选题：** {title}\n\n**💡 解读：**\n{insight}"}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"URL: {display_url}"}]},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "✍️ 开始改写"}, "type": "primary", "value": f"rewrite_{topic_url_b64}"},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "🔄 换一个"}, "type": "default", "value": "next_new"}
                ]}
            ]
        }

    def run_repurpose_and_send_card(self, token, action_value):
        """Run repurpose - generate script + article, send two review cards."""
        try:
            os.chdir(WORKDIR)
            start_time = time.time()
            
            # 1. 强力净化：改写前彻底清理旧状态，并同步到磁盘，切断旧数据引用路径
            try:
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state_to_clean = json.load(f)
                    state_to_clean['draft_file'] = None
                    state_to_clean['video_script'] = None
                    # 保存这个“干净”的状态，防止脚本读到旧值
                    with open(STATE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(state_to_clean, f, ensure_ascii=False, indent=2)
                    print(f"[DEBUG] [{time.strftime('%H:%M:%S')}] Cleared old draft paths in state file.", flush=True)
            except Exception as e:
                print(f"[WARN] Failed to clean state: {e}", flush=True)

            # 2. 准备执行参数 - 用 URL 解码查找选题，彻底避免 index/guid 混淆
            raw_id = action_value.split('_', 1)[1] if '_' in action_value else action_value
            topic_url_for_repurpose = None

            # Try to decode as base64 URL first (primary method)
            import base64
            try:
                decoded_url = base64.b64decode(raw_id.encode('utf-8')).decode('utf-8')
                if decoded_url.startswith('http'):
                    topic_url_for_repurpose = decoded_url
                    print(f"[DEBUG] [repurpose] decoded URL from button: {decoded_url[:50]}...", flush=True)
            except Exception:
                pass

            # Load state and find the correct topic
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state_for_topic = json.load(f)
                candidates = state_for_topic.get('last_candidates', [])

                if topic_url_for_repurpose:
                    # Match by URL
                    for c in candidates:
                        if c.get('id') == topic_url_for_repurpose or c.get('url') == topic_url_for_repurpose:
                            state_for_topic['topic_context'] = c
                            print(f"[DEBUG] [repurpose] matched topic by URL: {c.get('title', '')[:30]}", flush=True)
                            break
                else:
                    # Fallback: try guid/index match
                    for c in candidates:
                        if c.get('guid') == raw_id:
                            state_for_topic['topic_context'] = c
                            break
                    if 'topic_context' not in state_for_topic and raw_id.isdigit():
                        idx = int(raw_id) - 1
                        if 0 <= idx < len(candidates):
                            state_for_topic['topic_context'] = candidates[idx]

                # Write back the correct topic_context BEFORE repurpose runs
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state_for_topic, f, ensure_ascii=False, indent=2)
                print(f"[DEBUG] [repurpose] topic_context updated before repurpose", flush=True)
            except Exception as e:
                print(f"[WARN] [repurpose] failed to update topic_context: {e}", flush=True)

            # Use URL as topic_id for repurpose (most reliable)
            topic_id_for_cmd = topic_url_for_repurpose if topic_url_for_repurpose else raw_id
            import sys
            cmd = [sys.executable, '-X', 'utf8', 'workflow_controller.py', 'repurpose', '--id', str(topic_id_for_cmd)]
            print(f"[DEBUG] Executing repurpose: {' '.join(cmd)[:100]}...", flush=True)

            # 3. 执行子进程，延长超时时间至 300 秒以防 LLM 响应慢
            process_start = time.time()
            # 🎯 极其重要：Windows 环境必须强制指定 utf-8 编码，否则 subprocess 会报 GBK 解码错误
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace')
            process_duration = time.time() - process_start
            
            # 记录详细调试日志
            debug_log = os.path.join(WORKDIR, "subprocess_debug.log")
            with open(debug_log, "a", encoding='utf-8') as debug_f:
                debug_f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] REPURPOSE RUN (ID: {topic_id_for_cmd[:30]}...)\n")
                debug_f.write(f"Duration: {process_duration:.2f}s | RetCode: {result.returncode}\n")
                if result.stderr: debug_f.write(f"STDERR samples: {result.stderr[:500]}\n")
                debug_f.write("-" * 40 + "\n")

            # 4. 严格校验：如果进程失败或输出中没有包含保存成功的字样，严禁继续
            stdout_str = str(result.stdout or "")
            stderr_str = str(result.stderr or "")
            # 合并输出流进行搜索，防止 logging 模块输出到 stderr 导致匹配失败
            combined_output = stdout_str + "\n" + stderr_str
            success_markers = ["[保存稿件]", "[保存文件]", "script_path=", "article_path=", "✅ [保存"]
            actually_saved = any(m in combined_output for m in success_markers)
            
            if result.returncode != 0 or not actually_saved:
                error_msg = f"⚠️ 改写流程执行异常 (Code {result.returncode})。"
                if "timeout" in stderr_str.lower(): error_msg = "⚠️ 改写请求超时，请稍后重试。"
                print(f"[ERROR] Repurpose verification failed. Stdout/Stderr: {combined_output[:500]}", flush=True)
                self.send_text(token, f"{error_msg}\n可能原因：LLM 响应过慢或原内容抓取失败。")
                return

            # 5. 再次载入状态，并进行文件“新鲜度”校验
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            draft_file = state.get('draft_file', '')
            script_file = state.get('video_script', '')

            # 如果路径依然为空，或者文件修改时间在启动之前，说明没写成功
            def is_file_fresh(path, threshold_time):
                if not path or not os.path.exists(path): return False
                return os.path.getmtime(path) >= threshold_time

            if not is_file_fresh(draft_file, start_time) and not is_file_fresh(script_file, start_time):
                print(f"[ERROR] Stale files detected. Start: {start_time}, Draft: {os.path.getmtime(draft_file) if draft_file and os.path.exists(draft_file) else 'N/A'}", flush=True)
                self.send_text(token, "⚠️ 检测到生成文件失效，请尝试重试按钮。")
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
                article_full = "（未生成文章）"

            script_full = ""
            if script_file and os.path.exists(script_file):
                try:
                    with open(script_file, 'r', encoding='utf-8') as f:
                        script_full = f.read().strip()
                except Exception:
                    pass
            if not script_full:
                script_full = "（未生成脚本）"

            self.send_text(token, "✨ 改写完成，请分别审核【脚本】和【文章】...")

            script_card = self.build_review_card_v2(
                cover_path="",
                title=f"🎬 短视频脚本 | {title}",
                content=script_full,
                tags="脚本",
                review_id="script_01",
                template="orange",
                header_title="🎬 脚本审核"
            )
            self.send_card(token, script_card)

            article_card = self.build_review_card_v2(
                cover_path="",
                title=f"📖 深度长文 | {title}",
                content=article_full,
                tags="文章",
                review_id="article_01",
                template="blue",
                header_title="📖 文章审核"
            )
            self.send_card(token, article_card)

        except Exception as e:
            self.send_text(token, f"⚠️ 改写失败: {str(e)[:100]}")

    def build_review_card_v2(self, cover_path, title, content, tags, review_id, template="blue", header_title=None):
        """Build review card with anti-fake labels and timestamps."""
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
            "elements": [{"tag": "plain_text", "content": f"流水号: {review_id} | 生成时间: {now_str}"}]
        })
        elements.append({
            "tag": "action",
            "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "✅ 通过"}, "type": "primary", "value": f"approve_{review_id}"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "✏️ 修改"}, "type": "default", "value": f"modify_{review_id}"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "❌ 重写"}, "type": "default", "value": f"rewrite_{review_id}"}
            ]
        })

        hdr = f"{header_title}" if header_title else "📋 内容审核"
        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"tag": "plain_text", "content": hdr}},
            "elements": elements
        }

    def run_modify_and_send_card(self, token, action_value):
        """User clicked modify - ask what to change."""
        parts = action_value.split('_', 1)
        if len(parts) < 2:
            self.send_text(token, "⚠️ 无法识别修改目标，请重新操作")
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
            f"当前内容预览（前200字）：\n"
            f"```{current_content[:200]}```\n\n"
            f"请直接告诉我您想怎么修改，例如：\n"
            f"• \"把开头改得更吸引人\"\n"
            f"• \"第三段加一个金句\"\n"
            f"• \"语言风格更口语化\"\n\n"
            f"我收到后会重新生成该【{kind}】。"
        )
        self.send_text(token, guide_msg)

    def run_rescript_and_send_card(self, token, action_value):
        """Regenerate script only, keep article."""
        self.send_text(token, "🔄 正在重新生成【脚本】，请稍候...\n（脚本已保留，内容将重新生成）")
        os.chdir(WORKDIR)

        cmd = ['python', 'workflow_controller.py', 'repurpose', '--script-only']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

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
            script_full = "（未生成脚本）"

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
            article_full = "（未生成文章）"

        self.send_text(token, "✨ 脚本已重新生成，请审核新版本...")

        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"🎬 短视频脚本 | {title}",
            content=script_full, tags="脚本（已重写）",
            review_id="script_01", template="orange", header_title="🎬 脚本审核（新版）"
        ))
        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"📖 深度长文 | {title}",
            content=article_full, tags="文章（未变）",
            review_id="article_01", template="blue", header_title="📖 文章审核"
        ))

    def run_rearticle_and_send_card(self, token, action_value):
        """Regenerate article only, keep script."""
        self.send_text(token, "🔄 正在重新生成【文章】，请稍候...\n（文章将重新生成，脚本已保留）")
        os.chdir(WORKDIR)

        cmd = ['python', 'workflow_controller.py', 'repurpose', '--article-only']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

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
            article_full = "（未生成文章）"


        script_full = ""
        if script_file and os.path.exists(script_file):
            try:
                with open(script_file, 'r', encoding='utf-8') as f:
                    script_full = f.read().strip()
            except Exception:
                pass
        if not script_full:
            script_full = "（未生成脚本）"

        self.send_text(token, "✨ 文章已重新生成，请审核新版本...")

        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"🎬 短视频脚本 | {title}",
            content=script_full, tags="脚本（未变）",
            review_id="script_01", template="orange", header_title="🎬 脚本审核"
        ))
        self.send_card(token, self.build_review_card_v2(
            cover_path="", title=f"📖 深度长文 | {title}",
            content=article_full, tags="文章（已重写）",
            review_id="article_01", template="blue", header_title="📖 文章审核（新版）"
        ))

    def run_approve_and_track(self, token, action_value):
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

        approved_count = sum([
            state.get('script_approved', False),
            state.get('article_approved', False)
        ])

        state[flag_key] = True
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        new_approved_count = approved_count + 1
        remaining = 2 - new_approved_count

        if new_approved_count < 2:
            self.send_text(token, f"✅ 【{kind}】已通过，还剩{remaining}项通过后即可生成封面图...")
        else:
            self.send_text(token, "🎉 脚本+文章均已通过，正在生成封面图...")
            time.sleep(1)
            state['script_approved'] = False
            state['article_approved'] = False
            state['is_generating_cover'] = False # 🎯 极其重要：触发流程前强制清除锁
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            self.run_final_and_send_card(token)

    def send_image_preview(self, token, image_path, caption=""):
        """Show generated image in a beautiful interactive card IMMEDIATELY."""
        if not image_path or not os.path.exists(image_path): return
        try:
            token = self.get_token()
            # 🎯 闪电上传：使用 curl 进行 multipart 上传效率最高
            upload_result = subprocess.run([
                'curl', '-s', '-X', 'POST',
                'https://open.feishu.cn/open-apis/im/v1/images',
                '-H', f'Authorization: Bearer {token}',
                '-F', 'image_type=message',
                '-F', f'image=@{image_path}'
            ], capture_output=True, text=True).stdout
            image_key = json.loads(upload_result).get("data", {}).get("image_key", "")
            
            if image_key:
                # 构造即时预览卡片：大图预览，提升体感
                preview_card = {
                    "config": {"wide_screen_mode": True},
                    "header": {"template": "green", "title": {"tag": "plain_text", "content": "✅ 视觉素材已就位"}},
                    "elements": [
                        {"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": caption}, "title": {"tag": "plain_text", "content": caption}},
                        {"tag": "note", "elements": [{"tag": "plain_text", "content": f"🕒 {time.strftime('%H:%M:%S')} | {caption}"}]}
                    ]
                }
                self.send_card(token, preview_card) # 依然走 MESSAGE_QUEUE 确保亚秒级触达
        except: pass

    def run_final_and_send_card(self, token):
        """Generate visuals and send final publish card."""
        try:
            # Mutex guard
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                guard_state = json.load(f)
            if guard_state.get('is_generating_cover', False):
                self.send_text(token, "⏳ 视觉素材正在制作中，请稍候...")
                print("[DEBUG] Skip run_final_and_send_card due to is_generating_cover=True", flush=True)
                return
            
            guard_state['is_generating_cover'] = True
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(guard_state, f, ensure_ascii=False, indent=2)

            self.send_text(token, "🎨 正在为您生成视觉素材，请稍候...")
            print(f"[DEBUG] Starting visuals sub-process at {time.strftime('%H:%M:%S')}...", flush=True)

            os.chdir(WORKDIR)
            import sys
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'

            proc = subprocess.Popen(
                [sys.executable, 'workflow_controller.py', 'visuals'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8', 
                errors='replace',
                env=env,
                bufsize=1
            )

            img_count = 0
            any_image_generated = False
            violation_detected = False

            for line in proc.stdout:
                line = line.strip()
                if not line: continue
                print(f"[visuals] {line}", flush=True)

                # 检测安全规则拦截
                if "violate platform rules" in line or "SafeSearch" in line:
                    violation_detected = True

                # [修复] 增加 :? 匹配，兼容 workflow_controller 的输出格式
                m_cover = re.search(r'cover.*?就位:?\s*(.+\.(?:jpg|jpeg|png))', line)
                if m_cover:
                    img_count += 1
                    any_image_generated = True
                    img_path = m_cover.group(1).strip()
                    threading.Thread(target=self.send_image_preview, args=(token, img_path, "🖼️ 封面图生成成功！")).start()
                    continue

                m_ins = re.search(r'插.?图\s*(\d+)\s*已就位:?\s*(.+\.(?:jpg|jpeg|png))', line)
                if m_ins:
                    img_count += 1
                    any_image_generated = True
                    img_path = m_ins.group(2).strip()
                    threading.Thread(target=self.send_image_preview, args=(token, img_path, f"🖼️ 插图 {m_ins.group(1)} 生成成功！")).start()
            
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
                print("[WARN] No images generated this run", flush=True)
                if violation_detected:
                    self.send_text(token, "⚠️ 部分配图因触发平台合规（SafeSearch）未能生成。")
                else:
                    self.send_text(token, "⚠️ 视觉素材由于 API 超时或网络抖动未能完成生成。建议在预览卡片上点击“重新生图”。")
            
            # 如果生成了一部分，但也有合规拦截。
            elif violation_detected:
                self.send_text(token, "🔔 视觉素材已部分产出，但由于合规拦截未能产出全文配图。")

            # Upload cover image to Feishu
            image_key = ""
            if cover_path and os.path.exists(cover_path):
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
                        '-F', f'image=@{cover_path}'
                    ], capture_output=True, text=True).stdout
                    upload_data = json.loads(upload_result)
                    image_key = upload_data.get("data", {}).get("image_key", "")
                    print(f"[DEBUG] Uploaded cover: {image_key}", flush=True)
                except Exception as e:
                    print(f"[WARN] Cover upload failed: {e}", flush=True)

            card = self.build_final_card(image_key, title, content, "AI|迭代|成长", "final_01")
            self.send_card(token, card)

            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                cleanup = json.load(f)
            cleanup['is_generating_cover'] = False
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
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cleanup, f, ensure_ascii=False, indent=2)
            except:
                pass


    def build_final_card(self, image_key, title, content, tags, review_id):
        """Build final publish card."""
        elements = []

        if image_key:
            elements.append({"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "封面图"}})

        content_clean = re.sub(r'^#+\s*', '', content, flags=re.MULTILINE).strip() if content else ""

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🔥 标题：** {title}"}
        })

        if content_clean:
            for i in range(0, len(content_clean), 800):
                chunk = content_clean[i:i+800]
                elements.append({"tag": "div", "text": {"tag": "lark_md", "content": chunk}})

        elements.append({"tag": "hr"})
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": tags}]})
        elements.append({
            "tag": "action",
            "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "📤 发布到公众号"}, "type": "primary", "value": f"post_{review_id}"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "🖼️ 重新生图"}, "type": "default", "value": f"revisuals_{review_id}"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "📋 复制文案"}, "type": "default", "value": f"copy_{review_id}"}
            ]
        })

        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": "green", "title": {"tag": "plain_text", "content": "🎉 最终稿"}},
            "elements": elements
        }

    def run_post(self, token):
        """Trigger post workflow asynchronously to avoid blocking and allow browser GUI."""
        def post_worker():
            try:
                # Check if draft exists
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                draft_file = state.get('draft_file')
                if not draft_file or not os.path.exists(draft_file):
                    self.send_text(token, "⚠️ 草稿文件不存在，请重新生成文章")
                    return

                # Preparation
                os.chdir(WORKDIR)
                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                env["HEADLESS"] = "false"  # Force GUI for Windows/Mac

                # 直接调用 workflow_controller.py post，wechat-article.ts 会统一启动和管理 Chrome
                self.send_text(token, "🚀 正在启动浏览器发布，请稍候...")

                result = subprocess.run(
                    [sys.executable, '-X', 'utf8', 'workflow_controller.py', 'post', '--method', 'browser'],
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=WORKDIR
                )

                # 检查输出中是否有明确的失败关键词
                output = (result.stdout + result.stderr).lower()
                failure_keywords = ['error', 'fail', 'exception', 'cancelled', 'cdp timeout']
                is_failure = (
                    result.returncode != 0 or
                    any(kw in output for kw in failure_keywords) or
                    '成功' not in result.stdout
                )

                if not is_failure and result.returncode == 0:
                    self.send_text(token, "✅ 公众号发布成功！请检查草稿箱。")
                else:
                    error_detail = (result.stdout + result.stderr)[-500:] if (result.stdout + result.stderr) else f'进程退出码: {result.returncode}'
                    self.send_text(token, f"❌ 发布失败 (Code {result.returncode})\n\n{error_detail}")
            except Exception as e:
                self.send_text(token, f"⚠️ 发布线程异常: {str(e)}")

        import threading
        threading.Thread(target=post_worker, daemon=True).start()

    def send_copy_guide(self, token):
        """Guide user to copy content."""
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

        self.send_text(token, f"📋 以下是可复制文案：\n\n{content[:4000]}")


def main():
    # Use a fixed port to ensure single instance
    port = 18799
    pid_file = os.path.join(WORKDIR, ".feishu_card_server.pid")

    # ===== 杀掉旧实例，确保只有一个运行 =====
    try:
        import subprocess
        if os.name == 'nt': # Windows 环境
            # 1. 通过 PID 文件找到旧进程并杀掉
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, "r") as f:
                        old_pid = int(f.read().strip())
                    if old_pid != os.getpid():
                        try:
                            os.kill(old_pid, 0)  # 检查进程是否存在
                            print(f"[SINGLETON] 杀掉旧实例 PID {old_pid}...", flush=True)
                            subprocess.run(f'taskkill /F /PID {old_pid}', capture_output=True)
                        except OSError:
                            pass  # 进程已不存在
                except (ValueError, OSError):
                    pass
                finally:
                    try:
                        os.remove(pid_file)
                    except Exception:
                        pass

            # 2. 强力回收端口：杀掉任何占用 18799 端口的进程
            check_cmd = f'powershell -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"'
            res = subprocess.run(check_cmd, capture_output=True, text=True)
            if res.stdout.strip():
                old_pids = set(res.stdout.strip().split())
                for pid in old_pids:
                    try:
                        if int(pid) != os.getpid():
                            print(f"[RECLAIM] 端口被 PID {pid} 占用，杀掉...", flush=True)
                            subprocess.run(f'taskkill /F /PID {pid}', capture_output=True)
                    except ValueError:
                        pass
            time.sleep(1)  # 等待端口完全释放
        else: # Linux/Mac 环境
            subprocess.run(f'fuser -k {port}/tcp', shell=True, capture_output=True)
            if os.path.exists(pid_file):
                try:
                    os.remove(pid_file)
                except Exception:
                    pass
            time.sleep(1)
    except Exception as e:
        print(f"[WARN] Failed to reclaim port: {e}", flush=True)

    # 写入当前 PID
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    try:
        # 🎯 启动独立异步消息 Worker：解耦类实例，确保鉴权与下发稳定
        threading.Thread(target=message_sender_worker, daemon=True).start()

        server = HTTPServer(('0.0.0.0', port), FeishuHandler)
        print(f"Feishu Card Server running on http://0.0.0.0:{port}")
        print(f"Webhook endpoint: http://0.0.0.0:{port}/feishu/callback")
        print(f"[PID] {os.getpid()} | PID file: {pid_file}", flush=True)
        server.serve_forever()
    except OSError as e:
        print(f"[ERROR] Failed to start server: {e}")
        if os.path.exists(pid_file):
            os.remove(pid_file)
        sys.exit(1)


if __name__ == '__main__':
    main()
