"""
Pytest 共享 fixture 和配置
"""
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def temp_dir(tmp_path):
    """创建临时目录用于测试文件操作"""
    return tmp_path


@pytest.fixture
def mock_logger():
    """创建模拟 logger"""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.debug = MagicMock()
    return logger


@pytest.fixture
def deepseek_config():
    """DeepSeek API 测试配置"""
    return {
        'api_key': 'test-sk-1234567890abcdef',
        'base_url': 'https://api.test-deepseek.com/v1',
        'model': 'deepseek-chat'
    }


@pytest.fixture
def xiaohu_config():
    """Xiaohu 排版测试配置"""
    return {
        'default_theme': 'newspaper',
        'gallery_timeout': 60
    }


@pytest.fixture
def topic_fetcher_config():
    """选题获取器测试配置"""
    return {
        'cimi_app_id': 'test_app_id',
        'cimi_app_secret': 'test_app_secret'
    }


@pytest.fixture
def mock_requests_response():
    """创建模拟的 requests.Response 对象"""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {}
    response.text = ''
    response.raise_for_status = MagicMock()
    return response


@pytest.fixture(autouse=True)
def clean_env():
    """每个测试前清理环境变量"""
    # 保存当前环境变量
    saved_env = os.environ.copy()
    yield
    # 恢复环境变量
    os.environ.clear()
    os.environ.update(saved_env)
