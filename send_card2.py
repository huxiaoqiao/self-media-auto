import subprocess
import sys
import os

script_dir = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto"
os.chdir(script_dir)
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

# #6 微信官方接入龙虾接Claude Code - 热度12771
args = [
    sys.executable, "send_feishu_card.py", "topic",
    "--title", "微信官方接入龙虾，我顺手给接上了 Claude Code。已开源",
    "--data", "33973阅读 | 367点赞 | 热度12771",
    "--url", "https://mp.weixin.qq.com/s?__biz=MzA4NzgzMjA4MQ==&mid=2453481779&idx=1&sn=5ab1bd7301be1b33487d006ff81db003",
    "--analysis", "微信+AI+Claude Code开源玩法，热度爆发中",
    "--id", "6"
]
subprocess.run(args, env=env)
