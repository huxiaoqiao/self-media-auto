import subprocess
import sys
import os

script_dir = r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto"
os.chdir(script_dir)
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

# #5 利好国产，远洋捕捞... - 热度10944
args = [
    sys.executable, "send_feishu_card.py", "topic",
    "--title", "利好国产，远洋捕捞：超微创始人被捕，走私25亿美元英伟达GPU",
    "--data", "61440阅读 | 51点赞 | 热度10944",
    "--url", "http://mp.weixin.qq.com/s?__biz=MzYyMTI5MjIyMA==&mid=2247487669&idx=1&sn=2e95012716ccd0ff29e50bf2fa038825",
    "--analysis", "科技财经+国际事件，话题性强，争议度高",
    "--id", "5"
]
subprocess.run(args, env=env)
