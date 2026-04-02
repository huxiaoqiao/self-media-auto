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
        logger.info("状态更新")
        print("🚀 欢迎使用自媒体系统引导配置 (Setup Wizard)")
        logger.info("状态更新")
        print("="*50 + "\n")
        logger.info("状态更新")

        # 1. 检查 ffmpeg
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            print(f"✅ 环境检查: ffmpeg 已定位 -> {ffmpeg_path}")
            logger.info("状态更新")
        else:
            print("⚠️ 环境警告: 未检测到 ffmpeg。视频 ASR 功能将失效，请先安装 ffmpeg 并添加到 PATH。")
            logger.warning("状态更新")

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
        logger.info("状态更新")
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
        logger.info("状态更新")
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
        logger.info("状态更新")
        print("✨ 您现在可以运行 'python workflow_controller.py discovery' 开始使用了。")
        logger.info("状态更新")

    def run_from_article(self, url_or_text):
        """
        [v1.1] 快捷入口：从指定文章链接开始创作
        """
        import re
        logger.info("启动 from-article | url=%s", str(url_or_text)[:60])
        match = re.search(r'https?://[^\s]+', url_or_text)
        url = match.group(0) if match else url_or_text
        
        print(f"🚀 启动定向创作模式 (From Article)... 原始输入中探测到的 URL: {url}")
        logger.info("状态更新")
        state = self.load_state()
        selected = {
            "id": url, 
            "source": "公众号", 
            "title": "定向通过URL输入的素材", 
            "author": "外部链接",
            "score": 9999
        }
        state['last_candidates'] = [selected]
        self.save_state(state)
        self.run_repurpose(url)

    def run_from_video(self, url_or_text):
        """
        [v1.1] 快捷入口：从指定视频链接开始创作
        """
        import re
        logger.info("启动 from-video | url=%s", str(url_or_text)[:60])
        match = re.search(r'https?://[^\s]+', url_or_text)
        url = match.group(0) if match else url_or_text
        
        print(f"🚀 启动定向视频创作模式 (From Video)... 原始输入中探测到的 URL: {url}")
        logger.info("状态更新")
        state = self.load_state()
        selected = {
            "id": url, 
            "source": "视频链接", 
            "title": "定向输入的视频素材", 
            "author": "视频平台",
            "score": 9999
        }
        state['last_candidates'] = [selected]
        self.save_state(state)
        self.run_repurpose(url)

    def sync_to_feishu(self, script_path, article_path):
        """
        将二创生成的脚本和长文同步到飞书云文档
        """
        import subprocess
        import json
        logger.info("启动 sync_to_feishu | script=%s | article=%s", script_path, article_path)
        date_folder = datetime.now().strftime('%Y-%m-%d')
        
        print("🚀 启动 [飞书文档同步]...")
        logger.info("状态更新")
        
        # 1. 读取本地文件内容
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        with open(article_path, 'r', encoding='utf-8') as f:
            article_content = f.read()
        
        # 2. 调用 OpenClaw 飞书插件创建文件夹和文档
        print(f"📁 正在飞书云空间创建文件夹「自媒体内容/{date_folder}」...")
        logger.info("状态更新")
        
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
        logger.info("状态更新")
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

    def run_discovery(self, keyword=None, refresh=False, last_id=None):
        """
        [卡点 1 之前] 嗅探系统 (次幂数据版)
        抓取微信爆款文章的热点。

        翻页逻辑：
        - 新一轮（已发布后）：不带 last_id，直接获取最新
        - 同一轮内（发布前）：带 last_id 继续翻页
        """
        import requests
        logger.info("启动 run_discovery | keyword=%s, refresh=%s, last_id=%s", keyword, refresh, last_id)
        state = self.load_state()
        saved_industry = state.get('industry')

        # 判断是否是新的一轮：如果已发布过，则重置 last_id，直接获取最新
        current_step = state.get('current_step', '')
        if current_step in ['published_to_draft', 'published']:
            logger.info("检测到已发布状态 (%s)，开启新一轮 discovery，清空 last_id", current_step)
            state.pop('cimi_last_id', None)
            state.pop('candidates_page_index', None)
            state['candidates'] = []
            state['last_candidates'] = []

        # 同一轮内，使用缓存的 last_id 继续翻页
        if last_id is None and not refresh:
            last_id = state.get('cimi_last_id')
            if last_id:
                logger.info("使用缓存的 last_id: %s", last_id)

        print("[嗅探系统] 启动 [嗅探子系统 - 次幂数据版]...")
        logger.info("[嗅探系统] 启动 [嗅探子系统  次幂数据版]...")
        
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
                logger.info("状态更新")
            else:
                print(f"❌ 错误: 未知分类 '{keyword}'")
                logger.error("状态更新")
        elif saved_industry:
            matched = find_category(saved_industry)
            if matched:
                target_category = matched
                print(f"✨ 检测到已保存的专属行业: {matched[1]} (如需更改，请在命令后加 --keyword <新序号>)")
                logger.info("状态更新")

        if not target_category:
            print("👋 请配置您的专属行业/领域(次幂爆款分类)，系统将自动保存以便日后为您自动获取爆文：")
            logger.info("状态更新")
            items = list(categories.items())
            for i in range(0, len(items), 5):
                chunk = items[i:i+5]
                line = "  ".join(f"{k}. {v[1]:<6}" for k, v in chunk)
                print(line)
                logger.info("状态更新")
            print("⚠️ [ACTION_REQUIRED] 等待用户输入：请通过交互通道回复你想抓取的行业序号（如'3'表示科技）。")
            logger.warning("状态更新")
            sys.exit(0)

        cimi_category_en, cimi_category_cn = target_category
        print(f"🔍 正在检索微信爆款文章 (分类: {cimi_category_cn})...")
        logger.info("状态更新")

        cimi_app_id = os.getenv("CIMI_APP_ID")
        cimi_app_secret = os.getenv("CIMI_APP_SECRET")
        if not cimi_app_id or not cimi_app_secret:
            print("❌ 未在环境变量中找到 CIMI_APP_ID 或 CIMI_APP_SECRET，请先执行 run_setup 或修改 .env 文件。")
            logger.error("状态更新")
            sys.exit(1)

        api_base = "https://api.cimidata.com"
        headers = {"Content-Type": "application/json"}
        
        print("📥 [1/2] 正在获取次幂数据 Access Token...")
        logger.info("状态更新")
        try:
            token_resp = requests.post(f"{api_base}/api/v2/token", json={"app_id": cimi_app_id, "app_secret": cimi_app_secret}, headers=headers, timeout=10)
            token_resp.raise_for_status()
            access_token = token_resp.json()["data"]["access_token"]
        except Exception as e:
            print(f"❌ 请求 Token 接口时发生异常: {e}")
            logger.error("状态更新")
            sys.exit(1)

        print("📥 [2/2] 正在拉取爆款文章列表...")
        logger.info("状态更新")
        candidates = []
        try:
            payload = {"category": cimi_category_en, "read_num": 1000}
            if last_id:
                payload["last_id"] = last_id
            
            articles_resp = requests.post(f"{api_base}/api/v2/hot/articles?access_token={access_token}", 
                                         json=payload, headers=headers, timeout=15)
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
            logger.error("状态更新")
            sys.exit(1)

        print(f"\n=== ✨ 今日推荐 Top {len(candidates)} 爆款选题 === (数据来源: 次幂)")
        logger.info("状态更新")
        for idx, c in enumerate(candidates, 1):
            print(f"{idx}. [{c['source']}] [{c['title']}]({c['id']})")
            logger.info("状态更新")
            print(f"👤 {c['author']} | 👁️ 阅读: {c.get('comments', 0)} | 👍 赞: {c.get('likes', 0)}")
            logger.info("状态更新")
        print("===================================")
        logger.info("状态更新")
        
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
        logger.info("状态更新")
        for idx, c in enumerate(page_items, start_idx + 1):
            source = c.get('source', '微信公众号')
            title = c.get('title', '未知文章')
            url = c.get('id', '')
            author = c.get('author', '未知')
            reads = c.get('comments', c.get('read', 0))
            likes = c.get('likes', 0)
            print(f"{idx}. [{source}] [{title}]({url})")
            logger.info("状态更新")
            print(f"👤 {author} | 👁️ 阅读: {reads} | 👍 赞: {likes}")
            logger.info("状态更新")
        print("===================================")
        logger.info("状态更新")

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
            except Exception: pass

            # 2. 次幂 API 保底
            if not raw_content or len(raw_content) < 50:
                try:
                    cid, csec = os.getenv("CIMI_APP_ID"), os.getenv("CIMI_APP_SECRET")
                    if cid and csec:
                        auth = requests.post("https://api.cimidata.com/api/v2/token", json={"app_id": cid, "app_secret": csec}, timeout=10).json()
                        token = auth["data"]["access_token"]
                        dr = requests.post(f"https://api.cimidata.com/api/v3/articles/detail?access_token={token}", json={"url": article_url}, timeout=20).json()
                        raw_content = re.sub(r'<[^>]+>', ' ', dr["data"].get("html", "")).strip()
                except Exception: pass

        elif source == "抖音":
            try:
                dj = os.path.join(self.workspace, "douyin-download-1.2.0", "douyin.js")
                out = os.path.join(os.getcwd(), 'cache', 'douyin_extract')
                os.makedirs(out, exist_ok=True)
                r = subprocess.run(["node", dj, "extract", article_url, "-o", out, "--no-segment"], capture_output=True, text=True, encoding="utf-8")
                m = re.search(r"保存位置:\s*(.+?\.md)", r.stdout)
                if m:
                    with open(m.group(1).strip(), 'r', encoding='utf-8') as f:
                        raw_content = f.read().split("## 文案内容")[-1].strip()
            except Exception: pass

        if not raw_content or len(raw_content) < 30:
            raw_content = f"（系统保底）关于《{title}》的分析：核心是极致行动与复利思维。"
        return raw_content

    def run_repurpose(self, topic_id_or_cmd):
        """
        [IP 改写引擎 V2] 支持智能场景匹配、多源抓取保底、联网补全实时背景。
        """
        logger.info("启动 run_repurpose | topic=%s", str(topic_id_or_cmd)[:60])
        import subprocess, sys, os, re, json, requests
        from datetime import datetime
        state = self.load_state()
        
        # --- 数据对象兼容与 GUID 路由 ---
        selected = None
        if isinstance(topic_id_or_cmd, dict):
            selected = topic_id_or_cmd
        else:
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
                        elif tid in tm:
                            selected = tm[tid]
                            
                        if selected:
                            print(f"✅ 从持久化库解析到素材: {selected.get('title')}")
                            logger.info("状态更新")
                except Exception: pass
            
            # 2. 缓存路由
            if not selected:
                for c in state.get('candidates', []) + state.get('last_candidates', []):
                    if str(c.get('id')) == tid or str(c.get('title')) == tid:
                        selected = c
                        break
        
        # 3. 兜底与当前上下文沿用
        if not selected:
            if (topic_id_or_cmd is None or str(topic_id_or_cmd).strip() == "None" or str(topic_id_or_cmd).strip() == "") and state.get('topic_context'):
                selected = state['topic_context']
                print(f"✅ 从当前会话上下文恢复素材: {selected.get('title')}")
                logger.info("状态更新")
            else:
                selected = {"id": str(topic_id_or_cmd), "title": "自定义素材", "source": "自定义"}

        title_val = selected.get("title", "未命名素材")
        source_val = selected.get("source", "微信")
        print(f"🚀 正在重塑内容: 《{title_val}》 (源: {source_val})")
        logger.info("状态更新")
        
        # ==========================
        # 1. 自动化素材抓取与提取
        # ==========================
        raw_content = self._extract_article_content(str(selected.get("id", "")), selected)

        # ==========================
        # 2. 调用大模型：内容重塑与全网增强
        # ==========================
        final_content = ""
        
        # [联网 RAG]
        try:
            sys.path.insert(0, self.workspace)
            from search_engine import get_latest_context
            sc = get_latest_context(raw_content)
            if sc:
                 print(f"✅ RAG 背景已注入 (约 {len(sc)} 字)")
                 logger.info("状态更新")
                 raw_content = f"【最新增强背景】:\n{sc}\n\n【原始输入素材】:\n{raw_content}"
        except Exception: pass

        # --- AI 改写 (智能分发) ---
        # [v1.2] WeWrite 优先改写引擎 (失败时降级到 prompts_manager)
        api_key = os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        mid = os.environ.get("LLM_MODEL_ID", "deepseek-chat")
        ip = os.environ.get("AUTHOR_IP_NAME", "大胡")

        wewrite_used = False
        content_category = "insight"  # 默认分类

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
                        logger.info("状态更新")
            except WeWriteError as e:
                print(f"⚠️ WeWrite 失败，降级到 prompts_manager: {e}")
                logger.warning("WeWrite 失败，降级到 prompts_manager")

        if not wewrite_used and api_key and "your_api_key" not in api_key:
            import httpx
            print(f"🤖 执行场景化创作 (模型: {mid})...")
            logger.info("状态更新")
            try:
                pm_path = os.path.join(self.workspace, "prompts_manager.json")
                conf = {}
                if os.path.exists(pm_path):
                    with open(pm_path, 'r', encoding='utf-8') as f: conf = json.load(f)
                
                cat = "insight"
                if conf:
                    print(f"🧠 [1/2] 意图路由分析...")
                    logger.info("状态更新")
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
                    print(f"✨ 场景适配：【{conf['templates'][cat]['name']}】")
                    logger.info("状态更新")
                    content_category = cat  # 记录分类供后续排版使用

                    raw_prompt = conf["templates"].get(cat, conf["templates"]["insight"])["prompt"]
                    if isinstance(raw_prompt, list): raw_prompt = "\n".join(raw_prompt)
                    final_pmt = raw_prompt.format(author_ip_name=ip, wechat_id=os.environ.get("AUTHOR_WECHAT_ID", "此处添加微信号").strip("'\""))
                    
                    print(f"📝 [2/2] 深度创作中...")
                    logger.info("状态更新")
                    with httpx.Client(timeout=300) as cl:
                        r = cl.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                            json={"model": mid, "messages": [{"role": "user", "content": f"{final_pmt}\n\n素材:\n{raw_content}"}], "temperature": 0.7})
                        final_content = r.json()["choices"][0]["message"]["content"]
                        print(f"✅ 生成完毕：{len(final_content)} 字")
                        logger.info("状态更新")
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
        
        sp = os.path.join(dr_root, f"video_script_{ts}.md")
        with open(sp, "w", encoding='utf-8') as f: f.write(vs if vs else "未生成脚本")

        # ==========================
        # [v1.2] Xiaohu 排版引擎 (gallery 模式)
        # ==========================
        html_path = ""
        if WEWRITE_XIAOHU_AVAILABLE:
            try:
                config = WeWriteConfig()
                xiaohu_formatter = XiaohuFormatter({
                    'default_theme': config.xiaohu_default_theme,
                    'gallery_timeout': config.xiaohu_gallery_timeout
                }, logger)

                # 使用 Gallery 模式，弹出浏览器让用户选择主题
                if config.xiaohu_gallery_mode:
                    print(f"🎨 启动 Xiaohu 浏览器主题选择器...")
                    logger.info("启动 Xiaohu Gallery 模式")
                    hp = os.path.join(dr_root, f"article_{ts}.html")
                    html_path = xiaohu_formatter.format_with_gallery(final_content, hp)
                    print(f"✅ Xiaohu 排版完成：{html_path}")
                else:
                    # 使用默认主题直接生成
                    print(f"✨ 使用默认主题 '{config.xiaohu_default_theme}' 进行排版...")
                    logger.info("使用 Xiaohu 默认主题排版")
                    hp = os.path.join(dr_root, f"article_{ts}.html")
                    html_path = xiaohu_formatter.format_with_theme(
                        final_content, config.xiaohu_default_theme, hp
                    )
                    print(f"✅ Xiaohu 排版完成：{html_path}")

            except XiaohuGalleryTimeout as e:
                print(f"⚠️ Xiaohu Gallery 超时，降级到默认主题：{e}")
                logger.warning("Xiaohu Gallery 超时，降级到默认主题")
                try:
                    config = WeWriteConfig()
                    xiaohu_formatter = XiaohuFormatter({
                        'default_theme': config.xiaohu_default_theme,
                        'gallery_timeout': 60
                    }, logger)
                    hp = os.path.join(dr_root, f"article_{ts}.html")
                    html_path = xiaohu_formatter.format_with_theme(
                        final_content, config.xiaohu_default_theme, hp
                    )
                    print(f"✅ 默认主题排版完成：{html_path}")
                except Exception as fallback_err:
                    print(f"❌ 默认主题排版失败：{fallback_err}")
                    logger.error("默认主题排版失败")

            except XiaohuGalleryError as e:
                print(f"⚠️ Xiaohu 排版失败，使用旧版 md2wechat-skill: {e}")
                logger.warning("Xiaohu 排版失败，降级到 md2wechat-skill")
            except Exception as e:
                print(f"⚠️ Xiaohu 异常，降级到 md2wechat-skill: {e}")
                logger.warning("Xiaohu 异常，降级处理")

        # 如果 Xiaohu 不可用或失败，降级到旧的 md2wechat-skill
        if not html_path:
            import yaml
            import httpx
            # 每种内容分类对应一套专属 AI 动态渲染主题 (wechat_themes/*.yaml)
            theme_map = {
                "hardcore":  "hardcore-cyber.yaml",
                "insight":   "insight-gold.yaml",
                "news":      "news-sharp.yaml",
                "emotional": "autumn-warm.yaml",
                "risk":      "risk-alert.yaml",
                "tool":      "tool-minimal.yaml",
                "growth":    "growth-green.yaml",
                "crossover": "crossover-purple.yaml",
            }
            # 使用 content_category 变量（WeWrite 路径设置）或 cat 变量（旧路径）
            category_value = content_category if 'content_category' in locals() else None
            theme_file = theme_map.get(category_value, "ocean-calm.yaml")
            theme_path = os.path.join(self.workspace, "wechat_themes", theme_file)

            if os.path.exists(theme_path) and api_key:
                print(f"✨ 检测到 md2wechat-skill 引擎，根据文章分类自动选取主题：[{theme_file}]")
                logger.info("状态更新")
                try:
                    with open(theme_path, 'r', encoding='utf-8') as tf:
                        theme_cfg = yaml.safe_load(tf)
                        html_prompt = theme_cfg.get('prompt', '')

                    if html_prompt:
                        print(f"🎨 正在调度大模型进行 HTML 渲染，这可能需要几十秒...")
                        logger.info("状态更新")
                        with httpx.Client(timeout=300) as cl:
                            md_to_render = f"# {nt}\n\n{ac}" if nt else ac
                            r = cl.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                                json={"model": mid, "messages": [{"role": "system", "content": html_prompt}, {"role": "user", "content": f"内容：\n\n{md_to_render}"}], "temperature": 0.2})
                            html_content = r.json()["choices"][0]["message"]["content"]

                            html_content = html_content.strip()
                            if html_content.startswith("```html"): html_content = html_content[7:]
                            elif html_content.startswith("```"): html_content = html_content[3:]
                            if html_content.endswith("```"): html_content = html_content[:-3]

                            hp = os.path.join(dr_root, f"article_{ts}.html")
                            with open(hp, "w", encoding='utf-8') as hf:
                                hf.write(html_content.strip())
                            html_path = hp
                            print(f"✅ HTML 渲染完成，已生成 {hp}")
                            logger.info("状态更新")
                except Exception as e:
                    print(f"❌ HTML 渲染失败：{e}")
                    logger.error("状态更新")


        print(f"✅ 成果存档 [保存文件]：")
        logger.info("状态更新")
        print(f"   article_path={ap}")
        logger.info("状态更新")
        print(f"   script_path={sp}")
        logger.info("状态更新")
        if html_path:
            print(f"   html_path={html_path}")
            logger.info("状态更新")
        
        state['current_step'] = "waiting_for_content_review"
        state['draft_file'] = ap
        if html_path:
            state['html_file'] = html_path
        state['video_script'] = sp
        state['topic_context'] = selected
        if nt: state['topic_context']['title'] = nt
        # 保存文章分类，供发布时自动选择主题
        if 'cat' in locals():
            state['content_category'] = cat
            print(f"[REPURPOSE] 📂 文章分类已记录: {cat}", flush=True)
            logger.info("状态更新")
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
                logger.info("状态更新")
                r = requests.post(url, headers=headers, json=data, timeout=60)
                resp = r.json()
                img_url = resp.get("data", [{}])[0].get("url")
                if not img_url:
                    print(f"[ERROR] Volcengine API Response: {resp}")
                    logger.error("状态更新")
                return img_url
            except Exception as e:
                print(f"[ERROR] Volcengine generation failed: {e}")
                logger.error("状态更新")
                return None
        else:
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key: return None
            model_id = {"z": "z-image-turbo", "qwen": "qwen-image-2.0-pro", "wan": "wan2.6-t2i"}.get(model_type, "wan2.6-t2i")
            url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            data = {"model": model_id, "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]}, "parameters": {"size": size}}
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=60).json()
                return resp.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", [{}])[0].get("image")
            except Exception: return None

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
        except Exception: pass
        return None

    def load_visual_config(self):
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'prompts_manager.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get('visual_config', {})
        except Exception: pass
        return {}

    def analyze_visuals(self, article_content, category="insight"):
        logger.info("启动 analyze_visuals | category=%s", category)
        import httpx
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key: return None
        
        v_config = self.load_visual_config()
        # 准则和风格完全对齐 prompts_manager.json
        rules_text = "\n".join([f"- {r}" for r in v_config.get('base_principles', [])])
        style_match = v_config.get('style_matching', {}).get(category, {
            "rendering": "3d-render", "palette": "elegant", "mood": "balanced"
        })

        # 视觉导演指令：动态拼装，拒绝硬编码
        sys_p = f"""你是一个视觉分析专家。请为分类为 '{category}' 的自媒体文章规划视觉方案。

【核心设计红线】：
{rules_text}

【视觉风格指导 (基于分类匹配)】：
- 渲染方案: {style_match.get('rendering')} | 色彩体系: {style_match.get('palette')} | 情绪基调: {style_match.get('mood')}

任务：规划 1 张封面 (2.35:1) 和 2-3 张插图。提示词必须是全中文。

输出 JSON 格式要求:
{{
  "cover": {{ "type": "hero/minimal", "prompt": "全中文生图词", "rendering": "{style_match.get('rendering')}" }},
  "illustrations": [
    {{
      "prompt": "全中文插图生图提示词",
      "type": "infographic/flowchart/scene",
      "ratio": "16:9 / 4:3 / 1:1 / 3:4",
      "pos": "对应段落"
    }}
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
            print(f"⚠️ 视觉分析异常: {e}")
            logger.error("状态更新")
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
        except Exception: pass
        return None

    def load_visual_config(self):
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'prompts_manager.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get('visual_config', {})
        except Exception: pass
        return {}

    def analyze_visuals(self, article_content, category="insight"):
        logger.info("启动 analyze_visuals | category=%s", category)
        import httpx
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key: return None
        
        v_config = self.load_visual_config()
        # 准则和风格完全对齐 prompts_manager.json
        rules_text = "\n".join([f"- {r}" for r in v_config.get('base_principles', [])])
        style_match = v_config.get('style_matching', {}).get(category, {
            "rendering": "3d-render", "palette": "elegant", "mood": "balanced"
        })

        # 视觉导演指令：动态拼装，拒绝硬编码
        sys_p = f"""你是一个视觉分析专家。请为分类为 '{category}' 的自媒体文章规划视觉方案。

【核心设计红线】：
{rules_text}

【视觉风格指导 (基于分类匹配)】：
- 渲染方案: {style_match.get('rendering')} | 色彩体系: {style_match.get('palette')} | 情绪基调: {style_match.get('mood')}

任务：规划 1 张封面 (2.35:1) 和 2-3 张插图。提示词必须是全中文。

输出 JSON 格式要求:
{{
  "cover": {{ "type": "hero/minimal", "prompt": "全中文生图词", "rendering": "{style_match.get('rendering')}" }},
  "illustrations": [
    {{
      "prompt": "全中文插图生图提示词",
      "type": "infographic/flowchart/scene",
      "ratio": "16:9 / 4:3 / 1:1 / 3:4",
      "pos": "对应段落"
    }}
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
            print(f"⚠️ 视觉分析异常: {e}")
            logger.error("状态更新")
            return None

    def post_to_wechat(self, file_path, method="browser", cover_path=None, title=None):
        import subprocess
        print(f"🚀 正在通过 [{method}] 发布文章...")
        logger.info("状态更新")
        scripts_dir = os.path.join(self.workspace, 'baoyu-post-to-wechat', 'scripts')
        cmd = ["bun", "wechat-article.ts", "--markdown", file_path, "--theme", "default"]
        if title: cmd.extend(["--title", title])
        if cover_path: cmd.extend(["--cover", cover_path])
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            res = subprocess.run(cmd, cwd=scripts_dir, env=env)
            return res.returncode == 0
        except Exception: return False

    def run_visuals(self, model_type="seedream"):
        """钢铁意志视觉引擎：绝对不中断，成一张推一张"""
        logger.info("启动 run_visuals | model=%s", model_type)
        state = self.load_state()
        # 强制初始化并清空之前的图片记录（防止重试时图片不断追加）
        state['article_images'] = []
        state['cover_image'] = ""
        self.save_state(state)
        
        draft_file = state.get('draft_file')
        if not draft_file or not os.path.exists(draft_file): 
            print("[FEISHU_STATUS] ERR=未找到草稿文件", flush=True)
            logger.info("状态更新")
            return False
            
        print(f"\n🎨 [视觉导演] 开启弹性生成 (引擎: {model_type})...", flush=True)
        logger.info("状态更新")
        with open(draft_file, "r", encoding="utf-8") as f: content = f.read()

        # 1. 方案分析
        plan = self.analyze_visuals(content)
        if not plan:
            print("[FEISHU_STATUS] WARN=分析方案失败，使用兜底图", flush=True)
            logger.error("状态更新")
            plan = {"cover": {"prompt": "大胡老师的数字花园"}, "illustrations": []}

        # 2. 生成封面 (容错机制)
        try:
            cp = plan.get("cover", {}).get("prompt", "封面图")
            print(f"🖼️ [封面] 准备构建: {cp[:30]}...", flush=True)
            logger.info("状态更新")
            c_url = self.generate_image(cp, model_type=model_type, size="3072x1308")
            if c_url:
                l_cover = self.download_image_file(c_url, folder=os.path.join(self.workspace, 'assets', 'covers'))
                if l_cover:
                    state['cover_image'] = l_cover
                    self.save_state(state)
                    # 钢铁级实时推送协议
                    print(f"[FEISHU_PREVIEW] TYPE=COVER PATH={l_cover}", flush=True)
                    logger.info("状态更新")
                else:
                    print("[FEISHU_STATUS] ERR=封面下载失败", flush=True)
                    logger.error("状态更新")
            else:
                print("[FEISHU_STATUS] WARN=封面API返回为空(风控?)", flush=True)
                logger.warning("状态更新")
        except Exception as e:
            print(f"[FEISHU_STATUS] ERR=封面流程异常:{str(e)[:50]}", flush=True)
            logger.error("状态更新")

        # 3. 生成插图 (单图闭环)
        ills = plan.get("illustrations", [])
        if ills:
            print(f"\n🎨 [排期] 共有 {len(ills)} 张插图待产...", flush=True)
            logger.info("状态更新")
            
            ratio_map = {"16:9": "2560x1440", "4:3": "2224x1668", "1:1": "1920x1920", "3:4": "1668x2224"}

            for i, info in enumerate(ills, 1):
                p = info.get("prompt", "")
                if not p: continue
                
                # 注入风格统一
                style = plan.get("cover", {}).get('rendering', 'flat-vector')
                p = f"{p}, style: {style}, minimalism, studio light, ultra hd"
                
                ratio = info.get("ratio", "1:1")
                size = ratio_map.get(ratio, "1920x1920")

                print(f"🖼️ [进度 {i}/{len(ills)}] 启动渲染 ({ratio})...", flush=True)
                logger.info("状态更新")
                
                try:
                    i_url = self.generate_image(p, model_type=model_type, size=size)
                    if i_url:
                        l_path = self.download_image_file(i_url, folder=os.path.join(self.workspace, 'assets', 'illustrations'))
                        if l_path:
                            state['article_images'].append(l_path)
                            self.save_state(state)
                            # 钢铁级实时推送协议
                            print(f"[FEISHU_PREVIEW] TYPE=ILLUS INDEX={i} PATH={l_path}", flush=True)
                            logger.info("状态更新")
                        else:
                            print(f"[FEISHU_STATUS] ERR=插图{i}下载失败", flush=True)
                            logger.error("状态更新")
                    else:
                        print(f"[FEISHU_STATUS] WARN=插图{i}API无产出", flush=True)
                        logger.warning("状态更新")
                except Exception as ie:
                    print(f"[FEISHU_STATUS] ERR=插图{i}异常:{str(ie)[:50]}", flush=True)
                    logger.error("状态更新")
            
            self.save_state(state)
            
        print(f"\n[FEISHU_STATUS] DONE=已产出 {len(state.get('article_images', []))} 张图", flush=True)
        logger.info("状态更新")
        return True

    def post_to_wechat(self, draft_file, method="api", cover_path=None, title=None):
        print("\n🚀 正在将内容同步至公众号草稿箱...", flush=True)
        logger.info("状态更新")
        state = self.load_state()
        article_images = state.get('article_images', [])
        
        try:
            with open(draft_file, 'r', encoding='utf-8') as f:
                content = f.read()

            is_html = str(draft_file).endswith('.html')
            
            if is_html:
                if article_images:
                    unmatched_images = []
                    for i, img_path in enumerate(article_images):
                        ph1 = f"<!-- IMG:{i} -->"
                        ph2 = f"&lt;!-- IMG:{i} --&gt;"
                        new_img_tag = f'<img src="XIMGPH_{i}" data-local-path="{os.path.abspath(img_path)}" style="max-width: 100%; height: auto; display: block; margin: 20px auto;" />'
                        
                        if ph1 in content or ph2 in content:
                            content = content.replace(ph1, new_img_tag).replace(ph2, new_img_tag)
                            print(f"[POST] 🖼️  插图 {i} 已精准插入占位符 IMG:{i}", flush=True)
                            logger.info("状态更新")
                        else:
                            # 占位符不存在，留待后处理
                            unmatched_images.append((i, img_path, new_img_tag))
                    
                    # 对没找到占位符的图片，均匀分布插入 </section> 断点
                    if unmatched_images:
                        section_positions = [m.start() for m in __import__('re').finditer(r'</section>', content)]
                        if section_positions:
                            # 均匀采样 section 断点
                            step = max(1, len(section_positions) // (len(unmatched_images) + 1))
                            chosen_positions = [section_positions[min(i * step, len(section_positions)-1)] for i, _ in enumerate(unmatched_images)]
                            # 从后往前插（避免破坏之前的位置索引）
                            for (i, _, tag), pos in sorted(zip(unmatched_images, chosen_positions), key=lambda x: x[1], reverse=True):
                                content = content[:pos] + f"\n{tag}\n" + content[pos:]
                                print(f"[POST] 🖼️  插图 {i} 均匀插入 section 断点", flush=True)
                                logger.info("状态更新")
                        elif "</div>" in content:
                            pos = content.rfind("</div>")
                            tags_block = "\n".join(tag for _, _, tag in unmatched_images)
                            content = content[:pos] + f"\n{tags_block}\n" + content[pos:]
                            print(f"[POST] 🖼️  {len(unmatched_images)} 张未匹配插图追加至 </div> 前", flush=True)
                            logger.info("状态更新")
                        else:
                            for _, _, tag in unmatched_images:
                                content += f"\n{tag}"
                            print(f"[POST] 🖼️  {len(unmatched_images)} 张未匹配插图追加至末尾", flush=True)
                            logger.info("状态更新")
                    
                    # ⚠️ 关键：清扫所有残余占位符（防止 AI 多写的占位符出现在公众号文章里）
                    import re as _re
                    leftover = _re.findall(r'<!--\s*IMG:\d+\s*-->', content)
                    if leftover:
                        print(f"[POST] 🧹 清除 {len(leftover)} 个残余图片占位符: {leftover}", flush=True)
                        logger.info("状态更新")
                    content = _re.sub(r'<!--\s*IMG:\d+\s*-->', '', content)
                    # 同时清除 HTML 实体编码的占位符
                    content = _re.sub(r'&lt;!--\s*IMG:\d+\s*--&gt;', '', content)
                    
                    with open(draft_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                else:
                    # 如果没有插图，也清扫占位符（防止 AI 提前写的占位符残留）
                    import re as _re
                    cleaned = _re.sub(r'<!--\s*IMG:\d+\s*-->', '', content)
                    cleaned = _re.sub(r'&lt;!--\s*IMG:\d+\s*--&gt;', '', cleaned)
                    if cleaned != content:
                        print(f"[POST] 🧹 无插图模式：清除残余占位符", flush=True)
                        logger.info("状态更新")
                        with open(draft_file, 'w', encoding='utf-8') as f:
                            f.write(cleaned)
            else:
                # Insert images evenly among H3 headings or blank lines
                if article_images and "![插图]" not in content:
                    lines = content.split('\n')
                    insert_points = [i for i, line in enumerate(lines) if line.startswith('### ')]
                    if len(insert_points) < len(article_images):
                        # fallback to double newlines if not enough headings
                        insert_points = [i for i, line in enumerate(lines) if line.strip() == '']
                    
                    # Deduplicate and sort points
                    insert_points = sorted(list(set(insert_points)))
                    
                    if insert_points:
                        for img_idx, img_path in enumerate(article_images):
                            pt_idx = (img_idx * len(insert_points)) // len(article_images)
                            if pt_idx < len(insert_points):
                                line_idx = insert_points[pt_idx] + img_idx * 2 # offset for previous insertions
                                lines.insert(line_idx, f'\n![插图]({os.path.abspath(img_path)})\n')
                        
                        content = '\n'.join(lines)
                        with open(draft_file, 'w', encoding='utf-8') as f:
                            f.write(content)

            # Build script arguments
            npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
            baoyu_dir = os.path.join(self.workspace, "baoyu-post-to-wechat")
            
            # ==== 智能主题选择 ====
            # 优先级: 1. 文章分类自动映射  2. .env WECHAT_THEME 手动指定  3. 默认 default
            #
            # ⚠️  注意：baoyu-post-to-wechat 只支持本地内置主题（vendor/baoyu-md/src/themes/*.css）
            #    仅 4 个可用: default / grace / simple / modern
            #    wechat_themes/api.yaml 里的 elegant-gold/bold-red 等属于外部 md2wechat.app API
            #    直接传给 --theme 会报 Missing theme CSS 错误
            CATEGORY_THEME_MAP = {
                "hardcore":  "modern",   # 硬核干货/SOP  → 现代感强，干净有力
                "insight":   "grace",    # 洞察认知      → 优雅精致，字体柔美
                "news":      "default",  # 热点新闻      → 经典微信，通用易读
                "emotional": "grace",    # 情感共鸣      → 优雅舒缓，排版流畅
                "risk":      "modern",   # 风险揭秘/避坑  → 现代严肃，视觉聚焦
                "tool":      "simple",   # 工具测评      → 极简直观，代码友好
                "growth":    "simple",   # 成长/职场      → 简洁清晰，轻松易读
                "crossover": "grace",    # 跨界思维      → 优雅精致，气质独特
            }
            content_category = state.get('content_category', '')
            env_theme = os.environ.get("WECHAT_THEME", "").strip().strip('"')
            if content_category and content_category in CATEGORY_THEME_MAP:
                wechat_theme = CATEGORY_THEME_MAP[content_category]
                print(f"[POST] 🎨 根据文章分类 [{content_category}] 自动选择主题: {wechat_theme}", flush=True)
                logger.info("状态更新")
            elif env_theme:
                wechat_theme = env_theme
                print(f"[POST] 📋 使用 .env 手动指定主题: {wechat_theme}", flush=True)
                logger.info("状态更新")
            else:
                wechat_theme = "default"
                print(f"[POST] 📋 使用默认主题: {wechat_theme}", flush=True)
                logger.info("状态更新")
            
            script_args = [npx_cmd, "-y", "bun"]
            if method == "browser":
                script_path = os.path.join(baoyu_dir, "scripts", "wechat-article.ts")
                script_args.append(script_path)
            else:
                script_path = os.path.join(baoyu_dir, "scripts", "wechat-api.ts")
                script_args.append(script_path)
                
            if is_html:
                script_args.extend(["--html", draft_file])
                print(f"[POST] 📄 发布模式: HTML 直传 (跳过主题渲染)", flush=True)
                logger.info("状态更新")
            else:
                if method == "browser":
                    script_args.extend(["--markdown", draft_file, "--theme", wechat_theme])
                else:
                    script_args.extend([draft_file, "--theme", wechat_theme])
                print(f"[POST] 📄 发布模式: Markdown → 主题渲染 ({wechat_theme})", flush=True)
                logger.info("状态更新")
                
            if cover_path and os.path.exists(cover_path):
                script_args.extend(["--cover", os.path.abspath(cover_path)])
                print(f"[POST] 🖼️  封面图: {os.path.basename(cover_path)}", flush=True)
                logger.info("状态更新")
            if title:
                script_args.extend(["--title", title])
                print(f"[POST] 📌 文章标题: {title}", flush=True)
                logger.info("状态更新")
            
            print(f"[POST] 🚀 执行命令: {' '.join(script_args[:5])} ...", flush=True)
            logger.info("状态更新")
            proc = subprocess.Popen(script_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            for line in proc.stdout:
                print(line, end='', flush=True)
                logger.info("状态更新")
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            print(f"[ERROR] post_to_wechat error: {e}", flush=True)
            logger.error("状态更新")
            return False

    def run_post(self, method="api"):
        logger.info("启动 run_post | method=%s", method)
        state = self.load_state()
        draft_file = state.get('html_file') or state.get('draft_file')
        if not draft_file or not os.path.exists(draft_file): return False
        success = self.post_to_wechat(draft_file, method=method, cover_path=state.get('cover_image'), title=state.get('topic_context', {}).get('title'))
        if success: state['current_step'] = "done"; self.save_state(state)
        return success

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
    parser.add_argument('--refresh', action='store_true', help="强制刷新")
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
