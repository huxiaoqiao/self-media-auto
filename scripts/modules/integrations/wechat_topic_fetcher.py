"""
微信热点选题获取

免费方案：从 wewrite 的热点捕捉功能获取
付费方案：从次幂 API 获取
"""
import os
import logging
import requests
from typing import List, Optional, Dict, Any


class TopicFetcher:
    """选题获取引擎"""

    def __init__(self, config: dict, logger: logging.Logger):
        """
        初始化选题获取引擎

        Args:
            config: 配置项
                - cimi_app_id: 次幂 AppID
                - cimi_app_secret: 次幂 AppSecret
            logger: 日志实例
        """
        self.config = config
        self.logger = logger
        self.cimi_app_id = config.get('cimi_app_id')
        self.cimi_app_secret = config.get('cimi_app_secret')

    def fetch_topics(self, source: str = 'power-fee') -> List[Dict[str, Any]]:
        """
        获取热点选题

        Args:
            source: 选题来源
                - 'power-fee': 次幂接口（付费）
                - 'wewrite-free': wewrite 热点捕捉（免费）

        Returns:
            List[Dict]: 选题列表，每个选题包含：
                - title: 标题
                - source_url: 来源 URL
                - heat_score: 热度值
                - platform: 平台
        """
        if source == 'power-fee':
            return self._fetch_from_cimi()
        elif source == 'wewrite-free':
            return self._fetch_from_wewrite()
        else:
            raise ValueError(f"未知的选题来源：{source}")

    def _fetch_from_cimi(self) -> List[Dict[str, Any]]:
        """从次幂 API 获取热点选题（付费）"""
        if not self.cimi_app_id or not self.cimi_app_secret:
            self.logger.warning("次幂 API 配置缺失，降级到免费方案")
            return self._fetch_from_wewrite()

        try:
            self.logger.info("从次幂 API 获取热点选题")

            # 调用次幂 API
            # 根据实际 API 文档调整 endpoint 和参数
            response = requests.get(
                'https://api.getcimi.com/api/applet_hot_searchs?sort[rank]=ASC',
                headers={
                    'Appid': self.cimi_app_id,
                    'Secret': self.cimi_app_secret
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_cimi_response(data)
            else:
                self.logger.warning(f"次幂 API 返回错误：{response.status_code}")
                return self._fetch_from_wewrite()

        except Exception as e:
            self.logger.warning(f"次幂 API 调用失败：{e}，降级到免费方案")
            return self._fetch_from_wewrite()

    def _fetch_from_wewrite(self) -> List[Dict[str, Any]]:
        """从 wewrite 热点捕捉获取选题（免费）"""
        try:
            self.logger.info("从 wewrite 热点捕捉获取选题")

            # 调用 wewrite 的热点捕捉功能
            from pathlib import Path
            import subprocess
            import sys
            import json

            wewrite_dir = Path(__file__).parent.parent / 'wewrite'
            openclaw_dir = wewrite_dir / 'dist' / 'openclaw'
            script_path = openclaw_dir / 'scripts' / 'fetch_hotspots.py'

            if not script_path.exists():
                self.logger.warning(f"fetch_hotspots.py 不存在：{script_path}")
                return []

            result = subprocess.run(
                [sys.executable, str(script_path), '--limit', '20'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                self.logger.error(f"fetch_hotspots 失败：{result.stderr}")
                return []

            # 解析输出（JSON 格式）
            try:
                topics = json.loads(result.stdout.strip())
                return self._parse_wewrite_topics(topics)
            except json.JSONDecodeError:
                self.logger.error("解析热点数据失败")
                return []

        except Exception as e:
            self.logger.error(f"wewrite 热点捕捉失败：{e}")
            return []

    def _parse_cimi_response(self, data: dict) -> List[Dict[str, Any]]:
        """解析次幂 API 响应"""
        topics = []
        # 根据实际 API 响应结构调整
        for item in data.get('data', {}).get('list', []):
            topics.append({
                'title': item.get('title', ''),
                'source_url': item.get('link', ''),
                'heat_score': item.get('hot_score', 0),
                'platform': item.get('source', 'wechat'),
                'description': item.get('abstract', '')
            })
        return topics

    def _parse_wewrite_topics(self, topics: list) -> List[Dict[str, Any]]:
        """解析 wewrite 热点数据"""
        result = []
        for topic in topics:
            result.append({
                'title': topic.get('title', ''),
                'source_url': topic.get('url', ''),
                'heat_score': topic.get('hot', 0),
                'platform': topic.get('source', ''),
                'description': topic.get('description', '')
            })
        return result
