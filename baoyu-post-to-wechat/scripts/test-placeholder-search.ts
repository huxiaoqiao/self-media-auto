/**
 * Test: Placeholder search logic validation
 * 
 * Verifies the core bug fix: placeholder search must handle text nodes that have
 * been split across multiple DOM nodes (as happens when ProseMirror re-renders
 * after an image paste operation).
 * 
 * Run: npx -y bun test-placeholder-search.ts
 */

// Simulate the search logic extracted from selectAndReplacePlaceholder

interface FakeTextNode {
  textContent: string;
}

interface SearchResult {
  found: boolean;
  startNodeIdx?: number;
  startOffset?: number;
  endNodeIdx?: number;
  endOffset?: number;
}

/**
 * Phase 2: Single-node search (original logic, post-normalize)
 */
function searchSingleNode(textNodes: FakeTextNode[], placeholder: string): SearchResult {
  for (let i = 0; i < textNodes.length; i++) {
    const text = textNodes[i]!.textContent;
    let searchStart = 0;
    let idx: number;
    while ((idx = text.indexOf(placeholder, searchStart)) !== -1) {
      const afterIdx = idx + placeholder.length;
      const charAfter = text[afterIdx];
      if (charAfter === undefined || !/\d/.test(charAfter)) {
        return {
          found: true,
          startNodeIdx: i,
          startOffset: idx,
          endNodeIdx: i,
          endOffset: afterIdx,
        };
      }
      searchStart = afterIdx;
    }
  }
  return { found: false };
}

/**
 * Phase 3: Cross-node search (new fallback logic)
 */
function searchCrossNode(textNodes: FakeTextNode[], placeholder: string): SearchResult {
  let fullText = '';
  const map: Array<{ nodeIdx: number; startInFull: number; length: number }> = [];
  for (let i = 0; i < textNodes.length; i++) {
    const t = textNodes[i]!.textContent;
    map.push({ nodeIdx: i, startInFull: fullText.length, length: t.length });
    fullText += t;
  }

  let searchStart = 0;
  let idx: number;
  while ((idx = fullText.indexOf(placeholder, searchStart)) !== -1) {
    const afterIdx = idx + placeholder.length;
    const charAfter = fullText[afterIdx];
    if (charAfter === undefined || !/\d/.test(charAfter)) {
      let startNodeIdx: number | undefined, startOffset: number | undefined;
      let endNodeIdx: number | undefined, endOffset: number | undefined;
      for (const m of map) {
        const mEnd = m.startInFull + m.length;
        if (startNodeIdx === undefined && idx >= m.startInFull && idx < mEnd) {
          startNodeIdx = m.nodeIdx;
          startOffset = idx - m.startInFull;
        }
        if (afterIdx >= m.startInFull && afterIdx <= mEnd) {
          endNodeIdx = m.nodeIdx;
          endOffset = afterIdx - m.startInFull;
          break;
        }
      }
      if (startNodeIdx !== undefined && endNodeIdx !== undefined) {
        return { found: true, startNodeIdx, startOffset, endNodeIdx, endOffset };
      }
    }
    searchStart = afterIdx;
  }
  return { found: false };
}

// ────────────────────── Test Cases ──────────────────────

let passed = 0;
let failed = 0;

function assert(label: string, condition: boolean) {
  if (condition) {
    console.log(`  ✅ ${label}`);
    passed++;
  } else {
    console.error(`  ❌ ${label}`);
    failed++;
  }
}

console.log('\n=== Test 1: All placeholders in single text node (happy path) ===');
{
  const nodes: FakeTextNode[] = [
    { textContent: '一些文字 WECHATIMGPH_1 更多文字 WECHATIMGPH_2 还有 WECHATIMGPH_3 结尾' },
  ];
  assert('Find WECHATIMGPH_1', searchSingleNode(nodes, 'WECHATIMGPH_1').found);
  assert('Find WECHATIMGPH_2', searchSingleNode(nodes, 'WECHATIMGPH_2').found);
  assert('Find WECHATIMGPH_3', searchSingleNode(nodes, 'WECHATIMGPH_3').found);
}

console.log('\n=== Test 2: Placeholder split across two text nodes (the bug) ===');
{
  // Simulates ProseMirror splitting "WECHATIMGPH_2" across two <span> elements
  const nodes: FakeTextNode[] = [
    { textContent: '一些文字 ' },
    { textContent: 'WECHATIM' },    // first half of WECHATIMGPH_2
    { textContent: 'GPH_2' },       // second half
    { textContent: ' 还有 WECHATIMGPH_3 结尾' },
  ];
  
  // Single-node search should FAIL for the split placeholder
  assert('Single-node CANNOT find split WECHATIMGPH_2', !searchSingleNode(nodes, 'WECHATIMGPH_2').found);
  
  // Cross-node search should SUCCEED
  const result = searchCrossNode(nodes, 'WECHATIMGPH_2');
  assert('Cross-node finds split WECHATIMGPH_2', result.found);
  assert('Start node is index 1', result.startNodeIdx === 1);
  assert('Start offset is 0', result.startOffset === 0);
  assert('End node is index 2', result.endNodeIdx === 2);
  assert('End offset is 5', result.endOffset === 5);
  
  // WECHATIMGPH_3 is intact in a single node — both should find it
  assert('Single-node finds intact WECHATIMGPH_3', searchSingleNode(nodes, 'WECHATIMGPH_3').found);
  assert('Cross-node finds intact WECHATIMGPH_3', searchCrossNode(nodes, 'WECHATIMGPH_3').found);
}

console.log('\n=== Test 3: Exact-match guard — WECHATIMGPH_1 should not match inside WECHATIMGPH_10 ===');
{
  const nodes: FakeTextNode[] = [
    { textContent: 'prefix WECHATIMGPH_10 suffix' },
  ];
  assert('WECHATIMGPH_1 does NOT match WECHATIMGPH_10 (single)', !searchSingleNode(nodes, 'WECHATIMGPH_1').found);
  assert('WECHATIMGPH_1 does NOT match WECHATIMGPH_10 (cross)', !searchCrossNode(nodes, 'WECHATIMGPH_1').found);
  assert('WECHATIMGPH_10 DOES match (single)', searchSingleNode(nodes, 'WECHATIMGPH_10').found);
  assert('WECHATIMGPH_10 DOES match (cross)', searchCrossNode(nodes, 'WECHATIMGPH_10').found);
}

console.log('\n=== Test 4: All three placeholders in separate nodes ===');
{
  const nodes: FakeTextNode[] = [
    { textContent: 'WECHATIMGPH_1' },
    { textContent: ' some text ' },
    { textContent: 'WECHATIMGPH_2' },
    { textContent: ' more ' },
    { textContent: 'WECHATIMGPH_3' },
  ];
  assert('Find PH_1 (single)', searchSingleNode(nodes, 'WECHATIMGPH_1').found);
  assert('Find PH_2 (single)', searchSingleNode(nodes, 'WECHATIMGPH_2').found);
  assert('Find PH_3 (single)', searchSingleNode(nodes, 'WECHATIMGPH_3').found);
}

console.log('\n=== Test 5: Placeholder at boundary — split at underscore ===');
{
  // "WECHATIMGPH_" in one node, "2" in the next
  const nodes: FakeTextNode[] = [
    { textContent: 'text WECHATIMGPH_' },
    { textContent: '2 more text' },
  ];
  assert('Single-node CANNOT find boundary-split PH_2', !searchSingleNode(nodes, 'WECHATIMGPH_2').found);
  const result = searchCrossNode(nodes, 'WECHATIMGPH_2');
  assert('Cross-node finds boundary-split PH_2', result.found);
  assert('Start offset is 5', result.startOffset === 5);
  assert('End offset is 1', result.endOffset === 1);
}

console.log('\n=== Test 6: After first image removed, remaining placeholders still found ===');
{
  // Simulates state after WECHATIMGPH_1 was replaced with an image:
  // PH_1 is gone, PH_2 got split, PH_3 is intact
  const nodes: FakeTextNode[] = [
    { textContent: '段落一的内容。' },
    // (image element would be here — not a text node)
    { textContent: '段落二 WECHAT' },
    { textContent: 'IMGPH_2 段落三 ' },
    { textContent: 'WECHATIMGPH_3 结尾。' },
  ];
  
  assert('PH_1 is gone', !searchCrossNode(nodes, 'WECHATIMGPH_1').found);
  assert('Cross-node finds split PH_2', searchCrossNode(nodes, 'WECHATIMGPH_2').found);
  assert('Cross-node finds intact PH_3', searchCrossNode(nodes, 'WECHATIMGPH_3').found);
}

// ────────────────────── Summary ──────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed, ${passed + failed} total`);
if (failed > 0) {
  console.error('\n⚠️  SOME TESTS FAILED');
  process.exit(1);
} else {
  console.log('\n✅ ALL TESTS PASSED');
}
