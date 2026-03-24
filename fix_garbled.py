#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix garbled docstrings in feishu-card-server.py"""
import re

filename = r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py'

with open(filename, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

fixed_lines = []
fix_count = 0

for i, line in enumerate(lines):
    original = line
    # Replace common garbled UTF-8/GBK sequences that produce invalid Python chars
    # These are telltale signs of the corruption
    garbled_patterns = [
        (r'[\u20ac\u00a3\u0080-\U0010ffff]+', '?'),  # Very high Unicode chars
    ]
    
    # Check if line has characters that would break Python parsing
    # Specifically, look for Private Use Area chars (U+E000-U+F8FF) which are never valid in Python source
    has_invalid = False
    for ch in line:
        code = ord(ch)
        # Private Use Area and other non-character code points
        if 0xE000 <= code <= 0xF8FF or (0x80 <= code <= 0x9F and '"' in line):
            has_invalid = True
            break
    
    if has_invalid and ('"""' in line or "'''" in line or '#' in line):
        # This is a docstring or comment with garbled text - replace with safe ASCII
        if '"""' in line or "'''" in line:
            # Preserve the triple quotes but replace content
            line = re.sub(r'"""[^"]*"""', '"""[FIXED]"""', line)
            line = re.sub(r"'''[^']*'''", "'''[FIXED]'''", line)
        else:
            # Comment line - replace entirely
            line = '# [FIXED COMMENT]\n'
        fix_count += 1
    fixed_lines.append(line)

print(f'Fixed {fix_count} lines')

with open(filename, 'w', encoding='utf-8-sig') as f:
    f.writelines(fixed_lines)

print('Written back.')
