#!/bin/bash
cd /root/.openclaw/skills/self-media-auto
pkill -f feishu-card-server.py 2>/dev/null
sleep 1
export PYTHONPATH=/root/.openclaw/skills/self-media-auto/scripts/modules:$PYTHONPATH
nohup python3 scripts/feishu/feishu-card-server.py > /tmp/card_server_new.log 2>&1 &
echo "Card server restarted"
sleep 2
ps aux | grep feishu-card-server | grep -v grep
