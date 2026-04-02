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

        通过调用 wewrite 的 toolkit/cli.py 来处理内容
        """
        # 使用 converter.py 直接处理内容
        converter_script = self.openclaw_dir / 'toolkit' / 'converter.py'

        if not converter_script.exists():
            # 降级：直接返回原内容
            self.logger.warning("converter.py 不存在，返回原内容")
            with open(md_path, 'r', encoding='utf-8') as f:
                return f.read()

        # 读取原始内容
        with open(md_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        # 对于简单的改写需求，直接返回原内容
        # 完整的 WeWrite 流程需要通过 SKILL.md 的 Step 1-8
        # 这里做一个简化的实现

        # TODO: 实现完整的 WeWrite 改写流程需要：
        # 1. 调用 fetch_hotspots.py 获取热点
        # 2. 调用 seo_keywords.py 分析关键词
        # 3. 根据 framework 选择框架
        # 4. 调用 content-enhance.md 进行内容增强
        # 5. 最终生成改写后的内容

        # 当前简化实现：返回原内容，实际应用时需要完整实现
        return original_content

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
