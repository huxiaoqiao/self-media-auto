#!/usr/bin/env python3
import json, os

with open('.workflow_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

cands = state.get('last_candidates', [])
print('=== 关键验证 ===')
print('1. candidates 数量:', len(cands))
print('2. topic_context:', state.get('topic_context'))
print('3. draft_file:', state.get('draft_file'))

if cands:
    first = cands[0]
    print('4. 第一个候选 id 类型:', type(first.get('id')).__name__)
    print('5. 第一个候选 id:', str(first.get('id'))[:60])
    print('6. 第一个候选 source:', first.get('source', '无'))
    print('7. 第一个候选 title:', first.get('title', '无')[:30])
    
    id_val = str(first.get('id', ''))
    is_url = id_val.startswith('http')
    print('8. id 是 URL:', is_url, '(', id_val[:20], ')')
else:
    print('4-8: 无 candidates')
