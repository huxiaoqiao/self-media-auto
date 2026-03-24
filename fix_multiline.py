#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix corrupted multi-line docstrings in feishu-card-server.py"""
import re

filename = r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py'

with open(filename, 'r', encoding='utf-8-sig', errors='replace') as f:
    content = f.read()

lines = content.split('\n')

# Find all triple-quote starts and ends
# Strategy: scan line by line, when we see """, record start, find end
i = 0
fixed_lines = []
in_string = False
string_start = -1
string_type = None  # '"""' or "'''"

while i < len(lines):
    line = lines[i]
    
    if not in_string:
        # Look for start of triple-quote string
        if '"""' in line:
            in_string = True
            string_type = '"""'
            string_start = i
            # Check if it's single-line
            parts = line.split('"""')
            # Count occurrences of """
            count = line.count('"""')
            if count >= 2:
                # Single-line string
                # Replace the entire string
                new_line = re.sub(r'"""[^"]*"""', '"""[FIXED]"""', line)
                if new_line == line:
                    new_line = re.sub(r"'''[^']*'''", "'''[FIXED]'''", new_line)
                fixed_lines.append(new_line)
                in_string = False
            else:
                # Multi-line starts - will find end
                # Replace this line's content before """
                before, sep, after = line.partition('"""')
                fixed_lines.append(before + '"""[FIXED CONTENT]')
        elif "'''" in line:
            in_string = True
            string_type = "'''"
            string_start = i
            count = line.count("'''")
            if count >= 2:
                new_line = re.sub(r"'''[^']*'''", "'''[FIXED]'''", line)
                fixed_lines.append(new_line)
                in_string = False
            else:
                before, sep, after = line.partition("'''")
                fixed_lines.append(before + "'''[FIXED CONTENT]")
        else:
            fixed_lines.append(line)
    else:
        # We're inside a multi-line string - find the end
        if string_type in line:
            # Found the end
            after = line.split(string_type, 1)[1]
            fixed_lines.append(after)
            in_string = False
        # else: skip this line (it's inside the string)
    
    i += 1

fixed_content = '\n'.join(fixed_lines)

# Write back
with open(filename, 'w', encoding='utf-8-sig') as f:
    f.write(fixed_content)

print('Done. Checking...')

# Verify
import ast
try:
    ast.parse(fixed_content)
    print('SUCCESS: File parses correctly!')
except SyntaxError as e:
    print(f'Still has error at line {e.lineno}: {e.msg}')
    # Show context
    for j in range(max(0, e.lineno-2), min(len(fixed_lines), e.lineno+1)):
        print(f'  {j+1}: {repr(fixed_lines[j])[:80]}')
