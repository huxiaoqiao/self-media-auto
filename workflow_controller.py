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
import os
import json
import io
from datetime import datetime
from dotenv import load_dotenv
import requests
import re

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

    def load_state(self):
        if os.path.exists(self.session_file):
            with open(self.session_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"current_step": "idle", "selected_topic": None, "draft_file": None}

    def save_state(self, state):
        with open(self.session_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def run_setup(self):
        """
        [v1.1] 首次使用引导：环境检测与配置
        """
        import shutil
        print("\n" + "="*50)
        print("🚀 欢迎使用自媒体系统引导配置 (Setup Wizard)")
        print("="*50 + "\n")

        # 1. 检查 ffmpeg
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            print(f"✅ 环境检查: ffmpeg 已定位 -> {ffmpeg_path}")
        else:
            print("⚠️ 环境警告: 未检测到 ffmpeg。视频 ASR 功能将失效，请先安装 ffmpeg 并添加到 PATH。")

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
        print("✨ 您现在可以运行 'python workflow_controller.py discovery' 开始使用了。")

    def run_from_article(self, url_or_text):
        """
        [v1.1] 快捷入口：从指定文章链接开始创作
        """
        import re
        match = re.search(r'https?://[^\s]+', url_or_text)
        url = match.group(0) if match else url_or_text
        
        print(f"🚀 启动定向创作模式 (From Article)... 原始输入中探测到的 URL: {url}")
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
        match = re.search(r'https?://[^\s]+', url_or_text)
        url = match.group(0) if match else url_or_text
        
        print(f"🚀 启动定向视频创作模式 (From Video)... 原始输入中探测到的 URL: {url}")
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
        
        date_folder = datetime.now().strftime('%Y-%m-%d')
        
        print("🚀 启动 [飞书文档同步]...")
        
        # 1. 读取本地文件内容
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        with open(article_path, 'r', encoding='utf-8') as f:
            article_content = f.read()
        
        # 2. 调用 OpenClaw 飞书插件创建文件夹和文档
        print(f"📁 正在飞书云空间创建文件夹「自媒体内容/{date_folder}」...")
        
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
        return result

    def run_discovery(self, keyword=None):
        """
        [卡点 1 之前] 嗅探系统 (次幂数据版)
        抓取微信爆款文章的热点。
        """
        import requests
        
        state = self.load_state()
        saved_industry = state.get('industry')

        print("[嗅探系统] 启动 [嗅探子系统 - 次幂数据版]...")
        
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
            else:
                print(f"❌ 错误: 未知分类 '{keyword}'")
        elif saved_industry:
            matched = find_category(saved_industry)
            if matched:
                target_category = matched
                print(f"✨ 检测到已保存的专属行业: {matched[1]} (如需更改，请在命令后加 --keyword <新序号>)")

        if not target_category:
            print("👋 请配置您的专属行业/领域(次幂爆款分类)，系统将自动保存以便日后为您自动获取爆文：")
            items = list(categories.items())
            for i in range(0, len(items), 5):
                chunk = items[i:i+5]
                line = "  ".join(f"{k}. {v[1]:<6}" for k, v in chunk)
                print(line)
            print("⚠️ [ACTION_REQUIRED] 等待用户输入：请通过交互通道回复你想抓取的行业序号（如'3'表示科技）。")
            sys.exit(0)

        cimi_category_en, cimi_category_cn = target_category
        print(f"🔍 正在检索微信爆款文章 (分类: {cimi_category_cn})...")

        cimi_app_id = os.getenv("CIMI_APP_ID")
        cimi_app_secret = os.getenv("CIMI_APP_SECRET")
        if not cimi_app_id or not cimi_app_secret:
            print("❌ 未在环境变量中找到 CIMI_APP_ID 或 CIMI_APP_SECRET，请先执行 run_setup 或修改 .env 文件。")
            sys.exit(1)

        api_base = "https://api.cimidata.com"
        headers = {"Content-Type": "application/json"}
        
        print("📥 [1/2] 正在获取次幂数据 Access Token...")
        try:
            token_resp = requests.post(f"{api_base}/api/v2/token", json={"app_id": cimi_app_id, "app_secret": cimi_app_secret}, headers=headers, timeout=10)
            token_resp.raise_for_status()
            access_token = token_resp.json()["data"]["access_token"]
        except Exception as e:
            print(f"❌ 请求 Token 接口时发生异常: {e}")
            sys.exit(1)

        print("📥 [2/2] 正在拉取爆款文章列表...")
        candidates = []
        try:
            articles_resp = requests.post(f"{api_base}/api/v2/hot/articles?access_token={access_token}", 
                                         json={"category": cimi_category_en, "read_num": 1000}, headers=headers, timeout=15)
            articles_data = articles_resp.json()
            items = articles_data.get("data", {}).get("items", [])
            for item in items[:15]:
                candidates.append({
                    "id": item.get("content_url"), "source": "微信公众号(次幂)", "title": item.get("title", ""),
                    "likes": int(item.get("like_num", 0)), "comments": int(item.get("read_num", 0)),
                    "author": item.get("nickname", "未知公众号"), "score": int(item.get("hotness", 0))
                })
        except Exception as e:
            print(f"❌ 请求获取文章接口时发生异常: {e}")
            sys.exit(1)

        print(f"\n=== ✨ 今日推荐 Top {len(candidates)} 爆款选题 === (数据来源: 次幂)")
        for idx, c in enumerate(candidates, 1):
            print(f"{idx}. [{c['source']}] [{c['title']}]({c['id']})")
        print("===================================")
        
        state['current_step'] = "discovery_done"
        state['last_sync'] = datetime.now().isoformat()
        state['candidates'] = candidates
        self.save_state(state)

    def _extract_article_content(self, article_url, selected=None):
        """通用素材提取服务：支持网页解析、次幂 API 保底、抖音文案提取。"""
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
                except Exception: pass
            
            # 2. 缓存路由
            if not selected:
                for c in state.get('candidates', []) + state.get('last_candidates', []):
                    if str(c.get('id')) == tid or str(c.get('title')) == tid:
                        selected = c
                        break
        
        # 3. 兜底
        if not selected:
             selected = {"id": str(topic_id_or_cmd), "title": "自定义素材", "source": "自定义"}

        title_val = selected.get("title", "未命名素材")
        source_val = selected.get("source", "微信")
        print(f"🚀 正在重塑内容: 《{title_val}》 (源: {source_val})")
        
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
                 raw_content = f"【最新增强背景】:\n{sc}\n\n【原始输入素材】:\n{raw_content}"
        except Exception: pass

        # --- AI 改写 (智能分发) ---
        api_key = os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        mid = os.environ.get("LLM_MODEL_ID", "deepseek-chat")
        ip = os.environ.get("AUTHOR_IP_NAME", "大胡")

        if api_key and "your_api_key" not in api_key:
            import httpx
            print(f"🤖 执行场景化创作 (模型: {mid})...")
            try:
                pm_path = os.path.join(self.workspace, "prompts_manager.json")
                conf = {}
                if os.path.exists(pm_path):
                    with open(pm_path, 'r', encoding='utf-8') as f: conf = json.load(f)
                
                cat = "insight"
                if conf:
                    print(f"🧠 [1/2] 意图路由分析...")
                    ci = conf.get("classifier_prompt", "").format(preview_content=raw_content[:1500])
                    try:
                        with httpx.Client(timeout=40) as cl:
                            cr = cl.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                               json={"model": mid, "messages": [{"role": "user", "content": ci}], "temperature": 0.1, "max_tokens": 10})
                            p_key = "".join(c for c in cr.json()["choices"][0]["message"]["content"].strip().lower() if c.isalnum())
                            if p_key in conf["templates"]: cat = p_key
                    except Exception: pass
                    print(f"✨ 场景适配：【{conf['templates'][cat]['name']}】")
                    
                    final_pmt = conf["templates"].get(cat, conf["templates"]["insight"])["prompt"].format(author_ip_name=ip)
                    
                    print(f"📝 [2/2] 深度创作中...")
                    with httpx.Client(timeout=300) as cl:
                        r = cl.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                            json={"model": mid, "messages": [{"role": "user", "content": f"{final_pmt}\n\n素材:\n{raw_content}"}], "temperature": 0.7})
                        final_content = r.json()["choices"][0]["message"]["content"]
                        print(f"✅ 生成完毕：{len(final_content)} 字")
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
        if "## 第二部分" in final_content:
            parts = final_content.split("## 第二部分")
            vs = parts[0].replace("## 第一部分", "").strip()
            ac = parts[1].replace("：", "", 1).strip()
            tm = re.search(r"\[文章标题\]\s*(.*)", ac)
            if tm:
                nt = tm.group(1).strip()
                ac = re.sub(r"\[文章标题\].*", "", ac, count=1).strip()

        ap = os.path.join(dr_root, f"article_{ts}.md")
        with open(ap, "w", encoding='utf-8') as f:
            if nt: f.write(f"# {nt}\n\n")
            f.write(ac)
        
        sp = os.path.join(dr_root, f"video_script_{ts}.md")
        with open(sp, "w", encoding='utf-8') as f: f.write(vs if vs else "未生成脚本")

        print(f"✅ 成果存档 [保存文件]：")
        print(f"   article_path={ap}")
        print(f"   script_path={sp}")
        
        state['current_step'] = "waiting_for_content_review"
        state['draft_file'] = ap
        state['video_script'] = sp
        state['topic_context'] = selected
        if nt: state['topic_context']['title'] = nt
        self.save_state(state)

    def generate_image(self, prompt, model_type="seedream", size="1024*1024"):
        """
        集成多生图引擎支持
        """
        import requests
        import time
        if model_type == "seedream":
            api_key = os.getenv("ARK_API_KEY")
            if not api_key: return None
            url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            
            # 🚀 强制同步为用户提供的最新 API 规范 (Seedream 4.5)
            data = {
                "model": "doubao-seedream-4-5-251128",
                "prompt": prompt, # Prompt is now expected to be Chinese
                "size": size,
                "response_format": "url",
                "sequential_image_generation": "disabled",
                "stream": False,
                "watermark": False # Ensure watermark is always False
            }
            try:
                print(f"[视觉工程] 正在通过 Ark 调用火山引擎(Seedream 4.5/2.0) 渲染 {size} 比例资产...")
                r = requests.post(url, headers=headers, json=data, timeout=60)
                resp = r.json()
                img_url = resp.get("data", [{}])[0].get("url")
                if not img_url:
                    print(f"[ERROR] Volcengine API Response: {resp}")
                return img_url
            except Exception as e:
                print(f"[ERROR] Volcengine generation failed: {e}")
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
            return None

    def download_image_file(self, url, folder=None):
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
            return None

    def post_to_wechat(self, file_path, method="browser", cover_path=None, title=None):
        import subprocess
        print(f"🚀 正在通过 [{method}] 发布文章...")
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
        state = self.load_state()
        # 强制初始化并清空之前的图片记录（防止重试时图片不断追加）
        state['article_images'] = []
        state['cover_image'] = ""
        self.save_state(state)
        
        draft_file = state.get('draft_file')
        if not draft_file or not os.path.exists(draft_file): 
            print("[FEISHU_STATUS] ERR=未找到草稿文件", flush=True)
            return False
            
        print(f"\n🎨 [视觉导演] 开启弹性生成 (引擎: {model_type})...", flush=True)
        with open(draft_file, "r", encoding="utf-8") as f: content = f.read()

        # 1. 方案分析
        plan = self.analyze_visuals(content)
        if not plan:
            print("[FEISHU_STATUS] WARN=分析方案失败，使用兜底图", flush=True)
            plan = {"cover": {"prompt": "大胡老师的数字花园"}, "illustrations": []}

        # 2. 生成封面 (容错机制)
        try:
            cp = plan.get("cover", {}).get("prompt", "封面图")
            print(f"🖼️ [封面] 准备构建: {cp[:30]}...", flush=True)
            c_url = self.generate_image(cp, model_type=model_type, size="3072x1308")
            if c_url:
                l_cover = self.download_image_file(c_url, folder=os.path.join(self.workspace, 'assets', 'covers'))
                if l_cover:
                    state['cover_image'] = l_cover
                    self.save_state(state)
                    # 钢铁级实时推送协议
                    print(f"[FEISHU_PREVIEW] TYPE=COVER PATH={l_cover}", flush=True)
                else:
                    print("[FEISHU_STATUS] ERR=封面下载失败", flush=True)
            else:
                print("[FEISHU_STATUS] WARN=封面API返回为空(风控?)", flush=True)
        except Exception as e:
            print(f"[FEISHU_STATUS] ERR=封面流程异常:{str(e)[:50]}", flush=True)

        # 3. 生成插图 (单图闭环)
        ills = plan.get("illustrations", [])
        if ills:
            print(f"\n🎨 [排期] 共有 {len(ills)} 张插图待产...", flush=True)
            
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
                
                try:
                    i_url = self.generate_image(p, model_type=model_type, size=size)
                    if i_url:
                        l_path = self.download_image_file(i_url, folder=os.path.join(self.workspace, 'assets', 'illustrations'))
                        if l_path:
                            state['article_images'].append(l_path)
                            self.save_state(state)
                            # 钢铁级实时推送协议
                            print(f"[FEISHU_PREVIEW] TYPE=ILLUS INDEX={i} PATH={l_path}", flush=True)
                        else:
                            print(f"[FEISHU_STATUS] ERR=插图{i}下载失败", flush=True)
                    else:
                        print(f"[FEISHU_STATUS] WARN=插图{i}API无产出", flush=True)
                except Exception as ie:
                    print(f"[FEISHU_STATUS] ERR=插图{i}异常:{str(ie)[:50]}", flush=True)
            
            self.save_state(state)
            
        print(f"\n[FEISHU_STATUS] DONE=已产出 {len(state.get('article_images', []))} 张图", flush=True)
        return True

    def run_post(self, method="api"):
        state = self.load_state()
        draft_file = state.get('draft_file')
        if not draft_file or not os.path.exists(draft_file): return False
        success = self.post_to_wechat(draft_file, method=method, cover_path=state.get('cover_image'), title=state.get('topic_context', {}).get('title'))
        if success: state['current_step'] = "done"; self.save_state(state)
        return success

    def run_publish(self, model_type="seedream", method="api"):
        if self.run_visuals(model_type=model_type):
            return self.run_post(method=method)
        return False

def main():
    parser = argparse.ArgumentParser(description="自媒体工作流调度器")
    parser.add_argument('action', choices=['setup', 'discovery', 'from-article', 'from-video', 'repurpose', 'visuals', 'post', 'publish', 'status', 'sync'], help="动作")
    parser.add_argument('--keyword', type=str); parser.add_argument('--url', type=str); parser.add_argument('--id', type=str)
    parser.add_argument('--model', default='seedream'); parser.add_argument('--method', default='api')
    parser.add_argument('--script', type=str); parser.add_argument('--article', type=str)
    
    args = parser.parse_args()
    controller = SelfMediaController()
    
    if args.action == 'setup': controller.run_setup()
    elif args.action == 'discovery': controller.run_discovery(args.keyword)
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
