---
name: self-media-auto
description: "自媒体自动化工具 / IP爆款制造机。负责找热点、改写文案、自动配图并发布。当看到 [ACTION_REQUIRED] 时，AI 必须停下来把选项发给用户，等用户回复后再继续。"
---

# 自媒体自动化作业规范 (SKILL 指南)

你可以调用这个工具来完成自媒体全流程工作。请严格遵守以下操作协议：

## 1. 核心交互协议 (必备逻辑)

⚠️ **如何处理中断信号**：
在本系统中，状态由 `.workflow_state.json` 记录。如果在执行命令时，屏幕输出包含 `[ACTION_REQUIRED]`，说明系统遇到了需要用户做决定的“断点”。
- **AI 任务**：你必须立即停止当前执行，将提示中的**原因**和**选项**发给用户。
- **状态恢复**：等用户回复决策后，你根据回复内容构造正确的参数（如 `--id` 或 `--keyword`）重新运行命令。系统会自动接着上次的地方跑。

## 2. 环境与配置要求

- **运行环境**：
  - Windows 必须运行 `setup.bat` 初始化。
  - 以后执行任何操作都必须通过 `python workflow_controller.py <动作>`。
- **密钥配置**：
  运行 `python workflow_controller.py setup` 进行设置。所有密钥存在根目录的 `.env` 中。

## 3. 操作指令清单 (API)

### 阶段一：找素材 (Discovery & Ingestion)

**1. 自动挖掘爆款文章**
拉取公众号爆品。如果没有行业设置，会报 `[ACTION_REQUIRED]` 让用户选分类。
```bash
python workflow_controller.py discovery [--keyword <序号或行业名>]
```

**2. 从文章链接直接开始**
直接抓取公众号或网页链接内容作为素材。
```bash
python workflow_controller.py from-article --url "<URL>"
```

**3. 从视频链接提取素材**
录入抖音等短视频链接，自动提取语音转为文字。
```bash
python workflow_controller.py from-video --url "<URL>"
```

### 阶段二：IP 化改写与内容生成 (Repurpose)

将选中的素材改写为：一个适合口播的**短视频脚本**和一篇有个人风格的**公众号长文**。
```bash
python workflow_controller.py repurpose --id <素材ID或URL>
```
- **输出**：改好的文件存在 `drafts/日期/` 文件夹。
- **后续**：改完后会报 `[ACTION_REQUIRED]` 停下来让用户在 drafts 里检查文件。

### 阶段三：视觉生成与自动发布 (Publish)

对长文进行配图处理并同步微信。
```bash
python workflow_controller.py publish [--model wan] [--method api|browser]
```
- **生图逻辑**：系统会自动给文章做封面（1280*544）和插图（16:9），并把图片插入 Markdown 里的锚点。
- **发布逻辑**：默认优先使用 **API 方式**（需要配置公众号 AppID/Secret）自动推送到草稿箱。如果 API 失效，也可以切换回 `browser` 模式。

### 辅助指令

**查看当前任务状态**
```bash
python workflow_controller.py status
```

**同步到飞书知识库**
```bash
python workflow_controller.py sync --script <脚本路径> --article <长文路径>
```
