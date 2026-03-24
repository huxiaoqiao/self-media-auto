import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 查找 UEditor API
  const ueditorAPI = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        // 尝试不同的 UEditor API 访问方式
        const apis = [
          window.UE,
          window.ue,
          window.UM,
          window.um,
          document.querySelector('#ueditor_0')?.contentWindow?.UE,
          document.querySelector('#ueditor_0')?.contentWindow?.ue,
        ];
        return apis.map((api, i) => 'api' + i + ': ' + (typeof api !== 'undefined' ? 'found' : 'undefined')).join(', ');
      })()
    `
  }, { sessionId });
  console.log('Editor APIs:', ueditorAPI.result.value);
  
  // 检查 #ueditor_0 的父级
  const parent = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('#ueditor_0');
        if (!editor) return 'no editor';
        let parent = editor;
        for (let i = 0; i < 5; i++) {
          parent = parent.parentElement || parent.parentNode;
          if (!parent) break;
          if (parent.id || parent.className) {
            return 'level ' + i + ': ' + parent.tagName + '#' + parent.id + '.' + parent.className;
          }
        }
        return 'no parent with id/class';
      })()
    `
  }, { sessionId });
  console.log('Parent:', parent.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
