import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/6DBDC78052F78FAD642B446CF20BE773';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '6DBDC78052F78FAD642B446CF20BE773', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查编辑器内容
  const editor = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const prose = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror');
        if (!prose) return 'ProseMirror not found';
        return 'Content: ' + prose.innerText?.substring(0, 200) + ' | Length: ' + prose.innerText?.length;
      })()
    `
  }, { sessionId });
  console.log('编辑器:', editor.result.value);
  
  // 检查字数
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || '0'`,
  }, { sessionId });
  console.log('字数:', charCount.result.value);
  
  // 检查标题
  const title = await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('#title')?.value || 'not found'`,
  }, { sessionId });
  console.log('标题:', title.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
