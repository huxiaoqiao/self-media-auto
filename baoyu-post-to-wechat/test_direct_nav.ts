import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = process.env.WECHAT_CDP_REMOTE_URL || 'wss://chrome.us.ci/devtools/page/0BAAA1F71B3B61B98BBC2E8D07EE9594';
const EDITOR_URL = 'https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=1090282002&lang=zh_CN&timestamp=1774257593624';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  
  const targetId = '0BAAA1F71B3B61B98BBC2E8D07EE9594';
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  console.log('导航到编辑器...');
  await cdp.send('Page.navigate', { url: EDITOR_URL }, { sessionId });
  
  // 等待页面加载
  await new Promise(r => setTimeout(r, 8000));
  
  const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
  console.log('当前 URL:', url.result.value);
  
  const title = await cdp.send('Runtime.evaluate', { expression: 'document.title' }, { sessionId });
  console.log('页面标题:', title.result.value);
  
  // 检查编辑器元素
  const hasEditor = await cdp.send('Runtime.evaluate', { expression: `
    document.querySelector('.ProseMirror') !== null ||
    document.querySelector('#edita45e') !== null ||
    document.querySelector('.editor-content') !== null ||
    document.body.innerText.substring(0, 500)
  ` }, { sessionId });
  console.log('编辑器内容:', hasEditor.result.value);
  
  await cdp.close();
  console.log('完成');
}

test().catch(e => console.error('错误:', e.message));
