# 视觉生成系统专用提示词库 (Visual System Prompts)

本文件集成了 baoyu-cover-image 和 baoyu-article-illustrator 的核心视觉逻辑，用于指导模型生成高质量、符合 IP 定位的配图。

## 核心设计原则 (Core Principles)
- **拒绝英文 (NO ENGLISH)**: 严禁在图片中出现任何英文字母或拉丁字符 (CRITICAL: NO LATIN LETTERS)。
- **中文优先 (CHINESE ONLY)**: 仅允许使用清晰的简体中文。
- **留白美学 (Whitespace)**: 保持 40-60% 的留白，构图要有“呼吸感”。
- **去真人化 (No Real Humans)**: 优先使用剪影、3D 符号、几何图形或扁平插画。
- **色彩一致性**: 同一篇文章的封面和插图必须使用相同的色系 (Palette)。

---

## 封面图生成模块 (Cover Image Module)
基于 baoyu-cover-image 的 5 维度设计。

### 1. 构图类型 (Type)
- **Conceptual (概念型)**: 适合深度长文。使用抽象几何体代表复杂观点（如：透明立方体代表透明度）。
- **Hero (主体型)**: 适合 IP 属性强的文章。中心放置一个精致的 3D 视觉锚点。
- **Minimal (极简型)**: 适合科技、思考类。大量留白 + 单一视觉符号。

### 2. 渲染风格建议 (Rendering)
- **Flat-Vector (扁平矢量)**: 干净、专业、适合科普。
- **3D Render (3D 渲染)**: 类 Apple/Notion 风格，材质要有光泽感，适合工具/AI 类。
- **Painterly (手绘感)**: 适合情感、生活方式类文章。

### 3. 给模型的生成指令 (Prompt to Model)
"你是一个顶尖的视觉设计师。请根据以下内容生成生图提示词：
内容：{{content}}
比例：2.35:1 (封面)
要求：
1. 风格采用 {{rendering}}。
2. 绝对严禁出现英文。
3. 必须包含文字：'{{title}}'，字体使用干净的黑体或圆体。
4. 构图：{{type}}，注重 whitespace 和 visual anchor。"

---

## 文章插图生成模块 (Article Illustrator Module)
基于 baoyu-article-illustrator 的 Type × Style 模型。

### 1. 插图类型 (Type)
- **Infographic (信息图)**: 核心观点可视化。使用简洁的层级结构。
- **Flowchart (流程图)**: 步骤描述可视化。使用箭头和圆角矩形。
- **Framework (架构图)**: 复杂系统可视化。使用模块化叠加风格。

### 2. 风格匹配 (Style)
- **Notion Style**: 黑白灰 + 单一缀色，极简干净。
- **Blueprint (蓝图风格)**: 深蓝底色 + 白色细线条，适合技术深度文章。
- **Warm (温暖风格)**: 柔和光影 + 低饱和度色彩。

### 3. 给模型的生成指令 (Prompt to Model)
"你是一个擅长信息可视化的专家。请为文章中的这一段落设计配图：
段落：{{paragraph}}
类型：{{type}}
要求：
1. 风格与封面保持一致 ({{style}})。
2. 严禁英文 (NO ENGLISH)。
3. 将段落中的核心逻辑转化为视觉符号：{{visual_logic}}。
4. 画面整洁，不要有复杂的背景。"
