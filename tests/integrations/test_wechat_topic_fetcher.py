"""微信公众号选题获取器测试"""
import os
import pytest
from unittest.mock import patch, MagicMock
from integrations.wechat_topic_fetcher import TopicFetcher


class TestTopicFetcherInit:
    """TopicFetcher 初始化测试"""

    def test_init_with_config(self, mock_logger, topic_fetcher_config):
        """测试使用配置初始化"""
        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)

        assert fetcher.config == topic_fetcher_config
        assert fetcher.logger == mock_logger
        assert fetcher.cimi_app_id == 'test_app_id'
        assert fetcher.cimi_app_secret == 'test_app_secret'

    def test_init_without_cimi_credentials(self, mock_logger):
        """测试无次幂凭证时初始化"""
        config = {'cimi_app_id': None, 'cimi_app_secret': None}
        fetcher = TopicFetcher(config, mock_logger)

        assert fetcher.cimi_app_id is None
        assert fetcher.cimi_app_secret is None


class TestFetchTopics:
    """获取选题测试"""

    @patch('integrations.wechat_topic_fetcher.TopicFetcher._fetch_from_cimi')
    def test_fetch_from_power_fee(self, mock_cimi, mock_logger, topic_fetcher_config):
        """测试从付费源获取选题"""
        mock_cimi.return_value = [
            {'title': '热门话题 1', 'heat_score': 100, 'platform': 'wechat'}
        ]

        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)
        topics = fetcher.fetch_topics(source='power-fee')

        assert len(topics) == 1
        assert topics[0]['title'] == '热门话题 1'
        mock_cimi.assert_called_once()

    @patch('integrations.wechat_topic_fetcher.TopicFetcher._fetch_from_wewrite')
    def test_fetch_from_wewrite_free(self, mock_wewrite, mock_logger, topic_fetcher_config):
        """测试从免费源获取选题"""
        mock_wewrite.return_value = [
            {'title': '免费话题 1', 'heat_score': 50, 'platform': 'douyin'}
        ]

        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)
        topics = fetcher.fetch_topics(source='wewrite-free')

        assert len(topics) == 1
        assert topics[0]['title'] == '免费话题 1'
        mock_wewrite.assert_called_once()

    def test_fetch_unknown_source(self, mock_logger, topic_fetcher_config):
        """测试未知来源抛出异常"""
        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)

        with pytest.raises(ValueError, match='未知的选题来源'):
            fetcher.fetch_topics(source='unknown-source')


class TestFetchFromCimi:
    """从次幂 API 获取测试"""

    @patch('integrations.wechat_topic_fetcher.requests.get')
    def test_successful_fetch(self, mock_get, mock_logger, topic_fetcher_config):
        """测试成功获取"""
        # 模拟 API 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'list': [
                    {
                        'title': 'API 话题 1',
                        'link': 'https://example.com/1',
                        'hot_score': 95,
                        'source': 'wechat',
                        'abstract': '话题摘要'
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)
        topics = fetcher._fetch_from_cimi()

        assert len(topics) == 1
        assert topics[0]['title'] == 'API 话题 1'
        assert topics[0]['source_url'] == 'https://example.com/1'
        assert topics[0]['heat_score'] == 95
        assert topics[0]['platform'] == 'wechat'

    @patch('integrations.wechat_topic_fetcher.requests.get')
    def test_api_error_falls_back(self, mock_get, mock_logger, topic_fetcher_config):
        """测试 API 错误时降级到免费方案"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        with patch.object(TopicFetcher, '_fetch_from_wewrite') as mock_wewrite:
            mock_wewrite.return_value = []

            fetcher = TopicFetcher(topic_fetcher_config, mock_logger)
            topics = fetcher._fetch_from_cimi()

            mock_wewrite.assert_called_once()

    @patch('integrations.wechat_topic_fetcher.requests.get')
    def test_missing_credentials_falls_back(self, mock_get, mock_logger, topic_fetcher_config):
        """测试缺少凭证时降级到免费方案"""
        fetcher = TopicFetcher({'cimi_app_id': None, 'cimi_app_secret': None}, mock_logger)

        with patch.object(TopicFetcher, '_fetch_from_wewrite') as mock_wewrite:
            mock_wewrite.return_value = []
            topics = fetcher._fetch_from_cimi()

            mock_wewrite.assert_called_once()


class TestFetchFromWewrite:
    """从 wewrite 获取测试（需要在真实环境中测试 Path 逻辑）"""

    def test_fetch_from_wewrite_returns_list(self, mock_logger, topic_fetcher_config):
        """测试 _fetch_from_wewrite 返回 list（不 mock 内部实现）"""
        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)
        result = fetcher._fetch_from_wewrite()

        # 只验证返回类型是 list
        # 实际功能测试需要在真实环境中运行
        assert isinstance(result, list)


class TestParseTopics:
    """解析话题数据测试"""

    def test_parse_cimi_response(self, mock_logger, topic_fetcher_config):
        """测试解析次幂 API 响应"""
        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)

        data = {
            'data': {
                'list': [
                    {'title': '话题 1', 'link': 'https://url1.com', 'hot_score': 80, 'source': 'wechat', 'abstract': '摘要 1'},
                    {'title': '话题 2', 'link': 'https://url2.com', 'hot_score': 90, 'source': 'douyin'}
                ]
            }
        }

        topics = fetcher._parse_cimi_response(data)

        assert len(topics) == 2
        assert topics[0] == {
            'title': '话题 1',
            'source_url': 'https://url1.com',
            'heat_score': 80,
            'platform': 'wechat',
            'description': '摘要 1'
        }
        assert topics[1]['heat_score'] == 90

    def test_parse_wewrite_topics(self, mock_logger, topic_fetcher_config):
        """测试解析 wewrite 话题数据"""
        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)

        topics_data = [
            {'title': '话题 A', 'url': 'https://a.com', 'hot': 70, 'source': 'xiaohongshu', 'description': '描述 A'},
            {'title': '话题 B', 'url': 'https://b.com', 'hot': 85}
        ]

        topics = fetcher._parse_wewrite_topics(topics_data)

        assert len(topics) == 2
        assert topics[0]['platform'] == 'xiaohongshu'
        assert topics[1]['description'] == ''  # 缺失字段返回空字符串

    def test_parse_empty_response(self, mock_logger, topic_fetcher_config):
        """测试解析空响应"""
        fetcher = TopicFetcher(topic_fetcher_config, mock_logger)

        topics = fetcher._parse_cimi_response({'data': {'list': []}})
        assert topics == []

        topics = fetcher._parse_wewrite_topics([])
        assert topics == []
