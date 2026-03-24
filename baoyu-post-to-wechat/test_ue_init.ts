import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查 UEditor 初始化状态
  const initStatus = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const UE = window.UE;
        if (!UE) return 'UE not found';
        
        // 检查 #ueditor_0 是否存在
        const editorEl = document.querySelector('#ueditor_0');
        if (!editorEl) return 'editor element not found';
        
        // 检查是否有ueditor对象
        const hasUEObj = typeof window.ueditor === 'function';
        
        // 检查编辑器是否已经创建
        const hasInstances = UE.instants && Object.keys(UE.instants).length > 0;
        
        // 尝试获取编辑器
        let editor = null;
        try {
          editor = UE.getEditor('ueditor_0');
        } catch(e) {}
        
        // 检查 _bak 方法
        const hasBak = editorEl._bak !== undefined;
        const hasUE = editorEl.UE !== undefined;
        
        return JSON.stringify({
          hasUE: hasUE,
          hasBak: hasBak,
          hasInstances: hasInstances,
          editorValue: editorEl.textContent?.substring(0, 50) || 'empty',
          innerHTML: editorEl.innerHTML?.substring(0, 100) || 'empty',
          contenteditable: editorEl.contentEditable
        });
      })()
    `
  }, { sessionId });
  
  console.log('UE Init Status:', initStatus.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));
