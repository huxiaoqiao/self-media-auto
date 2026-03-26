#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
sys.path.insert(0, '.')
from send_feishu_card import send_topic_list_card

with open('.workflow_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

candidates = state.get('last_candidates', [])
industry = state.get('industry', 'AI')

# Take top 5
topics = []
for i, c in enumerate(candidates[:5]):
    topics.append({
        'id': str(i + 1),
        'title': c.get('title', ''),
        'likes': c.get('likes', 0),
        'comments': c.get('comments', 0),
        'author': c.get('author', ''),
        'score': c.get('score', 0),
        'url': c.get('id', ''),
        'analysis': f"Author: {c.get('author', 'Unknown')} | Score: {c.get('score', 0)}"
    })

send_topic_list_card(topics, industry=industry.upper())
