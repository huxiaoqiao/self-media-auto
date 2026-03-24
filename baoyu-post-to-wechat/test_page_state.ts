import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查页面 URL
  const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
  console.log('URL:', url.result.value);
  
  // 检查标题输入框
  const title = await cdp.send('Runtime.evaluate', { 
    expression: `document.querySelector('#title')?.value || 'NOT FOUND'` 
  }, { sessionId });
  console.log('标题:', title.result.value);
  
  // 检查富文本编辑器内容
  const editor = await cdp.send('Runtime.evaluate', { 
    expression: `document.querySelector('#js_content')?.innerHTML || document.querySelector('.edit_area')?.innerHTML || 'NOT FOUND'` 
  }, { sessionId });
  console.log('编辑器内容:', editor.result.value?.substring(0, 200) || 'empty');
  
  // 检查是否有错误提示
  const errors = await cdp.send('Runtime.evaluate', { 
    expression: `Array.from(document.querySelectorAll('.weui-desktop-toast, .alert')).map(el => el.textContent).join(', ') || 'no errors'` 
  }, { sessionId });
  console.log('错误提示:', errors.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
