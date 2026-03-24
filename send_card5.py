import subprocess
import sys
import os

script_dir = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto"
os.chdir(script_dir)
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

# #3 宇树科技IPO - 热度7319
args = [
    sys.executable, "send_feishu_card.py", "topic",
    "--title", "宇树科技：史上最奇怪的IPO公司",
    "--data", "36476阅读 | 103点赞 | 热度7319",
    "--url", "https://mp.weixin.qq.com/s?__biz=MzkyNTY1MjE2OA==&mid=2247493493&idx=1&sn=3657974e1694cc05e531bb01bb0de6af",
    "--analysis", "机器人IPO赛道，独特视角，财经爆款潜质",
    "--id", "3"
]
subprocess.run(args, env=env)
