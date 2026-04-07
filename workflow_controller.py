#!/usr/bin/env python3
"""
新媒体超级工厂 - 中央调度器 (Agentic Controller)
本脚本负责串联 xiaohongshu-cli，baoyu-skills 和 huashu-skills，
实现选题发现、内容二创和视觉分发的异步调度。

新增功能 (v1.1):
  - setup         : 首次使用配置引导，检测并填充 .env 文件
  - from-article  : 输入公众号/任意文章 URL，自动抓取内容并二次创作
  - from-video    : 输入视频 URL（抖音/B站/YouTube等），自动提取音频转文字并二次创作
"""

import argparse
import sys
import subprocess
import os
import json
import io
import logging
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import requests
import certifi
# 设置 requests 库的 CA 证书，防止 TLS 报错
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
import re

# ==================== 统一日志配置 ====================
from utils.logger_config import get_workflow_logger, init_logging

# ==================== WeWrite + Xiaohu 集成导入 ====================
try:
    from config.wewrite_config import WeWriteConfig
    from integrations.wechat_topic_fetcher import TopicFetcher
    from integrations.wewrite_engine import WeWriteEngine, WeWriteError
    from integrations.xiaohu_formatter import XiaohuFormatter, XiaohuGalleryError, XiaohuGalleryTimeout
    WEWRITE_XIAOHU_AVAILABLE = True
except ImportError:
    WEWRITE_XIAOHU_AVAILABLE = False

# ==================== 飞书卡片导入 ====================
try:
    from send_feishu_card import build_url_preview_card, build_rewrite_card, send_card, get_token
except ImportError:
    build_url_preview_card = None
    send_card = None
    get_token = None

# 初始化日志系统（清理旧日志 + 创建日志目录）
init_logging()

# 获取 logger
logger = get_workflow_logger()

# 针对 Windows 环境下输出 Emoji 可能导致的 GBK 编码报错进行补丁
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass

# 统一加载环境变量
load_dotenv()

class SelfMediaController:
    def __init__(self):
        self.workspace = os.getcwd()
        self.session_file = os.path.join(self.workspace, '.workflow_state.json')
        logger.info('控制器初始化完成 | workspace=%s', self.workspace)

    def load_state(self):
        logger.debug('加载状态 | session_file=%s', self.session_file)
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                logger.info('从文件加载成功 | step=%s', state.get('current_step'))
                return state
            except Exception as e:
                logger.error('加载状态失败 | %s', e)
                return {"current_step": "idle", "selected_topic": None, "draft_file": None}
        logger.debug('状态文件不存在')
        return {"current_step": "idle", "selected_topic": None, "draft_file": None}

    def save_state(self, state):
        logger.debug('保存状态 | step=%s', state.get('current_step'))
        try:
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info('状态保存成功')
        except Exception as e:
            logger.error('保存状态失败 | %s', e)
            raise

    def run_setup(self):
        """
        [v1.1] 首次使用引导：环境检测与配置
        """
        import shutil
        logger.info("启动 setup 配置向导")
        print("\n" + "="*50)
        logger.info("[SETUP] Displaying welcome message")
        print("🚀 欢迎使用自媒体系统引导配置 (Setup Wizard)")
        print("="*50 + "\n")
        logger.info("[SETUP] Displaying welcome message")

        # 1. 检查 ffmpeg
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            print(f"✅ 环境检查: ffmpeg 已定位 -> {ffmpeg_path}")
        else:
            print("⚠️ 环境警告: 未检测到 ffmpeg。视频 ASR 功能将失效，请先安装 ffmpeg 并添加到 PATH。")
            logger.warning("[SETUP] FFmpeg not found in PATH")

        # 2. 配置 .env
        env_path = os.path.join(self.workspace, '.env')
        
        current_env = {}
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        parts = line.strip().split('=', 1)
                        if len(parts) == 2:
                            current_env[parts[0]] = parts[1]

        base_keys = [
            ("OPENAI_API_KEY", "OpenAI/DeepSeek API Key (用于文案改写)"),
            ("OPENAI_BASE_URL", "API 转发地址 (默认: https://api.openai.com/v1)"),
            ("LLM_MODEL_ID", "大模型 ID (如: deepseek-chat)"),
            ("AUTHOR_IP_NAME", "您的自媒体 IP 名称 (用于文章改写落款，默认：大胡)"),
            ("SILI_FLOW_API_KEY", "硅基流动 API Key (用于视频语音提取文字)"),
            ("FIRECRAWL_API_KEY", "Firecrawl API Key (用于网页/公众号文章抓取，可选)"),
            ("WECHAT_APP_ID", "微信公众号 AppID (用于自动发布，可选)"),
            ("WECHAT_APP_SECRET", "微信公众号 AppSecret (用于自动发布，可选)"),
            ("CIMI_APP_ID", "次幂数据 AppID (用于微信爆款选题)"),
            ("CIMI_APP_SECRET", "次幂数据 AppSecret (用于微信爆款选题)")
        ]

        print("\n🔧 正在配置核心 API 密钥 (直接回车可跳过已存在的设置):")
        logger.info("[SETUP] Starting API key configuration")
        final_kv = current_env.copy()
        
        # 1. 配置基础 key
        for key, desc in base_keys:
            curr_val = current_env.get(key, "")
            prompt = f"👉 {desc} [{key}]"
            if curr_val:
                prompt += f" (当前: {curr_val[:6]}...{curr_val[-4:] if len(curr_val)>10 else ''})"
            
            try:
                user_input = input(f"{prompt}: ").strip()
                if user_input:
                    final_kv[key] = user_input
                elif not curr_val and key == "OPENAI_BASE_URL":
                    final_kv[key] = "https://api.openai.com/v1"
                elif not curr_val and key == "AUTHOR_IP_NAME":
                    final_kv[key] = "大胡"
            except EOFError:
                continue

        # 2. 配置生图 Key (二选一)
        print("\n🎨 [生图子系统] 建议在 阿里云 DashScope 和 火山引擎 Ark 之间选择一个主用引擎：")
        logger.info("[SETUP] Prompting for image generation provider selection")
        img_provider = input("👉 请输入序号选择 (1: 阿里云 DashScope, 2: 火山引擎 Ark): ").strip()
        
        if img_provider == "1":
            key, desc = "DASHSCOPE_API_KEY", "阿里云百炼 API Key"
            curr_val = current_env.get(key, "")
            prompt = f"👉 {desc} [{key}]"
            if curr_val: prompt += f" (当前: {curr_val[:6]}...{curr_val[-4:]})"
            user_input = input(f"{prompt}: ").strip()
            if user_input: final_kv[key] = user_input
        elif img_provider == "2" or not img_provider: # 默认选火山
            key, desc = "ARK_API_KEY", "火山引擎 Ark API Key"
            curr_val = current_env.get(key, "")
            prompt = f"👉 {desc} [{key}]"
            if curr_val: prompt += f" (当前: {curr_val[:6]}...{curr_val[-4:]})"
            user_input = input(f"{prompt}: ").strip()
            if user_input: final_kv[key] = user_input

        # 保存到 .env
        with open(env_path, 'w', encoding='utf-8') as f:
            for key, value in final_kv.items():
                f.write(f"{key}={value}\n")

        print(f"\n✅ 配置保存成功！文件路径: {env_path}")
        logger.info("[SETUP] Saving .env configuration")
        print("✨ 您现在可以运行 'python workflow_controller.py discovery' 开始使用了。")
        logger.info("[SETUP] Configuration saved successfully")

    def _generate_insight(self, title, author, score, raw_content):
        """
        调用 LLM 生成选题的一句话解读（用于发给用户确认是否值得改写）。
        返回解读文本字符串。
        """
        import urllib.request
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        model_id = os.environ.get("LLM_MODEL_ID", "deepseek-chat")

        if not raw_content or not api_key or "your_api_key" in api_key:
            return f"🔥 **选题：** {title}\n\n热度指数：{score}\n\n请确认是否值得投入 IP 化改写。"

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
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 600
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/chat/completions",
                data=req_data,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                insight_text = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if insight_text:
                    return insight_text.strip()
        except Exception as e:
            logger.warning(f"[INSIGHT] LLM 调用失败: {e}")

        return f"🔥 **选题：** {title}\n\n热度指数：{score}\n\n请确认是否值得投入 IP 化改写。"

    def run_from_article(self, url_or_text):
        """
        [v1.2] 快捷入口：从指定文章链接开始创作
        流程：提取内容 → 生成解读 → 发送选题确认卡（等待用户点"开始改写"）→ 才执行改写
        """
        import re
        logger.info("启动 from-article | url=%s", str(url_or_text)[:60])
        match = re.search(r'https?://[^\s]+', url_or_text)
        url = match.group(0) if match else url_or_text

        print(f"🚀 启动定向创作模式 (From Article)... 原始输入中探测到的 URL: {url}")
        logger.info("[SETUP] Saving .env configuration")
        state = self.load_state()

        # 1. 提取文章内容
        raw_content = self._extract_article_content(url)

        # 2. 从内容中提取标题（尝试从 content 开头获取）
        article_title = "定向通过URL输入的素材"
        article_author = "外部链接"
        try:
            lines = raw_content.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 5:
                    article_title = line[:80]
                    break
            # 简单提取作者（如果有 "作者：" 这样的行）
            for line in lines[:20]:
                m = re.search(r'作者[：:]\s*(.+)', line)
                if m:
                    article_author = m.group(1).strip()
                    break
        except Exception:
            pass

        selected = {
            "id": url,
            "source": "公众号",
            "title": article_title,
            "author": article_author,
            "score": 9999
        }
        state['last_candidates'] = [selected]

        # 3. 生成选题解读
        print(f"🤖 正在生成选题解读...")
        insight_text = self._generate_insight(article_title, article_author, "外部链接", raw_content)

        # 4. 保存 topic_context（供后续 run_repurpose 使用）
        state['topic_context'] = {
            "id": url,
            "title": article_title,
            "author": article_author,
            "source": "公众号",
            "score": 9999
        }
        state['current_step'] = 'waiting_for_rewrite_confirm'
        self.save_state(state)

        # 5. 发送选题解读确认卡
        topic_id_str = url  # 用 URL 作为 topic_id
        if build_rewrite_card and send_card and get_token:
            try:
                token = get_token()
                card = build_rewrite_card(article_title, insight_text, topic_id_str)
                send_card(token, os.getenv("FEISHU_RECEIVE_ID", "ou_2da8e0f846c19c8fabebd6c6d82a8d6d"), card)
                print("✅ 选题解读卡片已发送，请确认是否改写")
            except Exception as e:
                logger.warning(f"[FROM_ARTICLE] 卡片发送失败: {e}")
                print(f"⚠️ 卡片发送失败: {e}")

        print(f"\n📝 选题：{article_title}")
        print(f"💡 解读：{insight_text[:100]}...")
        print(f"\n⏳ 等待确认后开始改写...（请在飞书中点击「✍️ 开始改写」）")
        logger.info("[FROM_ARTICLE] 流程暂停，等待用户确认改写")

    def run_from_video(self, url_or_text):
        """
        [v1.2] 快捷入口：从指定视频链接开始创作
        流程：提取内容 → 生成解读 → 发送选题确认卡（等待用户点"开始改写"）→ 才执行改写
        """
        import re
        logger.info("启动 from-video | url=%s", str(url_or_text)[:60])
        match = re.search(r'https?://[^\s]+', url_or_text)
        url = match.group(0) if match else url_or_text

        print(f"🚀 启动定向视频创作模式 (From Video)... 原始输入中探测到的 URL: {url}")
        logger.info("[SETUP] Configuration saved successfully")
        state = self.load_state()

        # 1. 提取视频内容（ASR 转录）
        raw_content = self._extract_article_content(url)

        # 2. 从 URL 推断视频标题
        video_title = f"视频素材: {url[:60]}"
        video_author = "视频平台"
        try:
            lines = raw_content.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 5:
                    video_title = line[:80]
                    break
        except Exception:
            pass

        selected = {
            "id": url,
            "source": "视频链接",
            "title": video_title,
            "author": video_author,
            "score": 9999
        }
        state['last_candidates'] = [selected]

        # 3. 生成选题解读
        print(f"🤖 正在生成视频内容解读...")
        insight_text = self._generate_insight(video_title, video_author, "视频素材", raw_content)

        # 4. 保存 topic_context
        state['topic_context'] = {
            "id": url,
            "title": video_title,
            "author": video_author,
            "source": "视频链接",
            "score": 9999
        }
        state['current_step'] = 'waiting_for_rewrite_confirm'
        self.save_state(state)

        # 5. 发送选题解读确认卡
        topic_id_str = url
        if build_rewrite_card and send_card and get_token:
            try:
                token = get_token()
                card = build_rewrite_card(video_title, insight_text, topic_id_str)
                send_card(token, os.getenv("FEISHU_RECEIVE_ID", "ou_2da8e0f846c19c8fabebd6c6d82a8d6d"), card)
                print("✅ 选题解读卡片已发送，请确认是否改写")
            except Exception as e:
                logger.warning(f"[FROM_VIDEO] 卡片发送失败: {e}")
                print(f"⚠️ 卡片发送失败: {e}")

        print(f"\n📝 选题：{video_title}")
        print(f"💡 解读：{insight_text[:100]}...")
        print(f"\n⏳ 等待确认后开始改写...（请在飞书中点击「✍️ 开始改写」）")
        logger.info("[FROM_VIDEO] 流程暂停，等待用户确认改写")

    def sync_to_feishu(self, script_path, article_path):
        """
        将二创生成的脚本和长文同步到飞书云文档
        """
        import subprocess
        import json
        logger.info("启动 sync_to_feishu | script=%s | article=%s", script_path, article_path)
        date_folder = datetime.now().strftime('%Y-%m-%d')
        
        print("🚀 启动 [飞书文档同步]...")
        logger.info("[DISCOVERY] Starting keyword-based discovery")
        
        # 1. 读取本地文件内容
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        with open(article_path, 'r', encoding='utf-8') as f:
            article_content = f.read()
        
        # 2. 调用 OpenClaw 飞书插件创建文件夹和文档
        print(f"📁 正在飞书云空间创建文件夹「自媒体内容/{date_folder}」...")
        logger.info("[DISCOVERY] Using cached industry from state")
        
        result = {
            "action": "sync_to_feishu",
            "folder_name": "自媒体内容",
            "subfolder_name": date_folder,
            "script_title": f"🎬 爆款脚本_{datetime.now().strftime('%m%d%H%M')}",
            "script_content": script_content,
            "article_title": f"📝 深度长文_{datetime.now().strftime('%m%d%H%M')}",
            "article_content": article_content
        }
        
        print("✅ 飞书同步参数已准备完成")
        logger.info("[DISCOVERY] Prompting for industry selection")
        return result

    def run_pre_discovery(self, keyword: Optional[str] = None):
        """预发现流程：设置状态，等待用户选择选题方式。

        不实际获取选题，只设置状态标记，触发卡服务器发送选择卡片。
        """
        logger.info("[PRE_DISCOVERY] 预发现流程启动 | keyword=%s", keyword)
        state = self.load_state()

        # 设置状态为等待选择
        state['step'] = 'awaiting_source_selection'
        state['source_selection_pending'] = True

        # 保存行业关键词（如果有）
        if keyword:
            state['industry'] = keyword
            print(f"[PRE_DISCOVERY] 行业关键词：{keyword}")

        self.save_state(state)

        # 输出标记，让卡服务器知道发送选择卡片
        print("[PRE_DISCOVERY] 请发送选题方式选择卡片")
        print("[STATE] awaiting_source_selection")
        print("[保存文件]")  # 确保飞书校验通过

        return True

    def _fetch_from_jizhile(self, refresh: bool, state: dict) -> list:
        """
        从极致了 API 获取微信爆款文章

        Args:
            refresh: True 表示获取最新，False 表示继续翻页
            state: 当前状态字典

        Returns:
            candidates 列表
        """
        from datetime import datetime, timedelta

        # 计算时间范围：过去 7 天（前天到 7 天前）
        end_date = datetime.now() - timedelta(days=1)
        start_date = datetime.now() - timedelta(days=7)
        start_time = start_date.strftime("%Y-%m-%d")
        end_time = end_date.strftime("%Y-%m-%d")

        # 获取配置
        jizhile_key = os.getenv("JIZHILE_KEY")
        jizhile_category = os.getenv("JIZHILE_CATEGORY", "7")
        jizhile_keyword = os.getenv("JIZHILE_KEYWORD", "OpenClaw")

        if not jizhile_key:
            print("❌ 未在环境变量中找到 JIZHILE_KEY，请先执行 run_setup 或修改 .env 文件。")
            logger.error("[JIZHILE] Missing JIZHILE_KEY in environment")
            sys.exit(1)

        # 计算页码
        if refresh:
            page = 1
            logger.info("[JIZHILE] refresh=True, starting from page 1")
        else:
            page = state.get('jizhile_page_index', 1) + 1
            logger.info("[JIZHILE] refresh=False, continuing from page %d", page)

        # 构建请求参数
        payload = {
            "key": jizhile_key,
            "keyword": jizhile_keyword,
            "pub_type": "0",  # 图文
            "category": jizhile_category,
            "page": str(page),
            "start_time": start_time,
            "end_time": end_time
        }

        endpoint = "https://www.dajiala.com/fbmain/monitor/v3/hot_typical_search"

        print(f"📥 [极致了 API] 正在获取爆款文章 (分类：{jizhile_category}, 时间：{start_time} 至 {end_time})...")
        logger.info("[JIZHILE] Fetching hot articles, category=%s, time_range=%s to %s",
                   jizhile_category, start_time, end_time)

        try:
            # 记录请求日志
            logger.info(">>> [HTTP REQUEST] POST %s", endpoint)
            logger.info(">>> [REQUEST PAYLOAD] key=%s, keyword=%s, page=%s",
                       jizhile_key[:10] + "..." if len(jizhile_key) > 10 else jizhile_key,
                       jizhile_keyword, page)

            # 发送请求 (multipart/form-data)
            response = requests.post(endpoint, data=payload, timeout=15)

            logger.info(">>> [HTTP RESPONSE] Status: %s", response.status_code)
            response.raise_for_status()

            result = response.json()

            # 检查返回码
            if result.get("code") != 0:
                print(f"❌ 极致了 API 返回错误：code={result.get('code')}, msg={result.get('msg')}")
                logger.error("[JIZHILE] API error: code=%s, msg=%s",
                           result.get('code'), result.get('msg'))
                sys.exit(1)

            # 提取费用信息
            cost = result.get("cost", 0)
            remain_money = result.get("remain_money", 0)
            note = result.get("note", "")
            total = result.get("total", 0)
            total_page = result.get("total_page", 0)

            # 打印费用信息
            print(f"📥 [极致了 API] 请求成功")
            print(f"   费用说明：{note}")
            print(f"   本次消费：{cost:.2f} 元")
            print(f"   账户余额：{remain_money:.2f} 元")
            print(f"   数据总量：{total} 条 | 总页数：{total_page}")
            logger.info("[JIZHILE] Cost: %s yuan, Balance: %s yuan, Total: %d articles",
                       cost, remain_money, total)

            # 映射数据
            candidates = []
            data_items = result.get("data", [])
            for item in data_items[:15]:
                candidates.append({
                    "id": item.get("url", ""),
                    "source": "微信公众号 (极致了)",
                    "title": item.get("title", ""),
                    "author": item.get("mp_nickname", "未知公众号"),
                    "likes": int(item.get("zan_num", 0)),
                    "comments": int(item.get("read_num", 0)),
                    "score": float(item.get("hot", 0))
                })

            # 保存分页状态
            state['jizhile_page_index'] = page
            logger.info("[JIZHILE] Saved page index: %d", page)

            return candidates

        except requests.exceptions.Timeout:
            print("❌ 请求极致了 API 超时，请检查网络连接")
            logger.error("[JIZHILE] Request timeout")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求极致了 API 失败：{e}")
            logger.error("[JIZHILE] Request failed: %s", e, exc_info=True)
            sys.exit(1)
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            print(f"❌ 解析极致了 API 响应失败：{e}")
            logger.error("[JIZHILE] Parse response failed: %s", e, exc_info=True)
            sys.exit(1)

    def run_discovery(self, keyword=None, refresh=True, last_id=None):
        """
        [卡点 1 之前] 嗅探系统 (次幂数据版)
        抓取微信爆款文章的热点。

        翻页逻辑：
        - 新一轮（默认）：refresh=True，不带 last_id，直接获取最新
        - 同一轮内（换一批）：refresh=False，带 last_id 继续翻页
        """
        import requests
        logger.info("启动 run_discovery | keyword=%s, refresh=%s, last_id=%s", keyword, refresh, last_id)
        state = self.load_state()
        saved_industry = state.get('industry')

        # ============================================================
        # [胡老板要求] 每当启动新一轮 discovery 时，全面重置状态
        # 避免上一轮流程卡在中间状态（waiting_for_content_review 等）
        # 影响新一轮业务逻辑
        # ============================================================
        if refresh:
            logger.info("[DISCOVERY] 新一轮选题开始，全面重置中间状态 | current_step=%s", state.get('current_step'))
            # 保留行业配置和关键持久化配置
            keep_fields = {'industry', 'candidates_page_size', 'candidates_total'}
            # 需要清理的上一轮流程相关字段
            reset_fields = [
                'current_step', 'selected_topic', 'cover_image', 'script_approved',
                'article_approved', 'is_generating_cover', 'last_discovery_time',
                'draft_file', 'video_script', 'topic_context', 'last_id',
                'cimi_last_id', 'candidates_page_index', 'candidates',
                'last_candidates', 'article_images', 'content_category',
                'source_selection_pending', 'step'
            ]
            for field in reset_fields:
                state.pop(field, None)
            state['current_step'] = 'idle'  # 重置为初始状态，等待新的 discovery 结果
            logger.info("[DISCOVERY] 状态重置完成，进入 idle | industry=%s", saved_industry)
        else:
            # 同一轮内换一批，只清分页相关
            current_step = state.get('current_step', '')
            if current_step in ['published_to_draft', 'published']:
                logger.info("检测到已发布状态 (%s)，开启新一轮 discovery，清空 last_id", current_step)
                state.pop('cimi_last_id', None)
                state.pop('candidates_page_index', None)
                state['candidates'] = []
                state['last_candidates'] = []

        # refresh=True 表示获取最新选题，不使用缓存的 last_id
        # refresh=False 表示使用缓存的 last_id 继续翻页
        if not refresh:
            if last_id is None:
                last_id = state.get('cimi_last_id')
                if last_id:
                    logger.info("使用缓存的 last_id: %s", last_id)
        else:
            # refresh=True 时，只有命令行没传 last_id 才清空，获取最新选题
            # 如果命令行明确传了 --last_id，则尊重用户输入
            if last_id is None:
                logger.info("refresh=True 且未传 --last_id，获取最新选题")
            else:
                logger.info("refresh=True 但命令行传了 --last_id=%s，尊重用户输入", last_id)

        # 选择 API Provider
        provider = os.getenv("HOT_ARTICLE_PROVIDER", "jizhile")

        if provider == "jizhile":
            print("[嗅探系统] 启动 [嗅探子系统 - 极致了 API]...")
            logger.info("[DISCOVERY] Using provider: jizhile")
            candidates = self._fetch_from_jizhile(refresh, state)
        else:
            # 使用次幂 API，需要先获取分类
            cimi_category_en, cimi_category_cn = self._get_cimi_category(keyword, saved_industry, state)
            print("[嗅探系统] 启动 [嗅探子系统 - 次幂数据版]...")
            logger.info("[DISCOVERY] Using provider: cimi")
            candidates = self._fetch_from_cimi(refresh, state, last_id, cimi_category_en)

        # 展示和保存候选列表
        print(f"\n=== ✨ 今日推荐 Top {len(candidates)} 爆款选题 === (数据来源：{provider})")
        logger.info("[DISCOVERY] Displaying %d recommendations", len(candidates))
        for idx, c in enumerate(candidates, 1):
            print(f"{idx}. [{c['source']}] [{c['title']}]({c['id']})")
            print(f"👤 {c['author']} | 👁️ 阅读：{c.get('comments', 0)} | 👍 赞：{c.get('likes', 0)} | 🔥 热度：{c.get('score', 0)}")
            logger.info("[DISCOVERY] Displaying candidate: %s", c["title"][:30])
        print("===================================")
        logger.info("[DISCOVERY] Display completed")

        state['current_step'] = "discovery_done"
        state['last_sync'] = datetime.now().isoformat()
        state['candidates'] = candidates
        state['last_candidates'] = candidates  # 保存用于分页浏览
        state['candidates_page_index'] = 1  # 重置页码
        self.save_state(state)

    def _get_cimi_category(self, keyword, saved_industry, state) -> tuple:
        """
        获取次幂 API 分类（仅在使用次幂 API 时调用）

        Returns:
            (category_en, category_cn) 元组
        """
        categories = {
            "1": ("xiaolvshu", "小绿书"), "2": ("yuer", "育儿"), "3": ("keji", "科技"),
            "4": ("tiyu", "体育健身"), "5": ("caijing", "财经"), "6": ("meishi", "美食"),
            "7": ("yiliao", "医疗"), "8": ("yule", "娱乐"), "9": ("qinggan", "情感"),
            "10": ("lishi", "历史"), "11": ("junshi", "军事国际"), "12": ("shishang", "美妆时尚"),
            "13": ("wenhua", "文化"), "14": ("qiche", "汽车"), "15": ("youxi", "游戏"),
            "16": ("lvyou", "旅游"), "17": ("fangchan", "房产"), "18": ("jiangkang", "健康养生"),
            "19": ("zhichang", "职场"), "20": ("sheying", "摄影"), "21": ("zixun", "资讯热点"),
            "22": ("jiaoyu", "教育"), "23": ("biancheng", "开发者"), "24": ("dianying", "影视"),
            "25": ("meizhuang", "美妆"), "26": ("shenghuo", "生活"), "27": ("shuma", "数码"),
            "28": ("meiti", "媒体"), "29": ("mengchong", "宠物"), "30": ("sannong", "三农"),
            "31": ("xingzuo", "星座命理"), "32": ("gaoxiao", "搞笑"), "33": ("dongman", "动漫"),
            "34": ("jiaju", "家居"), "35": ("kexue", "科学"), "36": ("yingxiao", "商业营销"),
            "37": ("chuangye", "个人成长"), "38": ("bizhi", "壁纸头像"), "39": ("falv", "法律"),
            "40": ("minsheng", "民生"), "41": ("wenan", "文案"), "42": ("tizhi", "体制"),
            "43": ("wenzhai", "文摘"), "44": ("ai", "AI"), "45": ("other", "其它")
        }

        def find_category(kw):
            kw = str(kw).strip()
            if kw in categories: return categories[kw]
            for key, val in categories.items():
                if kw == val[0] or kw == val[1]:
                    return val
            return None

        target_category = None

        if keyword:
            matched = find_category(keyword)
            if matched:
                target_category = matched
                state['industry'] = matched[0]
                self.save_state(state)
                print(f"✅ 已将您的专属行业更新为：{matched[1]}")
                logger.info("[DISCOVERY] Industry matched: %s", matched[1])
            else:
                print(f"❌ 错误：未知分类 '{keyword}'")
                logger.error("[STATE] Save failed: Invalid category")
                sys.exit(0)
        elif saved_industry:
            matched = find_category(saved_industry)
            if matched:
                target_category = matched
                print(f"✨ 检测到已保存的专属行业：{matched[1]} (如需更改，请在命令后加 --keyword <新序号>)")
                logger.info("[DISCOVERY] Using saved industry: %s", matched[1])

        if not target_category:
            print("👋 请配置您的专属行业/领域 (次幂爆款分类)，系统将自动保存以便日后为您自动获取爆文：")
            logger.info("[DISCOVERY] Displaying category list")
            items = list(categories.items())
            for i in range(0, len(items), 5):
                chunk = items[i:i+5]
                line = "  ".join(f"{k}. {v[1]:<6}" for k, v in chunk)
                print(line)
                logger.info("[DISCOVERY] Displaying category list")
            print("⚠️ [ACTION_REQUIRED] 等待用户输入：请通过交互通道回复你想抓取的行业序号（如'3'表示科技）。")
            logger.warning("[STATE] State file not found, starting fresh")
            sys.exit(0)

        return target_category

    def _fetch_from_cimi(self, refresh: bool, state: dict, last_id: Optional[str], cimi_category_en: str) -> list:
        """
        从次幂数据 API 获取微信爆款文章

        Args:
            refresh: True 表示获取最新，False 表示继续翻页
            state: 当前状态字典
            last_id: 上次请求的 last_id
            cimi_category_en: 分类英文名称

        Returns:
            candidates 列表
        """
        import requests

        # refresh=False 时使用缓存的 last_id
        if not refresh:
            if last_id is None:
                last_id = state.get('cimi_last_id')
                if last_id:
                    logger.info("使用缓存的 last_id: %s", last_id)
        else:
            if last_id is None:
                logger.info("refresh=True 且未传 --last_id，获取最新选题")
            else:
                logger.info("refresh=True 但命令行传了 --last_id=%s，尊重用户输入", last_id)

        cimi_app_id = os.getenv("CIMI_APP_ID")
        cimi_app_secret = os.getenv("CIMI_APP_SECRET")
        if not cimi_app_id or not cimi_app_secret:
            print("❌ 未在环境变量中找到 CIMI_APP_ID 或 CIMI_APP_SECRET，请先执行 run_setup 或修改 .env 文件。")
            logger.error("[CIMI] Missing credentials")
            sys.exit(1)

        api_base = "https://api.cimidata.com"
        headers = {"Content-Type": "application/json"}

        print("📥 [1/2] 正在获取次幂数据 Access Token...")
        try:
            token_payload = {"app_id": cimi_app_id, "app_secret": cimi_app_secret}
            logger.info(">>> [HTTP REQUEST] POST %s", f"{api_base}/api/v2/token")
            token_resp = requests.post(f"{api_base}/api/v2/token", json=token_payload, headers=headers, timeout=10)
            logger.info(">>> [HTTP RESPONSE] Status: %s", token_resp.status_code)
            token_resp.raise_for_status()
            access_token = token_resp.json()["data"]["access_token"]
            logger.info(">>> [TOKEN OK] access_token=%s", access_token[:10] + "..." if len(access_token) > 10 else access_token)
        except Exception as e:
            print(f"❌ 请求 Token 接口时发生异常：{e}")
            logger.error("[CIMI] Token request failed: %s", e, exc_info=True)
            sys.exit(1)

        print("📥 [2/2] 正在拉取爆款文章列表...")
        candidates = []
        try:
            payload = {"category": cimi_category_en, "read_num": 1000}
            if last_id:
                payload["last_id"] = last_id

            logger.info(">>> [HTTP REQUEST] POST %s", f"{api_base}/api/v2/hot/articles?access_token={access_token[:10]}...")
            articles_resp = requests.post(f"{api_base}/api/v2/hot/articles?access_token={access_token}",
                                         json=payload, headers=headers, timeout=15)
            logger.info(">>> [HTTP RESPONSE] Status: %s", articles_resp.status_code)
            articles_data = articles_resp.json()
            items = articles_data.get("data", {}).get("items", [])
            for item in items[:15]:
                candidates.append({
                    "id": item.get("content_url"),
                    "source": "微信公众号 (次幂)",
                    "title": item.get("title", ""),
                    "likes": int(item.get("like_num", 0)),
                    "comments": int(item.get("read_num", 0)),
                    "author": item.get("nickname", "未知公众号"),
                    "score": int(item.get("hotness", 0))
                })

            # Save pagination cursor if available
            new_last_id = articles_data.get("data", {}).get("last_id")
            if new_last_id:
                state['cimi_last_id'] = str(new_last_id)
        except Exception as e:
            print(f"❌ 请求获取文章接口时发生异常：{e}")
            logger.error("[CIMI] Request failed: %s", e, exc_info=True)
            sys.exit(1)

        return candidates
        
        categories = {
            "1": ("xiaolvshu", "小绿书"), "2": ("yuer", "育儿"), "3": ("keji", "科技"), 
            "4": ("tiyu", "体育健身"), "5": ("caijing", "财经"), "6": ("meishi", "美食"), 
            "7": ("yiliao", "医疗"), "8": ("yule", "娱乐"), "9": ("qinggan", "情感"), 
            "10": ("lishi", "历史"), "11": ("junshi", "军事国际"), "12": ("shishang", "美妆时尚"), 
            "13": ("wenhua", "文化"), "14": ("qiche", "汽车"), "15": ("youxi", "游戏"), 
            "16": ("lvyou", "旅游"), "17": ("fangchan", "房产"), "18": ("jiangkang", "健康养生"), 
            "19": ("zhichang", "职场"), "20": ("sheying", "摄影"), "21": ("zixun", "资讯热点"), 
            "22": ("jiaoyu", "教育"), "23": ("biancheng", "开发者"), "24": ("dianying", "影视"), 
            "25": ("meizhuang", "美妆"), "26": ("shenghuo", "生活"), "27": ("shuma", "数码"), 
            "28": ("meiti", "媒体"), "29": ("mengchong", "宠物"), "30": ("sannong", "三农"), 
            "31": ("xingzuo", "星座命理"), "32": ("gaoxiao", "搞笑"), "33": ("dongman", "动漫"), 
            "34": ("jiaju", "家居"), "35": ("kexue", "科学"), "36": ("yingxiao", "商业营销"), 
            "37": ("chuangye", "个人成长"), "38": ("bizhi", "壁纸头像"), "39": ("falv", "法律"), 
            "40": ("minsheng", "民生"), "41": ("wenan", "文案"), "42": ("tizhi", "体制"), 
            "43": ("wenzhai", "文摘"), "44": ("ai", "AI"), "45": ("other", "其它")
        }

        def find_category(kw):
            kw = str(kw).strip()
            if kw in categories: return categories[kw]
            for key, val in categories.items():
                if kw == val[0] or kw == val[1]:
                    return val
            return None

        target_category = None
        
        if keyword:
            matched = find_category(keyword)
            if matched:
                target_category = matched
                state['industry'] = matched[0]
                self.save_state(state)
                print(f"✅ 已将您的专属行业更新为: {matched[1]}")
                logger.info("[DISCOVERY] Industry matched: %s", matched[1])
            else:
                print(f"❌ 错误: 未知分类 '{keyword}'")
                logger.error("[STATE] Save failed: %s", e, exc_info=True)
        elif saved_industry:
            matched = find_category(saved_industry)
            if matched:
                target_category = matched
                print(f"✨ 检测到已保存的专属行业: {matched[1]} (如需更改，请在命令后加 --keyword <新序号>)")
                logger.info("[DISCOVERY] Using saved industry: %s", matched[1])

        if not target_category:
            print("👋 请配置您的专属行业/领域(次幂爆款分类)，系统将自动保存以便日后为您自动获取爆文：")
            logger.info("[DISCOVERY] Displaying category list")
            items = list(categories.items())
            for i in range(0, len(items), 5):
                chunk = items[i:i+5]
                line = "  ".join(f"{k}. {v[1]:<6}" for k, v in chunk)
                print(line)
                logger.info("[DISCOVERY] Displaying category list")
            print("⚠️ [ACTION_REQUIRED] 等待用户输入：请通过交互通道回复你想抓取的行业序号（如'3'表示科技）。")
            logger.warning("[STATE] State file not found, starting fresh")
            sys.exit(0)

        cimi_category_en, cimi_category_cn = target_category
        print(f"🔍 正在检索微信爆款文章 (分类: {cimi_category_cn})...")
        logger.info("[DISCOVERY] Searching WeChat articles, category=%s", cimi_category_cn)

        cimi_app_id = os.getenv("CIMI_APP_ID")
        cimi_app_secret = os.getenv("CIMI_APP_SECRET")
        if not cimi_app_id or not cimi_app_secret:
            print("❌ 未在环境变量中找到 CIMI_APP_ID 或 CIMI_APP_SECRET，请先执行 run_setup 或修改 .env 文件。")
            logger.error("[STATE] Save failed: %s", e, exc_info=True)
            sys.exit(1)

        api_base = "https://api.cimidata.com"
        headers = {"Content-Type": "application/json"}
        
        print("📥 [1/2] 正在获取次幂数据 Access Token...")
        logger.info("[POST] Publishing step completed")
        try:
            # ========== 网络请求日志：Token 请求 ==========
            token_payload = {"app_id": cimi_app_id, "app_secret": cimi_app_secret}
            logger.info(">>> [HTTP REQUEST] POST %s", f"{api_base}/api/v2/token")
            logger.info(">>> [REQUEST PAYLOAD] %s", json.dumps(token_payload, ensure_ascii=False))
            # ===========================================
            token_resp = requests.post(f"{api_base}/api/v2/token", json=token_payload, headers=headers, timeout=10)
            logger.info(">>> [HTTP RESPONSE] Status: %s", token_resp.status_code)
            token_resp.raise_for_status()
            access_token = token_resp.json()["data"]["access_token"]
            logger.info(">>> [TOKEN OK] access_token=%s", access_token[:10] + "..." if len(access_token) > 10 else access_token)
        except Exception as e:
            print(f"❌ 请求 Token 接口时发生异常: {e}")
            logger.error("[STATE] Save failed: %s", e, exc_info=True)
            sys.exit(1)

        print("📥 [2/2] 正在拉取爆款文章列表...")
        logger.info("[DISCOVERY] Fetching hot articles from CIMIPA API")
        candidates = []
        try:
            payload = {"category": cimi_category_en, "read_num": 1000}
            if last_id:
                payload["last_id"] = last_id

            # ========== 网络请求日志：文章列表请求 ==========
            logger.info(">>> [HTTP REQUEST] POST %s", f"{api_base}/api/v2/hot/articles?access_token={access_token[:10]}...")
            logger.info(">>> [REQUEST PAYLOAD] category=%s, read_num=1000, last_id=%s", cimi_category_en, last_id)
            # ==============================================
            articles_resp = requests.post(f"{api_base}/api/v2/hot/articles?access_token={access_token}",
                                         json=payload, headers=headers, timeout=15)
            logger.info(">>> [HTTP RESPONSE] Status: %s", articles_resp.status_code)
            articles_data = articles_resp.json()
            items = articles_data.get("data", {}).get("items", [])
            for item in items[:15]:
                candidates.append({
                    "id": item.get("content_url"), "source": "微信公众号(次幂)", "title": item.get("title", ""),
                    "likes": int(item.get("like_num", 0)), "comments": int(item.get("read_num", 0)),
                    "author": item.get("nickname", "未知公众号"), "score": int(item.get("hotness", 0))
                })
            
            # Save pagination cursor if available
            new_last_id = articles_data.get("data", {}).get("last_id")
            if new_last_id:
                state['cimi_last_id'] = str(new_last_id)
        except Exception as e:
            print(f"❌ 请求获取文章接口时发生异常: {e}")
            logger.error("[STATE] Save failed: %s", e, exc_info=True)
            sys.exit(1)

        print(f"\n=== ✨ 今日推荐 Top {len(candidates)} 爆款选题 === (数据来源: 次幂)")
        logger.info("[DISCOVERY] Displaying %d recommendations", len(candidates))
        for idx, c in enumerate(candidates, 1):
            print(f"{idx}. [{c['source']}] [{c['title']}]({c['id']})")
            print(f"👤 {c['author']} | 👁️ 阅读: {c.get('comments', 0)} | 👍 赞: {c.get('likes', 0)} | 🔥 热度：{c.get('score', 0)}")
            logger.info("[DISCOVERY] Displaying candidate: %s", c["title"][:30])
        print("===================================")
        logger.info("[DISCOVERY] Display completed")
        
        state['current_step'] = "discovery_done"
        state['last_sync'] = datetime.now().isoformat()
        state['candidates'] = candidates
        state['last_candidates'] = candidates  # 保存用于分页浏览
        state['candidates_page_index'] = 1  # 重置页码
        self.save_state(state)

    def run_next_discovery(self):
        logger.info("启动 run_next_discovery 分页浏览")
        state = self.load_state()
        candidates = state.get('candidates', [])
        page_index = state.get('candidates_page_index', 1)
        page_size = state.get('candidates_page_size', 5)
        
        start_idx = (page_index - 1) * page_size
        end_idx = start_idx + page_size
        page_items = candidates[start_idx:end_idx]
        
        print(f"\n=== ✨ 今日推荐 (第 {page_index} 页) === (数据来源: 缓存)")
        logger.info("[DISCOVERY] Candidates saved to state")
        for idx, c in enumerate(page_items, start_idx + 1):
            source = c.get('source', '微信公众号')
            title = c.get('title', '未知文章')
            url = c.get('id', '')
            author = c.get('author', '未知')
            reads = c.get('comments', c.get('read', 0))
            likes = c.get('likes', 0)
            score = c.get('score', c.get('hotness', 0))
            print(f"{idx}. [{source}] [{title}]({url})")
            logger.info("[DISCOVERY] Using cached last_id: %s", last_id)
            print(f"👤 {author} | 👁️ 阅读: {reads} | 👍 赞: {likes} | 🔥 热度：{score}")
            logger.info("[DISCOVERY] Starting from ID: %s", last_id)
        print("===================================")
        logger.info("[DISCOVERY] Fetching batch of articles")

    def _extract_article_content(self, article_url, selected=None):
        """通用素材提取服务：支持网页解析、次幂 API 保底、抖音文案提取。"""
        logger.info("启动内容提取 | url=%s", str(article_url)[:60])
        import subprocess, sys, os, re, json, requests
        raw_content = ""
        source = (selected or {}).get("source", "微信")
        title = (selected or {}).get("title", "素材")

        if source in ["公众号", "微信", "微信公众号(次幂)", "自定义"] or str(article_url).startswith("http"):
            # 1. url-reader 引擎
            try:
                reader_path = os.path.join(self.workspace, 'url-reader-0.1.1', 'scripts')
                if reader_path not in sys.path: sys.path.insert(0, reader_path)
                from url_reader import read_url
                result = read_url(article_url, verbose=False)
                if result.get("success"):
                    raw_content = result.get("content", "")
            except ImportError as e:
                logger.warning("url_reader 模块导入失败：%s", e)
            except Exception as e:
                logger.warning("url_reader 内容提取失败：%s", e)

            # 2. 次幂 API 保底
            if not raw_content or len(raw_content) < 50:
                try:
                    cid, csec = os.getenv("CIMI_APP_ID"), os.getenv("CIMI_APP_SECRET")
                    if cid and csec:
                        auth_resp = requests.post("https://api.cimidata.com/api/v2/token", json={"app_id": cid, "app_secret": csec}, timeout=10)
                        auth_resp.raise_for_status()
                        auth = auth_resp.json()
                        token = auth.get("data", {}).get("access_token", "")
                        if token:
                            detail_resp = requests.post(f"https://api.cimidata.com/api/v3/articles/detail?access_token={token}", json={"url": article_url}, timeout=20)
                            detail_resp.raise_for_status()
                            dr = detail_resp.json()
                            raw_content = re.sub(r'<[^>]+>', ' ', dr["data"].get("html", "")).strip()
                except requests.exceptions.RequestException as e:
                    logger.warning("次幂 API 请求失败：%s", e)
                except (KeyError, TypeError) as e:
                    logger.warning("次幂 API 响应解析失败：%s", e)

        elif source == "抖音":
            try:
                dj = os.path.join(self.workspace, "douyin-download-1.2.0", "douyin.js")
                if not os.path.exists(dj):
                    logger.warning("抖音提取脚本不存在：%s", dj)
                    return "（系统保底）抖音提取脚本未找到"
                out = os.path.join(os.getcwd(), 'cache', 'douyin_extract')
                os.makedirs(out, exist_ok=True)
                r = subprocess.run(["node", dj, "extract", article_url, "-o", out, "--no-segment"], capture_output=True, text=True, encoding="utf-8", timeout=60)
                if r.returncode != 0:
                    logger.warning("抖音提取失败：%s", r.stderr)
                    return "（系统保底）抖音提取失败"
                m = re.search(r"保存位置:\s*(.+?\.md)", r.stdout)
                if m:
                    with open(m.group(1).strip(), 'r', encoding='utf-8') as f:
                        raw_content = f.read().split("## 文案内容")[-1].strip()
            except subprocess.TimeoutExpired:
                logger.warning("抖音提取超时")
                raw_content = "（系统保底）抖音提取超时"
            except Exception as e:
                logger.warning("抖音提取异常：%s", e)

        if not raw_content or len(raw_content) < 30:
            raw_content = f"（系统保底）关于《{title}》的分析：核心是极致行动与复利思维。"
        return raw_content

    def _extract_title(self, content):
        """从内容中提取标题"""
        if not content:
            return None

        import re
        lines = content.strip().split('\n')
        # 时间戳正则：0:00, 0:00- , [0:00], （0:00），# 0:00 等
        timestamp_pattern = re.compile(r'^(\d{1,2}:\d{2}(?::\d{2})?[\s\--\.]*)|^#\s*\d{1,2}:\d{2}|^[\[【（(].*\d{1,2}:\d{2}')
        for line in lines[:10]:
            line = line.strip()
            if not line:
                continue
            # 跳过时间戳行
            if timestamp_pattern.match(line):
                continue
            if len(line) < 5 or len(line) > 120:
                continue
            # 去掉常见前缀
            line = re.sub(r'^(#{1,6}\s+|【[^】]+】|\[[^\]]+\]|#+\s*|●\s*|-\s*)', '', line)
            if line and len(line) >= 5:
                return line
        return None

    def _extract_author(self, content):
        """从内容中提取作者"""
        if not content:
            return None

        import re
        # 使用独立模式匹配全角和半角冒号，避免字符类问题
        match = re.search(r'作者：\s*([^\n]{2,20})', content)
        if match:
            return match.group(1).strip()
        match = re.search(r'作者:\s*([^\n]{2,20})', content)
        if match:
            return match.group(1).strip()
        match = re.search(r'author:\s*([^\n]{2,20})', content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r'出自：\s*([^\n]{2,20})', content)
        if match:
            return match.group(1).strip()
        match = re.search(r'出自:\s*([^\n]{2,20})', content)
        if match:
            return match.group(1).strip()
        return None

    def _extract_video_content(self, url):
        """提取视频文案（ASR）"""
        import os
        import subprocess
        import re

        if "douyin.com" in url:
            logger.info(f"[视频提取] 正在从抖音提取文案：{url}")
            douyin_js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "douyin-download-1.2.0", "douyin.js")
            output_dir = os.path.join(os.getcwd(), 'cache', 'douyin_extract')
            os.makedirs(output_dir, exist_ok=True)

            if not os.getenv("SILI_FLOW_API_KEY"):
                logger.warning("[视频提取] 未设置 SILI_FLOW_API_KEY，无法提取语音")
                return None

            cmd = ["node", douyin_js_path, "extract", url, "-o", output_dir, "--no-segment"]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=os.environ)
                if res.returncode == 0:
                    # 使用任意字符匹配冒号（避免字符类编码问题）
                    match = re.search(r"保存位置.\s*(.+?\.md)", res.stdout)
                    if match:
                        md_path = match.group(1).strip()
                        if os.path.exists(md_path):
                            with open(md_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            parts = content.split("## 文案内容")
                            if len(parts) > 1:
                                logger.info(f"[视频提取] 提取成功：{len(parts[-1].strip())} 字")
                                return parts[-1].strip()
                logger.warning(f"[视频提取] douyin.js 返回非零状态码：{res.returncode}")
            except Exception as e:
                logger.error(f"[视频提取] douyin.js 解析失败：{e}")
        else:
            logger.debug(f"[视频提取] 非抖音 URL，跳过：{url}")
        return None

    def _generate_summary(self, content, title):
        """使用 AI 生成文章摘要"""
        if not content:
            return ""

        import os
        import openai

        # 取前 3000 字进行摘要（足够生成准确摘要）
        truncated = content[:3000] if len(content) > 3000 else content

        prompt = f"""请为以下文章生成一个简洁的中文摘要，100 字以内，直接输出摘要内容，不需要其他说明。
文章标题：{title}
文章内容：
{truncated}
摘要："""

        try:
            client = openai.OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL")
            )
            model = os.getenv("LLM_MODEL_ID", "deepseek-chat")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
                timeout=30
            )
            summary = response.choices[0].message.content.strip()
            logger.info(f"[摘要生成] 成功生成：{len(summary)} 字")
            return summary
        except Exception as e:
            logger.warning(f"[摘要生成] AI 生成失败：{e}，降级到前 200 字")
            # 降级方案：返回前 200 字
            return truncated[:200] + "..."

    def _send_url_preview_card(self, title, author, source, summary, url, content_type, extra_info):
        """发送内容预览卡"""
        logger.info(f"[飞书卡片] 准备发送预览卡：{title}")

        try:
            # 使用模块级别的导入
            if build_url_preview_card is None or send_card is None or get_token is None:
                raise ImportError("飞书卡片模块未导入")

            # 构建卡片内容
            card = build_url_preview_card(title, author, source, summary, url, content_type, extra_info)

            # 获取 token 并发送
            token = get_token()
            receive_id = os.getenv("FEISHU_RECEIVE_ID", "")
            if token and receive_id:
                success = send_card(token, receive_id, card)
                if success:
                    logger.info("[飞书卡片] 预览卡发送成功")
                    print("✅ 预览卡发送成功")
                else:
                    logger.warning("[飞书卡片] 预览卡发送失败")
                    print("⚠️ 预览卡发送失败")
            else:
                logger.warning("[飞书卡片] 缺少 FEISHU_RECEIVE_ID 或 token")
                print("⚠️ 预览卡发送失败：缺少配置")
        except ImportError as e:
            logger.error(f"[飞书卡片] 模块导入失败：{e}")
            print(f"⚠️ 预览卡发送失败：{e}")
        except Exception as e:
            logger.error(f"[飞书卡片] 发送异常：{e}")
            print(f"⚠️ 预览卡发送异常：{e}")

    def _select_topic(self, topic_id_or_cmd, candidates, state):
        """
        从多种来源路由选题数据

        Args:
            topic_id_or_cmd: 传入的参数（可能是字典、ID 或命令）
            candidates: 候选列表
            state: 当前状态字典

        Returns:
            selected: 选中的选题字典
        """
        if isinstance(topic_id_or_cmd, dict):
            logger.info("[选题路由] 直接传入字典")
            return topic_id_or_cmd

        tid = str(topic_id_or_cmd).strip('"').strip("'")
        # 强化解析：剥离 rewrite_ 或 insight_ 等可能存在的动作前缀
        guid_to_find = tid.split('_')[-1] if '_' in tid else tid

        # 1. 持久化路由
        local_map = os.path.join(self.workspace, '.workflow_state.json')
        if os.path.exists(local_map):
            try:
                with open(local_map, 'r', encoding='utf-8') as f:
                    sd = json.load(f)
                    # 尝试多种匹配模式
                    tm = sd.get('topic_map', {})
                    if guid_to_find in tm:
                        selected = tm[guid_to_find]
                        logger.info(f"[选题路由] 从持久化库解析：{selected.get('title')}")
                        return selected
                    elif tid in tm:
                        selected = tm[tid]
                        logger.info(f"[选题路由] 从持久化库解析：{selected.get('title')}")
                        return selected
            except Exception as e:
                logger.warning(f"[选题路由] 持久化库读取失败：{e}")

        # 2. 缓存路由
        if candidates:
            for c in candidates:
                if str(c.get('id')) == tid or str(c.get('title')) == tid:
                    logger.info(f"[选题路由] 从候选列表匹配：{c.get('title')}")
                    return c

        # 3. 从上下文沿用
        if state and state.get('topic_context'):
            logger.info(f"[选题路由] 从会话上下文恢复：{state['topic_context'].get('title')}")
            return state['topic_context']

        # 4. 兜底
        logger.warning(f"[选题路由] 未找到匹配，使用默认对象：{tid}")
        return {"id": str(tid), "title": "自定义素材", "source": "自定义"}

    def run_repurpose(self, topic_id_or_cmd):
        """
        [IP 改写引擎 V2] 支持智能场景匹配、多源抓取保底、联网补全实时背景。
        """
        logger.info("启动 run_repurpose | topic=%s", str(topic_id_or_cmd)[:60])
        import subprocess, sys, os, re, json, requests
        from datetime import datetime
        state = self.load_state()
        
        # --- 1. 选题路由 ---
        candidates = state.get("candidates", []) + state.get("last_candidates", [])
        selected = self._select_topic(topic_id_or_cmd, candidates, state)

        title_val = selected.get("title", "未命名素材")
        source_val = selected.get("source", "微信")
        print(f"🚀 正在重塑内容：《{title_val}》 (源：{source_val})")
        logger.info("[REPURPOSE] Starting content reshaping: title=%s", title_val[:30])

        # --- 2. 素材提取 ---
        raw_content = self._extract_article_content(str(selected.get("id", "")), selected)

        # --- 3. 变量初始化 ---
        api_key = os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        mid = os.environ.get("LLM_MODEL_ID", "deepseek-chat")
        ip = os.environ.get("AUTHOR_IP_NAME", "大胡")
        wewrite_used = False
        content_category = "insight"
        final_content = ""

        # --- 4. WeWrite 改写引擎 ---
        if WEWRITE_XIAOHU_AVAILABLE:
            try:
                config = WeWriteConfig()
                if config.is_wewrite_available():
                    print(f"🤖 [v1.2] 使用 WeWrite 写作框架进行改写...")
                    logger.info("使用 WeWrite 引擎进行改写")

                    wewrite_engine = WeWriteEngine(config.get_deepseek_config(), logger)
                    rewrite_result = wewrite_engine.rewrite(raw_content, {'ip_name': ip})

                    if rewrite_result.success:
                        final_content = rewrite_result.content
                        content_category = "insight"
                        wewrite_used = True
                        print(f"✅ WeWrite 改写成功：{len(final_content)} 字")
                        logger.info("[REPURPOSE] WeWrite rewrite successful: %d chars", len(final_content))
            except WeWriteError as e:
                print(f"⚠️ WeWrite 失败，降级到 prompts_manager: {e}")
                logger.warning("WeWrite 失败，降级到 prompts_manager")

        if not wewrite_used and api_key and "your_api_key" not in api_key:
            import httpx
            print(f"🤖 执行场景化创作 (模型: {mid})...")
            logger.info("[REPURPOSE] Executing scenario creation, model=%s", mid)
            try:
                pm_path = os.path.join(self.workspace, "prompts_manager.json")
                conf = {}
                if os.path.exists(pm_path):
                    with open(pm_path, 'r', encoding='utf-8') as f: conf = json.load(f)
                else:
                    # prompts_manager.json 不存在时使用内置默认 prompt
                    logger.info("[REPURPOSE] prompts_manager.json 不存在，使用默认 prompt")
                    conf = {
                        "classifier_prompt": "分析以下内容的核心意图，从以下类别中选择一个最匹配的：insight(观点洞察), story(故事叙述), tutorial(教程指南), news(新闻资讯)。只返回类别名称。\n\n预览内容：{preview_content}",
                        "templates": {
                            "insight": {
                                "prompt": """你现在的身份是自媒体领域的顶级极客大 IP。
任务：对提供的素材进行口语化、节奏明快的改写。
要求：
- 忠实原文核心事实
- 开篇直接抛出核心观点
- 使用###小标题分隔段落
- 每 500 字插入金句（加黑加粗并使用>引用块）
- 结尾加上行动号召和微信号

作者 IP 名称：{author_ip_name}
微信号：{wechat_id}"""
                            }
                        }
                    }

                cat = "insight"
                if conf:
                    print(f"🧠 [1/2] 意图路由分析...")
                    logger.info("[REPURPOSE] Intent routing analysis")
                    raw_ci = conf.get("classifier_prompt", "")
                    if isinstance(raw_ci, list): raw_ci = "\n".join(raw_ci)
                    ci = raw_ci.format(preview_content=raw_content[:1500])
                    try:
                        with httpx.Client(timeout=40) as cl:
                            cr = cl.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                               json={"model": mid, "messages": [{"role": "user", "content": ci}], "temperature": 0.1, "max_tokens": 10})
                            p_key = "".join(c for c in cr.json()["choices"][0]["message"]["content"].strip().lower() if c.isalnum())
                            if p_key in conf["templates"]: cat = p_key
                    except Exception: pass
                    content_category = cat  # 记录分类供后续排版使用

                    raw_prompt = conf["templates"].get(cat, conf["templates"]["insight"])["prompt"]
                    if isinstance(raw_prompt, list): raw_prompt = "\n".join(raw_prompt)
                    final_pmt = raw_prompt.format(author_ip_name=ip, wechat_id=os.environ.get("AUTHOR_WECHAT_ID", "此处添加微信号").strip("'\""))
                    
                    print(f"📝 [2/2] 深度创作中...")
                    logger.info("[REPURPOSE] Deep creation in progress")
                    with httpx.Client(timeout=300) as cl:
                        r = cl.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                            json={"model": mid, "messages": [{"role": "user", "content": f"{final_pmt}\n\n素材:\n{raw_content}"}], "temperature": 0.7})
                        final_content = r.json()["choices"][0]["message"]["content"]
                        print(f"✅ 生成完毕：{len(final_content)} 字")
                        logger.info("[REPURPOSE] Generation completed: %d chars", len(final_content))
            except Exception as e: print(f"❌ LLM 阶段故障: {e}")

        if not final_content:
            final_content = f"# {title_val}\n\n**[生成超时]**\n\n原文：\n{raw_content[:500]}..."

        # ==========================
        # 3. 输出 Drafts 归档与状态保存
        # ==========================
        ts = datetime.now().strftime('%Y%m%d%H%M')
        dr_root = os.path.join(self.workspace, 'drafts', datetime.now().strftime('%Y-%m-%d'))
        os.makedirs(dr_root, exist_ok=True)
        
        vs, ac, nt = "", final_content, ""
        import re
        parts = re.split(r"##\s*【?第二部分[^】\n]*】?", final_content)
        if len(parts) > 1:
            vs = re.sub(r"##\s*【?第一部分[^】\n]*】?", "", parts[0]).strip()
            ac = parts[1].strip()
            # 兼容多种格式的标题行提取
            tm = re.search(r"(?:【标题】|\[文章标题\]|标题)[：:\s]*(.*?)(?:\n|$)", ac)
            if tm:
                nt = tm.group(1).strip()
                ac = re.sub(r"(?:【标题】|\[文章标题\]|标题)[：:\s]*.*\n", "", ac, count=1).strip()
            
            # 顽固标签终结者：大模型有可能会死心眼地输出这些内部结构词，直接正则洗掉
            wash_pattern = r"(?m)^(?:【|\*\*)?(?:开篇|正文|收尾|结论|总结|引言|结语|结尾|金句|长文|短视频剧本|脚本|互动标签)(?:】|\*\*)?[：:\s\*]*"
            ac = re.sub(wash_pattern, "", ac).strip()
            vs = re.sub(wash_pattern, "", vs).strip()

        ap = os.path.join(dr_root, f"article_{ts}.md")
        with open(ap, "w", encoding='utf-8') as f:
            if nt: f.write(f"# {nt}\n\n")
            f.write(ac)
        
        generate_script = os.getenv("GENERATE_VIDEO_SCRIPT", "FALSE").upper() == "TRUE"
        sp = ""
        if generate_script:
            sp = os.path.join(dr_root, f"video_script_{ts}.md")
            with open(sp, "w", encoding='utf-8') as f:
                f.write(vs if vs else "未生成脚本")

        print(f"✅ 成果存档 [保存文件]：")
        logger.info("[REPURPOSE] Archiving results: article=%s", os.path.basename(ap))
        print(f"   article_path={ap}")
        if generate_script:
            logger.info("[REPURPOSE] Archiving results: script=%s", os.path.basename(sp))
            print(f"   script_path={sp}")
        
        state['current_step'] = "waiting_for_content_review"
        state['draft_file'] = ap
        if 'html_file' in state:
            del state['html_file']
        state['video_script'] = sp if generate_script else ""
        state['topic_context'] = selected
        if nt: state['topic_context']['title'] = nt
        # 保存文章分类，供发布时自动选择主题
        if 'content_category' in locals():
            state['content_category'] = content_category
            print(f"[REPURPOSE] 📂 文章分类已记录: {content_category}", flush=True)
        logger.info("[REPURPOSE] Saving generated content")
        self.save_state(state)

    def generate_image(self, prompt, model_type="seedream", size="1024*1024"):
        """
        集成多生图引擎支持
        """
        logger.info("启动 generate_image | model=%s", model_type)
        import requests
        import time
        if model_type == "seedream":
            api_key = os.getenv("ARK_API_KEY")
            if not api_key: return None
            url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            
            # 🚀 强制同步为用户提供的最新 API 规范 (Seedream 4.5)
            data = {
                "model": "doubao-seedream-5-0-260128",
                "prompt": prompt, # Prompt is now expected to be Chinese
                "size": size,
                "response_format": "url",
                "sequential_image_generation": "disabled",
                "stream": False,
                "watermark": False # Ensure watermark is always False
            }
            try:
                print(f"[视觉工程] 正在通过 Ark 调用火山引擎(Seedream 4.5/2.0) 渲染 {size} 比例资产...")
                logger.info("[VISUALS] Calling Ark API for image generation")
                r = requests.post(url, headers=headers, json=data, timeout=60)
                resp = r.json()
                img_url = resp.get("data", [{}])[0].get("url")
                if not img_url:
                    print(f"[ERROR] Volcengine API Response: {resp}")
                    logger.error("[VISUALS] Save failed, no url in response: %s", resp)
                return img_url
            except Exception as e:
                print(f"[ERROR] Volcengine generation failed: {e}")
                logger.error("[VISUALS] Save failed: %s", e, exc_info=True)
                return None
        else:
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key: 
                logger.error("DASHSCOPE_API_KEY 未配置")
                return None
            model_id = {"z": "z-image-turbo", "qwen": "qwen-image-2.0-pro", "wan": "wan2.6-t2i"}.get(model_type, "wan2.6-t2i")
            url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            data = {"model": model_id, "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]}, "parameters": {"size": size}}
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=60).json()
                return resp.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", [{}])[0].get("image")
            except Exception as e:
                logger.error("Dashscope generation failed: %s", e)
                return None

    def download_image_file(self, url, folder=None):
        logger.debug("下载图片 | url=%s", url[:60] if url else "")
        if not folder:
            folder = os.path.join(self.workspace, 'assets', datetime.now().strftime('%Y-%m-%d'))
        os.makedirs(folder, exist_ok=True)
        try:
            filename = f"gen_{datetime.now().strftime('%H%M%S')}.png"
            filepath = os.path.join(folder, filename)
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(filepath, "wb") as f: f.write(r.content)
                return filepath
            else:
                logger.error("图片下载失败，状态码: %d", r.status_code)
        except Exception as e:
            logger.error("图片下载异常: %s", e)
        return None
    def load_visual_config(self):
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'prompts_manager.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get('visual_config', {})
        except Exception as e:
            logger.error("加载视觉配置失败: %s", e)
        return {}

    def analyze_visuals(self, article_content, category="insight"):
        logger.info("启动 analyze_visuals | category=%s", category)
        import httpx
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key: return None
        
        v_config = self.load_visual_config()
        rules_text = "\n".join([f"- {r}" for r in v_config.get('base_principles', [])])
        style_match = v_config.get('style_matching', {}).get(category, {
            "rendering": "3d-render", "palette": "elegant", "mood": "balanced"
        })

        sys_p = f"""你是一个视觉分析专家。请为分类为 '{category}' 的自媒体文章规划视觉方案。
【核心设计红线】：{rules_text}
【视觉风格指导 (基于分类匹配)】：
- 渲染方案: {style_match.get('rendering')} | 色彩体系: {style_match.get('palette')} | 情绪基调: {style_match.get('mood')}
任务：规划 1 张封面 (2.35:1) 和 2-3 张插图。提示词必须是全中文。
输出 JSON 格式要求:
{{
  "cover": {{ "type": "hero/minimal", "prompt": "全中文生图词", "rendering": "{style_match.get('rendering')}" }},
  "illustrations": [
    {{ "prompt": "全中文插图生图提示词", "type": "infographic/flowchart/scene", "ratio": "16:9 / 4:3 / 1:1 / 3:4", "pos": "对应段落" }}
  ]
}}"""
        
        try:
            resp = httpx.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat", 
                    "messages": [
                        {"role": "system", "content": sys_p},
                        {"role": "user", "content": f"内容：{article_content[:3000]}"}
                    ], 
                    "response_format": {"type": "json_object"}}, 
                timeout=60)
            return json.loads(resp.json()["choices"][0]["message"]["content"])
        except Exception as e: 
            logger.error("视觉分析异常: %s", e)
            return None

    def run_visuals(self, model_type="seedream"):
        """钢铁意志视觉引擎：绝对不中断，成一张推一张"""
        logger.info("启动 run_visuals | model=%s", model_type)
        state = self.load_state()
        state['article_images'] = []
        state['cover_image'] = ""
        self.save_state(state)
        
        draft_file = state.get('draft_file')
        if not draft_file or not os.path.exists(draft_file): 
            print("[FEISHU_STATUS] ERR=未找到草稿文件", flush=True)
            return False
            
        print(f"\n🎨 [视觉导演] 开启弹性生成 (引擎: {model_type})...", flush=True)
        with open(draft_file, "r", encoding="utf-8") as f: content = f.read()

        plan = self.analyze_visuals(content, category=state.get('content_category', 'insight'))
        if not plan:
            print("[FEISHU_STATUS] WARN=分析方案失败，使用兜底图", flush=True)
            plan = {"cover": {"prompt": "大胡老师的数字花园"}, "illustrations": []}

        try:
            cp = plan.get("cover", {}).get("prompt", "封面图")
            print(f"🖼️ [封面] 准备构建: {cp[:30]}...", flush=True)
            c_url = self.generate_image(cp, model_type=model_type, size="3072x1308")
            if c_url:
                l_cover = self.download_image_file(c_url, folder=os.path.join(self.workspace, 'assets', 'covers'))
                if l_cover:
                    state['cover_image'] = l_cover
                    self.save_state(state)
                    print(f"[FEISHU_PREVIEW] TYPE=COVER PATH={l_cover}", flush=True)
        except Exception as e:
            logger.error("封面生成失败: %s", e)

        ills = plan.get("illustrations", [])
        if ills:
            print(f"\n🎨 [排期] 共有 {len(ills)} 张插图待产...", flush=True)
            ratio_map = {"16:9": "2560x1440", "4:3": "2224x1668", "1:1": "1920x1920", "3:4": "1668x2224"}
            for i, info in enumerate(ills, 1):
                p = info.get("prompt", "")
                if not p: continue
                style = plan.get("cover", {}).get('rendering', 'flat-vector')
                p = f"{p}, style: {style}, minimalism, studio light, ultra hd"
                ratio = info.get("ratio", "1:1")
                size = ratio_map.get(ratio, "1920x1920")
                print(f"🖼️ [进度 {i}/{len(ills)}] 启动渲染 ({ratio})...", flush=True)
                try:
                    i_url = self.generate_image(p, model_type=model_type, size=size)
                    if i_url:
                        l_path = self.download_image_file(i_url, folder=os.path.join(self.workspace, 'assets', 'illustrations'))
                        if l_path:
                            # 保存 image-position 映射，而不是单纯路径
                            ill_info = {"path": l_path, "pos": info.get("pos", ""), "ratio": ratio, "prompt": p[:50]}
                            state['article_images'].append(ill_info)
                            self.save_state(state)
                            print(f"[FEISHU_PREVIEW] TYPE=ILLUS INDEX={i} POS={info.get('pos', 'N/A')} PATH={l_path}", flush=True)
                except Exception as ie:
                    logger.error("插图 %d 生成失败: %s", i, ie)
            self.save_state(state)
            
        print(f"\n[FEISHU_STATUS] DONE=已产出 {len(state.get('article_images', []))} 张图", flush=True)
        return True

    def post_to_wechat(self, draft_file, method="api", cover_path=None, title=None):
        import datetime as dt
        import os as _os
        import time as _time
        ts_str = dt.datetime.now().strftime('%H%M%S')
        log_path = _os.path.join(self.workspace, 'logs', f'post_{ts_str}.log')
        _os.makedirs(_os.path.dirname(log_path), exist_ok=True)
        log_f = open(log_path, 'w', encoding='utf-8')
        print(f"\n🚀 正在将内容同步至公众号草稿箱...", flush=True, file=log_f)
        state = self.load_state()
        article_images = state.get('article_images', [])
        
        try:
            with open(draft_file, 'r', encoding='utf-8') as f:
                content = f.read()

            is_html = str(draft_file).endswith('.html')
            if is_html:
                # Xiaohu 将 markdown 图片语法转换为 WECHATIMGPH_N 占位符（无下划线）
                # 这里替换为带 data-local-path 的真实 <img> 标签
                if article_images:
                    for i, img_path in enumerate(article_images):
                        ph = f"WECHATIMGPH_{i + 1}"  # Xiaohu 使用从1开始的计数器
                        tag = f'<img src="XIMGPH_{i}" data-local-path="{_os.path.abspath(img_path)}" style="max-width: 100%; height: auto; display: block; margin: 20px auto;" />'
                        content = content.replace(ph, tag)
                with open(draft_file, 'w', encoding='utf-8') as f: f.write(content)
            else:
                if article_images and "![插图]" not in content:
                    lines = content.split('\n')
                    pts = [i for i, l in enumerate(lines) if l.startswith('### ')] or [i for i, l in enumerate(lines) if not l.strip()]
                    pts = sorted(list(set(pts)))
                    for i, img in enumerate(article_images):
                        p_idx = (i * len(pts)) // len(article_images)
                        lines.insert(pts[p_idx] + i * 2, f'\n![插图]({_os.path.abspath(img)})\n')
                    with open(draft_file, 'w', encoding='utf-8') as f: f.write('\n'.join(lines))

            # 执行命令准备
            import shutil
            bun_path = shutil.which("bun") or shutil.which("bun.exe")
            npx_cmd = "npx.cmd" if _os.name == "nt" else "npx"
            baoyu_dir = _os.path.join(self.workspace, "baoyu-post-to-wechat")
            
            THEMES = {"hardcore": "modern", "insight": "grace", "news": "default", "emotional": "grace", "risk": "modern", "tool": "simple", "growth": "simple"}
            wechat_theme = THEMES.get(state.get('content_category', ''), _os.environ.get("WECHAT_THEME", "default"))
            
            script = _os.path.join(baoyu_dir, "scripts", "wechat-article.ts" if method == "browser" else "wechat-api.ts")
            args = [bun_path, script] if bun_path else [npx_cmd, "-y", "bun", script]

            if is_html:
                # wechat-api.ts 把 HTML 文件作为位置参数，不支持 --html
                args.append(draft_file)
                # HTML 文件内的图片已经在 post_to_wechat 开头处理过了（IMG placeholder 替换）
                # cover 单独传
            else:
                args.extend(["--markdown", draft_file, "--theme", wechat_theme])
            if cover_path and _os.path.exists(cover_path): args.extend(["--cover", _os.path.abspath(cover_path)])
            if title: args.extend(["--title", title])

            print(f"[POST] 🚀 执行发布脚本: {' '.join([_os.path.basename(str(a)) for a in args])} ...", flush=True, file=log_f)

            # 失败重试机制（最多3次，间隔3秒）
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                proc = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace'
                )
                for line in proc.stdout:
                    print(line, end='', flush=True, file=log_f)
                    log_f.flush()
                proc.wait()
                if proc.returncode == 0:
                    print("✅ 发布成功", flush=True, file=log_f)
                    log_f.close()
                    return True
                print(f"[WARN] 发布失败，第 {attempt}/{max_retries} 次，3秒后重试...", flush=True, file=log_f)
                log_f.flush()
                if attempt < max_retries:
                    import time as _time; _time.sleep(3)
            log_f.close()
            print(f"\n❌ 全部 {max_retries} 次发布均失败，详细日志：{log_path}", flush=True)
            return False
        except Exception as e:
            import traceback as tb
            tb.print_exc(file=log_f)
            log_f.close()
            print(f"[ERROR] post_to_wechat 失败: {e}", flush=True)
            return False

    def _recommend_themes(self, content: str, available_themes: list) -> list:
        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            mid = os.environ.get("LLM_MODEL_ID", "deepseek-chat")
            if not api_key or "your_api_key" in api_key:
                return []
            
            import httpx
            import json
            
            prompt = f"分析以下文章内容的风格（如科技、深度、故事、教程等），从提供的主题列表中，选出最适合的 1 到 2 个主题ID。\n只返回一个JSON数组，例如：[\"github\", \"newspaper\"]，不要返回任何其他说明文字。\n\n可用主题列表：{', '.join(available_themes)}\n\n文章预览：\n{content[:1500]}"
            
            with httpx.Client(timeout=30) as cl:
                resp = cl.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                               json={"model": mid, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1})
                if resp.status_code == 200:
                    answer = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if answer.startswith("```json"): answer = answer[7:]
                    if answer.startswith("```"): answer = answer[3:]
                    if answer.endswith("```"): answer = answer[:-3]
                    choice = json.loads(answer.strip())
                    if isinstance(choice, list):
                        valid_themes = [str(t).strip() for t in choice if str(t).strip() in available_themes]
                        if valid_themes:
                            print(f"🤖 AI 主题推荐成功: {valid_themes}")
                            return valid_themes
        except Exception as e:
            print(f"⚠️ AI 推荐主题失败，使用默认主题: {e}")
        return []

    def run_post(self, method="api"):
        """
        [v1.2] 发布到公众号（API 模式）
        流程：LLM 推荐 1-2 个主题 → 为每个主题分别生成 HTML → 每个 HTML 调用一次 post_to_wechat 保存草稿
        """
        logger.info("启动 run_post | method=%s", method)
        state = self.load_state()
        draft_file = state.get('draft_file')
        if not draft_file or not os.path.exists(draft_file):
            print("⚠️ 未找到可发布的草稿文件")
            return False

        with open(draft_file, 'r', encoding='utf-8') as f:
            final_content = f.read()

        base_title = state.get('topic_context', {}).get('title', '未命名文章')
        # 去掉标题中的 # 符号
        base_title = re.sub(r'^#+\s*', '', base_title).strip()
        cover_path = state.get('cover_image')
        article_images = state.get('article_images', [])

        # Xiaohu 排版：API 模式，不弹浏览器，直接按推荐主题批量生成
        html_files = []
        if WEWRITE_XIAOHU_AVAILABLE:
            try:
                from datetime import datetime
                config = WeWriteConfig()
                xiaohu_formatter = XiaohuFormatter({
                    'default_theme': config.xiaohu_default_theme,
                    'gallery_timeout': config.xiaohu_gallery_timeout
                }, logger)

                # 在 final_content 中插入 markdown 图片占位符，Xiaohu 会将其转为 WECHAT_IMGPH_N
                if article_images:
                    md_lines = final_content.split('\n')
                    
                    # 构建段落索引列表（用于 pos 匹配）
                    para_starts = []  # 每个段落开始的行号
                    for i, line in enumerate(md_lines):
                        stripped = line.strip()
                        if stripped and not stripped.startswith('#'):
                            para_starts.append(i)
                    
                    # 为每个图片找插入位置：优先用 pos 字段匹配，其次均匀分布
                    insert_map = []  # [(line_index, image_info), ...]
                    
                    for ill in article_images:
                        img_path = ill.get('path', ill) if isinstance(ill, dict) else ill
                        pos = ill.get('pos', '') if isinstance(ill, dict) else ''
                        
                        target_line = None
                        
                        # 方法1：pos 字段匹配段落
                        if pos:
                            pos_clean = pos.strip()
                            # 尝试数字索引匹配（如 "第2段"、"段落2"）
                            import re
                            num_match = re.search(r'[第]?(\d+)[段篇]', pos_clean)
                            if num_match:
                                idx = int(num_match.group(1)) - 1
                                if 0 <= idx < len(para_starts):
                                    target_line = para_starts[idx]
                            
                            # 尝试关键词匹配：在段落中找关键词
                            if target_line is None and len(pos_clean) > 2:
                                for pi, line_idx in enumerate(para_starts):
                                    line_text = md_lines[line_idx].lower()
                                    # 提取关键词（去除数字、符号）
                                    keywords = re.sub(r'[\d\.\。\、\，]', '', pos_clean).strip()
                                    if keywords[:4] in line_text:
                                        target_line = line_idx
                                        break
                        
                        # 方法2：均匀分布（兜底）
                        if target_line is None:
                            # 均匀分配到各段落
                            n_remaining = len(article_images) - len(insert_map)
                            n_slots = len(para_starts)
                            if n_slots > 0 and n_remaining > 0:
                                step = (n_slots - 1) / n_remaining
                                target_line = para_starts[min(int(len(insert_map) * step), n_slots - 1)]
                            elif para_starts:
                                target_line = para_starts[len(insert_map) % len(para_starts)]
                            else:
                                target_line = len(md_lines) // 2
                        
                        insert_map.append((target_line, img_path))
                    
                    # 按行号排序插入点（从后往前插入，避免索引偏移问题）
                    insert_map.sort(key=lambda x: x[0], reverse=True)
                    for line_idx, img_path in insert_map:
                        md_lines.insert(line_idx, f'\n![]({img_path})\n')
                    
                    final_content = '\n'.join(md_lines)
                    print(f"🖼️ 已在正文中插入 {len(article_images)} 个图片（按 pos 匹配段落）")
                    final_content = '\n'.join(md_lines)
                    print(f"🖼️ 已在正文中插入 {len(article_images)} 个图片占位符")

                print(f"🎨 启动 Xiaohu 排版引擎（API 模式）...")
                available_themes = xiaohu_formatter.list_themes()
                recommended_themes = self._recommend_themes(final_content, available_themes)

                # 如果没有推荐主题，使用默认主题
                if not recommended_themes:
                    recommended_themes = [config.xiaohu_default_theme]
                    print(f"⚠️ 未推荐到合适主题，使用默认主题：{recommended_themes}")

                dr_root = os.path.dirname(draft_file)
                ts = datetime.now().strftime('%Y%m%d%H%M')

                for theme in recommended_themes:
                    hp = os.path.join(dr_root, f"article_{ts}_{theme}.html")
                    try:
                        print(f"🎨 正在使用主题「{theme}」生成 HTML...")
                        html_path = xiaohu_formatter.format_with_theme(final_content, theme, hp)
                        html_files.append((theme, html_path))
                        print(f"✅ 主题「{theme}」排版完成：{html_path}")
                    except Exception as e:
                        print(f"⚠️ 主题「{theme}」排版失败: {e}")
                        logger.warning(f"主题「{theme}」排版异常: {e}")

                # 保存 HTML 文件列表到 state
                state['html_files'] = html_files
                self.save_state(state)

            except Exception as e:
                print(f"⚠️ Xiaohu 排版引擎异常: {e}")
                logger.warning(f"Xiaohu 异常: {e}")

        # 如果没有成功生成 HTML，降级使用原始 markdown 文件
        if not html_files:
            print(f"⚠️ 未生成任何 HTML，降级使用原始 markdown 文件发布")
            html_files = [("markdown", draft_file)]

        # 为每个 HTML 发布到公众号草稿箱
        success_count = 0
        for theme, html_path in html_files:
            title = f"{base_title} [{theme}]" if theme != "markdown" else base_title
            print(f"📤 正在发布「{title}」到公众号草稿箱...")
            ok = self.post_to_wechat(html_path, method=method, cover_path=cover_path, title=title)
            if ok:
                success_count += 1
                print(f"✅ 「{title}」已保存到草稿箱")
            else:
                print(f"❌ 「{title}」发布失败")

        if success_count > 0:
            state['current_step'] = "done"
            self.save_state(state)
            print(f"\n🎉 共成功发布 {success_count} 篇草稿到公众号后台，请前往确认")
            return True
        else:
            print(f"\n⚠️ 所有草稿发布均失败，请检查日志")
            return False

    def run_publish(self, model_type="seedream", method="api"):
        logger.info("启动 run_publish | model=%s | method=%s", model_type, method)
        if self.run_visuals(model_type=model_type):
            return self.run_post(method=method)
        return False

def main():
    logger.info("启动 workflow_controller")
    parser = argparse.ArgumentParser(description="自媒体工作流调度器")
    parser.add_argument('action', choices=['setup', 'pre_discovery', 'discovery', 'next', 'from-article', 'from-video', 'repurpose', 'visuals', 'post', 'publish', 'status', 'sync'], help="动作")
    parser.add_argument('--keyword', type=str); parser.add_argument('--url', type=str); parser.add_argument('--id', type=str)
    parser.add_argument('--model', default='seedream'); parser.add_argument('--method', default='api')
    parser.add_argument('--script', type=str); parser.add_argument('--article', type=str)
    parser.add_argument('--refresh', action='store_true', default=True, help="强制刷新（默认行为）")
    parser.add_argument('--last_id', type=str, help="游标分页用的 last_id")
    parser.add_argument('--script-only', action='store_true', help="仅重写短视频脚本")
    parser.add_argument('--article-only', action='store_true', help="仅重写深度长文")

    args, unknown = parser.parse_known_args()
    controller = SelfMediaController()
    
    if args.action == 'setup': controller.run_setup()
    elif args.action == 'pre_discovery': controller.run_pre_discovery(keyword=args.keyword)
    elif args.action == 'discovery': controller.run_discovery(keyword=args.keyword, refresh=args.refresh, last_id=args.last_id)
    elif args.action == 'next': controller.run_next_discovery()
    elif args.action == 'from-article': controller.run_from_article(args.url)
    elif args.action == 'from-video': controller.run_from_video(args.url)
    elif args.action == 'repurpose': controller.run_repurpose(args.id)
    elif args.action == 'visuals': controller.run_visuals(model_type=args.model)
    elif args.action == 'post': controller.run_post(method=args.method)
    elif args.action == 'publish': controller.run_publish(model_type=args.model, method=args.method)
    elif args.action == 'sync': controller.sync_to_feishu(args.script, args.article)
    elif args.action == 'status': print(json.dumps(controller.load_state(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
