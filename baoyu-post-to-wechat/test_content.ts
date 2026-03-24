import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查整个页面的文本内容
  const allText = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.substring(0, 500) || 'empty'`
  }, { sessionId });
  console.log('页面文本:', allText.result.value);
  
  // 查找含有关键词的元素
  const keywords = await cdp.send('Runtime.evaluate', {
    expression: `(function() {
      const keywords = ['域名', '智商税', '极客', '羊毛'];
      for (const kw of keywords) {
        const found = document.body?.innerText?.includes(kw);
        if (found) return 'FOUND: ' + kw;
      }
      return 'NO KEYWORDS FOUND';
    })()`
  }, { sessionId });
  console.log('关键词检查:', keywords.result.value);
  
  // 检查草稿保存状态
  const saveStatus = await cdp.send('Runtime.evaluate', {
    expression: `(function() {
      const btns = Array.from(document.querySelectorAll('button, a'));
      const saveBtn = btns.find(el => el.textContent.includes('保存') || el.textContent.includes('发布'));
      return saveBtn ? 'Save button found: ' + saveBtn.textContent : 'No save button';
    })()`
  }, { sessionId });
  console.log('保存按钮:', saveStatus.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
