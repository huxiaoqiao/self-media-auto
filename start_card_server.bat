@echo off
chcp 65001 >nul
cd /d C:\Users\Administrator\.openclaw\skills\self-media-auto
start /b python -X utf8 feishu-card-server.py
exit
