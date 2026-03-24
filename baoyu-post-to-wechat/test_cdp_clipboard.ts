import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  
  // 检查 CDP 支持的域
  const version = await cdp.send('Browser.getVersion', {});
  console.log('Chrome 版本:', version.product);
  
  // 尝试使用 Input.dispatchKeyEvent 模拟 Ctrl+V
  console.log('聚焦编辑器...');
  await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('#ueditor_0')?.focus()`
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 500));
  
  // 模拟 Ctrl+V
  console.log('发送 Ctrl+V...');
  await cdp.send('Input.dispatchKeyEvent', {
    type: 'keyDown',
    modifiers: 2, // Ctrl
    key: 'v',
    code: 'KeyV'
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 100));
  
  await cdp.send('Input.dispatchKeyEvent', {
    type: 'keyUp',
    modifiers: 2,
    key: 'v',
    code: 'KeyV'
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
