import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';
import { readFileSync } from 'fs';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';
const TUNNEL_URL = 'https://critics-mild-valley-supporting.trycloudflare.com';

async function test() {
  console.log('1. 连接 CDP...');
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
  
  // 注入到 ProseMirror
  console.log('2. 注入内容到 ProseMirror...');
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const prose = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror');
        if (!prose) return 'ProseMirror not found';
        prose.innerHTML = ${JSON.stringify(content)};
        prose.dispatchEvent(new Event('input', { bubbles: true }));
        prose.dispatchEvent(new Event('change', { bubbles: true }));
        return 'OK: ' + prose.innerHTML.length;
      })()
    `
  }, { sessionId });
  console.log('   结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 检查字数
  console.log('3. 检查字数...');
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || '0'`,
  }, { sessionId });
  console.log('   字数:', charCount.result.value);
  
  // 点击保存草稿
  console.log('4. 点击保存草稿...');
  const saveResult = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const all = document.querySelectorAll('*');
        for (const el of all) {
          if (el.textContent?.trim() === '保存为草稿' && el.offsetParent !== null) {
            el.click();
            return 'SAVED';
          }
        }
        return 'NOT FOUND';
      })()
    `
  }, { sessionId });
  console.log('   结果:', saveResult.result.value);
  
  await new Promise(r => setTimeout(r, 5000));
  
  // 检查保存状态
  console.log('5. 检查保存状态...');
  const saved = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.includes('已保存') ? 'SUCCESS' : 'PENDING'`,
  }, { sessionId });
  console.log('   状态:', saved.result.value);
  
  await cdp.close();
  console.log('✅ 完成');
}

test().catch(e => console.error('错误:', e.message));
