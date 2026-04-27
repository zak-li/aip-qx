// Post-process rendered HTML: wrap known entity references in clickable pills.
// Walks text nodes, skips <code>/<pre>/<a>, replaces matches with <button>.

const KIND_ICON = {
  asset: '▣',
  org:   '◎',
  tx:    '⇋',
};

function buildRegex(items) {
  // Build a single regex from unique ids/tokens (min length 6).
  const tokens = new Set();
  for (const it of items) {
    if (it.id && String(it.id).length >= 6) tokens.add(String(it.id));
    // Also match secondary identifiers (e.g. ISIN, MSP id, fabric_tx_id) if they're in haystack words
  }
  if (!tokens.size) return null;
  const escaped = [...tokens].map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  escaped.sort((a, b) => b.length - a.length); // longer first for correct matching
  // Word-ish boundary: not alphanumeric on either side
  return new RegExp(`(?<![\\w-])(${escaped.join('|')})(?![\\w-])`, 'g');
}

function kindOf(items, id) {
  for (const it of items) if (String(it.id) === String(id)) return it.kind;
  return null;
}

const BLOCKED = new Set(['CODE', 'PRE', 'A', 'BUTTON', 'SCRIPT', 'STYLE']);

export function pillifyContainer(rootEl, items) {
  if (!rootEl || !items || items.length === 0) return;
  const re = buildRegex(items);
  if (!re) return;

  const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      let p = node.parentElement;
      while (p && p !== rootEl) {
        if (BLOCKED.has(p.tagName)) return NodeFilter.FILTER_REJECT;
        if (p.classList?.contains('entity-pill')) return NodeFilter.FILTER_REJECT;
        p = p.parentElement;
      }
      return re.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
    },
  });

  const toProcess = [];
  let n; while ((n = walker.nextNode())) toProcess.push(n);

  for (const textNode of toProcess) {
    const txt = textNode.nodeValue;
    re.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0, m;
    while ((m = re.exec(txt)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(txt.slice(last, m.index)));
      const kind = kindOf(items, m[1]);
      if (kind) {
        const btn = document.createElement('button');
        btn.className = `entity-pill entity-pill--${kind}`;
        btn.type = 'button';
        btn.dataset.kind = kind;
        btn.dataset.id   = m[1];
        btn.innerHTML = `<span class="ep-icon">${KIND_ICON[kind] || '•'}</span><span class="ep-id">${m[1]}</span>`;
        frag.appendChild(btn);
      } else {
        frag.appendChild(document.createTextNode(m[1]));
      }
      last = m.index + m[1].length;
    }
    if (last < txt.length) frag.appendChild(document.createTextNode(txt.slice(last)));
    textNode.parentNode.replaceChild(frag, textNode);
  }
}
