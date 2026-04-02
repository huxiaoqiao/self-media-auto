# WeWrite + Xiaohu 集成设计文档

**日期**: 2026-04-02
**作者**: Claude Code
**状态**: 待审核

---

## 1. 背景与目标

### 1.1 背景
用户本地代码误删后重新 checkout GitHub 代码，发现之前实现的 wewrite-engine 和 xiaohu 排版功能未推送到远程仓库而丢失。需要重新集成这两个功能到当前项目中。

### 1.2 目标
集成 https://github.com/oaker-io/wewrite 和 https://github.com/xiaohuailabs/xiaohu-wechat-format，替换现有的改写和排版流程，同时保留现有的生图和 baoyu 发布流程。

---

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户命令入口                            │
│                    (同一个命令)                              │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────┐            ┌─────────────────┐
    │   选题来源       │            │   选题来源       │
    │   幂接口 (付费)  │            │   wewrite 热点  │
    │   [优先]        │            │   (免费)        │
    └─────────────────┘            └─────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
                    ┌─────────────────┐
                    │   内容改写引擎   │
                    └─────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────┐            ┌─────────────────┐
    │   WeWrite       │            │   huashu-       │
    │   [优先]        │            │   proofreading  │
    │   (写作框架 +     │            │   [备选]        │
    │    风格模板)     │            │   (自动降级)    │
    └─────────────────┘            └─────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
                    ┌─────────────────┐
                    │   排版引擎       │
                    │   xiaohu-       │
                    │   wechat-format │
                    │   (带浏览器主题  │
                    │    选择器)       │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   生图 + 发布    │
                    │   [保留现有]     │
                    │   宝玉发布流程   │
                    └─────────────────┘
```

### 2.2 数据流

```
选题输入 → 改写引擎 → 改写后内容 → 排版引擎 → HTML 文件 → 生图 → 发布
         (wewrite/huashu)      (xiaohu)     (现有)   (现有)
```

---

## 3. 模块设计

### 3.1 WeWrite 集成模块

**位置**: `integrations/wewrite_engine.py`

**职责**:
- 封装 wewrite 的核心改写功能
- 提供统一的改写接口
- 处理错误并触发降级逻辑

**接口设计**:
```python
class WeWriteEngine:
    def __init__(self, deepseek_config: dict, logger: Logger)

    def rewrite(self, source_content: str, options: dict) -> RewriteResult:
        """
        使用 wewrite 的写作框架和风格模板进行改写

        Args:
            source_content: 源内容
            options: 配置选项（风格、框架等）

        Returns:
            RewriteResult: 包含改写后的内容
        """

    def is_available(self) -> bool:
        """检查 wewrite 是否可用"""
```

**降级逻辑**:
- 捕获 wewrite 的所有异常
- 记录失败原因到日志
- 自动切换到 `huashu-proofreading` 备选方案
- 向用户发送降级通知

### 3.2 Xiaohu 排版模块

**位置**: `integrations/xiaohu_formatter.py`

**职责**:
- 封装 xiaohu-wechat-format 的排版功能
- 启动浏览器主题选择器（gallery 模式）
- 等待用户选择主题后生成 HTML

**接口设计**:
```python
class XiaohuFormatter:
    def __init__(self, config: dict, logger: Logger)

    def format_with_gallery(self, content: str, output_path: str) -> str:
        """
        启动浏览器主题选择器，用户选择后生成 HTML

        Args:
            content: Markdown 格式的内容
            output_path: 输出 HTML 文件路径

        Returns:
            str: 生成的 HTML 文件路径
        """

    def format_with_theme(self, content: str, theme: str, output_path: str) -> str:
        """
        使用指定主题直接生成 HTML（无需浏览器）

        Args:
            content: Markdown 格式的内容
            theme: 主题名称
            output_path: 输出 HTML 文件路径

        Returns:
            str: 生成的 HTML 文件路径
        """
```

**浏览器集成**:
- 启动 xiaohu 的 gallery 脚本
- 获取本地服务器 URL
- 在用户浏览器中打开
- 轮询等待用户选择完成
- 读取生成的 HTML 文件

### 3.3 命令入口

**位置**: 修改现有的命令入口（`workflow_controller.py` 或相关 CLI）

**命令设计**:
```bash
# 统一的命令入口
self-media-auto generate --topic-source [power-fee | wewrite-free] --content <source>
```

**参数说明**:
- `--topic-source`: 选题来源
  - `power-fee`: 幂接口（付费，优先）
  - `wewrite-free`: wewrite 热点捕捉（免费）
- `--content`: 源内容或 URL

**执行流程**:
1. 解析命令行参数
2. 根据 `topic-source` 获取选题
3. 调用改写引擎（wewrite 优先，失败自动降级）
4. 调用排版引擎（带浏览器主题选择）
5. 调用现有生图模块
6. 调用现有 baoyu 发布流程

### 3.4 配置管理

**位置**: `.env` + `config/wewrite_config.py`

**新增配置项**:
```env
# WeWrite 集成配置
WEWRITE_ENABLED=true
WEWRITE_FALLBACK_TO_HUASHU=true

# Xiaohu 排版配置
XIAOHU_GALLERY_MODE=true  # 是否使用浏览器主题选择
XIAOHU_DEFAULT_THEME=newspaper  # 默认主题（非 gallery 模式）

# 复用现有 DeepSeek 配置
DEEPSEEK_API_KEY=xxx
DEEPSEEK_BASE_URL=xxx
DEEPSEEK_MODEL=xxx
```

---

## 4. 文件结构

### 4.1 新增文件

```
skills/self-media-auto/
├── integrations/
│   ├── __init__.py
│   ├── wewrite_engine.py      # WeWrite 改写引擎封装
│   └── xiaohu_formatter.py    # Xiaohu 排版引擎封装
├── config/
│   └── wewrite_config.py      # WeWrite 配置管理
├── wewrite/                   # wewrite 代码库（直接复制）
│   └── [wewrite 源代码]
└── xiaohu-wechat-format/      # xiaohu 代码库（直接复制）
    └── [xiaohu 源代码]
```

### 4.2 修改文件

- `workflow_controller.py` - 修改命令入口和执行流程
- `requirements.txt` - 合并 wewrite 和 xiaohu 的依赖
- `.env` - 新增配置项

### 4.3 删除文件

- `wechat_themes/` - 删除整个目录（被 xiaohu 替代）

### 4.4 保留文件

- `huashu-proofreading/SKILL.MD` - 保留作为备选方案
- `prompts_manager.json` - 保留重塑引擎模板（用于备选方案）
- 现有生图模块
- 现有 baoyu 发布流程

---

## 5. 依赖管理

### 5.1 依赖合并策略

将 wewrite 和 xiaohu-wechat-format 的 `requirements.txt` 内容合并到当前项目的 `requirements.txt`：

**wewrite 依赖**:
- markdown
- requests
- openai（复用现有 DeepSeek 配置，使用 openai 兼容接口）

**xiaohu-wechat-format 依赖**:
- markdown
- requests

**去重处理**:
- `markdown` 和 `requests` 可能已存在于当前项目
- 使用 pip 的 `-r requirements.txt` 自动去重

### 5.2 日志统一

- 两个集成模块使用当前项目的日志系统
- 通过依赖注入传递 logger 实例
- 日志格式保持现有风格（按天生成日志文件）

---

## 6. 错误处理

### 6.1 WeWrite 降级逻辑

```python
try:
    result = wewrite_engine.rewrite(content, options)
    logger.info("WeWrite 改写成功")
except WeWriteError as e:
    logger.warning(f"WeWrite 失败，降级到 huashu-proofreading: {e}")
    result = huashu_engine.rewrite(content, options)
except Exception as e:
    logger.error(f"改写引擎异常：{e}")
    raise
```

### 6.2 排版错误处理

```python
try:
    html_path = xiaohu_formatter.format_with_gallery(content, output_path)
except XiaohuGalleryTimeout as e:
    logger.error(f"主题选择超时，使用默认主题：{e}")
    html_path = xiaohu_formatter.format_with_theme(content, DEFAULT_THEME, output_path)
except Exception as e:
    logger.error(f"排版失败：{e}")
    raise
```

---

## 7. 测试策略

### 7.1 单元测试

- `test_wewrite_engine.py` - 测试 WeWrite 引擎的改写功能和降级逻辑
- `test_xiaohu_formatter.py` - 测试 Xiaohu 排版功能（模拟浏览器选择）

### 7.2 集成测试

- 测试完整流程：选题 → 改写 → 排版 → 生图 → 发布
- 测试 WeWrite 失败时的自动降级
- 测试浏览器主题选择器的启动和完成检测

### 7.3 手动测试

1. 使用 wewrite-free 选题源生成一篇文章
2. 验证浏览器主题选择器正常弹出
3. 选择一个主题，验证 HTML 生成正确
4. 验证生图和发布流程正常

---

## 8. 实施计划

### Phase 1: 代码准备
1. Clone wewrite 到 `wewrite/` 目录
2. Clone xiaohu-wechat-format 到 `xiaohu-wechat-format/` 目录
3. 合并依赖到 `requirements.txt`

### Phase 2: 封装开发
1. 实现 `WeWriteEngine` 类
2. 实现 `XiaohuFormatter` 类
3. 修改命令入口

### Phase 3: 集成测试
1. 单元测试
2. 集成测试
3. 手动测试完整流程

### Phase 4: 清理
1. 删除 `wechat_themes/` 目录
2. 更新文档

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| wewrite/xiaohu 依赖冲突 | 中 | 提前检查 requirements.txt，处理版本冲突 |
| 浏览器主题选择器无法正常启动 | 中 | 提供降级方案（默认主题） |
| WeWrite 改写质量不符合预期 | 低 | 自动降级到 huashu-proofreading |
| 两个库的代码结构与当前项目不兼容 | 中 | 封装层隔离，不直接修改库代码 |

---

## 10. 验收标准

1. ✅ 能够通过统一命令入口生成文章
2. ✅ 选题来源支持幂接口（付费）和 wewrite 热点（免费）切换
3. ✅ WeWrite 作为优先改写引擎，失败时自动降级到 huashu-proofreading
4. ✅ 排版时弹出浏览器主题选择器
5. ✅ 生成的 HTML 文件正确应用选中的主题
6. ✅ 生图和 baoyu 发布流程正常工作
7. ✅ 日志系统统一，所有操作有迹可循
8. ✅ `wechat_themes/` 目录已删除
