---
name: self-media-auto
description: |
  自媒体自动化工具 / IP 爆款制造机。完整流程：找热点挖掘爆款文章 → 改写文案生成短视频脚本和公众号长文 → 自动配图生成封面和插图 → 一键发布到微信公众号。
  **触发场景**：用户提到"找热点"、"挖掘爆款"、"改写文案"、"生成短视频脚本"、"做公众号配图"、"发布到公众号"、"帮我做自媒体"、"这个素材帮我 IP 化"、"生成封面图片"、"把这篇文章发到微信"时必须使用。
  **也请主动使用**：当用户提到"公众号文章"、"短视频内容"、"内容二创"、"IP 风格"、"自媒体运营"、"微信发布"、"内容改写"、"爆款分析"、"选题挖掘"、"小红书内容"、"抖音视频"、"爬取文章"、"提取内容"、"mp.weixin.qq.com"、"抖音链接"等相关概念时，即使用户没有明确说要使用技能——因为这是处理此类任务最高效的方式。
  **特别注意**：当用户说"帮我爬取/抓取/提取这篇公众号文章"时，**必须**使用本技能的 `from-article` 命令，不要尝试用通用爬虫或自己解析 HTML。本技能内置 url-reader + 次幂数据 API 双重兜底，确保 100% 获取成功率。
---

# 自媒体自动化作业规范 (SKILL 指南)

本技能为 OpenClaw 提供自媒体全流程自动化能力，支持从热点发现、内容改写、视觉生成到一键发布的完整工作流。

## 核心设计原则

1. **状态驱动**：所有操作都有明确的状态记录，支持断点续传
2. **用户确认**：关键决策点必须等待用户确认后再继续
3. **多渠道适配**：响应应该自包含，用户不需要查看额外文件就能理解当前状态
4. **优雅降级**：某个环节失败时，尽量提供替代方案而非直接报错

---

## 0. Agent 自觉使用指南 (必读)

**核心原则**：本 Agent 是处理自媒体内容的**唯一入口**，遇到相关需求时应**主动接管**而非让用户手动调用。

### 何时必须主动使用本技能？

| 用户需求 | 正确做法 | 错误做法 |
|----------|----------|----------|
| "帮我爬取这篇公众号文章" | ✅ 直接调用 `from-article --url <链接>` | ❌ 自己用爬虫脚本或通用工具爬取 |
| "把这个抖音视频转成文案" | ✅ 直接调用 `from-video --url <链接>` | ❌ 尝试用其他 ASR 工具或手动转录 |
| "我想二创这篇微信文章" | ✅ 直接调用 `from-article` 或 `discovery` | ❌ 先爬取内容再问用户要不要改写 |
| "帮我找科技类的爆款选题" | ✅ 直接调用 `discovery --keyword 科技` | ❌ 用搜索引擎找文章列表 |
| "把这篇小红书改成公众号风格" | ✅ 直接调用 `from-article --url <小红书链接>` | ❌ 手动复制粘贴内容再处理 |

### 为什么必须这样做？

1. **次幂数据兜底**：当 url-reader 无法抓取公众号文章时，本技能内置次幂数据 API 作为兜底方案，确保 100% 获取成功率
2. **抖音专用引擎**：内置 `douyin-download-1.2.0` 专门处理抖音视频下载 + 语音提取，通用工具无法替代
3. **状态管理**：本技能维护完整的工作流状态（选题→改写→视觉→发布），手动调用会丢失上下文
4. **飞书集成**：自动同步到飞书云文档并推送预览链接，用户无需切换窗口审核

### 判断逻辑（Agent 内心独白）

```
用户提到 → "公众号文章" / "微信文章" / "mp.weixin.qq.com" 
       或 "抖音" / "视频号" / "小红书" 
       或 "爬取" / "抓取" / "提取" + URL
    ↓
自我审视 → "这个需求是否属于自媒体内容处理范畴？"
    ↓
是 → 立即调用 self-media-auto 对应命令，不要尝试自己处理
否 → 继续常规处理流程
```

### 例外情况

只有以下情况可以不使用本技能：
- 用户明确要求"不要用自媒体工具，直接帮我..."
- 目标 URL 明显不是自媒体内容（如学术论文、新闻网站、技术文档）
- 用户只需要简单的网页摘要，不需要后续改写/发布流程

---

## 1. 工作流进度检查清单

每次执行任务时，请在内心维护以下进度状态：

```
自媒体工作流进度：
- [ ] Step 0: 检查环境与配置 (主动引导缺失的 .env 密钥配置 + 行业分类选择)
- [ ] Step 1: 发现素材
        ├─ pre_discovery: 预发现流程，触发飞书卡片服务器发送选题方式选择卡片
        ├─ discovery: 从次幂数据 API 获取爆款选题列表 (15 篇)
        ├─ from-article: 从文章 URL 直接抓取内容
        └─ from-video: 从视频 URL 提取音频并转写文字
- [ ] Step 2: 推送选题列表到飞书 → ⛔ BLOCKING (等待用户回复序号)
- [ ] Step 3: IP 化改写 (repurpose) 并同步至飞书云文档（输出预览链接）
- [ ] Step 4: 等待用户基于飞书链接确认草稿 → ⛔ BLOCKING (等待确认指令)
- [ ] Step 5: 视觉生成 (visuals) 并推送图片到飞书预览 (+执行正文强力净化)
- [ ] Step 6: 自动发布 (post) 集成 CDP 注入及 2.35:1 封面确认逻辑
```

**关键理解**：这是一个线性流程，**飞书聊天窗口是用户唯一的审核和控制终端**。AI 必须确保每一个 [ACTION_REQUIRED] 节点都提供了足够的预览素材（链接或图片）。

**飞书卡片服务器**：`scripts/feishu/feishu-card-server.py` 提供基于卡片的交互式选题选择和状态通知，每 5 秒轮询一次飞书事件。启动方式：`python scripts/feishu/feishu-card-server.py` 或 `scripts/feishu/start_card_server.bat`。

---

## 2. 状态管理机制

### 2.1 状态文件

系统使用 `.workflow_state.json` 记录当前工作流状态，位置在工作目录根部。

**核心字段**：
| 字段 | 含义 | 示例值 |
|------|------|--------|
| `current_step` | 当前执行阶段 | `"waiting_for_topic_selection"` |
| `step` | 工作流步骤标记 | `"awaiting_source_selection"` |
| `selected_topic` | 用户选中的选题 | `{"id": "xxx", "title": "xxx"}` |
| `draft_file` | 草稿文件路径 | `"drafts/2024-01-15/topic-123.md"` |
| `industry` | 用户专属行业分类 | `"keji"` (科技) |
| `last_candidates` | 上次推荐的选题列表 | `[...]` |
| `candidates` | 完整候选列表 | `[...]` |
| `candidates_page_index` | 当前页码 | `1` |
| `candidates_page_size` | 每页显示数量 | `5` |
| `cimi_last_id` | 次幂 API 分页游标 | `"12345"` |
| `source_selection_pending` | 是否等待选题方式选择 | `true` |

### 2.2 ACTION_REQUIRED 协议

当输出包含 `[ACTION_REQUIRED]` 标记时，表示**需要用户决策**，此时必须：

1. **立即停止**当前执行流程
2. **生成预览文件**：调用飞书同步技能，将 Markdown 转换为云文档链接发送给用户。
3. **推送视觉素材**：将生成的封面图/插图预览发送到飞书聊天窗口。
4. **翻译原因**：将技术提示转换为用户能理解的中文说明，并展示确认/修改选项。
5. **等待回复**：不收到用户输入不继续

**为什么需要这个协议**：因为用户可能通过飞书、Telegram 等不同渠道与系统交互，AI 必须作为"翻译层"，将底层命令输出转换为用户友好的交互提示。

---

## 3. 操作指令清单 (API)

### 阶段一：发现素材 (Discovery & Ingestion)

#### 3.1 自动挖掘爆款文章

从微信公众号、小红书、抖音等平台抓取爆款内容。

```bash
python workflow_controller.py discovery [--keyword <序号或行业名>] [--refresh] [--last_id <游标>]
```

**参数说明**：
- `--keyword`: 行业分类序号（如"3"表示科技）或行业名称
- `--refresh`: 强制刷新获取最新（默认行为）
- `--last_id`: 分页游标，用于"换一批"功能

**执行逻辑**：
1. 检查是否已配置用户专属的行业分类（保存在 `.workflow_state.json`）
2. 如果没有配置，输出 `[ACTION_REQUIRED]` 等待用户选择行业
3. 调用次幂数据 API 获取该分类下的热门爆款文章
4. 输出推荐列表（通常 15 篇），每篇包含：标题、公众号、阅读量、点赞数、热度分

**行业分类示例**：科技、财经、美食、旅游、教育、健康、游戏、情感、职场等 45+ 分类

**用户后续操作**：用户回复选题序号（如"3"）进入改写阶段

**预期输出示例**：
```
=== 今日推荐 Top 15 爆款选题 === (数据来源：次幂)
1. [微信公众号 (次幂)] [AI  agent 爆发：2024 年最值得关注的 10 个方向](https://mp.weixin.qq.com/s/xxx)
   👤 某科技公众号 | 👁️ 阅读：10W+ | 👍 赞：5000 | 🔥 热度：9800
2. [微信公众号 (次幂)] [普通人如何抓住自媒体红利](https://mp.weixin.qq.com/s/yyy)
   👤 成长笔记 | 👁️ 阅读：8W+ | 👍 赞：3200 | 🔥 热度：8500
...
===================================
👉 请用户回复：包含 --id 对应你想二创的内容序号，或重新执行 discovery --keyword
```

#### 预发现流程 (pre_discovery)

```bash
python workflow_controller.py pre_discovery [--keyword <行业名>]
```

不实际获取选题，只设置状态标记，触发飞书卡服务器发送选择卡片。

#### 分页浏览 (next)

```bash
python workflow_controller.py next
```

浏览已缓存的选题列表下一页。

#### 3.2 从文章链接直接开始

已知具体文章 URL 时，直接抓取内容作为素材。

```bash
python workflow_controller.py from-article --url "<URL>"
```

**支持的 URL 类型**：
- 微信公众号文章链接 (`mp.weixin.qq.com/s/xxx`)
- 小红书笔记链接 (`xiaohongshu.com/explore/xxx`)
- 任意网页 URL（自动提取正文）

**执行逻辑**：
1. 调用 `url-reader-0.1.1` 技能提取文章正文
2. 如果文章来自公众号，优先使用次幂数据 API 作为兜底
3. 保存素材到临时目录，自动进入改写阶段

**预期输出示例**：
```
🚀 启动定向创作模式 (From Article)... 原始输入中探测到的 URL: https://mp.weixin.qq.com/s/xxx
📥 正在提取文章内容...
✅ 文章提取成功，文本长度：4500 字
⏳ 自动进入 repurpose 流程...
```

#### 3.3 从视频链接提取素材

录入抖音视频/B 站/YouTube 等短视频链接，自动提取语音转文字。

```bash
python workflow_controller.py from-video --url "<URL>"
```

**依赖配置**：需要配置 `SILI_FLOW_API_KEY` 用于语音识别

**执行逻辑**：
1. 检测视频平台类型（抖音优先支持）
2. 调用 `douyin-download-1.2.0` 下载视频并提取音频
3. 使用语音识别 API 转写为文字稿
4. 如果提取失败，降级使用视频标题/描述生成内容

**预期输出示例**：
```
🚀 启动定向视频创作模式 (From Video)... 原始输入中探测到的 URL: https://v.douyin.com/xxx
📥 正在下载视频并提取音频...
🎤 正在调用语音识别 API 转写文字...
✅ 文字稿提取成功，文本长度：2800 字
⏳ 自动进入 repurpose 流程...
```

---

### 阶段二：IP 化改写与内容生成 (Repurpose)

将选中的素材改写为：**短视频脚本**（适合口播） + **公众号长文**（带个人 IP 风格）。

```bash
python workflow_controller.py repurpose --id <素材 ID 或 URL> [--script-only] [--article-only]
```

**新增参数**：
- `--script-only`: 仅重写短视频脚本
- `--article-only`: 仅重写深度长文

**输出内容**：
| 文件 | 规格 | 用途 |
|------|------|------|
| 短视频脚本 | 分段落，每段约 60 秒口播时长 | 用于拍摄抖音/视频号 |
| 公众号长文 | 3000-5000 字，带金句、故事、观点 | 用于发布微信公众号 |

**改写策略**（为什么这样改写）：
- **去 AI 味**：避免机械式表达，增加口语化和个人风格
- **结构化**：开头吸引注意力，中间有逻辑递进，结尾有行动号召
- **金句密度**：每 300-500 字设置一个可传播的金句
- **故事化**：用具体案例替代抽象说教

**改写流程**：
1. 调用 `_extract_article_content()` 提取素材内容
2. 使用 WeWrite 引擎进行 IP 化改写
3. 生成短视频脚本和公众号长文
4. 同步到飞书云文档并推送预览链接

**输出目录**：`drafts/日期/素材 ID/`

**用户后续操作**：AI 会自动将长文同步到飞书知识库或云文档，用户点击链接审核。用户满意后在飞书回复"确认"或"满意"进入视觉生成阶段。

**预期输出示例**：
```
🧠 启动 [内容重塑引擎] 处理选题：[微信公众号 (次幂)] AI agent 爆发...
✅ 公众号原素材提取成功，文本长度：4500 字
⏳ 正在调用 LLM 进行 IP 化改写...
✅ 改写完成！

生成文件与预览：
✓ 飞书云文档预览链接：[点击审核文章草稿](https://feishu.cn/docx/xxx)
✓ 飞书知识库同步已完成

⚠️ [ACTION_REQUIRED] 请点击上方链接检查改写结果。确认满意后，请在飞书聊天窗口回复"确认"或"满意"，我将继续为您生成配图。
```

---

### 阶段三：视觉生成与自动发布 (Visuals & Post)

该阶段负责对长文进行配图处理，并同步发布到微信公众号。可以分步执行或一键执行。

#### 3.4 仅生成配图 (Visuals)

分析文章内容，自动生成封面图和文中插图，并将其路径插入到 Markdown 草稿中。

```bash
python workflow_controller.py visuals [--model seedream]
```

**执行逻辑**：
1. 视觉大脑分析：提取文章中的视觉锚点
2. 封面生成：生成符合公众号规格 (1280×544) 的封面图并置于文首
3. 插图生成：根据锚点内容生成图片并按 `![插图](路径)` 格式插入正文
4. **飞书推送**：将生成的封面和所有插图作为卡片发送给用户进行视觉审核。
5. 增强兼容：在 WSL 环境下自动处理 Windows 与 Linux 路径转换

#### 3.5 仅执行发布 (Post)

将已完成配图的 Markdown 文件推送到公众号平台。

```bash
python workflow_controller.py post [--method api|browser]
```

**发布方式**：
- `--method browser` (默认)：使用高级 CDP 驱动的浏览器自动化，支持**原生文件注入**、**封面 2.35:1 比例自动切换**以及**远程扫码登录**。
- `--method api`：使用微信开发接口，需配置 AppID。
  - **登录流程**：检测到未登录时自动截取公众号后台登录二维码，通过 `[FEISHU_IMAGE_REQUIRED]` 标记触发 OpenClaw 将二维码图片推送到飞书聊天窗口
  - **用户操作**：用户在飞书中收到二维码图片后扫码登录，脚本自动检测到登录成功后继续发布流程
  - **超时处理**：最长等待 5 分钟，超时后流程中断需重新执行

#### 3.6 一键配图并发布 (Publish)

依次自动执行 `visuals` 和 `post`。

```bash
python workflow_controller.py publish [--model seedream] [--method api|browser]
```

#### 生图模型选项

| 参数 | 模型 | 特点 |
|------|------|------|
| `--model wan` | Wan2.1（推荐，默认） | 效果最好，支持中文理解 |
| `--model seedream` | 火山引擎 Seedream | 速度快，风格偏写实 |
| `--model qwen` | 通义千问生图 | 对中文 prompt 友好 |
| `--model z` | Z-Image | 备选方案 |

#### 发布方式

| 参数 | 方式 | 前置条件 |
|------|------|----------|
| `--method browser`（默认） | 浏览器 CDP 模拟 | 具备**高精度比例切换 (2.35:1)** 和原生文件注入，更稳定 |
| `--method api` | API 自动推送 | 需配置 `WECHAT_APP_ID` / `WECHAT_SECRET` |

#### 生图规格

- **封面图**：1280×544 (16:9 宽屏)
- **文中插图**：16:9 比例，自动插入 Markdown 锚点位置
- **输出目录**：`covers/素材 ID/` 或按用户配置

**预期输出示例**：
```
🎨 启动 [视觉生成引擎]...
📊 分析文章内容，确定插图位置 (共 5 处需要配图)
🎨 正在生成封面图 (使用 Wan2.1 模型)...
✅ 封面图已发送至飞书窗口，请查看预览。
🎨 正在生成文中插图 (1/5)...
...
✅ 5 张插图已全部推送至飞书预览并完成正文强力净化。

📤 启动发布流程...
✅ 文章已推送到微信公众号草稿箱：https://mp.weixin.qq.com/xxx

🎉 完成！全流程结束
```

---

## 4. 辅助指令

### 查看当前任务状态

```bash
python workflow_controller.py status
```

显示当前工作流阶段、选中的选题、草稿文件位置等信息。

### 同步到飞书知识库

```bash
python workflow_controller.py sync --script <脚本路径> --article <长文路径>
```

将生成的脚本和长文同步到飞书知识库，便于团队协作。

### 飞书卡片服务器 (feishu-card-server.py)

飞书卡服务器提供基于卡片的交互式选题选择和状态通知。

**启动方式**：
```bash
# 后台运行
python feishu-card-server.py

# 或使用 batch 脚本
start_card_server.bat
```

**事件轮询**：服务器每 5 秒轮询一次飞书事件，检测用户交互（如选题选择、确认操作）。

**卡片类型**：
1. 选题方式选择卡片（预发现阶段）
2. 选题列表卡片（discovery 输出）
3. 状态通知卡片（各阶段进度）

**关键配置**：
- `FEISHU_APP_ID`: 飞书应用 ID
- `FEISHU_APP_SECRET`: 飞书应用密钥
- `FEISHU_CARD_TOKEN`: 飞书卡片机器人 token

---

## 5. 错误处理与边界情况

### 5.1 常见错误矩阵

| 错误标记 | 含义 | 原因 | 处理方式 |
|---------|------|------|---------|
| `[ACTION_REQUIRED]` | 需要用户决策 | 工作流到达决策点 | 停止执行，将选项翻译成中文发给用户，等待回复 |
| `未检测到 ffmpeg` | 视频处理依赖缺失 | 系统未安装 ffmpeg | 告知用户语音转文字功能失效，建议从标题/描述生成内容 |
| `.env 配置不完整` | 密钥缺失 | 首次使用未配置 | 引导用户运行 `setup` 命令或手动编辑 .env 文件 |
| `API 调用失败` | 网络或认证问题 | 密钥无效/网络超时 | 检查 .env 密钥配置，提示用户确认账户状态 |
| `素材抓取失败` | URL 不支持或反爬 | 目标站有反爬机制 | 尝试备用方案（如次幂 API 兜底），或让用户提供其他链接 |
| `生图失败` | 图像 API 异常 | 配额不足/服务不可用 | 自动重试一次，仍失败则建议用户更换模型 |
| `XiaohuGalleryError` | 小虎画廊超时 | Chrome 启动失败或渲染超时 | 检查 Chrome 配置，建议重启 |
| `WeWriteError` | WeWrite 改写失败 | API 配额不足或网络问题 | 自动重试，失败后降级到基础改写 |
| `SourceExtractionError` | 素材提取失败 | URL 不支持或反爬 | 尝试次幂 API 兜底 |

### 5.2 API 密钥配置清单

**核心必需**（缺少无法使用核心功能）：
- `OPENAI_API_KEY` — LLM 改写引擎
- `AUTHOR_IP_NAME` — 作者 IP 名称（用于生成个人风格）

**可选功能**（缺少时对应功能受限）：
- `CIMI_APP_ID` / `CIMI_APP_SECRET` — 次幂数据 API（爆款发现、公众号兜底提取）
- `SILI_FLOW_API_KEY` — 语音识别（视频 ASR 必需）
- `WECHAT_APP_ID` / `WECHAT_SECRET` — 微信公众号 API 发布
- `WAN_API_KEY` / `SEEDREAM_API_KEY` 等 — 各生图模型 API

### 5.3 首次使用引导 (飞书环境适配)

新用户通过飞书首次启动时，AI 必须主动执行以下引导流程：

1. **API Key 收集与配置**：
   - AI 主动检查 `.env` 文件（或 `setup` 命令输出）。
   - 若发现核心密钥（如 `OPENAI_API_KEY`）缺失，AI 必须在飞书请求用户提供，告知用户："为了启动自动化，我需要您的 OpenAI 密钥，请直接发送给我（示例：sk-xxxx）"。
   - 收到后，AI 负责调用 `write_to_file` 或相关工具更新服务器上的 `.env`。

2. **行业分类初始化**：
   - 第一次运行 `discovery` 时，AI 必须推送行业分类列表给用户。
   - 话术示例："由于是首次运行，我们需要确定您的内容赛道。请回复序号选择：1. 科技 2. 财经 3. 职场..."。
   - 用户回复后，AI 负责通过 `python workflow_controller.py discovery --keyword <行业>` 完成初始化并记录状态。

3. **依赖环境校验**：
   - AI 自行运行 `python workflow_controller.py setup`。
   - 如果发现服务器缺少 ffmpeg 等关键组件，AI 需告知用户："服务器环境监测中... 缺少音频解码组件，已记录，将通过非音频方式（如标题抓取）为您提供服务。"

---

## 6. 完整工作流示例

### 场景一：从零开始做一期内容

```
用户：帮我找今天的 AI 热点

AI: python workflow_controller.py discovery --keyword AI
    → 检查到未配置行业，输出 [ACTION_REQUIRED] 让用户选择分类
    → 用户回复"科技"
    → 输出 15 篇爆款文章列表

用户：3

AI: python workflow_controller.py repurpose --id 3
    → 抓取第 3 篇文章内容
    → 改写为短视频脚本 + 公众号长文
    → [ACTION_REQUIRED] 让用户确认草稿

用户：确认，写得很好

AI: python workflow_controller.py publish --model wan --method browser
    → 生成封面图 + 5 张文中插图
    → 推送到微信公众号草稿箱
    → 输出完成报告
```

### 场景二：已知文章链接，直接改写

```
用户：https://mp.weixin.qq.com/s/xxxx 这篇文章帮我改写

AI: python workflow_controller.py from-article --url "https://mp.weixin.qq.com/s/xxxx"
    → 抓取文章内容
    → 自动进入 repurpose 流程
    → 生成脚本 + 长文
    → [ACTION_REQUIRED] 等待确认

用户：确认

AI: python workflow_controller.py publish
    → 生成配图并发布
```

### 场景三：抖音视频转图文

```
用户：https://v.douyin.com/xxxx 这个视频帮我做成公众号文章

AI: python workflow_controller.py from-video --url "https://v.douyin.com/xxxx"
    → 调用 douyin-download-1.2.0 下载视频
    → 提取音频并转写为文字
    → 自动进入 repurpose 流程
    → 输出脚本 + 长文（如果 ASR 失败，降级使用标题生成）
```

---

## 7. 文件结构说明

```
self-media-auto/
├── SKILL.md                    # 本文件（技能入口）
├── workflow_controller.py       # 中央调度器（兼容层 wrapper）
├── README.md                   # 项目说明
├── .env                        # API 密钥配置（不提交到 git）
├── .env.example                # .env 配置模板
├── .workflow_state.json        # 工作流状态（运行时生成）
├── scripts/
│   ├── workflow/               # 工作流控制器
│   │   └── workflow_controller.py  # 实际的工作流调度器
│   ├── posting/                # 发布模块（公众号）
│   │   ├── wechat-article.ts  # Browser 模式发布
│   │   ├── wechat-api.ts      # API 模式发布
│   │   ├── wechat-extend-config.ts
│   │   ├── copy-to-clipboard.ts
│   │   ├── cdp.ts
│   │   ├── package.json        # npm 依赖配置
│   │   └── vendor/             # baoyu-md 渲染引擎
│   ├── formatting/            # 排版模块（Xiaohu）
│   │   ├── format.py          # 排版核心脚本
│   │   ├── html-sanitizer.ts  # 🔑 微信剪贴板格式修复
│   │   ├── themes/            # 30+ 主题文件
│   │   └── templates/          # gallery.html, preview.html
│   ├── feishu/                # 飞书集成模块
│   │   ├── feishu-card-server.py  # 卡片服务器
│   │   ├── send_feishu_card.py    # 卡片发送
│   │   ├── poll-card-event.py      # 事件轮询
│   │   ├── send_topics.py          # 选题发送
│   │   └── start_card_server.bat   # 启动脚本
│   ├── search/                 # 搜索模块
│   │   └── search_engine.py
│   ├── setup/                 # 安装脚本
│   │   ├── setup.bat
│   │   └── setup.ps1
│   ├── modules/               # 代码模块（被 import）
│   │   ├── config/            # 配置模块
│   │   │   └── wewrite_config.py
│   │   ├── integrations/      # 集成模块
│   │   │   ├── wechat_topic_fetcher.py
│   │   │   ├── wewrite_engine.py
│   │   │   └── xiaohu_formatter.py
│   │   ├── utils/             # 工具函数
│   │   │   └── logger_config.py
│   │   ├── wewrite/           # WeWrite 改写引擎
│   │   ├── url-reader-0.1.1/  # 网页内容提取工具
│   │   └── douyin-download-1.2.0/  # 抖音视频下载引擎
│   └── pyproject.toml         # Python 依赖配置
├── references/                 # 参考文档
│   ├── posting/
│   │   ├── article-posting.md
│   │   └── image-text-posting.md
│   ├── formatting/
│   │   └── themes-guide.md
│   └── prompts/
│       └── prompts_manager.json  # 提示词管理
├── assets/                     # 静态资源
├── drafts/                     # 改写草稿输出目录
├── logs/                       # 日志文件目录
├── tests/                      # 单元测试
└── .deprecated/                # 废弃但保留的旧模块
    ├── baoyu-article-illustrator/
    ├── baoyu-cover-image/
    └── huashu-proofreading/
```

---

## 8. 设计原则详解

### 8.1 为什么需要状态管理？

自媒体工作流是**长流程任务**，从发现热点到发布可能跨越多次用户交互。状态管理确保：
- 用户中断后可以从断点继续
- AI 知道当前应该执行哪一步
- 避免重复执行已完成的步骤

### 8.2 为什么需要用户确认？

关键决策点（选题选择、草稿确认）必须用户参与，因为：
- 选题决定了内容的方向和质量
- 改写结果需要符合用户的个人风格偏好
- 发布后无法轻易撤回

### 8.3 优雅降级策略

系统设计有多层兜底机制：
- url-reader 失败 → 次幂 API 兜底 → 生成模拟快照
- 视频 ASR 失败 → 使用标题/描述生成 → 提示用户功能受限
- API 发布失败 → 浏览器模式备用 → 提示手动发布
- 浏览器模式检测到未登录 → 自动截取二维码并通过飞书推送 → 等待用户扫码（最长 5 分钟）

---

## 9. 参考资源

- `scripts/posting/` — 公众号发布模块
- `scripts/formatting/` — Xiaohu 排版模块
- `references/` — 详细参考文档
- `douyin-download-1.2.0/` — 抖音视频下载与提取引擎
- `url-reader-0.1.1/` — 通用网页内容提取工具
- `wewrite/` — WeWrite 改写引擎

---

## 10. 飞书事件监听

**事件轮询机制**：
- 轮询间隔：5 秒
- 事件类型：卡片按钮点击、表单提交、消息回复
- 路由规则：根据 `event_type` 分发到不同处理函数

**关键配置**：
- `FEISHU_APP_ID`: 飞书应用 ID
- `FEISHU_APP_SECRET`: 飞书应用密钥
- `FEISHU_CARD_TOKEN`: 飞书卡片机器人 token

**事件处理流程**：
1. 轮询获取新事件
2. 解析 `event_type` 和 `content`
3. 根据事件类型触发对应工作流
   - 选题选择 → 更新 `.workflow_state.json`，进入 `repurpose` 流程
   - 草稿确认 → 进入 `visuals` 流程
   - 发布确认 → 进入 `post` 流程
4. 更新 `.workflow_state.json` 状态

**事件类型映射**：
| event_type | 处理函数 | 触发工作流 |
|------------|---------|-----------|
| `topic_selected` | `handle_topic_selection()` | 进入 repurpose |
| `draft_confirmed` | `handle_draft_confirm()` | 进入 visuals |
| `publish_confirmed` | `handle_publish_confirm()` | 进入 post |
