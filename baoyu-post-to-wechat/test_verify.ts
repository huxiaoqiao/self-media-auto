import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查编辑器内容
  const editorContent = await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('#ueditor_0')?.innerText?.substring(0, 300) || 'empty'`,
  }, { sessionId });
  console.log('编辑器内容:', editorContent.result.value);
  
  // 检查字数
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('#ueditor_0')?.innerText?.length || 0`,
  }, { sessionId });
  console.log('字符数:', charCount.result.value);
  
  // 点击保存草稿
  console.log('点击保存草稿...');
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const btns = Array.from(document.querySelectorAll('button, a, div'));
        const saveBtn = btns.find(el => el.textContent?.includes('保存为草稿') || el.textContent?.includes('保存草稿'));
        if (saveBtn) {
          saveBtn.click();
          return 'CLICKED: ' + saveBtn.textContent;
        }
        return 'SAVE BUTTON NOT FOUND';
      })()
    `
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 5000));
  
  // 检查是否有成功提示
  const toast = await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('.weui-desktop-toast, .alert')?.textContent || 'no toast'`,
  }, { sessionId });
  console.log('提示:', toast.result.value);
  
  await cdp.close();
  console.log('✅ 验证完成');
}

test().catch(e => console.error('错误:', e.message));
