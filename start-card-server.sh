#!/bin/bash
cd /root/.openclaw/skills/self-media-auto
export PYTHONPATH=/root/.openclaw/skills/self-media-auto/scripts/modules
export FEISHU_WORKDIR=/root/.openclaw/skills/self-media-auto
exec /usr/bin/python3 scripts/feishu/feishu-card-server.py
