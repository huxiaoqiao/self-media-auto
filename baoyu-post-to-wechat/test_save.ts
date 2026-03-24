import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 查找保存按钮并点击
  const saveResult = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        // 查找所有按钮
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
          if (el.textContent?.includes('保存为草稿') && el.offsetParent !== null) {
            el.click();
            return 'CLICKED: ' + el.textContent.trim();
          }
        }
        return 'NOT FOUND';
      })()
    `
  }, { sessionId });
  console.log('保存结果:', saveResult.result.value);
  
  await new Promise(r => setTimeout(r, 5000));
  
  // 检查页面状态
  const pageText = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.substring(0, 500)`,
  }, { sessionId });
  console.log('页面文本:', pageText.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
