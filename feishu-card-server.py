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

# Feishu App Config
APP_ID = "cli_a930dedc42789cd1"
APP_SECRET = "WOjERqoJ8OhIwIthMS3NAcJAxFDvXK2X"
DEFAULT_RECEIVE_ID = "ou_2da8e0f846c19c8fabebd6c6d82a8d6d"
WORKDIR = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto"
STATE_FILE = WORKDIR + r"/.workflow_state.json"


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
        if self.path != "/feishu/callback":
            self.send_response(404)
            self.end_headers()
            return

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

        # URL verification
        if data.get('type') == 'url_verification' or data.get('challenge'):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"challenge": data.get('challenge', '')}).encode('utf-8'))
            return

        # Card button event
        event = data.get('event', {})
        message = event.get('message', {})
        content_str = message.get('content', '{}')

        try:
            content = json.loads(content_str)
        except:
            content = {}

        # Get button value from actions or elements
        action_value = None
        actions = content.get('actions', [])
        for act in actions:
            if act.get('tag') == 'button' and act.get('value'):
                action_value = act.get('value')
                break

        if not action_value:
            for el in content.get('elements', []):
                if el.get('tag') == 'action':
                    for act in el.get('actions', []):
                        if act.get('tag') == 'button' and act.get('value'):
                            action_value = act.get('value')
                            break

        if not action_value:
            action_value = event.get('action', {}).get('value')

        if action_value:
            self.handle_card_action(action_value)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"code": 0, "msg": "success"}).encode('utf-8'))

    # ===== Feishu API =====

    def get_token(self):
        req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8')).get('tenant_access_token', '')

    def send_card(self, token, card):
        """Send an interactive card to Feishu."""
        try:
            payload = {
                "receive_id": DEFAULT_RECEIVE_ID,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False)
            }
            req = urllib.request.Request(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                if result.get('code') == 0:
                    return True
                else:
                    print(f"[WARN] send_card failed: {result.get('msg')}", flush=True)
                    return False
        except Exception as e:
            print(f"[ERROR] send_card failed: {e}", flush=True)
            return False

    def send_image_preview(self, token, image_path, caption=""):
        """Send image as Feishu image message."""
        if not image_path or not os.path.exists(image_path):
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
                return

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
                    print(f"[DEBUG] Image preview sent: {image_key}")
                else:
                    print(f"[WARN] Send image failed: {result.get('msg')}")
        except Exception as e:
            print(f"[ERROR] send_image_preview failed: {e}")

    def send_text(self, token, text):
        """Send a text message to Feishu."""
        try:
            payload = {
                "receive_id": DEFAULT_RECEIVE_ID,
                "msg_type": "text",
                "content": json.dumps({"text": text})
            }
            req = urllib.request.Request(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                if result.get('code') == 0:
                    return True
                else:
                    print(f"[WARN] send_text failed: {result.get('msg')}", flush=True)
                    return False
        except Exception as e:
            print(f"[ERROR] send_text failed: {e}", flush=True)
            return False

    def update_topic_context_by_id(self, token, topic_id):
        """Update workflow state with selected topic."""
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            topic_id_str = str(topic_id).strip()
            candidates = state.get('last_candidates', [])

            # Try as 1-based array index from "topic_05" -> 5
            numeric_id = None
            try:
                numeric_id = int(topic_id_str.split('_')[-1])
            except ValueError:
                pass

            updated = False
            if numeric_id is not None and 0 < numeric_id <= len(candidates):
                selected = candidates[numeric_id - 1]
                state['topic_context'] = {
                    'id': selected.get('id', ''),
                    'title': selected.get('title', ''),
                    'source': selected.get('source', ''),
                    'author': selected.get('author', ''),
                    'score': selected.get('score', '')
                }
                updated = True
                print(f"[DEBUG] Updated topic_context to topic {numeric_id}: {selected.get('title', '')[:50]}", flush=True)
            elif topic_id_str.startswith('http'):
                state['topic_context'] = {
                    'id': topic_id_str,
                    'title': topic_id_str.split('?')[0][-30:],
                    'source': 'custom',
                    'author': ''
                }
                updated = True
                print(f"[DEBUG] Updated topic_context to URL: {topic_id_str[:50]}", flush=True)
            else:
                print(f"[DEBUG] Topic ID {topic_id_str} out of range, keeping existing", flush=True)

            if updated:
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)
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

            # Strip common garbled quote chars
            for q in '"\'铐牢笼非':
                action_value = action_value.strip(q)

            parts = action_value.split('_', 1)
            action_type = parts[0] if parts else 'unknown'

            if action_type == 'next':
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token,)).start()
            elif action_type == 'insight':
                topic_id = parts[1] if len(parts) > 1 else None
                if topic_id:
                    self.update_topic_context_by_id(token, topic_id)
                threading.Thread(target=self.run_insight_and_send_card, args=(token, action_value)).start()
            elif action_type == 'skip':
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token,)).start()
            elif action_type == 'refresh':
                threading.Thread(target=self.run_discovery_and_send_cards, args=(token,)).start()
            elif action_type == 'init':
                threading.Thread(target=self.run_init_and_send_card, args=(token,)).start()
            elif action_type == 'rewrite':
                threading.Thread(target=self.run_repurpose_and_send_card, args=(token, action_value)).start()
            elif action_type == 'approve':
                threading.Thread(target=self.run_approve_and_track, args=(token, action_value)).start()
            elif action_type == 'modify':
                threading.Thread(target=self.run_modify_and_send_card, args=(token, action_value)).start()
            elif action_type == 'rescript':
                threading.Thread(target=self.run_rescript_and_send_card, args=(token, action_value)).start()
            elif action_type == 'rearticle':
                threading.Thread(target=self.run_rearticle_and_send_card, args=(token, action_value)).start()
            elif action_type == 'post':
                threading.Thread(target=self.run_post, args=(token,)).start()
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

    def run_discovery_and_send_cards(self, token):
        """Run discovery and send topic cards."""
        try:
            print("[DEBUG] run_discovery_and_send_cards starting", flush=True)
            os.chdir(WORKDIR)

            # Check if there's a cached page of candidates
            use_refresh = True
            try:
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    candidates = state.get('last_candidates', [])
                    page_index = state.get('candidates_page_index', 0)
                    page_size = state.get('candidates_page_size', 5)
                    if candidates and page_index * page_size < len(candidates):
                        state['candidates_page_index'] = page_index + 1
                        with open(STATE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(state, f, ensure_ascii=False)
                        use_refresh = False
                        cmd = ['python', 'workflow_controller.py', 'next']
            except:
                pass

            if use_refresh:
                cmd = ['python', 'workflow_controller.py', 'discovery', '--refresh']

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            output = result.stdout
            print(f"[DEBUG] command output length: {len(output)}", flush=True)

            topics = self.parse_discovery_output(output)
            print(f"[DEBUG] parsed topics count: {len(topics)}", flush=True)

            if topics:
                # Save candidates to state file (required for topic context lookup)
                try:
                    with open(STATE_FILE, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    state['last_candidates'] = topics
                    state['candidates_page_index'] = 1
                    state['candidates_page_size'] = 5
                    with open(STATE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)
                    print(f"[DEBUG] Saved {len(topics)} candidates to state", flush=True)
                except Exception as e:
                    print(f"[WARN] Failed to save candidates to state: {e}", flush=True)

                # Send single batch card with all topics
                batch_card = self.build_topic_list_card(topics, "AI")
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
        Returns list of dicts with keys: id (URL), title, source, author, score, data (display string), analysis.
        """
        topics = []
        lines = output.split('\n')
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
                    topics.append(current_topic)
                    current_topic = None

        return topics[:5]

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

    def build_topic_list_card(self, topics, industry="AI"):
        """Build batch topic card (all topics in one card).
        topics: list of dicts with keys: id(str), title, data, url, analysis, source, author, score
        """
        elements = []
        elements.append({"tag": "markdown", "content": f"**🔥 {industry}赛道 · 今日爆款选题 TOP {len(topics)}**"})
        elements.append({"tag": "hr"})

        for i, t in enumerate(topics):
            topic_id = str(t.get("id", i + 1))
            elements.append({
                "tag": "markdown",
                "content": f"**🔥 [{topic_id}] {t.get('title', '')}**\n📊 {t.get('data', '')}\n💡 {t.get('analysis', '爆款选题')}\n🔗 [原文链接]({t.get('url', '')})"
            })
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": f"🔍 解读选题 {topic_id}"},
                    "type": "primary",
                    "value": f"insight_{topic_id}"
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
            topic_ctx = state.get('topic_context', {})
            title = topic_ctx.get('title', '未知选题')
            url = topic_ctx.get('id', '')
            author = topic_ctx.get('author', '')
            score = topic_ctx.get('score', '')

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
                    f"1. 【传控铰剪辑】核心情绪是什么？为何能引发传播？\n"
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
            state['topic_context'] = topic_ctx
            state['current_step'] = 'waiting_for_rewrite_confirm'
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
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 选题：** {title}\n\n**💡 解读：**\n{insight}"}},
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
        try:
            os.chdir(WORKDIR)
            topic_id = action_value.split('_', 1)[1] if '_' in action_value else ''

            self.send_text(token, "🔄 改写进行中（脚本+文章），请稍候...\n（预计需要 20-40 秒）")

            cmd = ['python', 'workflow_controller.py', 'repurpose']
            if topic_id:
                cmd.extend(['--id', topic_id])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            title = state.get('topic_context', {}).get('title', '内容')
            draft_file = state.get('draft_file', '')
            script_file = state.get('video_script', '')

            article_full = ""
            if draft_file and os.path.exists(draft_file):
                try:
                    with open(draft_file, 'r', encoding='utf-8') as f:
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
        """Build review card with approve/modify/rewrite buttons."""
        CHUNK_SIZE = 800
        paragraphs = []
        if content:
            for i in range(0, len(content), CHUNK_SIZE):
                chunk = content[i:i+CHUNK_SIZE]
                paragraphs.append({"tag": "div", "text": {"tag": "lark_md", "content": chunk}})

        elements = []
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🔥 标题：** {title}\n\n**🏷️ 标签：** {tags}"}
        })
        elements.extend(paragraphs)
        elements.append({"tag": "hr"})
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"ID: {review_id}"}]})
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
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            self.run_final_and_send_card(token)

    def run_final_and_send_card(self, token):
        """Generate visuals and send final publish card."""
        try:
            # Mutex guard
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                guard_state = json.load(f)
            if guard_state.get('is_generating_cover', False):
                print("[DEBUG] Visual generation already in progress, skipping", flush=True)
                self.send_text(token, "⏳ 封面图正在生成中，请稍候...")
                return
            guard_state['is_generating_cover'] = True
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(guard_state, f, ensure_ascii=False, indent=2)

            self.send_text(token, "🖼️ 正在生成封面图，请稍候...")

            os.chdir(WORKDIR)
            proc = subprocess.Popen(
                ['python', 'workflow_controller.py', 'visuals'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            img_count = 0
            any_image_generated = False
            for line in proc.stdout:
                print(f"[visuals] {line}", end='', flush=True)
                m = re.search(r'cover.*?就位:\s*(.+\.(?:jpg|jpeg|png))', line)
                if m:
                    img_count += 1
                    any_image_generated = True
                    self.send_image_preview(token, m.group(1).strip(), f"🖼️ 封面图 {img_count} 已就位")
                    continue
                m = re.search(r'插入图\s*(\d+)\s*已就位\s*(.+\.(?:jpg|jpeg|png))', line)
                if m:
                    img_count += 1
                    any_image_generated = True
                    self.send_image_preview(token, m.group(2).strip(), f"🖼️ 插图 {m.group(1)} 已就位")

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
                print("[WARN] No images generated this run (SafeSearch triggered?)", flush=True)
                self.send_text(token,
                    "⚠️ 绘图失败了！\n\nDoubao Seedream 触发了限流（Safe Experience Mode），"
                    "请先到 Midjourney 控制台关闭\"安全模式\"，或等片刻后重试。\n\n"
                    "关闭方式：Midjourney → 模型激活 → doubao-seedream-5.0 → 关闭 Safe Experience Mode")
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    cleanup = json.load(f)
                cleanup['is_generating_cover'] = False
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cleanup, f, ensure_ascii=False, indent=2)
                return

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
                {"tag": "button", "text": {"tag": "plain_text", "content": "📋 复制文案"}, "type": "default", "value": f"copy_{review_id}"}
            ]
        })

        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": "green", "title": {"tag": "plain_text", "content": "🎉 最终稿"}},
            "elements": elements
        }

    def run_post(self, token):
        """Trigger post workflow."""
        try:
            os.chdir(WORKDIR)
            result = subprocess.run(
                ['python', 'workflow_controller.py', 'post', '--method', 'browser'],
                capture_output=True, text=True, timeout=60
            )
            if 'QR' in result.stdout or 'qr' in result.stdout.lower() or '二维码' in result.stdout:
                self.send_text(token, "📱 请扫描二维码并扫码登录公众号后台")
            else:
                self.send_text(token, "🚀 发布流程已启动，请检查公众号后台")
        except Exception as e:
            self.send_text(token, f"⚠️ 发布失败: {str(e)[:100]}")

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


def get_best_port():
    """Try to find an available port starting from 18799."""
    for port in [18799, 18800, 18801, 18802]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', port))
            s.close()
            return port
        except OSError:
            continue
    return 18799


def main():
    port = get_best_port()
    server = HTTPServer(('127.0.0.1', port), FeishuHandler)
    print(f"Feishu Card Server running on http://127.0.0.1:{port}")
    print(f"Webhook endpoint: http://127.0.0.1:{port}/feishu/callback")
    print(f"HTTP trigger: http://127.0.0.1:{port}/trigger")
    server.serve_forever()


if __name__ == '__main__':
    main()
