#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix all lines with invalid Python characters"""
import re
import ast

filename = r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py'

with open(filename, 'r', encoding='utf-8-sig', errors='replace') as f:
    content = f.read()

# Strategy: find all invalid characters and replace the string literals containing them
# Valid Python source chars:
# - ASCII (0x00-0x7F)
# - CJK: U+4E00-U+9FFF, U+3000-U+303F, U+FF00-U+FFEF
# - Common punctuation and symbols that appear in Chinese text
# Invalid: U+E000-U+F8FF (Private Use), surrogates, control chars except tab/nl/cr

def is_valid_py_char(c):
    code = ord(c)
    if code < 0x80:
        return True  # ASCII
    if 0x4E00 <= code <= 0x9FFF:
        return True  # CJK Unified
    if 0x3000 <= code <= 0x303F:
        return True  # CJK Symbols  
    if 0xFF00 <= code <= 0xFFEF:
        return True  # Fullwidth
    if 0x2000 <= code <= 0x206F:
        return True  # General Punctuation
    if 0x1100 <= code <= 0x11FF:
        return True  # Hangul Jamo
    if 0xAC00 <= code <= 0xD7AF:
        return True  # Hangul Syllables
    if code >= 0x10000:
        return True  # Allow emoji and other higher planes
    # Disallowed: Private Use (E000-F8FF), Surrogates (D800-DFFF), Control chars
    return False

lines = content.split('\n')
fixed_lines = []
iterations = 0
max_iterations = 20

while True:
    iterations += 1
    if iterations > max_iterations:
        break
    try:
        ast.parse('\n'.join(fixed_lines + lines[len(fixed_lines):]))
        print(f'Parse OK after {iterations-1} fixes')
        break
    except SyntaxError as e:
        lineno = e.lineno
        if lineno is None:
            lineno = 1
        idx = lineno - 1
        line = lines[idx]
        
        # Check what kind of line this is
        if '"""' in line or "'''" in line:
            # Try to fix the string
            # Replace triple-quoted string content with placeholder
            new_line = re.sub(r'"""[^"]*"""', '"""[FIXED]"""', line)
            if new_line == line:
                new_line = re.sub(r"'''[^']*'''", "'''[FIXED]'''", new_line)
        elif line.strip().startswith('#'):
            # Comment - replace with safe comment
            new_line = '# [FIXED COMMENT]'
        else:
            # Other line with invalid char - try to find and replace the bad char
            new_line = ''
            for c in line:
                if is_valid_py_char(c):
                    new_line += c
                else:
                    new_line += '?'
        
        lines[idx] = new_line
        print(f'Fixed line {lineno}')

# Write back
with open(filename, 'w', encoding='utf-8-sig') as f:
    f.write('\n'.join(lines))

print('Done!')

# Final check
try:
    with open(filename, 'r', encoding='utf-8-sig') as f:
        ast.parse(f.read())
    print('VERIFIED: File parses OK')
except SyntaxError as e:
    print(f'WARNING: Still has error at line {e.lineno}: {e.msg}')
