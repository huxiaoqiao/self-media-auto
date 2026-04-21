/**
 * HTML Sanitizer for WeChat Editor Compatibility
 *
 * Problem: Xiaohu's HTML uses <section> tags with modern CSS (display: flex, etc.)
 * that the WeChat editor's clipboard parser doesn't understand.
 *
 * Solution: Transform Xiaohu's HTML into standard HTML tags that WeChat supports:
 * <p>, <h1-h6>, <blockquote>, <ul/ol>, <li>, <strong>, <em>, <a>, <img>, <table>
 *
 * This sanitizer converts flex/grid layouts to table-based layouts,
 * and removes unsupported CSS properties.
 */

interface TransformRule {
  pattern: RegExp;
  replacement: string | ((match: string, ...args: string[]) => string);
}

/**
 * Convert Xiaohu HTML to WeChat-compatible HTML
 */
export function sanitizeHtmlForWechat(html: string): string {
  let result = html;

  // 1. Remove CF_HTML header if present (from clipboard)
  result = removeCfHtmlHeader(result);

  // 2. Convert section with flex to table-based layout
  result = convertFlexSections(result);

  // 3. Remove unsupported CSS properties
  result = removeUnsupportedCss(result);

  // 4. Convert section-based callouts to blockquotes
  result = convertCallouts(result);

  // 5. Clean up empty or redundant tags
  result = cleanupTags(result);

  // 6. Ensure proper paragraph structure
  result = normalizeParagraphs(result);

  return result;
}

/**
 * Remove Windows CF_HTML clipboard header
 */
function removeCfHtmlHeader(html: string): string {
  // CF_HTML format starts with Version:0.9 followed by StartHTML, EndHTML, etc.
  const cfHtmlPattern = /^Version:0\.9\r?\nStartHTML:\d+\r?\nEndHTML:\d+\r?\nStartFragment:\d+\r?\nEndFragment:\d+\r?\n.*?(<html|<!DOCTYPE)/i;
  return html.replace(cfHtmlPattern, '$1');
}

/**
 * Convert <section style="display:flex;..."> to table structure
 */
function convertFlexSections(html: string): string {
  // Pattern: <section style="display:flex; flex-direction:row; ... ">...</section>
  // Convert to a table with the same content

  // Handle horizontal flex (flex-direction: row or default)
  const rowFlexPattern = /<section\s+style="([^"]*display:\s*flex[^"]*)"[^>]*>([\s\S]*?)<\/section>/gi;

  let result = html;
  result = result.replace(rowFlexPattern, (match, style, content) => {
    // Check if it's a horizontal flex
    const isRow = /flex-direction:\s*row/i.test(style) || !/flex-direction:\s*column/i.test(style);

    if (isRow) {
      // Convert to table structure
      return `<table style="width:100%;border-collapse:collapse;"><tbody><tr><td>${content}</td></tr></tbody></table>`;
    } else {
      // Column flex - just remove the flex styling and keep content
      const cleanedStyle = style.replace(/display:\s*flex[^;]*;?/gi, '').replace(/;{2,}/g, ';').replace(/^;|;$/g, '');
      return `<section${cleanedStyle ? ` style="${cleanedStyle}"` : ''}>${content}</section>`;
    }
  });

  return result;
}

/**
 * Remove CSS properties that WeChat editor doesn't support
 */
function removeUnsupportedCss(html: string): string {
  const unsupportedProperties = [
    'display:flex',
    'display:-webkit-flex',
    'display:grid',
    'flex-direction',
    'flex-wrap',
    'justify-content',
    'align-items',
    'align-content',
    'gap',
    'grid-template-columns',
    'grid-template-rows',
    'grid-area',
    'position:fixed',
    'position:absolute',
    'left:-9999px',
    'top:-9999px',
    'user-select:none',
    '-webkit-backdrop-filter',
    'backdrop-filter',
  ];

  let result = html;

  for (const prop of unsupportedProperties) {
    // Remove the entire style attribute if it only contains unsupported properties
    const singlePropPattern = new RegExp(`style="${prop}[^"]*"`, 'gi');
    result = result.replace(singlePropPattern, '');

    // Remove just the property from multi-value style
    const multiPropPattern = new RegExp(`${prop.replace(/[()]/g, '\\$&')}\\s*:[^;]+;?\\s*`, 'gi');
    result = result.replace(multiPropPattern, '');
  }

  // Clean up empty style attributes
  result = result.replace(/\s*style="\s*"/gi, '');
  result = result.replace(/style="\s*;(?=["'])/gi, 'style="');
  result = result.replace(/(<[^>]+)\s+style=""\s*([^>]*>)/gi, '$1$2');

  return result;
}

/**
 * Convert section-based callouts to blockquote
 */
function convertCallouts(html: string): string {
  // Pattern: <section style="border-left: X; background: Y;">...</section>
  // These are often callout boxes - convert to blockquote

  const calloutPattern = /<section\s+style="([^"]*(?:border-left|border-color|background)[^"]*)"[^>]*>([\s\S]*?)<\/section>/gi;

  let result = html.replace(calloutPattern, (match, style, content) => {
    // Check if it looks like a callout (has border or background)
    const hasBorder = /border-left|border-color/i.test(style);
    const hasBg = /background/i.test(style);

    if (hasBorder || hasBg) {
      // Extract colors if present
      const borderMatch = style.match(/border-left:\s*([^;]+)/i) || style.match(/border-color:\s*([^;]+)/i);
      const bgMatch = style.match(/background:\s*([^;]+)/i);

      const borderColor = borderMatch ? borderMatch[1].trim() : '#ccc';
      const bgColor = bgMatch ? bgMatch[1].trim() : 'transparent';

      // Clean the style and create a blockquote
      const cleanedStyle = `border-left: ${borderColor}; background: ${bgColor}; padding: 10px 15px; margin: 10px 0;`;
      return `<blockquote style="${cleanedStyle}">${content}</blockquote>`;
    }
    return match;
  });

  return result;
}

/**
 * Clean up empty, redundant, or malformed tags
 */
function cleanupTags(html: string): string {
  let result = html;

  // Remove empty paragraphs
  result = result.replace(/<p[^>]*>\s*<\/p>/gi, '');

  // Remove empty sections
  result = result.replace(/<section[^>]*>\s*<\/section>/gi, '');
  result = result.replace(/<section[^>]*>\s*<\/section>/gi, '');

  // Remove multiple consecutive br tags
  result = result.replace(/(<br\s*\/?>\s*){3,}/gi, '<br>');

  // Clean up whitespace-only text nodes in paragraphs
  result = result.replace(/<p([^>]*)>\s+<\/p>/gi, '<p$1></p>');

  // Remove zero-width characters
  result = result.replace(/[\u200B-\u200D\uFEFF]/g, '');

  return result;
}

/**
 * Normalize paragraph structure
 */
function normalizeParagraphs(html: string): string {
  let result = html;

  // Ensure text content is wrapped in paragraphs
  // Split by double newlines and wrap non-HTML content

  // Convert multiple <br> to paragraph separation
  result = result.replace(/<br\s*\/?>\s*<br\s*\/?>/gi, '</p><p>');

  // Ensure standalone text is wrapped
  // This is a simplified approach - for full normalization we'd need DOM parsing

  return result;
}

/**
 * Generate CF_HTML header for Windows clipboard
 * This ensures the HTML is properly parsed by WeChat editor
 */
export function wrapForClipboard(html: string): string {
  const fragment = `<!--StartFragment-->${html}<!--EndFragment-->`;
  const fullHtml = `<html><body>${fragment}</body></html>`;

  const startOffset = `Version:0.9
StartHTML:0000000000
EndHTML:0000000000
StartFragment:0000000000
EndFragment:0000000000
`.length;

  const htmlStart = fullHtml.indexOf('<html>');
  const fragmentStart = fullHtml.indexOf('<!--StartFragment-->');
  const fragmentEnd = fullHtml.indexOf('<!--EndFragment-->') + '<!--EndFragment-->'.length;

  const totalLength = fullHtml.length + startOffset;

  return `Version:0.9
StartHTML:${String(htmlStart + startOffset).padStart(10, '0')}
EndHTML:${String(totalLength).padStart(10, '0')}
StartFragment:${String(fragmentStart + startOffset).padStart(10, '0')}
EndFragment:${String(fragmentEnd + startOffset).padStart(10, '0')}
${fullHtml}`;
}

/**
 * Main entry point: sanitize and prepare for clipboard
 */
export function prepareForWechatClipboard(html: string): string {
  const sanitized = sanitizeHtmlForWechat(html);
  return wrapForClipboard(sanitized);
}

// CLI for testing
if (import.meta.url === `file://${process.argv[1]}`) {
  const html = process.argv[2] || '<section style="display:flex"><p>Test</p></section>';
  console.log(prepareForWechatClipboard(html));
}
