import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查 UEditor 详细 API
  const ueDetail = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const UE = window.UE;
        if (!UE) return 'UE not found';
        
        // 列出所有 UE 实例
        const instances = [];
        for (const key in UE) {
          if (key.startsWith('instance') || key.startsWith('getEditor')) {
            instances.push(key + ': ' + typeof UE[key]);
          }
        }
        
        // 检查是否有 ready 事件
        const hasReady = typeof UE.ready === 'function';
        
        // 尝试获取编辑器
        let editor = null;
        if (UE.getEditor) {
          try {
            editor = UE.getEditor('ueditor_0');
          } catch(e) {}
        }
        
        return JSON.stringify({
          hasGetEditor: typeof UE.getEditor === 'function',
          hasReady: hasReady,
          editorType: editor ? editor.tagName : 'null',
          instances: instances.slice(0, 10),
          UEKeys: Object.keys(UE).slice(0, 20)
        });
      })()
    `
  }, { sessionId });
  
  console.log('UE Detail:', ueDetail.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
