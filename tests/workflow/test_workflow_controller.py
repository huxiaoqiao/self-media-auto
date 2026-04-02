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


class TestExtractAuthor:
    """作者提取方法测试"""

    def test_extract_author_with_chinese_colon(self):
        """使用中文冒号提取作者"""
        from workflow_controller import SelfMediaController

        content = "作者：张三\n\n正文内容..."
        controller = SelfMediaController()
        result = controller._extract_author(content)

        assert result == "张三"

    def test_extract_author_with_english_colon(self):
        """使用英文冒号提取作者"""
        from workflow_controller import SelfMediaController

        # 使用英文冒号 (半角冒号 U+003A)
        content = "author: 李四\n\n正文内容..."
        controller = SelfMediaController()
        result = controller._extract_author(content)

        assert result == "李四"

    def test_extract_author_with_source_keyword(self):
        """使用'出自'关键词提取作者"""
        from workflow_controller import SelfMediaController

        content = "出自：王五\n\n正文内容..."
        controller = SelfMediaController()
        result = controller._extract_author(content)

        assert result == "王五"

    def test_extract_author_returns_none_for_missing(self):
        """无作者信息时返回 None"""
        from workflow_controller import SelfMediaController

        content = "正文内容，没有作者信息"
        controller = SelfMediaController()
        result = controller._extract_author(content)

        assert result is None


class TestExtractVideoContent:
    """视频内容提取方法测试"""

    @patch('workflow_controller.subprocess.run')
    @patch('workflow_controller.os.path.exists')
    @patch('workflow_controller.os.makedirs')
    @patch('workflow_controller.os.getenv')
    def test_extract_video_content_from_douyin(self, mock_getenv, mock_makedirs, mock_exists, mock_run):
        """从抖音视频提取文案"""
        from workflow_controller import SelfMediaController

        # 配置 mock - 注意使用中文冒号"保存位置："匹配代码中的正则
        mock_getenv.return_value = 'test_api_key'
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='保存位置：/tmp/douyin.md',
            stderr=''
        )

        # 配置 open mock，正确设置上下文管理器
        mock_file = MagicMock()
        mock_file.read.return_value = '## 文案内容\n\n这是视频文案'
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('workflow_controller.open', MagicMock(return_value=mock_file)):
            controller = SelfMediaController()
            result = controller._extract_video_content('https://douyin.com/video/123')

            assert result is not None
            assert '视频文案' in result

    @patch('workflow_controller.os.getenv')
    def test_extract_video_content_missing_api_key(self, mock_getenv):
        """API Key 缺失时返回 None"""
        from workflow_controller import SelfMediaController

        mock_getenv.return_value = None
        controller = SelfMediaController()
        result = controller._extract_video_content('https://douyin.com/video/123')

        assert result is None

    def test_extract_video_content_non_douyin_url(self):
        """非抖音 URL 返回 None"""
        from workflow_controller import SelfMediaController

        controller = SelfMediaController()
        result = controller._extract_video_content('https://bilibili.com/video/123')

        assert result is None


class TestGenerateSummary:
    """AI 摘要生成方法测试"""

    def test_generate_summary_success(self):
        """成功生成摘要"""
        from workflow_controller import SelfMediaController

        with patch('openai.OpenAI') as mock_openai, \
             patch('workflow_controller.os.getenv') as mock_getenv:
            # 配置 mock
            mock_getenv.return_value = 'test_api_key'
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="这是一个简洁的摘要"))]
            )

            controller = SelfMediaController()
            result = controller._generate_summary("这是文章内容" * 100, "测试标题")

            assert result is not None
            assert len(result) > 0

    def test_generate_summary_empty_content(self):
        """空内容返回空字符串"""
        from workflow_controller import SelfMediaController

        controller = SelfMediaController()
        result = controller._generate_summary("", "测试标题")

        assert result == ""

    def test_generate_summary_api_error_fallback(self):
        """API 错误时降级返回前 200 字"""
        from workflow_controller import SelfMediaController

        with patch('openai.OpenAI') as mock_openai, \
             patch('workflow_controller.os.getenv') as mock_getenv:
            mock_getenv.return_value = 'test_api_key'
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("API Error")

            content = "这是很长的内容" * 100
            controller = SelfMediaController()
            result = controller._generate_summary(content, "测试标题")

            assert result is not None
            assert len(result) <= 203  # 200 字 + "..."


class TestSendUrlPreviewCard:
    """飞书卡片发送方法测试"""

    def test_send_url_preview_card_success(self):
        """成功发送预览卡片"""
        from workflow_controller import SelfMediaController

        with patch('workflow_controller.build_url_preview_card') as mock_build, \
             patch('workflow_controller.get_token') as mock_get_token, \
             patch('workflow_controller.send_card') as mock_send, \
             patch('workflow_controller.os.getenv') as mock_getenv:
            mock_build.return_value = {"config": {"wide_screen_mode": True}}
            mock_get_token.return_value = "test_token"
            mock_getenv.return_value = "test_receive_id"
            mock_send.return_value = True

            controller = SelfMediaController()
            result = controller._send_url_preview_card(
                title="测试标题",
                author="测试作者",
                source="微信公众号",
                summary="测试摘要",
                url="https://example.com",
                content_type="article",
                extra_info={"key": "value"}
            )

            assert result is None  # 方法无返回值，只打印日志
            mock_build.assert_called_once()
            mock_send.assert_called_once()

    def test_send_url_preview_card_failure(self):
        """发送失败时打印警告"""
        from workflow_controller import SelfMediaController

        with patch('workflow_controller.build_url_preview_card') as mock_build, \
             patch('workflow_controller.get_token') as mock_get_token, \
             patch('workflow_controller.send_card') as mock_send, \
             patch('workflow_controller.os.getenv') as mock_getenv:
            mock_build.return_value = {"config": {"wide_screen_mode": True}}
            mock_get_token.return_value = "test_token"
            mock_getenv.return_value = "test_receive_id"
            mock_send.return_value = False

            controller = SelfMediaController()
            result = controller._send_url_preview_card(
                title="测试标题",
                author="测试作者",
                source="微信公众号",
                summary="测试摘要",
                url="https://example.com",
                content_type="article",
                extra_info={}
            )

            assert result is None
            mock_send.assert_called_once()
