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
  
  // 读取 HTML 并准备内容
  const htmlContent = readFileSync('/tmp/wechat-article-images-jZqBcI/temp-article.html', 'utf-8');
  const outputMatch = htmlContent.match(/<div id="output">([\s\S]*?)<\/div>/);
  let content = outputMatch ? outputMatch[1] : '';
  content = content.replace(/WECHATIMGPH_1/g, `${TUNNEL_URL}/article_img1.jpg`);
  content = content.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  content = content.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
  
  console.log('内容长度:', content.length);
  
  // 注入到 ProseMirror
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const prose = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror');
        if (!prose) return 'ProseMirror not found';
        
        prose.innerHTML = ${JSON.stringify(content)};
        
        // 触发 input 事件
        prose.dispatchEvent(new Event('input', { bubbles: true }));
        prose.dispatchEvent(new Event('change', { bubbles: true }));
        
        return 'INJECTED: ' + prose.innerHTML.length + ' chars';
      })()
    `
  }, { sessionId });
  
  console.log('注入结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 检查字数
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || 'not found'`,
  }, { sessionId });
  console.log('字数:', charCount.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
