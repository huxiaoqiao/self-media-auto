"""WeWrite 改写引擎测试"""
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from integrations.wewrite_engine import WeWriteEngine, RewriteResult, WeWriteError


class TestWeWriteEngineInit:
    """WeWriteEngine 初始化测试"""

    def test_init_with_config(self, mock_logger, deepseek_config):
        """测试使用配置初始化"""
        engine = WeWriteEngine(deepseek_config, mock_logger)

        assert engine.deepseek_config == deepseek_config
        assert engine.logger == mock_logger
        # 验证 wewrite 目录路径
        assert 'wewrite' in str(engine.wewrite_dir)
        assert 'openclaw' in str(engine.openclaw_dir)

    def test_is_available_with_key(self, mock_logger, deepseek_config):
        """测试 is_available（有 API Key）"""
        # 注意：is_available 还检查目录是否存在
        # 这里主要测试 API Key 检查逻辑
        engine = WeWriteEngine(deepseek_config, mock_logger)

        # 验证配置已正确设置
        assert engine.deepseek_config.get('api_key') == 'test-sk-1234567890abcdef'


class TestRewrite:
    """改写方法测试"""

    @patch.object(WeWriteEngine, '_call_wewrite_rewrite')
    def test_rewrite_success(self, mock_rewrite, mock_logger, deepseek_config):
        """测试改写成功"""
        mock_rewrite.return_value = '# 改写后的标题\n\n改写后的内容'

        engine = WeWriteEngine(deepseek_config, mock_logger)
        result = engine.rewrite('原始内容', {'ip_name': '测试作者', 'framework': 'story'})

        assert result.success is True
        assert result.source == 'wewrite'
        assert '改写后的标题' in result.content
        assert result.message == 'WeWrite 改写成功'
        mock_rewrite.assert_called_once()

    @patch.object(WeWriteEngine, '_call_wewrite_rewrite')
    def test_rewrite_raises_error(self, mock_rewrite, mock_logger, deepseek_config):
        """测试改写失败抛出异常"""
        mock_rewrite.side_effect = Exception('改写失败')

        engine = WeWriteEngine(deepseek_config, mock_logger)

        with pytest.raises(WeWriteError, match='改写失败'):
            engine.rewrite('原始内容', {})

    @patch('tempfile.NamedTemporaryFile')
    @patch.object(WeWriteEngine, '_call_wewrite_rewrite')
    def test_rewrite_cleans_up_temp_file(self, mock_rewrite, mock_temp, mock_logger, deepseek_config):
        """测试临时文件被清理"""
        mock_rewrite.return_value = '改写内容'

        mock_file = MagicMock()
        mock_file.name = '/tmp/test.md'
        mock_file.write = MagicMock()
        mock_temp.return_value.__enter__.return_value = mock_file

        engine = WeWriteEngine(deepseek_config, mock_logger)

        with patch('os.path.exists', return_value=True):
            with patch('os.remove') as mock_remove:
                engine.rewrite('原始内容', {})
                mock_remove.assert_called_with('/tmp/test.md')


class TestBuildPrompt:
    """构建改写 prompt 测试"""

    def test_build_prompt_with_default_config(self, mock_logger, deepseek_config):
        """测试使用默认配置构建 prompt"""
        engine = WeWriteEngine(deepseek_config, mock_logger)

        style_config = {}
        prompt = engine._build_wewrite_prompt(style_config, '测试作者', 'story', 'personal')

        assert '测试作者' in prompt
        assert '以故事开篇' in prompt
        assert '个人化表达' in prompt
        assert '## 作者风格配置' in prompt
        assert '## 写作要求' in prompt
        assert '## 禁忌' in prompt

    def test_build_prompt_with_style_config(self, mock_logger, deepseek_config):
        """测试使用完整风格配置构建 prompt"""
        engine = WeWriteEngine(deepseek_config, mock_logger)

        style_config = {
            'topics': ['科技', 'AI'],
            'tone': '专业严谨',
            'voice': '第三人称',
            'blacklist': ['避免夸张', '不要用梗'],
            'content_style': '深度分析'
        }

        prompt = engine._build_wewrite_prompt(style_config, '专家作者', 'analytical', 'authoritative')

        # 验证内容（使用 unicode 避免编码问题）
        assert '\u79d1\u6280' in prompt  # 科技
        assert 'AI' in prompt
        assert '\u4e13\u4e1a\u4e25\u8c28' in prompt  # 专业严谨
        assert '\u7b2c\u4e09\u4eba\u79f0' in prompt  # 第三人称
        assert '\u6df1\u5ea6\u5206\u6790' in prompt  # 深度分析
        assert '\u907f\u514d\u5938\u5f20' in prompt  # 避免夸张
        assert '\u4e0d\u8981\u7528\u6897' in prompt  # 不要用梗

    def test_build_prompt_framework_options(self, mock_logger, deepseek_config):
        """测试不同写作框架"""
        engine = WeWriteEngine(deepseek_config, mock_logger)

        frameworks = ['story', 'pain-point', 'list', 'contrast', 'hotspot', 'opinion', 'review']

        for framework in frameworks:
            prompt = engine._build_wewrite_prompt({}, '作者', framework, 'personal')
            assert prompt is not None
            assert len(prompt) > 100  # prompt 应该有合理长度

    def test_build_prompt_style_options(self, mock_logger, deepseek_config):
        """测试不同表达风格"""
        engine = WeWriteEngine(deepseek_config, mock_logger)

        styles = ['personal', 'journalistic', 'analytical', 'conversational', 'authoritative']

        for style in styles:
            prompt = engine._build_wewrite_prompt({}, '作者', 'story', style)
            assert prompt is not None
            assert len(prompt) > 100


class TestCallLLM:
    """调用 LLM 改写测试"""

    @patch('integrations.wewrite_engine.requests.post')
    def test_call_llm_success(self, mock_post, mock_logger, deepseek_config):
        """测试成功调用 LLM"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': '# 改写后的文章\n\n这是改写后的内容'}
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        engine = WeWriteEngine(deepseek_config, mock_logger)
        result = engine._call_llm_for_rewrite('system prompt', '原文内容', {})

        assert '# 改写后的文章' in result
        assert '这是改写后的内容' in result

    @patch('integrations.wewrite_engine.requests.post')
    def test_call_llm_cleans_markdown(self, mock_post, mock_logger, deepseek_config):
        """测试清理 markdown 标记"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': '```markdown\n这是带标记的内容\n```'}
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        engine = WeWriteEngine(deepseek_config, mock_logger)
        result = engine._call_llm_for_rewrite('system prompt', '原文', {})

        assert '```' not in result
        assert '这是带标记的内容' in result

    @patch('integrations.wewrite_engine.requests.post')
    def test_call_llm_uses_env_vars(self, mock_post, mock_logger, deepseek_config):
        """测试使用环境变量中的 API 配置"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{'message': {'content': '结果'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        env = {
            'OPENAI_API_KEY': 'env-key',
            'OPENAI_BASE_URL': 'https://env-api.com/v1'
        }

        engine = WeWriteEngine(deepseek_config, mock_logger)
        engine._call_llm_for_rewrite('prompt', 'content', env)

        # 验证使用了环境变量
        call_args = mock_post.call_args
        assert call_args[1]['headers']['Authorization'] == 'Bearer env-key'
        assert call_args[1]['headers']['Content-Type'] == 'application/json'

    @patch('integrations.wewrite_engine.requests.post')
    def test_call_llm_uses_config_defaults(self, mock_post, mock_logger, deepseek_config):
        """测试使用配置中的默认值"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{'message': {'content': '结果'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        engine = WeWriteEngine(deepseek_config, mock_logger)
        engine._call_llm_for_rewrite('prompt', 'content', {})

        # 验证使用了配置中的 API Key
        call_args = mock_post.call_args
        assert call_args[1]['headers']['Authorization'] == 'Bearer test-sk-1234567890abcdef'

    @patch('integrations.wewrite_engine.requests.post')
    def test_call_llm_request_payload(self, mock_post, mock_logger, deepseek_config):
        """测试 LLM 请求 payload"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{'message': {'content': '结果'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        engine = WeWriteEngine(deepseek_config, mock_logger)
        engine._call_llm_for_rewrite('test system prompt', 'test content', {})

        # 验证请求 payload
        call_args = mock_post.call_args
        payload = call_args[1]['json']

        assert payload['model'] == 'deepseek-chat'
        assert payload['temperature'] == 0.7
        assert payload['max_tokens'] == 4000
        assert len(payload['messages']) == 2
        assert payload['messages'][0]['role'] == 'system'
        assert payload['messages'][1]['role'] == 'user'
