import subprocess
import sys
import os

script_dir = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto"
os.chdir(script_dir)

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

args = [
    sys.executable, "send_feishu_card.py", "topic",
    "--title", "腾讯上线 ima skill，知识管理终于可以全自动了",
    "--data", "47738阅读 | 193点赞 | 热度13024",
    "--url", "https://mp.weixin.qq.com/s?__biz=MzU4NTE1Mjg4MA==&mid=2247498110&idx=1&sn=46652ca78e67a74f2eb5f84d2157982f",
    "--analysis", "AI知识管理赛道，腾讯亲自下场，全自动时代开启",
    "--id", "7"
]

result = subprocess.run(args, env=env)
sys.exit(result.returncode)
