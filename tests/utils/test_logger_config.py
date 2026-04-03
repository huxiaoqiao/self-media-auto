"""日志配置模块测试"""
import os
import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from utils.logger_config import (
    cleanup_old_logs,
    get_today_log_filename,
    setup_logger,
    init_logging,
    get_workflow_logger,
    get_card_server_logger,
    LOG_DIR,
    MAX_LOG_AGE_DAYS,
)


class TestGetTodayLogFilename:
    """获取今天日志文件名测试"""

    def test_returns_correct_filename(self):
        """测试返回正确的文件名格式"""
        filename = get_today_log_filename('workflow')

        # 验证文件名包含前缀和日期
        assert filename.startswith(str(LOG_DIR))
        assert 'workflow_' in filename
        assert filename.endswith('.log')

    def test_different_prefixes(self):
        """测试不同前缀"""
        filename_card = get_today_log_filename('card_server')
        assert 'card_server_' in filename_card

    def test_log_dir_exists(self):
        """测试日志目录会被自动创建"""
        # 即使目录不存在，函数也应该能工作
        # Path.mkdir(exist_ok=True) 确保不会报错
        filename = get_today_log_filename('test')
        assert Path(filename).parent.exists()


class TestCleanupOldLogs:
    """清理旧日志测试"""

    def test_cleanup_old_logs(self, temp_dir):
        """测试清理超过指定天数的日志"""
        # 创建 10 天前的日志文件
        old_date = '20250101'  # 过去的日期
        old_log = Path(temp_dir) / f"workflow_{old_date}.log"
        old_log.touch()

        # 执行清理
        deleted_count = cleanup_old_logs(Path(temp_dir), max_age_days=7)

        # 验证：旧日志被删除
        assert old_log.exists() is False
        assert deleted_count == 1

    def test_cleanup_preserves_recent_logs(self, temp_dir):
        """测试保留最近的日志"""
        # 获取今天的日期
        today = Path(LOG_DIR).name[:8]
        if len(today) != 8 or not today.isdigit():
            from datetime import datetime
            today = datetime.now().strftime('%Y%m%d')

        # 创建今天的日志
        today_log = Path(temp_dir) / f"workflow_{today}.log"
        today_log.touch()

        # 执行清理（7 天保留期）
        deleted_count = cleanup_old_logs(Path(temp_dir), max_age_days=7)

        # 今天的日志应该保留
        assert today_log.exists() is True

    def test_cleanup_returns_deleted_count(self, temp_dir):
        """测试返回删除的文件数量"""
        # 创建多个旧日志（使用明确的过去日期）
        old_dates = ['20250101', '20250102', '20250103']
        for date in old_dates:
            old_log = Path(temp_dir) / f"test_{date}.log"
            old_log.touch()

        deleted_count = cleanup_old_logs(Path(temp_dir), max_age_days=7)

        # 所有 3 个旧日志都应该被删除
        assert deleted_count == 3


class TestSetupLogger:
    """setup_logger 函数测试"""

    def test_create_logger(self):
        """测试创建 logger"""
        logger = setup_logger('TestLogger', 'test')

        assert logger is not None
        assert logger.name == 'TestLogger'
        assert logger.level == logging.DEBUG

    def test_logger_caching(self):
        """测试 logger 缓存（相同配置返回同一个 logger）"""
        logger1 = setup_logger('CachedLogger', 'cached')
        logger2 = setup_logger('CachedLogger', 'cached')

        assert logger1 is logger2

    def test_different_config_creates_new_logger(self):
        """测试不同配置创建新 logger"""
        # 注意：logger 缓存是基于 cache_key = f'{name}_{log_prefix}'
        # 但 logger name 相同会返回同一个 logger（因为 logging.getLogger 返回单例）
        # 所以这里测试不同 logger name 的情况
        logger1 = setup_logger('LoggerA', 'prefix1')
        logger2 = setup_logger('LoggerB', 'prefix2')

        assert logger1.name != logger2.name
        assert logger1 is not logger2

    def test_logger_handlers_configured(self):
        """测试 logger handler 配置正确"""
        logger = setup_logger('HandlerTest', 'handler', console_level=logging.DEBUG)

        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        console_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]

        assert len(file_handlers) >= 1
        assert len(console_handlers) >= 1


class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_get_workflow_logger(self):
        """测试获取 workflow logger"""
        logger = get_workflow_logger()

        assert logger is not None
        assert 'Workflow' in logger.name

    def test_get_card_server_logger(self):
        """测试获取 card_server logger"""
        logger = get_card_server_logger()

        assert logger is not None
        assert 'Feishu' in logger.name or 'Card' in logger.name

    def test_init_logging(self):
        """测试初始化日志系统"""
        # init_logging 应该：
        # 1. 创建日志目录
        # 2. 清理旧日志
        # 不抛出异常即为成功
        init_logging()
        assert LOG_DIR.exists()
