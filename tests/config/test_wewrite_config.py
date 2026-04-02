"""WeWrite 和 Xiaohu 集成配置测试"""
import os
import pytest
from config.wewrite_config import WeWriteConfig


class TestWeWriteConfigInit:
    """WeWriteConfig 初始化测试"""

    def test_default_values(self):
        """测试默认配置值"""
        # 确保环境变量未设置
        for key in ['WEWRITE_ENABLED', 'WEWRITE_FALLBACK_TO_HUASHU',
                    'XIAOHU_GALLERY_MODE', 'XIAOHU_DEFAULT_THEME',
                    'XIAOHU_GALLERY_TIMEOUT', 'AUTHOR_IP_NAME']:
            if key in os.environ:
                del os.environ[key]

        config = WeWriteConfig()

        assert config.wewrite_enabled is True
        assert config.wewrite_fallback_to_huashu is True
        assert config.xiaohu_gallery_mode is True
        assert config.xiaohu_default_theme == 'newspaper'
        assert config.xiaohu_gallery_timeout == 300
        assert config.author_ip_name == '大胡'

    def test_env_override_wewrite_enabled(self):
        """测试通过环境变量覆盖 wewrite_enabled"""
        os.environ['WEWRITE_ENABLED'] = 'false'
        config = WeWriteConfig()
        assert config.wewrite_enabled is False

    def test_env_override_gallery_mode(self):
        """测试通过环境变量覆盖 gallery_mode"""
        os.environ['XIAOHU_GALLERY_MODE'] = 'false'
        config = WeWriteConfig()
        assert config.xiaohu_gallery_mode is False

    def test_env_override_default_theme(self):
        """测试通过环境变量覆盖默认主题"""
        os.environ['XIAOHU_DEFAULT_THEME'] = 'github'
        config = WeWriteConfig()
        assert config.xiaohu_default_theme == 'github'

    def test_env_override_gallery_timeout(self):
        """测试通过环境变量覆盖 gallery 超时"""
        os.environ['XIAOHU_GALLERY_TIMEOUT'] = '600'
        config = WeWriteConfig()
        assert config.xiaohu_gallery_timeout == 600

    def test_env_override_author_ip_name(self):
        """测试通过环境变量覆盖作者 IP 名称"""
        os.environ['AUTHOR_IP_NAME'] = '测试作者'
        config = WeWriteConfig()
        assert config.author_ip_name == '测试作者'


class TestWeWriteConfigMethods:
    """WeWriteConfig 方法测试"""

    def test_get_deepseek_config(self):
        """测试获取 DeepSeek 配置"""
        os.environ['OPENAI_API_KEY'] = 'test-key-123'
        os.environ['OPENAI_BASE_URL'] = 'https://test-api.com/v1'
        os.environ['LLM_MODEL_ID'] = 'test-model'

        config = WeWriteConfig()
        deepseek = config.get_deepseek_config()

        assert deepseek == {
            'api_key': 'test-key-123',
            'base_url': 'https://test-api.com/v1',
            'model': 'test-model'
        }

    def test_get_topic_config_empty(self):
        """测试获取选题配置（未设置时）"""
        for key in ['CIMI_APP_ID', 'CIMI_APP_SECRET']:
            if key in os.environ:
                del os.environ[key]

        config = WeWriteConfig()
        topic = config.get_topic_config()

        assert topic == {'cimi_app_id': None, 'cimi_app_secret': None}

    def test_get_topic_config_with_env(self):
        """测试获取选题配置（已设置环境变量）"""
        os.environ['CIMI_APP_ID'] = 'test-app-id'
        os.environ['CIMI_APP_SECRET'] = 'test-secret'

        config = WeWriteConfig()
        topic = config.get_topic_config()

        assert topic == {
            'cimi_app_id': 'test-app-id',
            'cimi_app_secret': 'test-secret'
        }

    def test_is_wewrite_available_with_key(self):
        """测试 WeWrite 可用性检查（有 API Key）"""
        os.environ['WEWRITE_ENABLED'] = 'true'
        os.environ['OPENAI_API_KEY'] = 'test-key'

        config = WeWriteConfig()
        assert config.is_wewrite_available() is True

    def test_is_wewrite_available_without_key(self):
        """测试 WeWrite 可用性检查（无 API Key）"""
        os.environ['WEWRITE_ENABLED'] = 'true'
        if 'OPENAI_API_KEY' in os.environ:
            del os.environ['OPENAI_API_KEY']

        config = WeWriteConfig()
        assert config.is_wewrite_available() is False

    def test_is_wewrite_available_disabled(self):
        """测试 WeWrite 可用性检查（已禁用）"""
        os.environ['WEWRITE_ENABLED'] = 'false'
        os.environ['OPENAI_API_KEY'] = 'test-key'

        config = WeWriteConfig()
        assert config.is_wewrite_available() is False

    def test_ip_name_property(self):
        """测试 ip_name 属性"""
        os.environ['AUTHOR_IP_NAME'] = '我的 IP 名称'
        config = WeWriteConfig()
        assert config.ip_name == '我的 IP 名称'
