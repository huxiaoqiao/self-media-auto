import os
import json

file_path = r'c:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\workflow_controller.py'

# 核心：完全动态化、解耦的 analyze_visuals 函数
new_method = """    def analyze_visuals(self, article_content, category="insight"):
        import httpx
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key: return None
        
        v_config = self.load_visual_config()
        # 准则和风格完全对齐 prompts_manager.json
        rules_text = "\\n".join([f"- {r}" for r in v_config.get('base_principles', [])])
        style_match = v_config.get('style_matching', {}).get(category, {
            "rendering": "3d-render", "palette": "elegant", "mood": "balanced"
        })

        # 视觉导演指令：动态拼装，拒绝硬编码
        sys_p = f\"\"\"你是一个视觉分析专家。请为分类为 '{category}' 的自媒体文章规划视觉方案。

【核心设计红线】：
{rules_text}

【视觉风格指导 (基于分类匹配)】：
- 渲染方案: {style_match.get('rendering')} | 色彩体系: {style_match.get('palette')} | 情绪基调: {style_match.get('mood')}

任务：规划 1 张封面 (2.35:1) 和 2-3 张插图。提示词必须是全中文。

输出 JSON 格式要求:
{{
  "cover": {{ "type": "hero/minimal", "prompt": "全中文生图词", "rendering": "{style_match.get('rendering')}" }},
  "illustrations": [ {{ "prompt": "中文插图词", "pos": "对应段落" }} ]
}}\"\"\"
        
        try:
            resp = httpx.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat", 
                    "messages": [
                        {"role": "system", "content": sys_p},
                        {"role": "user", "content": f"内容：{article_content[:3000]}"}
                    ], 
                    "response_format": {"type": "json_object"}}, 
                timeout=60)
            return json.loads(resp.json()["choices"][0]["message"]["content"])
        except Exception as e: 
            print(f"⚠️ 视觉分析异常: {e}")
            return None
"""

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 查找 analyze_visuals 的范围
start_line = -1
end_line = -1

for i, line in enumerate(lines):
    if 'def analyze_visuals(self, article_content, category="insight"):' in line:
        start_line = i
    if start_line != -1 and 'def post_to_wechat(self,' in line:
        end_line = i
        break

if start_line != -1 and end_line != -1:
    # 替换整个函数
    lines[start_line:end_line] = [new_method + "\n"]
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("REPLACE_SUCCESS")
else:
    print(f"FAILED: start={start_line}, end={end_line}")
