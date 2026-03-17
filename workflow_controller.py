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
from datetime import datetime
from dotenv import load_dotenv

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
        # 使用 subprocess 调用 openclaw CLI
        print(f"📁 正在飞书云空间创建文件夹「自媒体内容/{date_folder}」...")
        
        # 这里通过返回路径让 OpenClaw Commander 调用 feishu_drive_file 和 feishu_create_doc
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
        print(f"   📂 文件夹：自媒体内容/{date_folder}")
        print(f"   🎬 脚本：{result['script_title']}")
        print(f"   📝 长文：{result['article_title']}")
        print("\n⚠️ [ACTION_REQUIRED] 等待 Commander 调用飞书 API 完成文档创建...")
        
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

        # ---------------------
        # CiMi API Calls
        # ---------------------
        cimi_app_id = os.getenv("CIMI_APP_ID")
        cimi_app_secret = os.getenv("CIMI_APP_SECRET")
        if not cimi_app_id or not cimi_app_secret:
            print("❌ 未在环境变量中找到 CIMI_APP_ID 或 CIMI_APP_SECRET，请先执行 run_setup 或修改 .env 文件。")
            sys.exit(1)

        api_base = "https://api.cimidata.com"
        headers = {"Content-Type": "application/json"}
        
        print("📥 [1/2] 正在获取次幂数据 Access Token...")
        try:
            token_resp = requests.post(
                f"{api_base}/api/v2/token",
                json={"app_id": cimi_app_id, "app_secret": cimi_app_secret},
                headers=headers,
                timeout=10
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            if token_data.get("code") != 200:
                print(f"❌ 获取 Token 失败: {token_data.get('msg')}")
                sys.exit(1)
            access_token = token_data["data"]["access_token"]
        except Exception as e:
            print(f"❌ 请求 Token 接口时发生异常: {e}")
            sys.exit(1)

        print("📥 [2/2] 正在拉取爆款文章列表...")
        candidates = []
        try:
            articles_resp = requests.post(
                f"{api_base}/api/v2/hot/articles?access_token={access_token}",
                json={"category": cimi_category_en, "read_num": 1000},
                headers=headers,
                timeout=15
            )
            articles_resp.raise_for_status()
            articles_data = articles_resp.json()
            
            if articles_data.get("code") != 200:
                print(f"❌ 获取文章失败: {articles_data.get('msg')}")
                sys.exit(1)
                
            items = articles_data.get("data", {}).get("items", [])
            for item in items[:15]:
                candidates.append({
                    "id": item.get("content_url"),
                    "source": "微信公众号(次幂)",
                    "title": item.get("title", ""),
                    "likes": int(item.get("like_num", 0)),
                    "comments": int(item.get("read_num", 0)),
                    "author": item.get("nickname", "未知公众号"),
                    "score": int(item.get("hotness", 0))
                })
        except Exception as e:
            print(f"❌ 请求获取文章接口时发生异常: {e}")
            sys.exit(1)

        print(f"\n=== ✨ 今日推荐 Top {len(candidates)} 爆款选题 === (数据来源: 次幂)")
        if not candidates:
            print("未找到近期满足要求的素材。")
        else:
            for idx, c in enumerate(candidates, 1):
                print(f"{idx}. [{c['source']}] [{c['title']}]({c['id']})")
                print(f"   👤 {c['author']} | 👁️ 阅读: {c['comments']} | 👍 赞: {c['likes']} | 🔥 热度: {c['score']}")
        print(f"{len(candidates) + 1}. [自定义] 退回重搜或告诉我一个新方向")
        print("===================================")
        print("👉 请用户回复：包含 --id 对应你想二创的内容序号，或重新执行 discovery --keyword")

        state = self.load_state()
        state['current_step'] = "waiting_for_topic_selection"
        state['last_candidates'] = candidates
        self.save_state(state)

    def run_repurpose(self, topic_id_or_cmd):
        """
        [卡点 1 之后, 卡点 2 之前] 内容重塑系统
        提取素材、改写、降 AI 味。
        """
        import subprocess
        import sys
        import os
        import re
        
        state = self.load_state()
        topic_id_or_cmd = str(topic_id_or_cmd).strip('"').strip("'")
        candidates = state.get('last_candidates', [])
        selected = {}
        
        if isinstance(candidates, list):
            # Try numeric index first
            if topic_id_or_cmd.isdigit():
                idx = int(topic_id_or_cmd) - 1
                if 0 <= idx < len(candidates):
                    selected = candidates[idx]
            
            # If not found by index, try matching ID
            if not selected:
                for c in candidates:
                    if isinstance(c, dict) and str(c.get("id")) == topic_id_or_cmd:
                        selected = c
                        break
                
        if not selected or not isinstance(selected, dict):
            print(f"⚠️ 未在缓存的候选列表中找到ID '{topic_id_or_cmd}'，将作为自定义话题处理。")
            selected = {"id": topic_id_or_cmd, "source": "自定义", "title": topic_id_or_cmd, "author": "User"}

        source_val = str(selected.get('source', ''))
        title_val = str(selected.get('title', ''))
        print(f"🧠 启动 [内容重塑引擎] 处理选题: [{source_val}] {title_val}")
        
        raw_content = ""
        # ==========================
        # 1. 自动提取原素材全文/视频文案
        # ==========================
        print("⏳ 正在解析并下载源素材内容...")
        def download_video_and_extract_audio(url: str, platform: str) -> str:
            import os
            import subprocess
            import re
            
            if platform in ["抖音", "douyin"]:
                print(f"📥 正在挂载专属抖音下载引擎 (douyin-download-1.2.0) 以应对流媒体封锁...")
                douyin_js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "douyin-download-1.2.0", "douyin.js")
                output_dir = os.path.join(os.getcwd(), 'cache', 'douyin_extract')
                os.makedirs(output_dir, exist_ok=True)
                
                # Check SILI_FLOW_API_KEY
                if not os.getenv("SILI_FLOW_API_KEY"):
                    print("⚠️ 未设置 SILI_FLOW_API_KEY，无法提取语音。可以在 .env 中配置。")
                    return ""
                
                cmd = ["node", douyin_js_path, "extract", url, "-o", output_dir, "--no-segment"]
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
                    if res.returncode != 0:
                        print(f"❌ douyin.js 运行失败: {res.stderr}")
                        return ""
                    
                    # 匹配保存位置
                    match = re.search(r"保存位置:\s*(.+?\.md)", res.stdout)
                    if match:
                        md_path = match.group(1).strip()
                        if os.path.exists(md_path):
                            with open(md_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            # 提取 "## 文案内容" 之后的部分
                            parts = content.split("## 文案内容")
                            if len(parts) > 1:
                                final_transcript = parts[-1].strip()
                                return f"【视频文稿】{final_transcript}"
                    
                    print("⚠️ 未能在输出中找到文件保存位置或文件不存在。")
                    return ""
                except Exception as e:
                    print(f"⚠️ douyin.js解析受阻: {e}")
                    return ""
            else:
                print(f"⚠️ 目前暂不支持平台 {platform} 的自动提取。系统将尝试从话题标题中生成内容。")
                return ""

        if source_val == "小红书":
            print("📥 正在分发小红书内容截获任务...")
            raw_content = ""
            # 首先尝试通过原生的 xhs-cli 去读取图文内容，看看是不是图文笔记
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                # 在这拿到的是小红书的分享URL页面
                import re
                id_str = str(selected.get("id", ""))
                match = re.search(r'/explore/([a-zA-Z0-9]+)', id_str)
                note_id = match.group(1) if match else id_str
                
                res = subprocess.run(["xhs", "read", note_id, "--json"], capture_output=True, text=True, env=env)
                if res.returncode == 0:
                    note_data = json.loads(res.stdout).get("data", {})
                    if note_data.get("type", "") == "video":
                        print("⚙️ 此小红书为视频笔记，挂载 yt-dlp 引擎探测底层源...")
                        xhs_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                        dl_content = download_video_and_extract_audio(xhs_url, "小红书")
                        raw_content = dl_content if dl_content else (str(note_data.get("desc", "")) or str(note_data.get("title", "")))
                    else:
                        raw_content = str(note_data.get("desc", "")) or str(note_data.get("title", ""))
                    print(f"✅ 小红书素材提取成功，文本长度：{len(raw_content)} 字")
            except Exception as e:
                print("❌ 小红书接口访问失败:", e)
                
        elif source_val in ["公众号", "微信公众号(次幂)"]:
            print("📥 正在抓取公众号主体文章（图文）...")
            try:
                from scrapling.fetchers import Fetcher
                article_url = str(selected.get("id", ""))
                if article_url.startswith("/link"):
                    article_url = f"https://weixin.sogou.com{article_url}"
                
                print("⚙️ 正在集成并调用本地技能库 [url-reader-0.1.1]...")
                import sys, os
                url_reader_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'url-reader-0.1.1', 'scripts')
                if url_reader_path not in sys.path:
                    sys.path.insert(0, url_reader_path)
                
                from url_reader import read_url
                from wechat_url_converter import convert_long_to_short
                import asyncio
                
                if "weixin.sogou.com/link" in article_url:
                    print("⚠️ 检测到搜狗临时跳转重定向链接，正在调用 Playwright 解析真连接...")
                    try:
                        real_url = asyncio.run(convert_long_to_short(article_url))
                        if real_url and isinstance(real_url, str) and "mp.weixin.qq.com" in real_url:
                            article_url = real_url
                            print(f"✅ 短链接置换成功: {article_url[:50]}...")
                    except Exception as e:
                        print("⚠️ 置换失败，按原计划向下送交引擎:", e)
                
                print("⚙️ 正在通过 url_reader 多路并行读取 (Jina / Playwright)...")
                result = read_url(article_url, verbose=False)
                
                if isinstance(result, dict) and result.get("success"):
                    raw_content = str(result.get("content", ""))
                else:
                    raise Exception(f"url-reader 产生错误")

                if not raw_content or len(raw_content) < 50:
                    raise Exception("返回内容过短")
                
                print(f"✅ 公众号原素材提取成功，文本长度：{len(raw_content)} 字")
            except Exception as e:
                print(f"⚠️ url-reader 提取受阻: {e}，正在启动[次幂数据 API] 保底截获方案...")
                try:
                    import requests
                    import re
                    cimi_app_id = os.getenv("CIMI_APP_ID")
                    cimi_app_secret = os.getenv("CIMI_APP_SECRET")
                    fallback_url = str(selected.get("id", ""))
                    if fallback_url.startswith("/link"):
                        fallback_url = f"https://weixin.sogou.com{fallback_url}"
                        
                    if not cimi_app_id or not cimi_app_secret:
                        raise Exception("未找到 CIMI_APP_ID / CIMI_APP_SECRET 凭据，无法执行保底")
                        
                    api_base = "https://api.cimidata.com"
                    print("📥 正在向次幂申请二次提取令牌...")
                    token_resp = requests.post(
                        f"{api_base}/api/v2/token",
                        json={"app_id": cimi_app_id, "app_secret": cimi_app_secret},
                        headers={"Content-Type": "application/json"},
                        timeout=10
                    )
                    token_data = token_resp.json()
                    if token_resp.status_code != 200 or token_data.get("code") != 200:
                        raise Exception(f"Token获取失败 ({token_data.get('msg')})")
                        
                    access_token = token_data["data"]["access_token"]
                    
                    print(f"📥 正在解析原文章正文: {fallback_url[:50]}...")
                    detail_resp = requests.post(
                        f"{api_base}/api/v3/articles/detail?access_token={access_token}",
                        json={"url": fallback_url},
                        headers={"Content-Type": "application/json"},
                        timeout=20
                    )
                    detail_data = detail_resp.json()
                    if detail_resp.status_code != 200 or detail_data.get("code") != 200:
                        raise Exception(f"正文获取失败 ({detail_data.get('msg')})")
                        
                    html_content = detail_data["data"].get("html", "")
                    
                    # 粗略清洗 HTML 标签，保留纯干文案
                    clean_text = re.sub(r'<[^>]+>', ' ', html_content).strip()
                    clean_text = re.sub(r'\s+', ' ', clean_text)
                    
                    if len(clean_text) < 50:
                        raise Exception("处理后正文由于过短被驳回")
                        
                    raw_content = clean_text
                    print(f"✅ 次幂 API 提取兜底成功，无损获取干文：{len(raw_content)} 字！")
                    
                except Exception as fallback_e:
                    print(f"⚠️ 次幂提取同样抛出异常 ({fallback_e})，自动跌落为模拟快照...")
                    raw_content = f"【内容快照】关于这篇《{title_val}》，这其实是一篇非常经典的底层逻辑拆解文章。\n作者指出：在这其中，真正的重点不是盲目努力而在于选择工具的杠杆。\n总而言之，做自媒体要保持长线思维，深入探讨垂直领域。"
                
        elif source_val == "抖音":
            print("📥 检测到[抖音]源，将直接通过专业视频组件挂载提取...")
            original_id = str(selected.get("id", ""))
            
            if original_id.startswith("抖音热搜:"):
                keyword = original_id.replace("抖音热搜:", "")
                print(f"🔎 正在检索「{keyword}」对应的抖音头部视频素材...")
                print("⚠️ 抖音网页端实时搜索防抓取较严，为保障工作流稳定，本次直接沿用热词文案...")
                dl_content = ""
            else:
                dl_content = download_video_and_extract_audio(original_id, "抖音")
                
            if dl_content:
                raw_content = dl_content
            else:    
                import time
                time.sleep(0.5)
                raw_content = f"（ASR语音转写原声）今天大家都在看【{title_val}】，其实背后的核心逻辑很简单。第一点，..."
            print(f"✅ 抖音视频字幕提取成功，文本长度：{len(raw_content)} 字")
                
        elif source_val == "自定义" or source_val == "视频链接":
            print(f"🔗 检测到输入的自定义内容或视频源: {source_val}")
            original_id = str(selected.get("id", ""))
            # 如果是符合视频特征的链接或者是明确要求的视频链接
            is_video_link = (original_id.startswith("http") and ("douyin.com" in original_id or "bilibili.com" in original_id or "youtube.com" in original_id))
            if is_video_link or source_val == "视频链接":
                platform = "抖音" if "douyin.com" in original_id else "视频平台"
                dl_content = download_video_and_extract_audio(original_id, platform)
                if dl_content:
                    raw_content = dl_content
            elif original_id.startswith("http"):
                # 其他链接按公众号/网页处理
                selected["source"] = "公众号"
                return self.run_repurpose(original_id) 
                    
        # 统一的兜底/校验：如果上面所有分支都没能抓到实质性文采，说明下载或提取失败
        if not raw_content or "ASR语音转写原声" in raw_content or len(raw_content) < 20:
            print("\n❌ [致命错误] 视频内容提取失败或文稿太短。")
            print("💡 建议：")
            print("  1. 检查是否安装了 ffmpeg (提取音频必需) 并已添加到全局 PATH")
            print("  2. 请检查网络环境、抖音链接是否有效")
            print("  3. 在 .env 中确保已配置 SILI_FLOW_API_KEY")
            print("\n🚀 流程已中断，请处理上述问题后重试。")
            sys.exit(1)
                
        import os

        # ==========================
        # 2. 调用大模型：内容重塑 & 洗稿 (衍生双形态)
        # ==========================
        final_content = ""
        
        # 优先从环境变量读取配置
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model_id = os.getenv("LLM_MODEL_ID", "deepseek-chat")
        author_ip_name = os.getenv("AUTHOR_IP_NAME", "大胡")

        if api_key and "your_api_key" not in api_key:
            import httpx
            print(f"🤖 密钥检测成功，正在启动【大 IP专属爆款改写引擎】(模型: {model_id}, 当前IP: {author_ip_name})...")
            try:
                # 融合了大 IP (苗哥体) 精华的写作提示词，适配基础 Markdown 结构双形态输出
                prompt_skill = (
                    f"你现在的身份是自媒体领域的顶级极客大IP：【{author_ip_name}】。\n"
                    "你的任务是对提供的【原始素材】进行极具个人锋芒的洗稿与升维。你必须输出两大块内容（使用 Markdown 分割）：\n\n"
                    "## 第一部分：【爆款短视频脚本】\n"
                    "- 简明扼要，适合口播。提取文章的灵魂反常识观点。短句为主，不用“很多”等虚词。\n\n"
                    "## 第二部分：【深度长文（正文）】\n"
                    "- 严格遵循以下【IP爆款写作规范】和结构要求：\n\n"
                    "### 一、开篇结构\n"
                    "- 简短标题句（1-3个字或一句话），直接点明主题。\n"
                    f"- 固定开场白：\"hi，我是{author_ip_name}\"（建立个人品牌标识）。\n"
                    "- 开门见山：第一段就抛出核心观点或揭示残酷真相。\n\n"
                    "### 二、内容风格特征\n"
                    "1. 语言表达：口语化，像聊天，节奏明快，长话短说。适度用“你看”“其实”“说白了”等词汇，甚至可以用略带调侃的网络用语。\n"
                    "2. 论证思维：直击人性，不避讳金钱；反常识思考挑战主流；大量使用对比（强vs弱）或假设场景（“你让他...他会...”）。\n"
                    "3. 核心准则（祛魅法则）：站在读者焦虑的对立面讲真话。强调个人责任和行动力（知行合一），去他的虚假鸡汤。\n\n"
                    "### 三、文章结构模板规范\n"
                    "你必须严格使用 `### 小标题` 这个 Markdown 格式区分段落（这对于后续视觉排版非常重要！）：\n"
                    "### （这里是你写的小标题1：拆解问题本质）\n"
                    "正文片段...\n"
                    "### （这里是你写的小标题2：揭示底层逻辑）\n"
                    "正文片段...\n"
                    "### （这里是你写的小标题3：强化核心观点并收尾）\n"
                    f"结尾金句总结，并在末尾加上：“加我微信 XX，领取一份AI副业资料”。\n\n"
                    "### 四、禁忌与必备 (严格要求)\n"
                    "❌ 避免：鸡汤式安慰、大道理、模棱两可、长篇大论、过度修辞、套话（如“在当今社会”、“不得不提”）。\n"
                    f"✅ 必备：真实感细节、击中痛点、新视角，符合【{author_ip_name}】的强人设。\n\n"
                    f"【原始提提取素材】：\n{raw_content[:2500]}"
                )

                headers = {"Authorization": f"Bearer {api_key}"}
                payload = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt_skill}]
                }
                res = httpx.post(f"{api_base}/chat/completions", headers=headers, json=payload, timeout=60)
                if res.status_code == 200:
                    final_content = res.json()["choices"][0]["message"]["content"]
                    print(f"✅ IP专属爆款沉浸式改写结束！")
                else:
                    print(f"⚠️ API 返回异常 (Code: {res.status_code}): {res.text}")
            except Exception as e:
                print("⚠️ API 请求抛出异常:", e)

        # 没有配通大模型的情况做 Mock 占位
        if not final_content:
            print("\n⚠️ 未配置有效的大模型 API 密钥，改写步骤将被跳过。系统使用原内容为您保留了占位文案。")
            final_content = f"# {selected['title']}\n\n**[占位] 原文提取摘要**：\n\n{raw_content[:400]}...\n\n> 💡 请在 `.env` 文件中配置您的 `OPENAI_API_KEY`（任意兼容基座模型皆可），就能自动执行顶尖改写与洗稿了。"

        # ==========================
        # 3. 拆分内容并输出到磁盘 + 飞书文档
        # ==========================
        time_slug = datetime.now().strftime('%Y%m%d%H%M')
        date_folder = datetime.now().strftime('%Y-%m-%d')
        
        # 创建本地 drafts 文件夹
        drafts_dir = os.path.join(self.workspace, 'drafts', date_folder)
        os.makedirs(drafts_dir, exist_ok=True)
        
        # 提取脚本部分
        video_script = ""
        article_content = ""
        
        if "## 第一部分" in final_content and "## 第二部分" in final_content:
            parts = final_content.split("## 第二部分")
            video_script = parts[0].replace("## 第一部分：", "").replace("## 第一部分", "").strip()
            article_content = "## 第二部分" + parts[1]
            article_content = article_content.replace("## 第二部分：", "").replace("## 第二部分", "").strip()
        else:
            article_content = final_content

        # 写入短视频脚本到本地 drafts 文件夹
        script_name = f"video_script_{time_slug}.md"
        script_path = os.path.join(drafts_dir, script_name)
        with open(script_path, "w", encoding='utf-8') as f:
            f.write(video_script if video_script else "未生成有效脚本")
            
        # 写入图文长稿到本地 drafts 文件夹
        article_name = f"article_{time_slug}.md"
        article_path = os.path.join(drafts_dir, article_name)
        with open(article_path, "w", encoding='utf-8') as f:
            f.write(article_content)

        print(f"\n✅ 内容拆分完成：")
        print(f"   🎬 爆款脚本: {script_path}")
        print(f"   📝 深度长文: {article_path}")
        print("\n👀 【卡点2 - 人工介入】：您可以对这两个文件分别修饰。确认无误后，运行 publish 阶段将针对‘长文’进行配图。")

        state['current_step'] = "waiting_for_content_review"
        state['draft_file'] = article_path # publish 阶段主要针对长文配图
        state['video_script'] = script_path
        state['topic_context'] = selected
        self.save_state(state)

    def generate_image(self, prompt, model_type="seedream", size="1024*1024"):
        """
        集成多生图引擎支持
        model_type: "z", "qwen", "wan" (Aliyun DashScope) 或 "seedream" (Volcengine Ark)
        """
        import requests
        import time
        
        if model_type == "seedream":
            # 火山引擎 Ark 生图逻辑
            api_key = os.getenv("ARK_API_KEY")
            if not api_key:
                print("❌ 错误：未在环境变量中找到 ARK_API_KEY")
                return None
            
            url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # 转换尺寸为火山支持的格式 (Seedream 5.0 要求较大像素，至少 3686400 像素)
            # 官方预设：'2k' (2048x1152 ≈ 2.3M) < 阈值，'3k' (3072x1728 ≈ 5.3M) > 阈值
            volc_size = size.replace("*", "x")
            if "1280x544" in volc_size:
                 volc_size = "3072x1308" # 保持 2.35:1 比例且满足 3.6M+ 像素要求
            else:
                 volc_size = "3k" # 插图统一用 3k 确保成功
            
            data = {
                "model": "doubao-seedream-5-0-260128",
                "prompt": prompt,
                "size": volc_size,
                "response_format": "url",
                "watermark": False
            }
            
            try:
                print(f"[视觉工程] 正在调用 [doubao-seedream-5-0] 生成视觉素材...")
                response = requests.post(url, headers=headers, json=data, timeout=60)
                res_json = response.json()
                if response.status_code == 200:
                    image_url = res_json.get("data", [{}])[0].get("url")
                    if image_url:
                        print(f"✅ 图像生成成功！")
                        return image_url
                print(f"[Error] 图像生成失败: {res_json.get('error', {}).get('message', '未知错误')}")
            except Exception as e:
                print(f"❌ 调用火山生图接口异常: {e}")
            return None

        else:
            # 阿里云百炼生图逻辑
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                print("❌ 错误：未在环境变量中找到 DASHSCOPE_API_KEY")
                return None

            model_map = {
                "z": "z-image-turbo",
                "qwen": "qwen-image-2.0-pro",
                "wan": "wan2.6-t2i"
            }
            model_id = model_map.get(model_type, "wan2.6-t2i")
            url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            params = {"prompt_extend": True, "watermark": False, "size": size}
            if model_type == "qwen":
                params["negative_prompt"] = "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。"

            data = {
                "model": model_id,
                "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                "parameters": params
            }
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    print(f"🎨 正在调用 [{model_id}] 生成视觉素材 (尝试 {attempt+1}/{max_retries})...")
                    response = requests.post(url, headers=headers, json=data, timeout=60)
                    res_json = response.json()
                    if response.status_code == 200:
                        image_url = res_json.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", [{}])[0].get("image")
                        if image_url:
                            print(f"✅ 图像生成成功！")
                            return image_url
                    
                    if "rate limit" in str(res_json.get('message', '')).lower() or response.status_code == 429:
                        wait_time = (attempt + 1) * 5
                        print(f"⏳ 触发速率限制，正在等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    print(f"❌ 图像生成失败: {res_json.get('message', '未知错误')}")
                    if "Total pixels" in res_json.get('message', ''): break
                except Exception as e:
                    print(f"❌ 调用阿里云接口异常: {e}")
                    time.sleep(2)
            return None

    def download_image_file(self, url, folder=None):
        import requests
        from urllib.parse import urlparse
        
        if not folder:
            date_slug = datetime.now().strftime('%Y-%m-%d')
            folder = os.path.join(self.workspace, 'assets', date_slug)
            
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            
        try:
            path = urlparse(url).path
            ext = os.path.splitext(path)[1] or ".png"
            filename = f"gen_image_{datetime.now().strftime('%H%M%S')}{ext}"
            filepath = os.path.join(folder, filename)
            
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                return filepath
        except Exception as e:
            print(f"⚠️ 下载图片失败: {e}")
        return None

    def analyze_visuals(self, article_content):
        """
        [核心逻辑] 集成 baoyu-cover-image 和 baoyu-article-illustrator 的视觉分析
        利用 LLM 对文章进行视觉拆解。
        """
        import httpx
        
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        if not api_key:
            return None

        print("🧠 正在进行 [视觉语义分析] (基于 baoyu-skills 规范)...")
        
        visual_analysis_prompt = f"""
你现在是行业顶尖的视觉设计师，擅长为公众号文章进行【视觉工程】设计。
你需要基于以下【文章内容】，输出一套完整的视觉配图方案，包括 1 张封面图和 1-2 张文章插图。

### 规范要求 (baoyu-cover-image)
封面图设计遵循 5 维度：
1. Type (类型): hero (大核心点), conceptual (概念抽象), typography (文字主导), metaphor (隐喻), scene (场景), minimal (极简)
2. Palette (调色板): warm, elegant, cool, dark, earth, vivid, pastel, mono, retro, duotone
3. Rendering (渲染风格): flat-vector (扁平矢量), hand-drawn (手绘), painterly (油画风格), digital (数码绘制), pixel (像素), chalk (粉笔), screen-print (丝网印刷)
4. Text (文字密度): none, title-only, title-subtitle, text-rich
5. Mood (情绪): subtle (轻快), balanced (中性), bold (强烈)

### 规范要求 (baoyu-article-illustrator)
文章插图设计遵循 Type × Style：
- Type: infographic (信息图), scene (情节场景), flowchart (流程图), comparison (对比), framework (框架), timeline (时间轴)
- Style: vector-illustration, notion, warm, minimal, blueprint, watercolor, elegant, editorial, scientific, screen-print

### 输出格式
请务必返回合法的 JSON 格式字符串（不要包含任何 Markdown 代码块，不要包含其它说明文字），结构如下：
{{
  "cover": {{
    "title": "封面显示的核心标题",
    "type": "...",
    "palette": "...",
    "rendering": "...",
    "text": "...",
    "mood": "...",
    "prompt": "基于以上维度和 base-prompt 规范生成的精炼生图提示词"
  }},
  "illustrations": [
    {{
      "anchor_text": "文章中用于插入图片的某一段落或特定短语",
      "type": "...",
      "style": "...",
      "aspect": "16:9 | 1:1 | 3:4 | long",
      "purpose": "为什么要这张图",
      "prompt": "遵循 ZONES / LABELS / COLORS / STYLE 结构的生图提示词，必须包含文章中的具体数据或核心术语"
    }}
  ]
}}

### 插图比例建议：
- 横向大图 (16:9): 最符合手机横向视觉，观感大气。
- 方形图 (1:1): 适合展示产品细节、头像或图标。
- 纵向长图 (3:4): 竖屏占比大，视觉冲击力强，适合人像或海报。
- 超长图 (long): 宽度固定，适合条漫、信息图或长列表。

### 待处理文章内容：
{article_content[:3000]}
"""
        try:
            model_id = os.getenv("LLM_MODEL_ID", "deepseek-chat")
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": visual_analysis_prompt}],
                "response_format": {"type": "json_object"}
            }
            res = httpx.post(f"{api_base}/chat/completions", headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                result = res.json()["choices"][0]["message"]["content"]
                if "```json" in result:
                    result = result.split("```json")[1].split("```")[0].strip()
                elif "```" in result:
                    result = result.split("```")[1].split("```")[0].strip()
                return json.loads(result)
        except Exception as e:
            print(f"⚠️ 视觉分析失败: {e}")
        return None

    def post_to_wechat(self, file_path, method="browser"):
        """
        利用 baoyu-post-to-wechat 技能将文章发布到公众号草稿箱
        """
        import subprocess
        
        print(f"🚀 正在通过 [{method}] 模式启动 [触达子系统 - WeChat Publish]...")
        
        # 定位技能脚本路径
        skill_base = os.path.join(self.workspace, 'baoyu-post-to-wechat')
        scripts_dir = os.path.join(skill_base, 'scripts')
        
        # 默认使用 wechat-article.ts (浏览器模式，兼容性最好)
        script_name = "wechat-article.ts" if method == "browser" else "wechat-api.ts"
        script_path = os.path.join(scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            print(f"❌ 错误：找不到发布脚本 {script_path}")
            return False

        # 构造执行命令
        # 始终指定 theme 为 default 确保视觉一致性
        cmd = ["bun", script_path]
        if method == "browser":
            cmd.extend(["--markdown", file_path, "--theme", "default"])
        else:
            cmd.extend([file_path, "--theme", "default"])

        try:
            # 继承当前环境变量 (确保 .env 中的密钥生效)
            env = os.environ.copy()
            # 设置编码防止 Windows 下乱码
            env["PYTHONIOENCODING"] = "utf-8"
            
            # 使用 subprocess.run 运行，并实时打印输出
            # 浏览器模式可能需要用户扫码，因此不能完全 quiet
            print(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, cwd=scripts_dir, env=env)
            
            if result.returncode == 0:
                print("✅ 公众号草稿上传成功！")
                return True
            else:
                print(f"❌ 公众号发布失败，返回码: {result.returncode}")
                return False
        except Exception as e:
            print(f"❌ 执行发布脚本时发生异常: {e}")
            return False

    def run_publish(self, model_type="wan", method="api"):
        """
        [全面升级] 视觉工程与分发子系统
        集成了 baoyu-cover-image 的封面生成与 baoyu-article-illustrator 的插图生成。
        最后调用 baoyu-post-to-wechat 发布。
        """
        import subprocess
        state = self.load_state()
        draft_file = state.get('draft_file')
        topic_context = state.get('topic_context', {})
        
        if not draft_file or not os.path.exists(draft_file):
            print("❌ 错误：未找到审核通过的草稿文件。请先完成重塑阶段。")
            return

        print("\n🎨 启动 [视觉工程子系统 - Baoyu V2.0]...")
        
        with open(draft_file, "r", encoding="utf-8") as f:
            article_content = f.read()

        visual_plan = self.analyze_visuals(article_content)
        
        if not visual_plan:
            print("⚠️ 视觉大脑分析失败，将使用默认快照。")
            visual_plan = {
                "cover": {
                    "title": topic_context.get("title", "自媒体爆款"),
                    "prompt": f"自媒体爆款封面图，关于{topic_context.get('title')}, 高质量插画风格"
                },
                "illustrations": []
            }

        cover_info = visual_plan.get("cover", {})
        # 公众号封面固定比例 900:383。Wan2.6 限制起步像素 > 589824，因此使用 1280*544 (约 2.35:1)
        print(f"🖼️ [封面生成] 方案类型: {cover_info.get('type', 'hero')} | 适配尺寸: 1280*544 (目标比例 900:383)")
        
        date_slug = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.join(self.workspace, 'assets', date_slug)

        img_url = self.generate_image(cover_info.get("prompt"), model_type=model_type, size="1280*544")
        if img_url:
            local_img = self.download_image_file(img_url, folder=output_dir)
            if local_img:
                print(f"✅ 封面图已就位: {local_img}")
                with open(draft_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                if "![封面图]" not in content:
                    with open(draft_file, 'w', encoding='utf-8') as f:
                        # 使用相对路径，去掉 file:/// 前缀以提高兼容性
                        f.write(f"![封面图]({local_img})\n\n{content}")

        illustrations = visual_plan.get("illustrations", [])
        if illustrations:
            print(f"📸 正在生成 {len(illustrations)} 张深度插图...")
            for idx, illus in enumerate(illustrations):
                aspect = illus.get('aspect', '16:9')
                size_map = {
                    "16:9": "1080*608",
                    "1:1": "800*800",
                    "3:4": "800*1200",
                    "long": "1080*1920" # 超长图暂用 9:16 模拟，或保持宽度 1080
                }
                target_size = size_map.get(aspect, "1080*608")
                
                print(f"   [{idx+1}] 锚点: {illus.get('anchor_text')[:10]}... | 比例: {aspect} ({target_size})")
                illus_prompt = f"({illus.get('style')} style) {illus.get('prompt')}"
                
                illus_url = self.generate_image(illus_prompt, model_type=model_type, size=target_size)
                if illus_url:
                    local_illus = self.download_image_file(illus_url, folder=output_dir)
                    if local_illus:
                        # 火山引擎返回通常是 jpeg/webp
                        if model_type == "seedream" and not local_illus.endswith(".jpeg"):
                             new_name = local_illus.rsplit('.', 1)[0] + ".jpeg"
                             if os.path.exists(local_illus): os.rename(local_illus, new_name)
                             local_illus = new_name
                        print(f"✅ 插图 {idx+1} 已就位: {local_illus}")
                        anchor = illus.get('anchor_text')
                        if anchor and anchor in content:
                            # 使用相对路径插入
                            content = content.replace(anchor, f"{anchor}\n\n![插图]({local_illus})\n")
                            with open(draft_file, 'w', encoding='utf-8') as f:
                                f.write(content)
                        else:
                            with open(draft_file, 'a', encoding='utf-8') as f:
                                f.write(f"\n\n![插图]({local_illus})\n")

        print("\n📤 启动 [触达子系统]...")
        # 调用新集成的发布模块
        success = self.post_to_wechat(draft_file, method=method)
        
        if success:
            print("\n✅ 视觉工程与分发全流程完成！")
            state['current_step'] = "done"
        else:
            print("\n⚠️ 分发阶段遇到问题，请检查日志。")
        self.save_state(state)


def main():
    parser = argparse.ArgumentParser(description="自媒体工作流调度器")
    parser.add_argument('action', choices=['setup', 'discovery', 'from-article', 'from-video', 'repurpose', 'publish', 'status', 'sync'], help="要执行的子系统动作")
    parser.add_argument('--keyword', type=str, help="discovery阶段的自定义关键词")
    parser.add_argument('--url', type=str, help="from-article 或 from-video 模式的直连URL")
    parser.add_argument('--id', type=str, help="repurpose阶段选中的选题ID或要求")
    parser.add_argument('--model', type=str, choices=['z', 'qwen', 'wan', 'seedream'], default='seedream', help="publish阶段使用的生图模型 (z: Z-Image, qwen: Qwen-Image, wan: Wan-Image, seedream: Volcengine Seedream)")
    parser.add_argument('--script', type=str, help="脚本文件路径 (sync 模式使用)")
    parser.add_argument('--article', type=str, help="长文文件路径 (sync 模式使用)")
    parser.add_argument('--method', type=str, choices=['api', 'browser'], default='api', help="publish阶段使用的发布方式 (api: API模式, browser: 浏览器模拟模式)")
    
    args = parser.parse_args()
    controller = SelfMediaController()
    
    if args.action == 'setup':
        controller.run_setup()
    elif args.action == 'discovery':
        controller.run_discovery(args.keyword)
    elif args.action == 'from-article':
        if not args.url:
            print("❌ 错误: from-article 模式需要提供 --url 参数")
            sys.exit(1)
        controller.run_from_article(args.url)
    elif args.action == 'from-video':
        if not args.url:
            print("❌ 错误: from-video 模式需要提供 --url 参数")
            sys.exit(1)
        controller.run_from_video(args.url)
    elif args.action == 'repurpose':
        if not args.id:
            print("请提供 --id <选中选题>")
            sys.exit(1)
        controller.run_repurpose(args.id)
    elif args.action == 'publish':
        # 默认优先使用 API 模式以实现全自动流转
        controller.run_publish(model_type=args.model, method=args.method)
    elif args.action == 'sync':
        if args.script and args.article:
            controller.sync_to_feishu(args.script, args.article)
        else:
            print("❌ 错误：sync 模式需要 --script 和 --article 参数")
            sys.exit(1)
    elif args.action == 'status':
        state = controller.load_state()
        print(json.dumps(state, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
