"""
WeWrite + Xiaohu 集成配置管理
"""
import os
from typing import Optional


class WeWriteConfig:
    """WeWrite 和 Xiaohu 集成配置"""

    def __init__(self):
        # WeWrite 配置
        self.wewrite_enabled = os.getenv('WEWRITE_ENABLED', 'true').lower() == 'true'
        self.wewrite_fallback_to_huashu = os.getenv(
            'WEWRITE_FALLBACK_TO_HUASHU', 'true'
        ).lower() == 'true'

        # Xiaohu 排版配置
        self.xiaohu_gallery_mode = os.getenv(
            'XIAOHU_GALLERY_MODE', 'true'
        ).lower() == 'true'
        self.xiaohu_default_theme = os.getenv(
            'XIAOHU_DEFAULT_THEME', 'newspaper'
        )
        self.xiaohu_gallery_timeout = int(os.getenv(
            'XIAOHU_GALLERY_TIMEOUT', '300'
        ))

        # 复用现有 DeepSeek 配置
        self.deepseek_api_key = os.getenv('OPENAI_API_KEY')
        self.deepseek_base_url = os.getenv('OPENAI_BASE_URL')
        self.deepseek_model = os.getenv('LLM_MODEL_ID', 'deepseek-chat')

        # 次幂数据 API 配置（付费选题源）
        self.cimi_app_id = os.getenv('CIMI_APP_ID')
        self.cimi_app_secret = os.getenv('CIMI_APP_SECRET')

        # 作者 IP 配置
        self.author_ip_name = os.getenv('AUTHOR_IP_NAME', '大胡')
        self.author_wechat_id = os.getenv('AUTHOR_WECHAT_ID')

    def is_wewrite_available(self) -> bool:
        """检查 WeWrite 是否可用"""
        return self.wewrite_enabled and bool(self.deepseek_api_key)

    def get_deepseek_config(self) -> dict:
        """获取 DeepSeek 配置"""
        return {
            'api_key': self.deepseek_api_key,
            'base_url': self.deepseek_base_url,
            'model': self.deepseek_model
        }

    def get_topic_config(self) -> dict:
        """获取选题配置"""
        return {
            'cimi_app_id': self.cimi_app_id,
            'cimi_app_secret': self.cimi_app_secret
        }

    @property
    def ip_name(self) -> str:
        """获取作者 IP 名称"""
        return self.author_ip_name
