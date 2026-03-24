#!/usr/bin/env python3
# -*- coding: utf-8 -*-
with open(r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py', 'r', encoding='utf-8-sig') as f:
    content = f.read()

lines = content.split('\n')
# Look for lines with mojibake (garbled UTF-8/GBK bytes)
corrupted = []
for i, line in enumerate(lines):
    try:
        line.encode('gbk')
    except UnicodeEncodeError:
        corrupted.append((i+1, line[:100]))

with open(r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\corrupt_report.txt', 'w', encoding='utf-8') as out:
    out.write(f'Corrupted lines: {len(corrupted)}\n')
    for ln, text in corrupted[:50]:
        out.write(f'Line {ln}: {repr(text)}\n')
print('Done, check corrupt_report.txt')
