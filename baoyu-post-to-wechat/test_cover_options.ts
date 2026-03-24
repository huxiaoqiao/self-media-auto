import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/6DBDC78052F78FAD642B446CF20BE773';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '6DBDC78052F78FAD642B446CF20BE773', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 点击封面区域
  console.log('2. 点击封面区域...');
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        // 查找封面区域
        const coverArea = document.querySelector('.cover-area, .js_cover, [class*="cover"]');
        if (coverArea) {
          coverArea.click();
          return 'Clicked cover area: ' + coverArea.className;
        }
        return 'Cover area not found';
      })()
    `
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 查找所有封面相关的按钮
  console.log('3. 查找封面选项...');
  const options = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const result = [];
        // 查找包含"封面"或"cover"的元素
        const all = document.querySelectorAll('*');
        for (const el of all) {
          if (el.textContent && (el.textContent.includes('封面') || el.textContent.includes('从正文'))) {
            result.push({
              tag: el.tagName,
              class: el.className,
              text: el.textContent.substring(0, 50)
            });
          }
        }
        return JSON.stringify(result.slice(0, 10));
      })()
    `
  }, { sessionId });
  console.log('   找到的选项:', options.result.value);
  
  // 查找对话框内容
  console.log('4. 检查对话框...');
  const dialog = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const dialog = document.querySelector('.weui-desktop-dialog, .dialog, [class*="dialog"]');
        if (!dialog) return 'No dialog';
        
        return 'Dialog found: ' + dialog.className + '\\nButtons: ' + 
          Array.from(dialog.querySelectorAll('button, a')).map(b => b.textContent?.trim()).filter(Boolean).join(', ');
      })()
    `
  }, { sessionId });
  console.log('   对话框:', dialog.result.value);
  
  await cdp.close();
  console.log('✅ 完成');
}

test().catch(e => console.error('错误:', e.message));
