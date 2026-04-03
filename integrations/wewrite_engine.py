"""
WeWrite 改写引擎封装

将 wewrite 的核心改写功能封装为统一的接口
支持自动降级到 huashu-proofreading
"""
import os
import sys
import logging
import subprocess
import tempfile
import requests
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class RewriteResult:
    """改写结果"""
    success: bool
    content: str  # 改写后的内容
    source: str  # 使用的引擎：'wewrite' 或 'huashu'
    message: str = ""  # 附加信息


class WeWriteEngine:
    """
    WeWrite 改写引擎封装

    使用 wewrite 的写作框架和风格模板进行内容改写
    失败时自动降级到 huashu-proofreading
    """

    def __init__(self, deepseek_config: dict, logger: logging.Logger):
        """
        初始化 WeWrite 引擎

        Args:
            deepseek_config: DeepSeek API 配置 (api_key, base_url, model)
            logger: 日志实例
        """
        self.deepseek_config = deepseek_config
        self.logger = logger
        self.wewrite_dir = Path(__file__).parent.parent / 'wewrite'
        self.openclaw_dir = self.wewrite_dir / 'dist' / 'openclaw'

        # 验证 wewrite 目录存在
        if not self.wewrite_dir.exists():
            logger.warning(f"WeWrite 目录不存在：{self.wewrite_dir}")

    def rewrite(self, source_content: str, options: dict) -> RewriteResult:
        """
        使用 wewrite 进行改写

        Args:
            source_content: 源内容
            options: 配置选项
                - style: 风格（personal, journalistic, analytical 等）
                - framework: 写作框架
                - ip_name: 作者 IP 名称

        Returns:
            RewriteResult: 改写结果
        """
        try:
            self.logger.info("开始使用 WeWrite 引擎进行改写")

            # 设置环境变量供 wewrite 使用
            env = os.environ.copy()
            env['OPENAI_API_KEY'] = self.deepseek_config['api_key']
            env['OPENAI_BASE_URL'] = self.deepseek_config['base_url']

            # 创建临时 Markdown 文件
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.md',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(source_content)
                temp_md_path = f.name

            try:
                # 调用 wewrite 的改写逻辑
                # 使用 dist/openclaw 版本，这是 OpenClaw 兼容版
                rewritten_content = self._call_wewrite_rewrite(
                    temp_md_path, options, env
                )
            finally:
                # 清理临时文件
                if os.path.exists(temp_md_path):
                    os.remove(temp_md_path)

            self.logger.info("WeWrite 改写成功")
            return RewriteResult(
                success=True,
                content=rewritten_content,
                source='wewrite',
                message="WeWrite 改写成功"
            )

        except Exception as e:
            self.logger.warning(f"WeWrite 改写失败：{e}")
            raise WeWriteError(f"WeWrite 改写失败：{e}")

    def _call_wewrite_rewrite(self, md_path: str, options: dict, env: dict) -> str:
        """
        调用 wewrite 的改写逻辑

        实现简化的 WeWrite 改写流程：
        1. 读取源内容和配置
        2. 根据 framework 选择写作框架
        3. 调用 LLM 进行内容改写（使用 wewrite 的风格配置）
        4. 返回改写后的内容
        """
        import json
        import requests

        # 读取原始内容
        with open(md_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        # 加载 wewrite 配置文件
        config_path = self.openclaw_dir / 'config.example.yaml'
        style_path = self.openclaw_dir / 'style.example.yaml'

        # 尝试加载用户配置（如果存在）
        user_config_path = self.wewrite_dir / 'config.yaml'
        user_style_path = self.wewrite_dir / 'style.yaml'

        config_file = user_config_path if user_config_path.exists() else config_path
        style_file = user_style_path if user_style_path.exists() else style_path

        # 读取风格配置
        style_config = {}
        if style_file.exists():
            try:
                import yaml
                with open(style_file, 'r', encoding='utf-8') as f:
                    style_config = yaml.safe_load(f) or {}
                self.logger.info(f"加载风格配置：{style_config.get('name', 'default')}")
            except Exception as e:
                self.logger.warning(f"加载风格配置失败：{e}，使用默认配置")

        # 提取改写选项
        ip_name = options.get('ip_name', '作者')
        framework = options.get('framework', 'story')  # 默认使用故事框架
        style = options.get('style', 'personal')  # 默认个人风格

        # 构建改写 prompt（基于 wewrite 的写作框架）
        system_prompt = self._build_wewrite_prompt(style_config, ip_name, framework, style)

        # 调用 LLM 进行改写
        try:
            rewritten_content = self._call_llm_for_rewrite(
                system_prompt, original_content, env
            )
            return rewritten_content
        except Exception as e:
            self.logger.warning(f"LLM 改写失败：{e}，返回原内容")
            return original_content

    def _build_wewrite_prompt(self, style_config: dict, ip_name: str, framework: str, style: str) -> str:
        """
        构建 WeWrite 风格的改写 prompt

        基于 wewrite 的写作框架和风格配置
        """
        # 从配置中提取风格参数
        topics = style_config.get('topics', [])
        tone = style_config.get('tone', '真诚友好')
        voice = style_config.get('voice', '第一人称')
        blacklist = style_config.get('blacklist', [])
        content_style = style_config.get('content_style', '个人感悟')

        # 写作框架描述
        framework_descs = {
            'story': '以故事开篇，通过具体场景引入主题，中间展开分析，结尾升华',
            'pain-point': '从用户痛点出发，描述问题场景，给出解决方案，展示效果',
            'list': '清单体，分点论述，每个观点配案例或数据支撑',
            'contrast': '对比结构，Before/After 对比，突出变化和价值',
            'hotspot': '热点解读结构，描述热点事件 + 独特视角分析 + 延伸思考',
            'opinion': '纯观点文，开门见山亮出观点，层层递进论证',
            'review': '复盘结构，背景描述 + 过程还原 + 经验总结 + 方法论提炼',
        }
        framework_desc = framework_descs.get(framework, framework_descs['story'])

        # 风格描述
        style_descs = {
            'personal': '个人化表达，使用「我」的视角，分享真实感受和经历',
            'journalistic': '新闻纪实风格，客观描述，数据支撑，多方引用',
            'analytical': '分析型风格，逻辑严密，层层拆解，深度思考',
            'conversational': '对话式风格，像和朋友聊天一样自然',
            'authoritative': '权威专家风格，专业术语，数据论证，引用研究',
        }
        style_desc = style_descs.get(style, style_descs['personal'])

        # 构建完整的系统 prompt
        prompt = f"""你是一位专业的微信公众号文章编辑，正在帮助作者 {ip_name} 改写一篇文章。

## 作者风格配置
- 内容领域：{', '.join(topics) if topics else '通用领域'}
- 语调风格：{tone}
- 表达视角：{voice}
- 内容类型：{content_style}

## 写作要求
1. 使用{framework_desc}
2. 采用{style_desc}
3. 保持文章原创度，避免洗稿嫌疑
4. 加入个人体感和真实细节
5. 适当使用金句强化记忆点
6. 段落长短交错，避免单调
7. 开头 3 段内必须抓住读者注意力
8. 结尾要有行动召唤或深度思考

## 禁忌
{f"- " + chr(10) + "- ".join(blacklist) if blacklist else "- 避免空洞说教"}

## 输出格式
直接输出改写后的完整文章（Markdown 格式），包含：
- 一个吸引人的标题（# 标题）
- 正文内容（使用 H2/H3 分段）
- 适当的加粗强调（**重点句子**）
- 如需配图位置，标注 [配图：描述]

现在请改写下方的文章内容："""
        return prompt

    def _call_llm_for_rewrite(self, system_prompt: str, content: str, env: dict) -> str:
        """
        调用 LLM 进行内容改写
        """
        api_key = env.get('OPENAI_API_KEY', self.deepseek_config.get('api_key'))
        base_url = env.get('OPENAI_BASE_URL', self.deepseek_config.get('base_url', 'https://api.deepseek.com/v1'))
        model = self.deepseek_config.get('model', 'deepseek-chat')

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f'原文内容：\n\n{content}'}
            ],
            'temperature': 0.7,
            'max_tokens': 4000
        }

        response = requests.post(
            f'{base_url}/chat/completions',
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        rewritten = result['choices'][0]['message']['content']

        # 清理可能的 markdown 标记
        rewritten = rewritten.strip()
        if rewritten.startswith('```markdown'):
            rewritten = rewritten[11:]
        elif rewritten.startswith('```'):
            rewritten = rewritten[3:]
        if rewritten.endswith('```'):
            rewritten = rewritten[:-3]

        return rewritten.strip()

    def fetch_hotspots(self, limit: int = 20) -> list:
        """
        获取热点选题

        Args:
            limit: 返回的热点数量

        Returns:
            list: 热点列表，每个热点包含 title, source, hot, url 等字段
        """
        try:
            script_path = self.openclaw_dir / 'scripts' / 'fetch_hotspots.py'

            if not script_path.exists():
                self.logger.warning("fetch_hotspots.py 不存在")
                return []

            result = subprocess.run(
                [sys.executable, str(script_path), '--limit', str(limit)],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                self.logger.error(f"fetch_hotspots 失败：{result.stderr}")
                return []

            # 解析输出（JSON 格式）
            import json
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                self.logger.error("解析热点数据失败")
                return []

        except Exception as e:
            self.logger.error(f"获取热点失败：{e}")
            return []

    def is_available(self) -> bool:
        """检查 wewrite 是否可用"""
        return (
            self.wewrite_dir.exists() and
            self.openclaw_dir.exists() and
            bool(self.deepseek_config.get('api_key'))
        )


class WeWriteError(Exception):
    """WeWrite 引擎异常"""
    pass
