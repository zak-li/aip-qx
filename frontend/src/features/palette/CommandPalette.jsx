import { useEffect, useMemo, useRef, useState } from 'react';
import { usePaletteStore } from './paletteStore.js';
import { useAuthStore } from '../auth/hooks/useAuth.js';
import { fetchSearchIndex, searchIndex } from '../../services/searchService.js';

const KIND_META = {
  asset: { label: 'ASSET', icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3"  width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
  )},
  org:   { label: 'ORG', icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h18" />
      <path d="M5 21V7l7-4 7 4v14" />
      <path d="M9 9h.01M9 13h.01M9 17h.01M14 9h.01M14 13h.01M14 17h.01" />
    </svg>
  )},
  tx:    { label: 'TX', icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="17 1 21 5 17 9" />
      <path d="M3 11V9a4 4 0 0 1 4-4h14" />
      <polyline points="7 23 3 19 7 15" />
      <path d="M21 13v2a4 4 0 0 1-4 4H3" />
    </svg>
  )},
};

export default function CommandPalette() {
  const open    = usePaletteStore(s => s.open);
  const items   = usePaletteStore(s => s.items);
  const loading = usePaletteStore(s => s.loading);
  const error   = usePaletteStore(s => s.error);
  const hide    = usePaletteStore(s => s.hide);
  const setItems   = usePaletteStore(s => s.setItems);
  const setLoading = usePaletteStore(s => s.setLoading);
  const setError   = usePaletteStore(s => s.setError);
  const user    = useAuthStore(s => s.user);

  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef  = useRef(null);

  useEffect(() => {
    if (!open) return;
    setQ(''); setActive(0);
    setTimeout(() => inputRef.current?.focus(), 10);
    if (!items.length && user && !loading) {
      setLoading(true);
      fetchSearchIndex()
        .then(setItems)
        .catch(e => setError(String(e)));
    }
  }, [open]); // eslint-disable-line

  const results = useMemo(() => searchIndex(items, q, 40), [items, q]);

  useEffect(() => { setActive(0); }, [q]);

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); hide(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp')   { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter')     { e.preventDefault(); const r = results[active]; if (r) selectItem(r); }
  }

  function selectItem(r) {
    window.dispatchEvent(new CustomEvent('palette:select', { detail: r }));
    hide();
  }

  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-idx="${active}"]`);
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [active]);

  if (!open) return null;

  return (
    <div className="palette-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) hide(); }}>
      <div className="palette" role="dialog" aria-label="Command palette">
        <div className="palette-input-wrap">
          <span className="palette-prompt">/</span>
          <input
            ref={inputRef}
            className="palette-input"
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search assets, organizations, transactions..."
            spellCheck={false}
            autoComplete="off"
          />
          <span className="palette-hint">ESC</span>
        </div>

        <div className="palette-list" ref={listRef}>
          {loading && <div className="palette-empty">Loading index...</div>}
          {error   && <div className="palette-empty palette-err">Error: {error}</div>}
          {!loading && !error && results.length === 0 && (
            <div className="palette-empty">No results.</div>
          )}
          {results.map((r, i) => {
            const meta = KIND_META[r.kind] || { label: r.kind.toUpperCase(), icon: null };
            return (
              <button
                key={`${r.kind}-${r.id}-${i}`}
                data-idx={i}
                className={`palette-item${i === active ? ' active' : ''}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => selectItem(r)}
              >
                <span className="palette-icon">{meta.icon}</span>
                <span className="palette-main">
                  <span className="palette-title">{r.title}</span>
                  {r.sub && <span className="palette-sub">{r.sub}</span>}
                </span>
                <span className="palette-kind">{meta.label}</span>
              </button>
            );
          })}
        </div>

        <div className="palette-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
