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
  
  // 读取 HTML 文件
  const htmlContent = readFileSync('/tmp/wechat-article-images-jZqBcI/temp-article.html', 'utf-8');
  
  // 提取 #output 中的内容
  const outputMatch = htmlContent.match(/<div id="output">([\s\S]*?)<\/div>/);
  let content = outputMatch ? outputMatch[1] : '';
  
  // 替换图片占位符
  content = content.replace(/WECHATIMGPH_1/g, `${TUNNEL_URL}/article_img1.jpg`);
  
  // 移除script和style标签
  content = content.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  content = content.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
  
  console.log('注入内容长度:', content.length);
  
  // 直接注入到编辑器
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('#ueditor_0');
        if (editor) {
          editor.innerHTML = ${JSON.stringify(content)};
          return 'INJECTED: ' + editor.innerHTML.length + ' chars';
        }
        return 'EDITOR NOT FOUND';
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  
  console.log('注入结果:', result.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
