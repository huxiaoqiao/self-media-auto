# -*- coding: utf-8 -*-
import json
import sys
sys.path.insert(0, '.')
from send_feishu_card import send_topic_list_card

# Load candidates from workflow state
with open('.workflow_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

candidates = state.get('last_candidates', [])[:5]  # Top 5

# Format topics for the card
topics = []
for i, c in enumerate(candidates):
    topics.append({
        'id': str(i + 1),
        'title': c.get('title', ''),
        'data': '阅读: {} | 赞: {} | 热度: {}'.format(
            c.get('comments', 0), c.get('likes', 0), c.get('score', 0)),
        'url': c.get('id', ''),
        'analysis': '{} | 评分: {}'.format(c.get('author', ''), c.get('score', 0))
    })

result = send_topic_list_card(topics, industry='AI')
print('Success!' if result else 'Failed!')
