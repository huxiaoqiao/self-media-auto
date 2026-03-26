#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from send_feishu_card import send_url_preview_card

# Video content we already extracted
video_title = "兜里没有 100 万，哥们劝你别装 OpenClaw"
video_url = "https://v.douyin.com/h41Bt2APAhw/"
video_author = "抖音用户"

# Full transcript (abbreviated for card - use first 500 chars)
transcript = """🎼open cloud很强，但我劝你真别跟风装了，甚至可以说99.99%的人都犯不着去折腾open cloud。当然长线学习是没错的。如果看完视频，大家还想试试，我们也在后面给了大家一些实用的建议。首先毫不夸张的说，open cloud是今年目前为止最火的AI产品，只要把它装在电脑上或者部署到云端，咱在聊天软件里动动嘴皮子，这个AI助手就能帮你完成任务。当然，前提是大大小小权限都给到位了。又因为clo这个单词有小龙虾钳子的意思。所以。又被大伙们戏称为小龙虾，网上各种服务也满天飞，只要花上上百元就能找人来帮你装上最新最前沿最炫酷的open成为一个云上养虾人。光是上门小龙虾安装一次收费500元，已经有人号称几天赚到了20多万。甚至腾讯直接在深圳搞了个线下活动，免费帮你装寄龙虾，直接火到超出了小马哥的想象，属于是一代人有一代人的鸡蛋要领了。这一切看起来是个蛮不错的生意。但是我还是想说，求求各位别再花那个愿枉钱找人代装。🎼open了。说句大实话，如果你连open cloud怎么安装都搞不明白，那花钱找人袋装，纯属是赶着当韭菜。当然，咱们不是要否定open claw这个项目本身，相反我觉得它很棒，甚至可以说它是今年最让我激动的开源项目之一。但是如果你想着装了龙虾，就能立马帮你干活，那你只是在给自己挖坑埋雷。有没有一种可能，你装不上open那是open在保护你。..."""

summary = f"""【视频核心观点】
1. OpenClaw（小龙虾）虽火但门槛极高，99.99%的人没必要跟风安装
2. 花500元找人代装纯属割韭菜，安装只是万里长征第一步
3. 安全问题突出：超过10%的skills插件都有问题
4. 成本惊人：每次使用都在燃烧API费用
5. 建议：花周末时间亲自探索，别急着当韭菜

📝 文案长度: {len(transcript)}字"""

send_url_preview_card(
    title=video_title,
    author=video_author,
    source="抖音短视频",
    summary=summary,
    url=video_url,
    content_type="video",
    extra_info="点击下方按钮确认是否开始IP化改写"
)
