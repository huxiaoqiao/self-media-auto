"""
Xiaohu 排版引擎封装

封装 xiaohu-wechat-format 的排版功能
支持浏览器主题选择器（gallery 模式）
"""
import os
import sys
import time
import logging
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional


class XiaohuFormatter:
    """
    Xiaohu 排版引擎封装

    支持两种模式：
    1. Gallery 模式：弹出浏览器让用户选择主题
    2. 直接模式：使用指定主题直接生成
    """

    def __init__(self, config: dict, logger: logging.Logger):
        """
        初始化 Xiaohu 排版引擎

        Args:
            config: 配置项
                - default_theme: 默认主题
                - gallery_timeout: Gallery 模式超时时间（秒）
            logger: 日志实例
        """
        self.config = config
        self.logger = logger
        self.default_theme = config.get('default_theme', 'newspaper')
        self.gallery_timeout = config.get('gallery_timeout', 300)  # 5 分钟

        self.xiaohu_dir = Path(__file__).parent.parent / 'xiaohu-wechat-format'
        self.format_script = self.xiaohu_dir / 'scripts' / 'format.py'
        self.config_json = self.xiaohu_dir / 'config.json'

        # 验证脚本存在
        if not self.format_script.exists():
            logger.warning(f"Xiaohu format 脚本不存在：{self.format_script}")

    def format_with_gallery(self, content: str, output_path: str, recommend: list = None) -> str:
        """
        启动浏览器主题选择器，用户选择后生成 HTML

        Args:
            content: Markdown 格式的内容
            output_path: 输出 HTML 文件路径

        Returns:
            str: 生成的 HTML 文件路径
        """
        try:
            self.logger.info("启动 Xiaohu Gallery 模式")

            # 1. 准备临时 Markdown 文件
            temp_md_path = output_path.replace('.html', '.input.md')
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            with open(temp_md_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 2. 确保 config.json 存在
            self._ensure_config_exists(output_dir)

            # 3. 启动 gallery 模式
            cmd = [
                sys.executable,
                str(self.format_script),
                '--input', temp_md_path,
                '--gallery',
                '--output', output_path
            ]
            
            if recommend:
                cmd.extend(['--recommend'])
                cmd.extend(recommend)

            # 4. 启动进程
            self.logger.info(f"执行命令：{' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                cwd=str(self.xiaohu_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # 5. 等待用户完成选择（轮询输出文件）
            start_time = time.time()
            while time.time() - start_time < self.gallery_timeout:
                time.sleep(2)
                if os.path.exists(output_path):
                    self.logger.info(f"HTML 生成完成：{output_path}")
                    # 清理临时文件
                    if os.path.exists(temp_md_path):
                        os.remove(temp_md_path)
                    return output_path

                # 检查进程是否异常退出
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.logger.error(f"Gallery 进程异常退出：{stderr.decode()}")
                    raise XiaohuGalleryError(
                        f"Gallery 进程异常：{stderr.decode()}"
                    )

            # 超时
            process.kill()
            raise XiaohuGalleryTimeout(
                f"主题选择超时（{self.gallery_timeout}秒）"
            )

        except Exception as e:
            self.logger.error(f"排版失败：{e}")
            raise XiaohuGalleryError(f"排版失败：{e}")

    def format_with_theme(self, content: str, theme: str, output_path: str) -> str:
        """
        使用指定主题直接生成 HTML（无需浏览器）

        Args:
            content: Markdown 格式的内容
            theme: 主题名称
            output_path: 输出 HTML 文件路径

        Returns:
            str: 生成的 HTML 文件路径
        """
        try:
            self.logger.info(f"使用主题 '{theme}' 生成 HTML")

            # 1. 准备临时 Markdown 文件
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            temp_md_path = output_path.replace('.html', '.input.md')
            with open(temp_md_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 2. 确保 config.json 存在
            self._ensure_config_exists(output_dir)

            # 3. 执行排版命令
            cmd = [
                sys.executable,
                str(self.format_script),
                '--input', temp_md_path,
                '--theme', theme,
                '--output', output_path
            ]

            result = subprocess.run(
                cmd,
                cwd=str(self.xiaohu_dir),
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                raise XiaohuFormatError(f"排版命令失败：{result.stderr}")

            # 4. 清理临时文件
            if os.path.exists(temp_md_path):
                os.remove(temp_md_path)

            self.logger.info(f"HTML 生成完成：{output_path}")
            return output_path

        except subprocess.TimeoutExpired:
            raise XiaohuFormatError("排版命令超时")
        except Exception as e:
            self.logger.error(f"排版失败：{e}")
            raise XiaohuFormatError(f"排版失败：{e}")

    def _ensure_config_exists(self, output_dir: str):
        """确保 config.json 存在，如果不存在则创建"""
        if not self.config_json.exists():
            self.logger.info("创建 config.json")
            config = {
                "output_dir": output_dir or "/tmp/wechat-format",
                "vault_root": str(Path.home()),
                "settings": {
                    "default_theme": self.default_theme,
                    "auto_open_browser": True
                },
                "wechat": {
                    "app_id": "",
                    "app_secret": "",
                    "author": ""
                },
                "cover": {
                    "output_dir": "~/Documents/covers",
                    "image_generation_script": ""
                }
            }
            import json
            with open(self.config_json, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

    def list_themes(self) -> list:
        """列出可用的主题名称"""
        themes_dir = self.xiaohu_dir / 'themes'
        if not themes_dir.exists():
            return []

        themes = []
        for f in themes_dir.glob('*.json'):
            if f.is_file():
                themes.append(f.stem)
        return themes


class XiaohuGalleryError(Exception):
    """Xiaohu Gallery 模式异常"""
    pass


class XiaohuGalleryTimeout(XiaohuGalleryError):
    """Gallery 模式超时"""
    pass


class XiaohuFormatError(Exception):
    """Xiaohu 排版异常"""
    pass
