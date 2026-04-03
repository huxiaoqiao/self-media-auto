import fs, { readFile, writeFile } from 'node:fs/promises';
import fs from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { setTimeout } from 'node:timers/promises';
import process from 'node:process';
import { Buffer } from 'node:buffer';
import { fileURLToPath } from 'node:url';
import { launchChrome, tryConnectExisting, findExistingChromeDebugPort, getPageSession, waitForNewTab, clickElement, typeText, evaluate, sleep, getAccountProfileDir, maximizeChromeWindow, type ChromeSession, type CdpConnection, REMOTE_CDP_URL } from './cdp.ts';
import { startRemoteHtmlServer, stopRemoteHtmlServer, getTunnelUrl } from './remote-html-server.ts';
import { loadWechatExtendConfig, resolveAccount } from './wechat-extend-config.ts';

// 获取图片 tunnel URL - 优先使用外部设置�?IMAGE_TUNNEL_URL
function getImageTunnelUrl(): string | null {
  // 优先使用 IMAGE_TUNNEL_URL 环境变量
  if (process.env.IMAGE_TUNNEL_URL) {
    return process.env.IMAGE_TUNNEL_URL;
  }
  // 否则使用内部启动�?tunnel
  return getTunnelUrl();
}



const WECHAT_URL = 'https://mp.weixin.qq.com/';

interface ImageInfo {
  placeholder: string;
  localPath: string;
  originalPath: string;
}

interface ArticleOptions {
  title: string;
  content?: string;
  htmlFile?: string;
  markdownFile?: string;
  theme?: string;
  color?: string;
  citeStatus?: boolean;
  author?: string;
  summary?: string;
  images?: string[];
  contentImages?: ImageInfo[];
  submit?: boolean;
  profileDir?: string;
  cdpPort?: number;
  cover?: string;
}

async function waitForLogin(session: ChromeSession, timeoutMs = 120_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const url = await evaluate<string>(session, 'window.location.href');
    if (url.includes('/cgi-bin/home')) return true;
    await sleep(2000);
  }
  return false;
}

async function waitForElement(session: ChromeSession, selector: string, timeoutMs = 10_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const found = await evaluate<boolean>(session, `!!document.querySelector('${selector}')`);
    if (found) return true;
    await sleep(500);
  }
  return false;
}

async function clickMenuByText(session: ChromeSession, text: string): Promise<void> {
  console.log(`[wechat] Clicking "${text}" menu...`);
  const posResult = await session.cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const items = document.querySelectorAll('.new-creation__menu .new-creation__menu-item');
        console.log('[DEBUG] Found menu items:', items.length);
        for (const item of items) {
          const title = item.querySelector('.new-creation__menu-title');
          console.log('[DEBUG] Menu item title:', title?.textContent?.trim());
          if (title && title.textContent?.trim() === '${text}') {
            item.scrollIntoView({ block: 'center' });
            const rect = item.getBoundingClientRect();
            return JSON.stringify({ x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, found: true });
          }
        }
        return JSON.stringify({ found: false });
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });

  const result = JSON.parse(posResult.result.value || '{"found":false}');
  if (!result.found) throw new Error(`Menu "${text}" not found`);
  const pos = { x: result.x, y: result.y };

  console.log(`[wechat] Found menu item at (${pos.x}, ${pos.y}), clicking...`);
  await session.cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: pos.x, y: pos.y, button: 'left', clickCount: 1 }, { sessionId: session.sessionId });
  await sleep(100);
  await session.cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: pos.x, y: pos.y, button: 'left', clickCount: 1 }, { sessionId: session.sessionId });
  console.log('[wechat] Mouse click dispatched');
}

async function copyImageToClipboard(imagePath: string): Promise<void> {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const copyScript = path.join(__dirname, './copy-to-clipboard.ts');
  const result = spawnSync('npx', ['-y', 'bun', copyScript, 'image', imagePath], { stdio: 'inherit' });
  if (result.status !== 0) throw new Error(`Failed to copy image: ${imagePath}`);
}

async function pasteInEditor(session: ChromeSession): Promise<void> {
  const modifiers = process.platform === 'darwin' ? 4 : 2;
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'v', code: 'KeyV', modifiers, windowsVirtualKeyCode: 86 }, { sessionId: session.sessionId });
  await sleep(50);
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'v', code: 'KeyV', modifiers, windowsVirtualKeyCode: 86 }, { sessionId: session.sessionId });
}

async function sendCopy(cdp?: CdpConnection, sessionId?: string): Promise<void> {
  if (process.platform === 'darwin') {
    spawnSync('osascript', ['-e', 'tell application "System Events" to keystroke "c" using command down']);
  } else if (process.platform === 'linux') {
    spawnSync('xdotool', ['key', 'ctrl+c']);
  } else if (cdp && sessionId) {
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'c', code: 'KeyC', modifiers: 2, windowsVirtualKeyCode: 67 }, { sessionId });
    await sleep(50);
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'c', code: 'KeyC', modifiers: 2, windowsVirtualKeyCode: 67 }, { sessionId });
  }
}

async function sendPaste(cdp?: CdpConnection, sessionId?: string): Promise<void> {
  if (process.platform === 'darwin') {
    spawnSync('osascript', ['-e', 'tell application "System Events" to keystroke "v" using command down']);
  } else if (process.platform === 'linux') {
    spawnSync('xdotool', ['key', 'ctrl+v']);
  } else if (cdp && sessionId) {
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'v', code: 'KeyV', modifiers: 2, windowsVirtualKeyCode: 86 }, { sessionId });
    await sleep(50);
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'v', code: 'KeyV', modifiers: 2, windowsVirtualKeyCode: 86 }, { sessionId });
  }
}

async function copyHtmlFromBrowser(cdp: CdpConnection, htmlFilePath: string, contentImages: ImageInfo[] = [], useRemoteServer = false): Promise<void> {
  // 直接注入模式 - 不使用剪贴板
  console.log('[wechat] 直接注入 HTML 内容模式...');
  
  // 读取 HTML 文件
  const absolutePath = path.isAbsolute(htmlFilePath) ? htmlFilePath : path.resolve(process.cwd(), htmlFilePath);
  let htmlContent = await readFile(absolutePath, 'utf-8');
  
  // 提取 #output 中的内容
  const outputMatch = htmlContent.match(/<div id="output">([\s\S]*?)<\/div>/);
  let content = outputMatch ? outputMatch[1] : htmlContent;
  
  // 替换图片 URL
  const tunnelUrl = getImageTunnelUrl();
  if (tunnelUrl && contentImages.length > 0) {
    console.log(`[wechat] 使用 tunnel ${tunnelUrl} 替换图片 URL`);
    for (const img of contentImages) {
      const imgFileName = path.basename(img.localPath);
      content = content.split(img.placeholder).join(`${tunnelUrl}/${imgFileName}`);
      content = content.split(img.localPath).join(`${tunnelUrl}/${imgFileName}`);
    }
  }
  
  // 保存修改后的 HTML �?SMB 共享目录
  if (tunnelUrl) {
    const smbShare = 'C:\Users\Administrator\smb-share';
    const smbFilePath = path.join(smbShare, 'temp-article.remote.html');
    await writeFile(smbFilePath, `<div id="output">${content}</div>`, 'utf-8');
    console.log(`[wechat] HTML 已保存到 SMB 共享目录`);
  }
  
  // 存储内容供后续注入使�?  
(globalThis as any).__wechatHtmlContent = content;
  console.log('[wechat] HTML 内容已准备，长度:', content.length);
}

async function pasteFromClipboardInEditor(session: ChromeSession): Promise<void> {
  console.log('[wechat] Pasting content...');
  await sendPaste(session.cdp, session.sessionId);
  await sleep(1000);
}

async function parseMarkdownWithPlaceholders(
  markdownPath: string,
  theme?: string,
  color?: string,
  citeStatus: boolean = true
): Promise<{ title: string; author: string; summary: string; htmlPath: string; contentImages: ImageInfo[] }> {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const mdToWechatScript = path.join(__dirname, 'md-to-wechat.ts');
  const args = ['-y', 'bun', mdToWechatScript, markdownPath];
  if (theme) args.push('--theme', theme);
  if (color) args.push('--color', color);
  if (!citeStatus) args.push('--no-cite');

  const result = spawnSync('npx', args, { stdio: ['inherit', 'pipe', 'pipe'] });
  if (result.status !== 0) {
    const stderr = result.stderr?.toString() || '';
    throw new Error(`Failed to parse markdown: ${stderr}`);
  }

  const output = result.stdout.toString();
  return JSON.parse(output);
}

function parseHtmlMeta(htmlPath: string): { title: string; author: string; summary: string; contentImages: ImageInfo[] } {
  const content = fs.readFileSync(htmlPath, 'utf-8');

  let title = '';
  const titleMatch = content.match(/<title>([^<]+)<\/title>/i);
  if (titleMatch) title = titleMatch[1]!;

  let author = '';
  const authorMatch = content.match(/<meta\s+name=["']author["']\s+content=["']([^"']+)["']/i)
    || content.match(/<meta\s+content=["']([^"']+)["']\s+name=["']author["']/i);
  if (authorMatch) author = authorMatch[1]!;

  let summary = '';
  const descMatch = content.match(/<meta\s+name=["']description["']\s+content=["']([^"']+)["']/i)
    || content.match(/<meta\s+content=["']([^"']+)["']\s+name=["']description["']/i);
  if (descMatch) summary = descMatch[1]!;

  if (!summary) {
    const firstPMatch = content.match(/<p[^>]*>([^<]+)<\/p>/i);
    if (firstPMatch) {
      const text = firstPMatch[1]!.replace(/<[^>]+>/g, '').trim();
      if (text.length > 20) {
        summary = text.length > 120 ? text.slice(0, 117) + '...' : text;
      }
    }
  }

  const mdPath = htmlPath.replace(/\.html$/i, '.md');
  if (fs.existsSync(mdPath)) {
    const mdContent = fs.readFileSync(mdPath, 'utf-8');
    const fmMatch = mdContent.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (fmMatch) {
      const lines = fmMatch[1]!.split('\n');
      for (const line of lines) {
        const colonIdx = line.indexOf(':');
        if (colonIdx > 0) {
          const key = line.slice(0, colonIdx).trim();
          let value = line.slice(colonIdx + 1).trim();
          if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
          }
          if (key === 'title' && !title) title = value;
          if (key === 'author' && !author) author = value;
          if ((key === 'description' || key === 'summary') && !summary) summary = value;
        }
      }
    }
  }

  const contentImages: ImageInfo[] = [];
  const imgRegex = /<img[^>]*\ssrc=["']([^"']+)["'][^>]*>/gi;
  const matches = [...content.matchAll(imgRegex)];
  for (const match of matches) {
    const [fullTag, src] = match;
    if (!src || src.startsWith('http')) continue;
    const localPathMatch = fullTag.match(/data-local-path=["']([^"']+)["']/);
    if (localPathMatch) {
      contentImages.push({
        placeholder: src,
        localPath: localPathMatch[1]!,
        originalPath: src,
      });
    }
  }

  return { title, author, summary, contentImages };
}

async function selectAndReplacePlaceholder(session: ChromeSession, placeholder: string): Promise<boolean> {
  // 调试：先看编辑器里所有 img 标签的 src
  const debugImgs = await session.cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return 'NO_EDITOR';
        const imgs = editor.querySelectorAll('img');
        const srcs = [];
        for (const img of imgs) {
          srcs.push(img.src + ' || ' + img.getAttribute('src') + ' || ' + img.outerHTML.slice(0, 80));
        }
        return 'IMGS:' + srcs.join('|||');
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });
  console.log('[DEBUG] Editor img scan:', (debugImgs.result.value || 'null').slice(0, 300));

  // 方法1：HTML 注入模式下，图片是 <img src="XIMGPH_X"> 标签
  const imgResult = await session.cdp.send<{ result: { value: boolean } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return false;
        const placeholder = ${JSON.stringify(placeholder)};
        // 查找 img[src="XIMGPH_X"]
        const imgs = editor.querySelectorAll('img[src="' + placeholder + '"]');
        if (imgs.length > 0) {
          const img = imgs[0];
          img.scrollIntoView({ behavior: 'smooth', block: 'center' });
          // 选中整个 img 节点
          const range = document.createRange();
          range.selectNode(img);
          const sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
          return true;
        }
        return false;
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });

  if (imgResult.result.value) return true;

  // 方法2：文本节点中的占位符
  const textResult = await session.cdp.send<{ result: { value: boolean } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return false;
        const placeholder = ${JSON.stringify(placeholder)};
        const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null, false);
        let node;
        while ((node = walker.nextNode())) {
          const text = node.textContent || '';
          let searchStart = 0;
          let idx;
          while ((idx = text.indexOf(placeholder, searchStart)) !== -1) {
            const afterIdx = idx + placeholder.length;
            const charAfter = text[afterIdx];
            if (charAfter === undefined || !/\\d/.test(charAfter)) {
              node.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
              const range = document.createRange();
              range.setStart(node, idx);
              range.setEnd(node, idx + placeholder.length);
              const sel = window.getSelection();
              sel.removeAllRanges();
              sel.addRange(range);
              return true;
            }
            searchStart = afterIdx;
          }
        }
        return false;
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });

  return textResult.result.value;
}

async function pressDeleteKey(session: ChromeSession): Promise<void> {
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 }, { sessionId: session.sessionId });
  await sleep(50);
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 }, { sessionId: session.sessionId });
}

async function removeExtraEmptyLineAfterImage(session: ChromeSession): Promise<boolean> {
  const removed = await evaluate<boolean>(session, `
    (function() {
      const editor = document.querySelector('.ProseMirror');
      if (!editor) return false;

      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return false;

      let node = sel.anchorNode;
      if (!node) return false;
      let element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
      if (!element || !editor.contains(element)) return false;

      const isEmptyParagraph = (el) => {
        if (!el || el.tagName !== 'P') return false;
        const text = (el.textContent || '').trim();
        if (text.length > 0) return false;
        return el.querySelectorAll('img, figure, video, iframe').length === 0;
      };

      const hasImage = (el) => {
        if (!el) return false;
        return !!el.querySelector('img, figure img, picture img');
      };

      const placeCursorAfter = (el) => {
        if (!el) return;
        const range = document.createRange();
        range.setStartAfter(el);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
      };

      // Case 1: caret is inside an empty paragraph right after an image block.
      const emptyPara = element.closest('p');
      if (emptyPara && editor.contains(emptyPara) && isEmptyParagraph(emptyPara)) {
        const prev = emptyPara.previousElementSibling;
        if (prev && hasImage(prev)) {
          emptyPara.remove();
          placeCursorAfter(prev);
          return true;
        }
      }

      // Case 2: caret is on the image block itself; remove the next empty paragraph.
      const imageBlock = element.closest('figure, p');
      if (imageBlock && editor.contains(imageBlock) && hasImage(imageBlock)) {
        const next = imageBlock.nextElementSibling;
        if (next && isEmptyParagraph(next)) {
          next.remove();
          placeCursorAfter(imageBlock);
          return true;
        }
      }

      return false;
    })()
  `);

  if (removed) console.log('[wechat] Removed extra empty line after image.');
  return removed;
}

export async function postArticle(options: ArticleOptions): Promise<void> {
  const { title, content, htmlFile, markdownFile, theme, color, citeStatus = true, author, summary, images = [], submit = false, profileDir, cdpPort } = options;
  let { contentImages = [] } = options;
  let effectiveTitle = title || '';
  let effectiveAuthor = author || '';
  let effectiveSummary = summary || '';
  let effectiveHtmlFile = htmlFile;

  if (markdownFile) {
    console.log(`[wechat] Parsing markdown: ${markdownFile}`);
    const parsed = await parseMarkdownWithPlaceholders(markdownFile, theme, color, citeStatus);
    effectiveTitle = effectiveTitle || parsed.title;
    effectiveAuthor = effectiveAuthor || parsed.author;
    effectiveSummary = effectiveSummary || parsed.summary;
    effectiveHtmlFile = parsed.htmlPath;
    contentImages = parsed.contentImages;
    console.log(`[wechat] Title: ${effectiveTitle || '(empty)'}`);
    console.log(`[wechat] Author: ${effectiveAuthor || '(empty)'}`);
    console.log(`[wechat] Summary: ${effectiveSummary || '(empty)'}`);
    console.log(`[wechat] Found ${contentImages.length} images to insert`);
  } else if (htmlFile && fs.existsSync(htmlFile)) {
    console.log(`[wechat] Parsing HTML: ${htmlFile}`);
    const meta = parseHtmlMeta(htmlFile);
    effectiveTitle = effectiveTitle || meta.title;
    effectiveAuthor = effectiveAuthor || meta.author;
    effectiveSummary = effectiveSummary || meta.summary;
    effectiveHtmlFile = htmlFile;
    if (meta.contentImages.length > 0) {
      contentImages = meta.contentImages;
    }
    console.log(`[wechat] Title: ${effectiveTitle || '(empty)'}`);
    console.log(`[wechat] Author: ${effectiveAuthor || '(empty)'}`);
    console.log(`[wechat] Summary: ${effectiveSummary || '(empty)'}`);
    console.log(`[wechat] Found ${contentImages.length} images to insert`);
  }

  if (effectiveTitle && effectiveTitle.length > 64) throw new Error(`Title too long: ${effectiveTitle.length} chars (max 64)`);
  if (!content && !effectiveHtmlFile) throw new Error('Either --content, --html, or --markdown is required');

  let cdp: CdpConnection;
  let chrome: ReturnType<typeof import('node:child_process').spawn> | null = null;

  // Handle remote CDP mode (when WECHAT_CDP_REMOTE_URL is set)
  let isDirectPageConnection = false;
  if (REMOTE_CDP_URL) {
    console.log(`[cdp] 远程模式: 直接连接 ${REMOTE_CDP_URL}`);
    isDirectPageConnection = REMOTE_CDP_URL.includes('/devtools/page/');
    const remoteCdp = await tryConnectExisting(9222); // port is ignored when REMOTE_CDP_URL is set
    if (remoteCdp) {
      console.log('[cdp] 远程 CDP 连接成功');
      cdp = remoteCdp;
    } else {
      throw new Error('[cdp] 远程连接失败，请检查 Cloudflare Tunnel 或 Windows Chrome 远程调试是否正常');
    }
  } else {
    // Try connecting to existing Chrome: explicit port > auto-detect > launch new
    const portToTry = cdpPort ?? await findExistingChromeDebugPort();
    if (portToTry) {
      const existing = await tryConnectExisting(portToTry);
      if (existing) {
        console.log(`[cdp] Connected to existing Chrome on port ${portToTry}`);
        cdp = existing;
      } else {
        console.log(`[cdp] Port ${portToTry} not available, launching new Chrome...`);
        const launched = await launchChrome(WECHAT_URL, profileDir);
        if (!launched.cdp) throw new Error('Chrome launch failed: CDP connection is null');
        cdp = launched.cdp;
        chrome = launched.chrome;
        await maximizeChromeWindow(cdp);
        // 强制将 Chrome 窗口最大化并激活到前台
        spawnSync('powershell', [
          '-ExecutionPolicy', 'Bypass',
          '-File', path.join(path.dirname(fileURLToPath(import.meta.url)), 'maximize_chrome.ps1')
        ]);
      }
    } else {
      const launched = await launchChrome(WECHAT_URL, profileDir);
      if (!launched.cdp) throw new Error('Chrome launch failed: CDP connection is null');
      cdp = launched.cdp;
      chrome = launched.chrome;
      await maximizeChromeWindow(cdp);
      // 强制将 Chrome 窗口最大化并激活到前台
      spawnSync('powershell', [
        '-ExecutionPolicy', 'Bypass',
        '-File', path.join(path.dirname(fileURLToPath(import.meta.url)), 'maximize_chrome.ps1')
      ]);
    }
  }

  try {
    console.log('[wechat] Waiting for page load...');
    await sleep(3000);

    let session: ChromeSession;
    if (!chrome) {
      // Remote direct page connection: already attached to a specific page
      if (isDirectPageConnection) {
        console.log('[wechat] 使用远程直接连接模式，跳�?tab 查找');
        const targetIdMatch = REMOTE_CDP_URL.match(/\/devtools\/page\/([^/]+)$/);
        const targetId = targetIdMatch ? targetIdMatch[1] : '';
        
        if (targetId) {
          console.log(`[wechat] 附加到目标页�? ${targetId}`);
          const { sessionId: reuseSid } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId, flatten: true });
          await cdp.send('Page.enable', {}, { sessionId: reuseSid });
          await cdp.send('Runtime.enable', {}, { sessionId: reuseSid });
          await cdp.send('DOM.enable', {}, { sessionId: reuseSid });
          session = { cdp, sessionId: reuseSid, targetId };
          await maximizeChromeWindow(cdp);
          spawnSync('powershell', [
            '-ExecutionPolicy', 'Bypass',
            '-File', path.join(path.dirname(fileURLToPath(import.meta.url)), 'maximize_chrome.ps1'),
            '-waitSeconds', '3'
          ]);
          
          const currentUrl = await evaluate<string>(session, 'window.location.href');
          console.log(`[wechat] 当前页面 URL: ${currentUrl.substring(0, 80)}`);
          
          if (!currentUrl.includes('/cgi-bin/')) {
            console.log('[wechat] 导航到公众号后台...');
            await evaluate(session, `window.location.href = '${WECHAT_URL}cgi-bin/home?t=home/index'`);
            await sleep(5000);
          }
        } else {
          throw new Error('[wechat] 无法�?URL 提取 targetId');
        }
      } else {
      // Reusing existing Chrome: find an already-logged-in tab (has token in URL)
      const allTargets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
      const loggedInTab = allTargets.targetInfos.find(t => t.type === 'page' && t.url.includes('mp.weixin.qq.com') && t.url.includes('token='));
      const wechatTab = loggedInTab || allTargets.targetInfos.find(t => t.type === 'page' && t.url.includes('mp.weixin.qq.com'));

      if (wechatTab) {
        console.log(`[wechat] Reusing existing tab: ${wechatTab.url.substring(0, 80)}...`);
        const { sessionId: reuseSid } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId: wechatTab.targetId, flatten: true });
        await cdp.send('Page.enable', {}, { sessionId: reuseSid });
        await cdp.send('Runtime.enable', {}, { sessionId: reuseSid });
        await cdp.send('DOM.enable', {}, { sessionId: reuseSid });
        session = { cdp, sessionId: reuseSid, targetId: wechatTab.targetId };
        spawnSync('powershell', [
          '-ExecutionPolicy', 'Bypass',
          '-File', path.join(path.dirname(fileURLToPath(import.meta.url)), 'maximize_chrome.ps1')
        ]);

        // Navigate to home if not already there
        const currentUrl = await evaluate<string>(session, 'window.location.href');
        const isEditorTab = currentUrl.includes('/cgi-bin/appmsg') && currentUrl.includes('appmsg_edit');
        if (isEditorTab) {
          console.log('[wechat] Already on editor tab, skipping home navigation.');
        } else if (!currentUrl.includes('/cgi-bin/home')) {
          console.log('[wechat] Navigating to home...');
          await evaluate(session, `window.location.href = '${WECHAT_URL}cgi-bin/home?t=home/index'`);
          await sleep(5000);
        }
      }
      }
    } else {
      session = await getPageSession(cdp, 'mp.weixin.qq.com');
    }

    const url = await evaluate<string>(session, 'window.location.href');
    if (!url.includes('/cgi-bin/')) {
      console.log('[wechat] Not logged in. Detecting QR code for remote login...');
      
      try {
        const qrSelector = '.login__type_default .login__qrcode';
        const hasQr = await waitForElement(session, qrSelector, 10000);
        
        if (hasQr) {
          const qrPath = path.resolve(process.cwd(), '../../assets/login_qr.png');
          const qrDir = path.dirname(qrPath);
          if (!fs.existsSync(qrDir)) fs.mkdirSync(qrDir, { recursive: true });

          const pos = await evaluate<{x:number, y:number, w:number, h:number}>(session, `
            (function() {
              const el = document.querySelector('${qrSelector}');
              const rect = el.getBoundingClientRect();
              return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
            })()
          `);
          
          if (pos) {
            console.log(`[wechat] Capturing QR code to: ${qrPath}`);
            const screenshot = await cdp.send<{ data: string }>('Page.captureScreenshot', {
              format: 'png',
              clip: { x: pos.x, y: pos.y, width: pos.w, height: pos.h, scale: 1 }
            }, { sessionId: session.sessionId });
            
            fs.writeFileSync(qrPath, Buffer.from(screenshot.data, 'base64'));
            
            // Notify user via Feishu - OpenClaw will detect [FEISHU_IMAGE_REQUIRED] marker
            console.log('\n🔔 [FEISHU_IMAGE_REQUIRED] ' + qrPath);
            console.log('\n⚠️ [LOGIN_REQUIRED] 微信公众号需要登录');
            console.log('📸 二维码截图已保存，请查收飞书推送的图片');
            console.log('\n\xe2\x8f\xb3 \xe7\xad\x89\xe5\xbe\x85\xe7\x94\xa8\xe6\x88\xb7\xe6\x89\xab\xe7\xa0\x81\xe7\x99\xbb\xe5\xbd\x95...\xef\xbc\x88\xe6\x9c\x80\xe9\x95\xbf\xe7\xad\x89\xe5\xbe\x85 5 \xe5\x88\x86\xe9\x92\x9f\xef\xbc\x89\n');
          }
        }
      } catch (e) {
        console.error(`[wechat] Failed to capture QR code: ${e}`);
      }

      const loggedIn = await waitForLogin(session, 300000); 
      if (!loggedIn) throw new Error('Login timeout');
    }
    console.log('[wechat] Logged in.');

    await sleep(2000);

    // Check if already on editor page
    const currentUrl = await evaluate<string>(session, 'window.location.href');
    const isEditorPage = currentUrl.includes('/cgi-bin/appmsg') && currentUrl.includes('appmsg_edit');
    
    if (!isEditorPage) {
      // Wait for menu to be ready
      const menuReady = await waitForElement(session, '.new-creation__menu', 20_000);
      if (!menuReady) throw new Error('Home page menu did not load');

      const targets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
      const initialIds = new Set(targets.targetInfos.map(t => t.targetId));

      await clickMenuByText(session, '文章');
      await sleep(3000);

      // 调试：检查当前 tab 的 URL 是否已经变化（可能在当前 tab 跳转了）
      const currentUrlAfterClick = await evaluate<string>(session, 'window.location.href');
      console.log(`[DEBUG] Current URL after click: ${currentUrlAfterClick}`);

      // 调试：打印所有打开的 Tab
      const allTabs = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
      console.log('[DEBUG] All tabs after click:');
      for (const t of allTabs.targetInfos) {
        console.log(`  - ${t.type}: ${t.url.substring(0, 80)}`);
      }

      const editorTargetId = await waitForNewTab(cdp, initialIds, 'mp.weixin.qq.com');
      console.log('[wechat] Editor tab opened.');

      const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId: editorTargetId, flatten: true });
      session = { cdp, sessionId, targetId: editorTargetId };

      await cdp.send('Page.enable', {}, { sessionId });
      await cdp.send('Runtime.enable', {}, { sessionId });
      await cdp.send('DOM.enable', {}, { sessionId });

      await sleep(3000);
    } else {
      console.log('[wechat] Already on editor page, skipping menu navigation.');
    }

    if (effectiveTitle) {
      console.log('[wechat] Filling title...');
      await evaluate(session, `document.querySelector('#title').value = ${JSON.stringify(effectiveTitle)}; document.querySelector('#title').dispatchEvent(new Event('input', { bubbles: true }));`);
    }

    if (effectiveAuthor) {
      console.log('[wechat] Filling author...');
      await evaluate(session, `document.querySelector('#author').value = ${JSON.stringify(effectiveAuthor)}; document.querySelector('#author').dispatchEvent(new Event('input', { bubbles: true }));`);
    }

    await sleep(500);

    // --- 强制标题校验与补�?---
    if (effectiveTitle) {
      const actualTitle = await evaluate<string>(session, `document.querySelector('#title')?.value || ''`);
      if (actualTitle !== effectiveTitle) {
        console.log(`[wechat] Title mismatch, re-filling...`);
        await evaluate(session, `document.querySelector('#title').value = ${JSON.stringify(effectiveTitle)}; document.querySelector('#title').dispatchEvent(new Event('input', { bubbles: true }));`);
      }
    }

    // --- 封面图上传 ---
    const coverPath = options.cover || '';
    if (coverPath && fs.existsSync(coverPath)) {
      console.log(`[wechat] Starting cover upload for: ${coverPath}`);
      try {
        await evaluate(session, `document.querySelector('.js_imagedialog')?.click()`);
        await sleep(2000);

        const docRes: any = await cdp.send('DOM.getDocument', { depth: -1 }, { sessionId: session.sessionId });
        const rootNodeId = docRes.root.nodeId;

        const queryRes: any = await cdp.send('DOM.querySelector', {
            nodeId: rootNodeId,
            selector: '.weui-desktop-dialog input[type="file"]'
        }, { sessionId: session.sessionId });

        const nodeId = queryRes.nodeId;
        if (!nodeId) throw new Error('Could not find file input node in modal');

        await cdp.send('DOM.setFileInputFiles', {
            files: [coverPath],
            nodeId: nodeId
        }, { sessionId: session.sessionId });

        console.log('[wechat] Native file injection to modal successful.');
        await sleep(4000);

        console.log('[wechat] Waiting for "Next" button...');
        await evaluate(session, `
          (async function() {
            const nextBtn = document.querySelector('.weui-desktop-dialog__ft .weui-desktop-btn_primary') || document.querySelector('.weui-desktop-dialog .weui-desktop-btn_primary');
            if (nextBtn) {
              console.log('[wechat] Clicking Next button');
              nextBtn.click();
            } else {
              console.log('[wechat] Next button not found, checking if already on crop page');
            }
          })()
        `);

        await sleep(3000);

          console.log('[wechat] Selecting 2.35:1 ratio and confirming...');
          await evaluate(session, `
            (async function() {
              // 1. 尝试选择比例
              const items = Array.from(document.querySelectorAll('.weui-desktop-image-preview__selectable_item_v2, .weui-desktop-image-preview__item, .weui-desktop-image-preview__selectable_item'));
              const ratioBtn = items.find(el => el.textContent.includes('2.35:1'));
              if (ratioBtn) {
                 console.log('[wechat] Selecting 2.35:1 ratio');
                 ratioBtn.click();
                 await new Promise(r => setTimeout(r, 1000));
              }

              // 2. 尝试点击确认按钮
                            const btns = Array.from(document.querySelectorAll('button, .weui-desktop-btn_primary, .weui-desktop-btn'));
              const okBtn = btns.find(el => 
                (el.textContent.includes('确认') || el.textContent.includes('确定') || el.textContent.includes('完成')) 
                && el.offsetParent !== null
              );
              if (okBtn) {
                console.log('[wechat] Clicking Confirm button');
                okBtn.click();
              } else {
                console.error('[wechat] Confirm button NOT found in modal');
              }
            })()
          `);
          
          console.log('[wechat] Cover upload flow completed.');
          await sleep(4000);
        } catch (e) {
          console.error(`[wechat] Cover upload failed: ${e}.`);
        }
    }

    // --- 确保返回编辑器上下文 ---
    console.log('[wechat] Re-focusing editor...');
    await sleep(3000);
    // 等待 ProseMirror 编辑器出现（最多等 15 秒）
    const editorSelector = '#ueditor_0 .mock-iframe-body .ProseMirror, .ProseMirror';
    let editorFound = false;
    for (let i = 0; i < 15; i++) {
      const found = await evaluate<boolean>(session, `
        !!(document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror') || document.querySelector('.ProseMirror'))
      `);
      if (found) { editorFound = true; break; }
      await sleep(1000);
    }
    if (!editorFound) {
      console.warn('[wechat] ProseMirror editor not found after waiting, proceeding anyway...');
    } else {
      console.log('[wechat] Editor found, focusing...');
    }
    await evaluate(session, `
        (function() {
           const el = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror') || document.querySelector('.ProseMirror');
           if (el) {
              el.scrollIntoView({ behavior: 'smooth', block: 'center' });
              el.focus();
           }
        })()
    `);
    await sleep(500);

    console.log('[wechat] Clicking on editor...');
    await clickElement(session, editorSelector);
    await sleep(1000);

    if (effectiveHtmlFile && fs.existsSync(effectiveHtmlFile)) {
      console.log(`[wechat] Copying HTML content from: ${effectiveHtmlFile}`);
      
      const useRemoteServer = !!REMOTE_CDP_URL;
      if (useRemoteServer && contentImages.length > 0) {
        console.log('[wechat] 远程模式: 准备同步图片...');
        // 如果是远程模式，且有图片，可以在这里加入同步逻辑
      }
      
      await copyHtmlFromBrowser(cdp, effectiveHtmlFile, contentImages, useRemoteServer);
      
      // 直接注入 HTML 内容到编辑器（不依赖剪贴板）
      await sleep(1000);
      const injectedContent = (globalThis as any).__wechatHtmlContent;
      if (injectedContent) {
        console.log('[wechat] 直接注入 HTML 内容到编辑器...');
        await evaluate(session, `
          (function(c) {
            const prose = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror') || document.querySelector('.ProseMirror');
            if (!prose) return 'ProseMirror not found';
            prose.innerHTML = c;
            prose.dispatchEvent(new Event('input', { bubbles: true }));
            prose.dispatchEvent(new Event('change', { bubbles: true }));
            return 'OK: ' + prose.innerHTML.length;
          })(${JSON.stringify(injectedContent)})
        `);
        await sleep(2000);
      }

      const editorHasContent = await evaluate<boolean>(session, `
        (function() {
          const editor = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror') || document.querySelector('.ProseMirror');
          if (!editor) return false;
          const text = editor.innerText?.trim() || '';
          return text.length > 0;
        })()
      `);
      if (editorHasContent) {
        console.log('[wechat] Body content verified OK.');
      } else {
        console.warn('[wechat] Body content verification failed: editor appears empty after injection.');
      }

      if (contentImages.length > 0) {
        console.log(`[wechat] Inserting ${contentImages.length} images...`);
        for (let i = 0; i < contentImages.length; i++) {
          const img = contentImages[i]!;
          console.log(`[wechat] [${i + 1}/${contentImages.length}] Processing: ${img.placeholder}`);

          const found = await selectAndReplacePlaceholder(session, img.placeholder);
          if (!found) {
            console.warn(`[wechat] Placeholder not found: ${img.placeholder}`);
            continue;
          }

          await sleep(500);

          console.log(`[wechat] Copying image: ${path.basename(img.localPath)}`);
          await copyImageToClipboard(img.localPath);
          await sleep(300);

          console.log('[wechat] Deleting placeholder with Backspace...');
          await pressDeleteKey(session);
          await sleep(200);

          console.log('[wechat] Pasting image...');
          await pasteFromClipboardInEditor(session);
          await sleep(3000);
          await removeExtraEmptyLineAfterImage(session);
        }
        console.log('[wechat] All images inserted.');
      }
    } else if (content) {
      for (const img of images) {
        if (fs.existsSync(img)) {
          console.log(`[wechat] Pasting image: ${img}`);
          await copyImageToClipboard(img);
          await sleep(500);
          await pasteInEditor(session);
          await sleep(2000);
          await removeExtraEmptyLineAfterImage(session);
        }
      }

      console.log('[wechat] Injecting content via innerHTML...');
      // 使用 innerHTML 直接注入内容（针对 WeChat 编辑器的 mock-iframe 结构）
      const injectedContent = JSON.stringify(content);
      await evaluate(session, `
        (function(c) {
          // WeChat 编辑器使�?mock-iframe 结构
          const prose = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror') || document.querySelector('.ProseMirror');
          if (!prose) return 'ProseMirror not found';
          prose.innerHTML = c;
          prose.dispatchEvent(new Event('input', { bubbles: true }));
          prose.dispatchEvent(new Event('change', { bubbles: true }));
          return 'OK: ' + prose.innerHTML.length;
        })(${injectedContent})
      `);
      await sleep(2000);

      const editorHasContent = await evaluate<boolean>(session, `
        (function() {
          const editor = document.querySelector('#ueditor_0 .mock-iframe-body .ProseMirror') || document.querySelector('.ProseMirror');
          if (!editor) return false;
          const text = editor.innerText?.trim() || '';
          return text.length > 0;
        })()
      `);
      if (editorHasContent) {
        console.log('[wechat] Body content verified OK.');
      } else {
        console.warn('[wechat] Body content verification failed: editor appears empty after injection.');
      }
    }

    // --- 摘要填写 ---
    if (effectiveSummary) {
      console.log(`[wechat] Filling summary (after content paste): ${effectiveSummary.substring(0, 100)}...`);
      await evaluate(session, `
        (function() {
          const textarea = document.querySelector('#js_description');
          if (textarea) {
            textarea.value = ${JSON.stringify(effectiveSummary)};
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
          }
        })()
      `);
      await sleep(1000);
      const summaryValue = await evaluate<string>(session, `document.querySelector('#js_description')?.value || ''`);
      if (summaryValue.length > 0) {
        console.log('[wechat] Summary verified OK.');
      }
    }

    console.log('[wechat] Saving as draft...');
    await evaluate(session, `document.querySelector('#js_submit button').click()`);
    await sleep(3000);

    const saved = await evaluate<boolean>(session, `!!document.querySelector('.weui-desktop-toast')`);
    if (saved) {
      console.log('[wechat] Draft saved successfully!');
    } else {
      console.log('[wechat] Waiting for save confirmation...');
      await sleep(5000);
    }

    console.log('[wechat] Done. Browser window left open.');
  } finally {
    if (cdp) await cdp.close();
  }
}

function printUsage(): never {
  console.log(`Post article to WeChat Official Account

Usage:
  npx -y bun wechat-article.ts [options]

Options:
  --title <text>     Article title (auto-extracted from markdown)
  --content <text>   Article content (use with --image)
  --html <path>      HTML file to paste (alternative to --content)
  --markdown <path>  Markdown file to convert and post (recommended)
  --theme <name>     Theme for markdown (default, grace, simple, modern)
  --color <name|hex> Primary color (blue, green, vermilion, etc. or hex)
  --no-cite          Disable bottom citations for ordinary external links in markdown mode
  --author <name>    Author name
  --summary <text>   Article summary
  --image <path>     Content image, can repeat (only with --content)
  --submit           Save as draft
  --cover <path>     Cover image for the article
  --profile <dir>    Chrome profile directory
  --account <alias>  Select account by alias (for multi-account setups)
  --cdp-port <port>  Connect to existing Chrome debug port instead of launching new instance

Examples:
  npx -y bun wechat-article.ts --markdown article.md
  npx -y bun wechat-article.ts --markdown article.md --theme grace --submit
  npx -y bun wechat-article.ts --markdown article.md --no-cite
  npx -y bun wechat-article.ts --title "标题" --content "内容" --image img.png
  npx -y bun wechat-article.ts --title "标题" --html article.html --submit

Markdown mode:
  Images in markdown are converted to placeholders. After pasting HTML,
  each placeholder is selected, scrolled into view, deleted, and replaced
  with the actual image via paste. Ordinary external links are converted to
  bottom citations by default.
`);
  process.exit(0);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  if (args.includes('--help') || args.includes('-h')) printUsage();

  const images: string[] = [];
  let title: string | undefined;
  let content: string | undefined;
  let htmlFile: string | undefined;
  let markdownFile: string | undefined;
  let theme: string | undefined;
  let color: string | undefined;
  let citeStatus = true;
  let author: string | undefined;
  let summary: string | undefined;
  let submit = false;
  let profileDir: string | undefined;
  let cdpPort: number | undefined;
  let accountAlias: string | undefined;

  const options: ArticleOptions = { title: '' };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--title' && args[i + 1]) title = args[++i];
    else if (arg === '--content' && args[i + 1]) content = args[++i];
    else if (arg === '--html' && args[i + 1]) htmlFile = args[++i];
    else if (arg === '--markdown' && args[i + 1]) markdownFile = args[++i];
    else if (arg === '--theme' && args[i + 1]) theme = args[++i];
    else if (arg === '--color' && args[i + 1]) color = args[++i];
    else if (arg === '--cite') citeStatus = true;
    else if (arg === '--no-cite') citeStatus = false;
    else if (arg === '--author' && args[i + 1]) author = args[++i];
    else if (arg === '--summary' && args[i + 1]) summary = args[++i];
    else if (arg === '--image' && args[i + 1]) images.push(args[++i]!);
    else if (arg === '--submit') submit = true;
    else if (arg === '--cover' && args[i + 1]) options.cover = args[++i];
    else if (arg === '--profile' && args[i + 1]) profileDir = args[++i];
    else if (arg === '--account' && args[i + 1]) accountAlias = args[++i];
    else if (arg === '--cdp-port' && args[i + 1]) cdpPort = parseInt(args[++i]!, 10);
  }

  const extConfig = loadWechatExtendConfig();
  const resolved = resolveAccount(extConfig, accountAlias);
  if (resolved.name) console.log(`[wechat] Account: ${resolved.name} (${resolved.alias})`);

  if (!author && resolved.default_author) author = resolved.default_author;

  if (!profileDir && resolved.alias) {
    profileDir = resolved.chrome_profile_path || getAccountProfileDir(resolved.alias);
  }

  if (!markdownFile && !htmlFile && !title) { console.error('Error: --title is required (or use --markdown/--html)'); process.exit(1); }
  if (!markdownFile && !htmlFile && !content) { console.error('Error: --content, --html, or --markdown is required'); process.exit(1); }

  await postArticle({ title: title || '', content, htmlFile, markdownFile, theme, color, citeStatus, author, summary, images, submit, profileDir, cdpPort, cover: options.cover });
}

await main().then(() => {
  process.exit(0);
}).catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
