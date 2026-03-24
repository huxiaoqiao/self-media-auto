import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';
import { readFileSync } from 'fs';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';
const TUNNEL_URL = 'https://critics-mild-valley-supporting.trycloudflare.com';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 读取 HTML 并准备纯文本内容
  const htmlContent = readFileSync('/tmp/wechat-article-images-jZqBcI/temp-article.html', 'utf-8');
  const outputMatch = htmlContent.match(/<div id="output">([\s\S]*?)<\/div>/);
  let content = outputMatch ? outputMatch[1] : '';
  
  // 转换为纯文本
  content = content.replace(/<[^>]+>/g, '\n').replace(/\n+/g, '\n').trim();
  content = content.replace(/WECHATIMGPH_1/g, '[图片]');
  
  console.log('纯文本长度:', content.length);
  
  // 使用 PowerShell 设置剪贴板
  console.log('设置 Windows 剪贴板...');
  const setClipboard = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const psScript = \`Set-Clipboard -Value ${JSON.stringify(content)}\`;
        // 注意：这段代码在浏览器上下文中无法直接执行 PowerShell
        // 需要通过其他方式
        return 'Need to use PowerShell outside browser context';
      })()
    `
  }, { sessionId });
  console.log('剪贴板设置:', setClipboard.result.value);
  
  await cdp.close();
  console.log('需要使用外部 PowerShell 来设置剪贴板');
}

test().catch(e => console.error('错误:', e.message));
