import subprocess
import sys
import os

script_dir = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto"
os.chdir(script_dir)
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

# #10 Rabbit又行了 - 热度9175
args = [
    sys.executable, "send_feishu_card.py", "topic",
    "--title", "Rabbit又行了？油管大V改口，将发第二款AI硬件",
    "--data", "52782阅读 | 375点赞 | 热度9175",
    "--url", "https://mp.weixin.qq.com/s?__biz=MjM5OTQzMTAxOA==&mid=2450418285&idx=1&sn=3684a6cfa610d963949df58444e64c31",
    "--analysis", "AI硬件赛道，大V效应，热度持续攀升",
    "--id", "10"
]
subprocess.run(args, env=env)
