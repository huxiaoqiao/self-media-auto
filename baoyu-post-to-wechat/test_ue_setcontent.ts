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
  
  // 使用 UEditor API 设置内容
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        try {
          const UE = window.UE;
          if (!UE) return 'UE not found';
          
          // 尝试获取编辑器实例
          const editors = UE.instants;
          if (editors && editors.length > 0) {
            const editor = editors[0];
            if (editor && editor.setContent) {
              editor.setContent(${JSON.stringify(content)});
              return 'setContent called successfully';
            }
          }
          
          // 尝试直接访问
          if (UE.getEditor) {
            const editor = UE.getEditor('ueditor_0');
            if (editor) {
              editor.setContent(${JSON.stringify(content)});
              return 'getEditor + setContent worked';
            }
          }
          
          return 'Could not find editor API';
        } catch(e) {
          return 'Error: ' + e.message;
        }
      })()
    `
  }, { sessionId });
  
  console.log('UE API 结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 检查字数
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || 'not found'`,
  }, { sessionId });
  console.log('字数:', charCount.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
