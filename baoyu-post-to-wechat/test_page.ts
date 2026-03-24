import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2C98127E835B5CB5A19E3EEF777D7651';

async function test() {
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2C98127E835B5CB5A19E3EEF777D7651', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  const url = await cdp.send('Runtime.evaluate', {
    expression: `window.location.href`
  }, { sessionId });
  console.log('URL:', url.result.value);
  
  const readyState = await cdp.send('Runtime.evaluate', {
    expression: `document.readyState`
  }, { sessionId });
  console.log('ReadyState:', readyState.result.value);
  
  const title = await cdp.send('Runtime.evaluate', {
    expression: `document.title`
  }, { sessionId });
  console.log('Title:', title.result.value);
  
  const bodyHTML = await cdp.send('Runtime.evaluate', {
    expression: `document.body ? document.body.innerHTML.substring(0, 500) : 'no body'`
  }, { sessionId });
  console.log('Body HTML:', bodyHTML.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('Error:', e.message));
