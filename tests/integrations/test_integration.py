"""端到端集成测试"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestRewriteToPublishFlow:
    """从改写到发布的完整流程测试"""

    @patch('integrations.wewrite_engine.requests.post')
    @patch('integrations.xiaohu_formatter.subprocess.run')
    def test_full_rewrite_and_format(self, mock_subprocess, mock_post, mock_logger):
        """测试完整改写 + 格式化流程"""
        from integrations.wewrite_engine import WeWriteEngine, RewriteResult
        from integrations.xiaohu_formatter import XiaohuFormatter

        # Mock LLM API
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{'message': {'content': '# 改写后的文章\n\n正文内容'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Mock formatter
        mock_subprocess.return_value = MagicMock(returncode=0)

        # 执行流程
        deepseek_config = {'api_key': 'test', 'base_url': 'https://test.com', 'model': 'test'}
        xiaohu_config = {'default_theme': 'newspaper'}

        engine = WeWriteEngine(deepseek_config, mock_logger)
        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        # 改写
        rewrite_result = engine.rewrite('原始素材', {'ip_name': '测试', 'framework': 'story'})
        assert rewrite_result.success is True
        assert rewrite_result.source == 'wewrite'

        # 格式化 (需要临时文件和目录)
        with patch('builtins.open', MagicMock()):
            with patch('os.path.exists', return_value=True):
                with patch('os.remove'):
                    html_path = formatter.format_with_theme(
                        rewrite_result.content,
                        'newspaper',
                        '/tmp/test_output.html'
                    )
                    assert html_path == '/tmp/test_output.html'


class TestModuleImports:
    """模块导入测试"""

    def test_import_integrations(self):
        """测试集成模块可导入"""
        from integrations import wewrite_engine
        from integrations import xiaohu_formatter
        from integrations import wechat_topic_fetcher

        assert wewrite_engine is not None
        assert xiaohu_formatter is not None
        assert wechat_topic_fetcher is not None

    def test_import_config(self):
        """测试配置模块可导入"""
        from config import wewrite_config

        assert wewrite_config is not None

    def test_import_utils(self):
        """测试工具模块可导入"""
        from utils import logger_config

        assert logger_config is not None


class TestExceptionClasses:
    """异常类测试"""

    def test_wewrite_exception(self):
        """测试 WeWrite 异常"""
        from integrations.wewrite_engine import WeWriteError

        error = WeWriteError("测试错误")
        assert str(error) == "测试错误"

    def test_xiaohu_exception(self):
        """测试 Xiaohu 异常"""
        from integrations.xiaohu_formatter import XiaohuGalleryError, XiaohuGalleryTimeout, XiaohuFormatError

        gallery_error = XiaohuGalleryError("Gallery 错误")
        assert str(gallery_error) == "Gallery 错误"

        timeout_error = XiaohuGalleryTimeout("超时错误")
        assert "超时错误" in str(timeout_error)

        format_error = XiaohuFormatError("格式化错误")
        assert str(format_error) == "格式化错误"

    def test_xiaohu_exception_inheritance(self):
        """测试 Xiaohu 异常继承关系"""
        from integrations.xiaohu_formatter import XiaohuGalleryError, XiaohuGalleryTimeout

        timeout = XiaohuGalleryTimeout("超时")
        assert isinstance(timeout, XiaohuGalleryError)
        assert isinstance(timeout, Exception)


class TestConfigDataClasses:
    """配置数据类测试"""

    def test_rewrite_result(self):
        """测试改写结果数据类"""
        from integrations.wewrite_engine import RewriteResult

        result = RewriteResult(
            success=True,
            content="测试内容",
            source='wewrite',
            message="成功"
        )

        assert result.success is True
        assert result.content == "测试内容"
        assert result.source == 'wewrite'
        assert result.message == "成功"

    def test_rewrite_result_default_message(self):
        """测试改写结果默认消息"""
        from integrations.wewrite_engine import RewriteResult

        result = RewriteResult(
            success=False,
            content="",
            source='huashu'
        )

        assert result.success is False
        assert result.message == ""
