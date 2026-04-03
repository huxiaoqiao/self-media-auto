# WeWrite + Xiaohu 集成文档

> 公众号文章全流程自动化：选题 → 改写 → 排版 → 发布

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `.env` 文件，确保以下配置项存在：

```env
# WeWrite 配置
WEWRITE_ENABLED=true
WEWRITE_FALLBACK_TO_HUASHU=true

# Xiaohu 配置
XIAOHU_GALLERY_MODE=true
XIAOHU_DEFAULT_THEME=newspaper
XIAOHU_GALLERY_TIMEOUT=300

# DeepSeek API（复用现有）
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL_ID=deepseek-chat

# 次幂 API（付费选题源，可选）
CIMI_APP_ID=your-app-id
CIMI_APP_SECRET=your-app-secret
```

### 3. 使用命令

```bash
# 使用免费选题源（wewrite 热点捕捉）
python workflow_controller.py generate \
    --topic-source wewrite-free \
    --output output/article.html

# 使用付费选题源（次幂 API）
python workflow_controller.py generate \
    --topic-source power-fee \
    --output output/article.html

# 指定内容直接改写（跳过选题）
python workflow_controller.py generate \
    --content "你的文章内容或 URL" \
    --output output/article.html

# 指定主题（不弹出浏览器）
python workflow_controller.py generate \
    --topic-source wewrite-free \
    --theme newspaper \
    --output output/article.html
```

## 功能说明

### 选题来源

| 选项 | 说明 |
|------|------|
| `power-fee` | 次幂 API（付费）- 优先，数据质量高 |
| `wewrite-free` | wewrite 热点捕捉（免费）- 微博/头条/百度热搜 |

### 改写引擎

| 引擎 | 说明 |
|------|------|
| WeWrite（优先） | 使用写作框架和风格模板，支持 5 种写作人格 |
| huashu-proofreading（备选） | WeWrite 失败时自动降级，三遍审校 |

### 排版引擎

| 模式 | 说明 |
|------|------|
| Gallery 模式 | 弹出浏览器选择主题（30 个主题可视化预览） |
| 直接模式 | 使用指定主题或默认主题 |

#### 可用主题

**深度长文（4 个）**: newspaper, magazine, ink, coffee-house

**科技产品（4 个）**: bytedance, github, sspai, midnight

**文艺随笔（4 个）**: terracotta, mint-fresh, sunset-amber, lavender-dream

**活力动态（4 个）**: sports, bauhaus, chinese, wechat-native

**模板布局（4 个）**: minimal-gold, focus-blue, elegant-green, bold-blue

## 命令参数

```
python workflow_controller.py generate [OPTIONS]

选项:
  --topic-source    选题来源：power-fee | wewrite-free (默认：power-fee)
  --content         源内容或 URL（不指定则自动获取选题）
  --output          输出 HTML 文件路径 (默认：output/article.html)
  --theme           排版主题名称（不指定则使用 gallery 模式）
```

## 执行流程

```
1. 获取选题 → 2. 改写内容 → 3. 排版 → 4. 生图 → 5. 发布
         ↓              ↓           ↓
     次幂/wewrite   WeWrite/   Xiaohu
                    huashu
```

### 降级策略

- **选题获取失败**：次幂 API 失败 → 降级到 wewrite 热点捕捉
- **改写失败**：WeWrite 失败 → 降级到 huashu-proofreading
- **排版失败**：Gallery 超时 → 降级到默认主题

## 常见问题

### Q: Gallery 模式浏览器没有打开？

A:
1. 检查 `XIAOHU_GALLERY_MODE=true` 配置
2. 确保系统默认浏览器已正确配置
3. 检查防火墙是否阻止本地服务器

### Q: WeWrite 改写失败？

A:
1. 检查 DeepSeek API 配置是否正确
2. 检查 `wewrite/` 目录是否存在
3. 失败时会自动降级到 huashu-proofreading

### Q: 如何跳过选题直接改写？

A: 使用 `--content` 参数指定内容：
```bash
python workflow_controller.py generate \
    --content "这里是你的文章内容" \
    --output output/article.html
```

### Q: 如何禁用自动降级？

A: 设置 `WEWRITE_FALLBACK_TO_HUASHU=false`，WeWrite 失败时会直接报错而不是降级。

## 架构说明

```
workflow_controller.py (命令入口)
    │
    ├── TopicFetcher (选题获取)
    │   ├── 次幂 API
    │   └── wewrite 热点捕捉
    │
    ├── WeWriteEngine (改写引擎)
    │   ├── WeWrite (优先)
    │   └── huashu-proofreading (备选)
    │
    └── XiaohuFormatter (排版引擎)
        ├── Gallery 模式
        └── 直接模式
```

## 相关文件

- `integrations/wewrite_engine.py` - WeWrite 引擎封装
- `integrations/xiaohu_formatter.py` - Xiaohu 排版封装
- `integrations/wechat_topic_fetcher.py` - 选题获取封装
- `config/wewrite_config.py` - 配置管理
- `wewrite/` - wewrite 代码库
- `xiaohu-wechat-format/` - xiaohu 代码库
