import os
import sys
import json
import subprocess

try:
    with open(".workflow_state.json", "r", encoding="utf-8") as f:
        state = json.load(f)

    html_file = state.get("html_file") or state.get("draft_file")
    cover_image = state.get("cover_image")
    title = state.get("topic_context", {}).get("title")
    category = state.get("content_category", "")

    import shutil
    bun_path = shutil.which("bun") or shutil.which("bun.exe")
    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    baoyu_dir = os.path.join(os.getcwd(), "baoyu-post-to-wechat")
    script = os.path.join(baoyu_dir, "scripts", "wechat-article.ts")

    THEMES = {"hardcore": "modern", "insight": "grace", "news": "default", "emotional": "grace", "risk": "modern", "tool": "simple", "growth": "simple"}
    wechat_theme = THEMES.get(category, os.environ.get("WECHAT_THEME", "default"))

    args = [bun_path, script] if bun_path else [npx_cmd, "-y", "bun", script]

    if str(html_file).endswith(".html"):
        args.extend(["--html", html_file])
    else:
        args.extend(["--markdown", html_file, "--theme", wechat_theme])

    if cover_image and os.path.exists(cover_image):
        args.extend(["--cover", os.path.abspath(cover_image)])
    if title:
        args.extend(["--title", title])

    print("Running command: " + " ".join(args))
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    for line in proc.stdout:
        print(line, end="")
    proc.wait()
    print("Return code:", proc.returncode)

except Exception as e:
    print("Error:", e)
