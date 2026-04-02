import os
import io

in_file = 'baoyu-post-to-wechat/scripts/wechat-article.ts'
with open(in_file, 'rb') as f:
    text_bytes = f.read()

# Using 'replace' to safely decode UTF-8 where corruption occurred
text = text_bytes.decode('utf-8', errors='replace')
lines = text.split('\n')

for i in range(len(lines)):
    line = lines[i]
    if '' in line:
        if 'Cloudflare Tunnel' in line:
            lines[i] = "      throw new Error('[cdp] 远程连接失败，请检查 Cloudflare Tunnel 或 Windows Chrome 远程调试是否正常');"
        elif '[LOGIN_REQUIRED]' in line:
            lines[i] = "            console.log('\\n⚠️ [LOGIN_REQUIRED] 微信公众号需要登录');"
        elif '等待用户扫码登录' in line:
            lines[i] = "            console.log('\\n⏳ 等待用户扫码登录...（最长等待 5 分钟）\\n');"
        elif '通过 HTTP URL' in line and 'imageTunnelUrl && REMOTE_CDP_URL' in line:
            # this line accidentally concatenated the next line
            lines[i] = "      // 远程模式下：通过 HTTP URL 到 Chrome 下载图片到本地\n      if (imageTunnelUrl && REMOTE_CDP_URL) {"
        elif '文件检' in line and 'JSON.stringify(fileCheck)' in line:
            lines[i] = "          console.log('[wechat] 文件检查: ' + JSON.stringify(fileCheck));"
        elif '封面图下载成' in line and 'windowsLocalPath' in line:
            lines[i] = "            console.log('[wechat] 封面图下载成功: ' + windowsLocalPath);"
        elif 'el.textContent.includes(\'下一' in line:
            lines[i] = "              const nextBtn = btns.find(el => el.textContent.includes('下一页'));"
        elif '使用 innerHTML 直接注入内容' in line and 'injectedContent =' in line:
            # another merged line
            lines[i] = "      // 使用 innerHTML 直接注入内容（针对 WeChat 编辑器的 mock-iframe 结构）\n      const injectedContent = JSON.stringify(content);"

res = '\n'.join(lines)
with open('baoyu-post-to-wechat/scripts/wechat-article.ts', 'w', encoding='utf-8') as f:
    f.write(res)
print("Fix script applied.")
