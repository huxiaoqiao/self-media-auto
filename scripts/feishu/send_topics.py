import json, sys
sys.path.insert(0, '.')
from send_feishu_card import get_token, send_card, build_topic_list_card

topics = [
    {
        "title": "微信原生支持各种 OpenClaw 龙虾接入，附教程",
        "author": "特工宇宙",
        "score": "3230",
        "data": "阅读: 11611 | 赞: 67",
        "id": "http://mp.weixin.qq.com/s?__biz=MzYyMTY1NDA0Nw==&mid=2247515925&idx=1&sn=a81c761213e7c47f03bfd5e3b3e2ee92&chksm=fe33415d24af945ab1f5f29a7aefd3729631255e57f3b525be2a550106ccb6c87d684cf366d5&scene=126&sessionid=0#rd",
        "guid": "topic_001",
        "analysis": "微信内置OpenClaw，里程碑事件，教程实操性强"
    },
    {
        "title": "只用一个Skills，我把OpenClaw打造成了投资顾问",
        "author": "程序猿玩AI",
        "score": "6856",
        "data": "阅读: 15120 | 赞: 175",
        "id": "https://mp.weixin.qq.com/s?__biz=Mzk0MjYzMDUzMg==&mid=2247495613&idx=1&sn=9750e70adcd392c1c4d26267bdc4e0d9&chksm=c3e720df566eadd890479a0cb2c9c638a3bf4fc09b591a1b6e28793f501d29b862b43e86451d&scene=0&xtrack=1#rd",
        "guid": "topic_002",
        "analysis": "Skills实操教程，投资场景垂直，干货足"
    },
    {
        "title": "宇树科技：史上最奇怪的IPO公司",
        "author": "硅基观察Pro",
        "score": "8377",
        "data": "阅读: 42378 | 赞: 130",
        "id": "https://mp.weixin.qq.com/s?__biz=MzkyNTY1MjE2OA==&mid=2247493493&idx=1&sn=3657974e1694cc05e531bb01bb0de6af&chksm=c03b4a5239d4ace32cdf5112e966494b24bbd61f4b401534cef216fa95e5278b090f62fb2a9d&scene=0&xtrack=1#rd",
        "guid": "topic_003",
        "analysis": "宇树IPO，独特叙事角度，财经圈层传播强"
    },
    {
        "title": "利好国产！超微创始人被捕：向中国走私25亿美元GPU，最高30年刑期",
        "author": "算力百科",
        "score": "10944",
        "data": "阅读: 61440 | 赞: 65",
        "id": "http://mp.weixin.qq.com/s?__biz=MzYyMTI5MjIyMA==&mid=2247487669&idx=1&sn=2e95012716ccd0ff29e50bf2fa038825&chksm=fe037bf586b8a940e3f457c1b7a4a0a3f21d5e3842b4abc9f6e8653a27c3d16f95af24075233&scene=126&sessionid=0#rd",
        "guid": "topic_004",
        "analysis": "GPU走私大案，戏剧性叙事，舆情热度高"
    },
    {
        "title": "110万美元悬赏！AMD发起全球战书：谁能打破DeepSeek与Kimi的推理速度极限？",
        "author": "AI科技大本营",
        "score": "5352",
        "data": "阅读: 34747 | 赞: 24",
        "id": "https://mp.weixin.qq.com/s?__biz=Mzg4NDQwNTI0OQ==&mid=2247589081&idx=1&sn=e06a58ce15c0ea992b42d6e6846fd197&chksm=ce68abab53f0a451ce0ff91c9157a3660868fc1715156ce16cecab4f570d4c48f169409c6485&scene=0&xtrack=1#rd",
        "guid": "topic_005",
        "analysis": "AMD悬赏挑战DeepSeek/Kimi，话题性强"
    }
]

with open('temp_topics.json', 'w', encoding='utf-8') as f:
    json.dump(topics, f, ensure_ascii=False)

token = get_token()
card = build_topic_list_card(topics, 'AI')
send_card(token, 'ou_2da8e0f846c19c8fabebd6c6d82a8d6d', card)
print('Card sent successfully')
