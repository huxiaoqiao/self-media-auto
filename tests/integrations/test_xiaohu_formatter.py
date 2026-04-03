"""Xiaohu 排版引擎测试"""
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from integrations.xiaohu_formatter import (
    XiaohuFormatter,
    XiaohuGalleryError,
    XiaohuGalleryTimeout,
    XiaohuFormatError,
)


class TestXiaohuFormatterInit:
    """XiaohuFormatter 初始化测试"""

    def test_init_with_config(self, mock_logger, xiaohu_config):
        """测试使用配置初始化"""
        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        assert formatter.config == xiaohu_config
        assert formatter.logger == mock_logger
        assert formatter.default_theme == 'newspaper'
        assert formatter.gallery_timeout == 60
        assert 'xiaohu-wechat-format' in str(formatter.xiaohu_dir)

    def test_init_default_values(self, mock_logger):
        """测试默认值"""
        formatter = XiaohuFormatter({}, mock_logger)

        assert formatter.default_theme == 'newspaper'
        assert formatter.gallery_timeout == 300  # 5 分钟

    def test_init_custom_theme(self, mock_logger):
        """测试自定义默认主题"""
        config = {'default_theme': 'github'}
        formatter = XiaohuFormatter(config, mock_logger)

        assert formatter.default_theme == 'github'


class TestFormatWithTheme:
    """使用指定主题格式化测试"""

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_format_success(self, mock_remove, mock_exists, mock_run, mock_logger, xiaohu_config):
        """测试成功格式化"""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        with patch('builtins.open', mock_open()):
            result = formatter.format_with_theme(
                '# 文章内容',
                'newspaper',
                '/tmp/output.html'
            )

        assert result == '/tmp/output.html'
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_format_command_timeout(self, mock_run, mock_logger, xiaohu_config):
        """测试命令超时"""
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(cmd='test', timeout=60)

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        with patch('builtins.open', mock_open()):
            with pytest.raises(XiaohuFormatError, match='排版命令超时'):
                formatter.format_with_theme('# 内容', 'theme', '/tmp/out.html')

    @patch('subprocess.run')
    def test_format_command_error(self, mock_run, mock_logger, xiaohu_config):
        """测试命令执行错误"""
        mock_run.return_value = MagicMock(returncode=1, stderr='错误信息')

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        with patch('builtins.open', mock_open()):
            with pytest.raises(XiaohuFormatError, match='排版命令失败'):
                formatter.format_with_theme('# 内容', 'theme', '/tmp/out.html')

    @patch('os.remove')
    @patch('os.makedirs')
    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_format_creates_output_dir(self, mock_run, mock_exists, mock_makedirs, mock_remove, mock_logger, xiaohu_config):
        """测试创建输出目录"""
        mock_exists.side_effect = [False, True]  # 输出目录不存在，但 temp file 检查存在
        mock_run.return_value = MagicMock(returncode=0)

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        with patch('builtins.open', mock_open()):
            formatter.format_with_theme('# 内容', 'theme', '/tmp/newdir/output.html')

            # 验证创建了输出目录
            mock_makedirs.assert_called_once()


class TestFormatWithGallery:
    """Gallery 模式格式化测试"""

    @patch('subprocess.Popen')
    @patch('os.path.exists')
    @patch('time.time')
    def test_gallery_success(self, mock_time, mock_exists, mock_popen, mock_logger, xiaohu_config):
        """测试 Gallery 模式成功"""
        # 模拟时间流逝
        mock_time.side_effect = [0, 2, 4, 6]  # 4 次调用

        # 模拟进程
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # 进程运行中
        mock_popen.return_value = mock_process

        # 模拟输出文件在第三次检查时存在
        exists_calls = [False, False, True]  # 前两次不存在，第三次存在
        mock_exists.side_effect = lambda path: exists_calls.pop(0) if path.endswith('.html') else True

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        with patch('builtins.open', mock_open()):
            with patch('os.remove'):
                result = formatter.format_with_gallery('# 内容', '/tmp/output.html')

        assert result == '/tmp/output.html'

    @patch('subprocess.Popen')
    @patch('os.path.exists')
    @patch('time.time')
    def test_gallery_timeout(self, mock_time, mock_exists, mock_popen, mock_logger, xiaohu_config):
        """测试 Gallery 模式超时"""
        # 模拟时间流逝超过超时时间
        mock_time.side_effect = [0, 60, 120, 300, 301]  # 超过 300 秒超时

        # 模拟进程
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        # 输出文件始终不存在
        mock_exists.return_value = False

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        with patch('builtins.open', mock_open()):
            # 超时异常会被包装成 XiaohuGalleryError
            with pytest.raises(XiaohuGalleryError):
                formatter.format_with_gallery('# 内容', '/tmp/output.html')

    @patch('subprocess.Popen')
    @patch('os.path.exists')
    @patch('time.time')
    def test_gallery_process_error(self, mock_time, mock_exists, mock_popen, mock_logger, xiaohu_config):
        """测试 Gallery 进程异常退出"""
        # 模拟时间流逝
        mock_time.side_effect = [0, 2, 4]

        # 模拟进程异常退出
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # 进程异常退出
        mock_process.communicate.return_value = (b'', b'error message')
        mock_popen.return_value = mock_process

        # 输出文件不存在
        mock_exists.return_value = False

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)

        with patch('builtins.open', mock_open()):
            with pytest.raises(XiaohuGalleryError, match='进程异常'):
                formatter.format_with_gallery('# 内容', '/tmp/output.html')


class TestListThemes:
    """列出可用主题测试"""

    @patch.object(Path, 'exists')
    @patch.object(Path, 'glob')
    def test_list_themes_success(self, mock_glob, mock_exists, mock_logger, xiaohu_config):
        """测试成功列出主题"""
        mock_exists.return_value = True

        # 创建模拟的 Path 对象，正确返回 stem
        mock_theme1 = MagicMock()
        mock_theme1.is_file.return_value = True
        mock_theme1.stem = 'newspaper'

        mock_theme2 = MagicMock()
        mock_theme2.is_file.return_value = True
        mock_theme2.stem = 'github'

        mock_not_file = MagicMock()
        mock_not_file.is_file.return_value = False

        mock_glob.return_value = [mock_theme1, mock_theme2, mock_not_file]

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)
        themes = formatter.list_themes()

        assert 'newspaper' in themes
        assert 'github' in themes
        assert len(themes) == 2  # 只有 2 个是文件

    @patch.object(Path, 'exists')
    def test_list_themes_dir_not_exists(self, mock_exists, mock_logger, xiaohu_config):
        """测试主题目录不存在时返回空列表"""
        mock_exists.return_value = False

        formatter = XiaohuFormatter(xiaohu_config, mock_logger)
        themes = formatter.list_themes()

        assert themes == []


# 注意：_ensure_config_exists 是私有方法，其测试已在 format_with_theme 和 format_with_gallery 中间接测试
