# 飞书知识库双向联动 (Knowledge Base Sync)

## 1. 系统定位与价值

本模块负责将 **IP 爆款制造机** 的生产成果（包括爆款脚本与深度长文）无缝同步至企业级飞书云空间。通过这种联动，团队可以在云端进行二次协作、素材沉淀及知识管理。

## 2. 自动化同步逻辑

当流水线进入 `repurpose` 阶段并产出 MD 文件后，控制器的状态机将支持通过 `sync` 指令将本地资产上链。

### 核心流转步骤：
1. **资产探查**：定位 `drafts/` 目录下由状态机生成的最新资产。
2. **云空间初始化**：自动在飞书根目录维持「自媒体内容/YYYY-MM-DD」的树状结构。
3. **原子文档创建**：利用 `feishu-skills` 工具链创建高度可读的云文档，并注入生成的时间戳。

## 3. 命令行手动触发 (高级联动)

如果需要对特定任务进行追溯同步，可以使用以下标准指令：

```bash
# 1. 确认项目根目录下的任务成果
ls drafts/$(date +%Y-%m-%d)/

# 2. 执行双向同步 (使用隔离环境解释器)
# Windows:
.\.venv\Scripts\python workflow_controller.py sync --script drafts/YYYY-MM-DD/script.md --article drafts/YYYY-MM-DD/article.md

# Linux/macOS:
./.venv/bin/python workflow_controller.py sync --script drafts/YYYY-MM-DD/script.md --article drafts/YYYY-MM-DD/article.md
```

## 4. 自动化集成逻辑 (Commander 视角)

Agent 在响应用户「同步飞书」请求时，应遵循以下算法：
- **查**: 获取 `state.json` 中最后一次成功重塑的文件路径。
- **推**: 调用 `workflow_controller.py sync` 执行原子同步操作。
- **回**: 将飞书返回的分布式文档链接完整展示给用户。

## 5. 云空间结构规范

```text
飞书云空间/
└── 自媒体内容/ (Root Folder)
    └── 2026-03-17/ (Date Context)
        ├── 🎬 爆款脚本_HHMM (Smart Doc)
        └── 📝 深度长文_HHMM (Smart Doc)
```

## 6. 注意事项

1. **授权确认**：确保飞书机器人已获得对应文件夹的「可编辑」权限。
2. **环境一致性**：同步操作依赖 `.env` 中的飞书应用凭据。
3. **原子性**：同步过程会自动去重，避免重复创建同名文档。
