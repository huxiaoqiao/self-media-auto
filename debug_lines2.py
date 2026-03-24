#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

filename = r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py'

with open(filename, 'r', encoding='utf-8-sig', errors='replace') as f:
    lines = f.readlines()

# Debug specific lines
for i in [207, 208, 415, 416, 477, 478, 520, 521]:
    if i < len(lines):
        line = lines[i]
        triple_double = line.count('"""')
        triple_single = line.count("'''")
        print(f'Line {i+1}: dbl={triple_double}, sgl={triple_single}')
        print(f'  {repr(line[:80])}')
