#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志配置模块

功能：
1. 按天生成日志文件（同一天所有日志写入同一文件）
2. 自动清理 7 天前的旧日志
3. 支持多 logger 统一配置

使用示例：
    from utils.logger_config import setup_logger

    logger = setup_logger('MyModule', 'workflow')
    logger.info('日志消息')
"""

import os
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# 日志目录
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 日志保留天数
MAX_LOG_AGE_DAYS = 7

# 日志格式
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 全局缓存：存储已创建的 logger，避免重复创建
_logger_cache = {}


def cleanup_old_logs(log_dir: Optional[Path] = None, max_age_days: int = MAX_LOG_AGE_DAYS) -> int:
    """
    清理指定天数之前的日志文件

    Args:
        log_dir: 日志目录，默认使用全局 LOG_DIR
        max_age_days: 保留天数，默认 7 天

    Returns:
        被删除的文件数量
    """
    if log_dir is None:
        log_dir = LOG_DIR

    cutoff = datetime.now() - timedelta(days=max_age_days)
    deleted_count = 0

    # 匹配日志文件名：prefix_YYYYMMDD.log 或 prefix_YYYYMMDD_HHMMSS.log
    pattern = re.compile(r'^[a-zA-Z_]+_(\d{8})(?:_\d{6})?\.log$')

    for f in log_dir.iterdir():
        if not f.is_file():
            continue

        match = pattern.match(f.name)
        if match:
            try:
                # 从文件名解析日期（只取前 8 位）
                date_str = match.group(1)
                file_date = datetime.strptime(date_str, '%Y%m%d')

                if file_date < cutoff:
                    f.unlink()
                    deleted_count += 1
                    print(f"[LOG_CLEANUP] Deleted old log: {f.name}")
            except ValueError:
                # 日期解析失败，跳过
                pass

    if deleted_count > 0:
        print(f"[LOG_CLEANUP] Removed {deleted_count} old log file(s) (older than {max_age_days} days)")
    else:
        print(f"[LOG_CLEANUP] No old logs to remove (retaining {len(list(log_dir.glob('*.log')))} files)")

    return deleted_count


def get_today_log_filename(prefix: str) -> str:
    """
    生成今天的日志文件名

    Args:
        prefix: 文件名前缀，如 'workflow', 'card_server'

    Returns:
        日志文件完整路径
    """
    today = datetime.now().strftime('%Y%m%d')
    return str(LOG_DIR / f'{prefix}_{today}.log')


def setup_logger(
    name: str,
    log_prefix: str,
    level: int = logging.DEBUG,
    console_level: int = logging.INFO
) -> logging.Logger:
    """
    设置并返回一个 logger

    Args:
        name: logger 名称，如 'WorkflowController'
        log_prefix: 日志文件前缀，如 'workflow' -> workflow_20260331.log
        level: 文件日志级别，默认 DEBUG
        console_level: 控制台日志级别，默认 INFO

    Returns:
        配置好的 logger 实例
    """
    # 检查缓存
    cache_key = f'{name}_{log_prefix}'
    if cache_key in _logger_cache:
        return _logger_cache[cache_key]

    # 创建 logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        _logger_cache[cache_key] = logger
        return logger

    # 获取今天的日志文件路径
    log_file = get_today_log_filename(log_prefix)

    # 文件 Handler - 追加模式
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)

    # 控制台 Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    # 打印日志文件路径（仅首次）
    print(f"[LOG] {name} 日志文件：{log_file}")
    logger.info(f"{name} 初始化完成，日志文件：{log_file}")

    # 缓存 logger
    _logger_cache[cache_key] = logger

    return logger


def init_logging(log_prefix: str = 'workflow') -> None:
    """
    初始化日志系统（在程序启动时调用）

    - 清理旧日志
    - 创建日志目录

    Args:
        log_prefix: 清理日志时使用的前缀，默认 'workflow'
    """
    # 确保日志目录存在
    LOG_DIR.mkdir(exist_ok=True)

    # 清理旧日志
    cleanup_old_logs()


# 便捷函数：获取主工作流 logger
def get_workflow_logger() -> logging.Logger:
    """获取 workflow_controller 的 logger"""
    return setup_logger('WorkflowController', 'workflow')


# 便捷函数：获取卡片服务 logger
def get_card_server_logger() -> logging.Logger:
    """获取 feishu-card-server 的 logger"""
    return setup_logger('FeishuCardServer', 'card_server')
