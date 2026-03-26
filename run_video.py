#!/usr/bin/env python3
import os
os.chdir(r"C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto")

from dotenv import load_dotenv
load_dotenv()

print('STEP1')
import sys
print('STEP2')
sys.path.insert(0, '.')
print('STEP3')
import workflow_controller
print('STEP4')
ctrl = workflow_controller.SelfMediaController()
print('STEP5')
result = ctrl._extract_video_content('https://v.douyin.com/h41Bt2APAhw/')
print('STEP6 - result:', result[:100] if result else 'None')
