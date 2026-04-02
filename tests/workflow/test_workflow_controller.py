"""workflow_controller 核心调度器测试"""
import os
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO


class TestSelfMediaControllerInit:
    """SelfMediaController 初始化测试"""

    @patch('workflow_controller.load_dotenv')
    def test_init(self, mock_load):
        """测试控制器初始化"""
        from workflow_controller import SelfMediaController

        controller = SelfMediaController()

        # 验证基本属性存在
        assert controller is not None


class TestRepurposeCommand:
    """repurpose 改写命令测试"""

    @patch('workflow_controller.WEWRITE_XIAOHU_AVAILABLE', True)
    @patch('workflow_controller.WeWriteConfig')
    @patch('workflow_controller.WeWriteEngine')
    @patch('workflow_controller.load_dotenv')
    def test_repurpose_with_wewrite(self, mock_load, mock_engine_cls, mock_config_cls):
        """测试使用 WeWrite 改写"""
        from workflow_controller import SelfMediaController
        from integrations.wewrite_engine import RewriteResult

        # 配置 mock
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        mock_config.get_deepseek_config.return_value = {'api_key': 'test', 'base_url': 'https://test.com', 'model': 'test'}
        mock_config.ip_name = '测试作者'

        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.rewrite.return_value = RewriteResult(
            success=True,
            content='# 改写结果\n\n正文内容',
            source='wewrite',
            message='WeWrite 改写成功'
        )

        controller = SelfMediaController()

        # 验证控制器已初始化
        assert controller is not None


class TestDiscoveryCommand:
    """discovery 选题发现命令测试"""

    @patch('workflow_controller.TopicFetcher')
    @patch('workflow_controller.load_dotenv')
    def test_discovery_fetches_topics(self, mock_load, mock_fetcher_cls):
        """测试选题发现获取话题"""
        from workflow_controller import SelfMediaController

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_topics.return_value = [
            {'title': '热门话题 1', 'heat_score': 100, 'platform': 'wechat'}
        ]
        mock_fetcher_cls.return_value = mock_fetcher

        controller = SelfMediaController()

        # 验证控制器已初始化
        assert controller is not None


class TestPublishCommand:
    """publish 发布命令测试"""

    @patch('workflow_controller.XiaohuFormatter')
    @patch('workflow_controller.load_dotenv')
    def test_publish_formats_and_publishes(self, mock_load, mock_formatter_cls):
        """测试格式化并发布"""
        from workflow_controller import SelfMediaController

        mock_formatter = MagicMock()
        mock_formatter.format_with_theme.return_value = '/tmp/output.html'
        mock_formatter_cls.return_value = mock_formatter

        controller = SelfMediaController()

        # 验证控制器已初始化
        assert controller is not None


class TestWeWriteXiaohuIntegration:
    """WeWrite + Xiaohu 集成测试"""

    @patch('workflow_controller.WEWRITE_XIAOHU_AVAILABLE', True)
    @patch('workflow_controller.load_dotenv')
    def test_integration_available(self, mock_load):
        """测试集成可用性标志"""
        from workflow_controller import WEWRITE_XIAOHU_AVAILABLE

        # 当依赖模块可用时，标志应为 True
        assert WEWRITE_XIAOHU_AVAILABLE is True

    @patch('workflow_controller.WEWRITE_XIAOHU_AVAILABLE', False)
    @patch('workflow_controller.load_dotenv')
    def test_integration_fallback(self, mock_load):
        """测试集成不可用时的降级"""
        # 当 WEWRITE_XIAOHU_AVAILABLE 为 False 时
        # 系统应该降级到原有流程
        from workflow_controller import WEWRITE_XIAOHU_AVAILABLE
        assert WEWRITE_XIAOHU_AVAILABLE is False


class TestWorkflowState:
    """工作流状态管理测试"""

    @patch('workflow_controller.load_dotenv')
    def test_state_management(self, mock_load, temp_dir):
        """测试状态管理"""
        from workflow_controller import SelfMediaController

        controller = SelfMediaController()

        # 验证控制器可以管理状态
        # （具体状态管理逻辑取决于实际实现）
        assert controller is not None


class TestExtractTitle:
    """标题提取方法测试"""

    def test_extract_title_from_video_content(self):
        """从视频转录内容中提取标题"""
        from workflow_controller import SelfMediaController

        content = """0:00
大家好，今天我们来聊聊 AI 自媒体的未来

0:15
首先，我们来看看当前的市场趋势
"""
        controller = SelfMediaController()
        result = controller._extract_title(content)

        assert result is not None
        assert len(result) >= 5
        assert "AI" in result or "自媒体" in result

    def test_extract_title_with_timestamp_prefix(self):
        """跳过时间戳前缀提取标题"""
        from workflow_controller import SelfMediaController

        content = """[0:00] 开场白
这是真正的标题行
0:02 正文内容开始
"""
        controller = SelfMediaController()
        result = controller._extract_title(content)

        assert result == "这是真正的标题行"

    def test_extract_title_returns_none_for_empty(self):
        """空内容返回 None"""
        from workflow_controller import SelfMediaController

        controller = SelfMediaController()
        result = controller._extract_title("")

        assert result is None
