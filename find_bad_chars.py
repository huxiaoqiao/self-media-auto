#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find lines with invalid Python characters in string literals"""
import ast
import sys
import io

filename = r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py'

with open(filename, 'r', encoding='utf-8-sig') as f:
    content = f.read()

# Try to parse - collect errors
try:
    ast.parse(content)
    print("OK - file parses fine!")
except SyntaxError as e:
    print(f"SyntaxError at line {e.lineno}: {e.msg}")
    print(f"Text: {repr(e.text)[:100]}")
    
    # Show context around error
    lines = content.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
        marker = ">>> " if i == e.lineno - 1 else "    "
        print(f"{marker}{i+1}: {repr(lines[i])[:80]}")
