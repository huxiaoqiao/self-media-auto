import { execSync, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

import {
  CdpConnection,
  findChromeExecutable as findChromeExecutableBase,
  findExistingChromeDebugPort as findExistingChromeDebugPortBase,
  getFreePort as getFreePortBase,
  launchChrome as launchChromeBase,
  resolveSharedChromeProfileDir,
  sleep,
  waitForChromeDebugPort,
  type PlatformCandidates,
} from 'baoyu-chrome-cdp';

// 远程 CDP 连接配置（可选，不配置则走本地连接）
export const REMOTE_CDP_URL = process.env.WECHAT_CDP_REMOTE_URL; // 例如: wss://abc123.cf-tunnel.com

export { CdpConnection, sleep, waitForChromeDebugPort };

const CHROME_CANDIDATES_FULL: PlatformCandidates = {
  darwin: [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
    '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ],
  win32: [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ],
  default: [
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
    '/usr/bin/microsoft-edge',
  ],
};

let wslHome: string | null | undefined;
function getWslWindowsHome(): string | null {
  if (wslHome !== undefined) return wslHome;
  if (!process.env.WSL_DISTRO_NAME) {
    wslHome = null;
    return null;
  }
  try {
    const raw = execSync('cmd.exe /C "echo %USERPROFILE%"', {
      encoding: 'utf-8',
      timeout: 5_000,
    }).trim().replace(/\r/g, '');
    wslHome = execSync(`wslpath -u "${raw}"`, {
      encoding: 'utf-8',
      timeout: 5_000,
    }).trim() || null;
  } catch {
    wslHome = null;
  }
  return wslHome;
}

export async function getFreePort(): Promise<number> {
  return await getFreePortBase('WECHAT_BROWSER_DEBUG_PORT');
}

export function findChromeExecutable(chromePathOverride?: string): string | undefined {
  if (chromePathOverride?.trim()) return chromePathOverride.trim();
  return findChromeExecutableBase({
    candidates: CHROME_CANDIDATES_FULL,
    envNames: ['WECHAT_BROWSER_CHROME_PATH'],
  });
}

export function getDefaultProfileDir(): string {
  return resolveSharedChromeProfileDir({
    envNames: ['BAOYU_CHROME_PROFILE_DIR', 'WECHAT_BROWSER_PROFILE_DIR'],
    wslWindowsHome: getWslWindowsHome(),
  });
}

export function getAccountProfileDir(alias: string): string {
  const base = getDefaultProfileDir();
  return path.join(path.dirname(base), `wechat-${alias}`);
}

export interface ChromeSession {
  cdp: CdpConnection;
  sessionId: string;
  targetId: string;
}

export async function tryConnectExisting(port: number): Promise<CdpConnection | null> {
  try {
    // 优先使用远程 CDP URL（方案二核心改动）
    if (REMOTE_CDP_URL) {
      // 支持两种格式：
      // 1. wss://chrome.us.ci/devtools/page/<id> - 直接连接指定页面
      // 2. wss://chrome.us.ci - 先连接再自动选择目标页面
      const wsUrl = REMOTE_CDP_URL.includes('/devtools/page/') 
        ? REMOTE_CDP_URL 
        : REMOTE_CDP_URL;
      console.log(`[cdp] 使用远程 CDP: ${wsUrl}`);
      return await CdpConnection.connect(wsUrl, 30_000);
    }
    
    // 原有本地连接逻辑保持不变
    const wsUrl = await waitForChromeDebugPort(port, 5_000, { includeLastError: true });
    return await CdpConnection.connect(wsUrl, 5_000);
  } catch {
    return null;
  }
}

export async function findExistingChromeDebugPort(profileDir = getDefaultProfileDir()): Promise<number | null> {
  // 远程模式下不需要查找本地端口
  if (REMOTE_CDP_URL) {
    console.log('[cdp] 远程模式下跳过本地端口检测');
    return null;
  }
  return await findExistingChromeDebugPortBase({ profileDir });
}

export async function launchChrome(
  url: string,
  profileDir?: string,
  chromePathOverride?: string,
): Promise<{ cdp: CdpConnection; chrome: ChildProcess }> {
  // 远程模式下不需要启动本地 Chrome
  if (REMOTE_CDP_URL) {
    throw new Error('[cdp] 远程模式下不应调用 launchChrome，请确保 Windows Chrome 已启动');
  }
  
  const chromePath = findChromeExecutable(chromePathOverride);
  if (!chromePath) throw new Error('Chrome not found. Set WECHAT_BROWSER_CHROME_PATH env var.');

  const profile = profileDir ?? getDefaultProfileDir();
  const port = await getFreePort();
  console.log(`[cdp] Launching Chrome (profile: ${profile})`);

  const chrome = await launchChromeBase({
    chromePath,
    profileDir: profile,
    port,
    url,
    extraArgs: ['--disable-blink-features=AutomationControlled', '--start-maximized'],
  });

  const wsUrl = await waitForChromeDebugPort(port, 30_000, { includeLastError: true });
  const cdp = await CdpConnection.connect(wsUrl, 30_000);

  return { cdp, chrome };
}

export async function getPageSession(cdp: CdpConnection, urlPattern: string): Promise<ChromeSession> {
  const targets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
  const pageTarget = targets.targetInfos.find((target) => target.type === 'page' && target.url.includes(urlPattern));

  if (!pageTarget) throw new Error(`Page not found: ${urlPattern}`);

  const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', {
    targetId: pageTarget.targetId,
    flatten: true,
  });

  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  await cdp.send('DOM.enable', {}, { sessionId });

  return { cdp, sessionId, targetId: pageTarget.targetId };
}

export async function waitForNewTab(
  cdp: CdpConnection,
  initialIds: Set<string>,
  urlPattern: string,
  timeoutMs = 30_000,
): Promise<string> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const targets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
    const newTab = targets.targetInfos.find((target) => (
      target.type === 'page' &&
      !initialIds.has(target.targetId) &&
      target.url.includes(urlPattern)
    ));
    if (newTab) return newTab.targetId;
    await sleep(500);
  }
  throw new Error(`New tab not found: ${urlPattern}`);
}

export async function clickElement(session: ChromeSession, selector: string): Promise<void> {
  const position = await session.cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const el = document.querySelector('${selector}');
        if (!el) return 'null';
        el.scrollIntoView({ block: 'center' });
        const rect = el.getBoundingClientRect();
        return JSON.stringify({ x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 });
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });

  if (position.result.value === 'null') throw new Error(`Element not found: ${selector}`);
  const pos = JSON.parse(position.result.value);

  await session.cdp.send('Input.dispatchMouseEvent', {
    type: 'mousePressed',
    x: pos.x,
    y: pos.y,
    button: 'left',
    clickCount: 1,
  }, { sessionId: session.sessionId });
  await sleep(50);
  await session.cdp.send('Input.dispatchMouseEvent', {
    type: 'mouseReleased',
    x: pos.x,
    y: pos.y,
    button: 'left',
    clickCount: 1,
  }, { sessionId: session.sessionId });
}

export async function typeText(session: ChromeSession, text: string): Promise<void> {
  const lines = text.split('\n');
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.length > 0) {
      await session.cdp.send('Input.insertText', { text: line }, { sessionId: session.sessionId });
    }
    if (index < lines.length - 1) {
      await session.cdp.send('Input.dispatchKeyEvent', {
        type: 'keyDown',
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
      }, { sessionId: session.sessionId });
      await session.cdp.send('Input.dispatchKeyEvent', {
        type: 'keyUp',
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
      }, { sessionId: session.sessionId });
    }
    await sleep(30);
  }
}

export async function pasteFromClipboard(session: ChromeSession): Promise<void> {
  const modifiers = process.platform === 'darwin' ? 4 : 2;
  await session.cdp.send('Input.dispatchKeyEvent', {
    type: 'keyDown',
    key: 'v',
    code: 'KeyV',
    modifiers,
    windowsVirtualKeyCode: 86,
  }, { sessionId: session.sessionId });
  await session.cdp.send('Input.dispatchKeyEvent', {
    type: 'keyUp',
    key: 'v',
    code: 'KeyV',
    modifiers,
    windowsVirtualKeyCode: 86,
  }, { sessionId: session.sessionId });
}

export async function evaluate<T = unknown>(session: ChromeSession, expression: string): Promise<T> {
  const result = await session.cdp.send<{ result: { value: T } }>('Runtime.evaluate', {
    expression,
    returnByValue: true,
  }, { sessionId: session.sessionId });
  return result.result.value;
}
