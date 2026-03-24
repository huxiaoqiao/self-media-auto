import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';
import { readFileSync } from 'fs';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/6DBDC78052F78FAD642B446CF20BE773';
const TUNNEL_URL = 'https://critics-mild-valley-supporting.trycloudflare.com';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '6DBDC78052F78FAD642B446CF20BE773', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 直接注入内容
  console.log('2. 加载 HTML 内容...');
  const html = readFileSync('C:\Users\Administrator\smb-share/temp-article.remote.html', 'utf-8');
  const outputMatch = html.match(/<div id="output">([\s\S]*?)<\/div>/);
  let content = outputMatch ? outputMatch[1] : '';
  content = content.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  content = content.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
  
  console.log('3. 注入到编辑器...');
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const prose = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror') || document.querySelector('.ProseMirror');
        if (!prose) return 'ProseMirror not found';
        prose.innerHTML = arguments[0];
        prose.dispatchEvent(new Event('input', { bubbles: true }));
        return 'OK: ' + prose.innerHTML.length;
      })(${JSON.stringify(content)})
    `
  }, { sessionId });
  console.log('   结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 检查字�?  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || '0'`,
  }, { sessionId });
  console.log('4. 字数:', charCount.result.value);
  
  // 保存草稿
  console.log('5. 保存草稿...');
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const all = document.querySelectorAll('*');
        for (const el of all) {
          if (el.textContent?.trim() === '保存为草�? && el.offsetParent !== null) {
            el.click();
            return 'SAVED';
          }
        }
        return 'NOT FOUND';
      })()
    `
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 5000));
  
  // 检查保存状�?  const saved = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.includes('已保�?) ? 'SUCCESS' : 'PENDING'`,
  }, { sessionId });
  console.log('6. 保存状�?', saved.result.value);
  
  await cdp.close();
  console.log('�?完成');
}

test().catch(e => console.error('错误:', e.message));
