import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';
const HTML_URL = 'https://critics-mild-valley-supporting.trycloudflare.com/temp-article.remote.html';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 导航到 HTML 页面
  console.log('导航到 HTML 页面...');
  await cdp.send('Page.navigate', { url: HTML_URL }, { sessionId });
  await new Promise(r => setTimeout(r, 5000));
  
  // 选择内容
  console.log('选择内容...');
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const output = document.querySelector('#output') || document.body;
        const range = document.createRange();
        range.selectNodeContents(output);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        return 'selected: ' + selection.toString().length + ' chars';
      })()
    `
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 1000));
  
  // 复制
  console.log('复制...');
  await cdp.send('Runtime.evaluate', {
    expression: `document.execCommand('copy') ? 'copied' : 'copy failed'`
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 1000));
  
  // 返回编辑页
  console.log('返回编辑页...');
  await cdp.send('Page.navigate', { url: 'https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=1090282002&lang=zh_CN&timestamp=1774265668841' }, { sessionId });
  await new Promise(r => setTimeout(r, 8000));
  
  // 点击编辑器
  console.log('点击编辑器...');
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('#ueditor_0');
        if (editor) {
          editor.focus();
          return 'focused editor';
        }
        return 'editor not found';
      })()
    `
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 1000));
  
  // 粘贴
  console.log('粘贴...');
  await cdp.send('Runtime.evaluate', {
    expression: `document.execCommand('paste') ? 'pasted' : 'paste failed'`
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 检查字数
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || 'not found'`,
  }, { sessionId });
  console.log('字数:', charCount.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
