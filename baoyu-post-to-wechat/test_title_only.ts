import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';
import { readFileSync } from 'fs';

const EDITOR_URL = 'https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=1090282002&lang=zh_CN&timestamp=1774261590212';
const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/96557FC489A8B3640283F0BD6D0C1C33';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  
  const targetId = '96557FC489A8B3640283F0BD6D0C1C33';
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  console.log('2. CDP 连接成功');
  
  // 导航到编辑器
  console.log('3. 导航到编辑器...');
  await cdp.send('Page.navigate', { url: EDITOR_URL }, { sessionId });
  await new Promise(r => setTimeout(r, 8000));
  
  const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
  console.log('4. 当前 URL:', url.result.value);
  
  // 填写标题
  console.log('5. 填写标题...');
  const title = '还在给域名商送钱？这届极客的羊毛，你根本不会薅';
  const titleResult = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        // 查找标题输入框
        const inputs = document.querySelectorAll('input[type="text"], textarea');
        for (const input of inputs) {
          if (input.title && input.title.includes('标题')) {
            input.value = '${title}';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            return 'title-filled: ' + input.value;
          }
        }
        // 尝试通用标题选择器
        const titleInput = document.querySelector('#title, .title_input, input[name="title"]');
        if (titleInput) {
          titleInput.value = '${title}';
          titleInput.dispatchEvent(new Event('input', { bubbles: true }));
          return 'title-filled: ' + titleInput.value;
        }
        return 'title-input-not-found';
      })()
    `
  }, { sessionId });
  console.log('6. 标题填写结果:', titleResult.result.value);
  
  await cdp.close();
  console.log('✅ 测试完成');
}

test().catch(e => console.error('❌ 错误:', e.message));
