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
  
  // 直接注入并触发事件
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('#ueditor_0');
        if (!editor) return 'EDITOR NOT FOUND';
        
        // 设置内容
        editor.innerHTML = ${JSON.stringify(content)};
        
        // 触发 input 事件更新编辑器状态
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.dispatchEvent(new Event('change', { bubbles: true }));
        
        // 尝试触发内部的更新机制
        const evt = new InputEvent('input', { bubbles: true, inputType: 'insertFromPaste' });
        editor.dispatchEvent(evt);
        
        return 'INJECTED: ' + editor.innerHTML.length + ' chars';
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  
  console.log('注入结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 检查字数
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || 'not found'`,
  }, { sessionId });
  console.log('字数:', charCount.result.value);
  
  // 点击保存
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const btns = Array.from(document.querySelectorAll('*'));
        for (const btn of btns) {
          if (btn.textContent?.trim() === '保存为草稿' && btn.offsetParent !== null) {
            btn.click();
            return 'SAVED';
          }
        }
        return 'BUTTON NOT FOUND';
      })()
    `
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 5000));
  
  // 检查结果
  const status = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.includes('已保存') ? 'SUCCESS: 已保存' : 'FAILED: 未保存'`,
  }, { sessionId });
  console.log('保存结果:', status.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
