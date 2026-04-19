import { useState, useRef } from 'react';
import Suggestions from './Suggestions.jsx';
import { OptionsPanel } from '../../../features/settings/index.js';

export default function InputBar({ onSend, busy }) {
  const [text, setText]         = useState('');
  const [sugOpen, setSugOpen]   = useState(false);
  const [optsOpen, setOptsOpen] = useState(false);
  const [stream, setStream]     = useState(true);
  const textareaRef             = useRef(null);

  function resize() {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
  }

  function handleChange(e) {
    setText(e.target.value);
    resize();
    setSugOpen(true);
  }

  function handleFocus() { setSugOpen(true); }
  function handleBlur()  { setTimeout(() => setSugOpen(false), 150); }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
    if (e.key === 'Escape') setSugOpen(false);
  }

  function submit() {
    const msg = text.trim();
    if (!msg || busy) return;
    onSend(msg, stream);
    setText('');
    setSugOpen(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }

  function pickSuggestion(s) {
    setText(s);
    setSugOpen(false);
    textareaRef.current?.focus();
    setTimeout(resize, 0);
  }

  return (
    <div className="input-area">
      <div className="input-shell">

        {/* Suggestions */}
        {sugOpen && (
          <Suggestions query={text} onPick={pickSuggestion} />
        )}

        {/* Terminal bar */}
        <div className="terminal-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="status-dot" />
            <span>ONLINE</span>
          </div>
          <span>RAG_CONSOLE // LLAMA-3.3-70B</span>
        </div>

        {/* Input row */}
        <div className="input-main">
          <div className="term-indicator">HET-X &gt;</div>
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            placeholder="Enter query or command..."
            onChange={handleChange}
            onFocus={handleFocus}
            onBlur={handleBlur}
            onKeyDown={handleKey}
          />
          <button className="btn-send" onClick={submit} disabled={busy || !text.trim()}>
            <svg viewBox="0 0 24 24">
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
          </button>
        </div>

        {/* Options panel */}
        <OptionsPanel open={optsOpen} />

        {/* Footer */}
        <div className="input-footer">
          <label className="stream-toggle">
            <input
              type="checkbox"
              checked={stream}
              onChange={e => setStream(e.target.checked)}
            />
            <span>STREAM</span>
          </label>
          <button
            className={`opts-toggle${optsOpen ? ' active' : ''}`}
            onClick={() => setOptsOpen(o => !o)}
            title="Options"
          >
            <svg viewBox="0 0 16 16">
              <line x1="2" y1="4"  x2="14" y2="4"  />
              <line x1="2" y1="8"  x2="14" y2="8"  />
              <line x1="2" y1="12" x2="14" y2="12" />
              <circle cx="5"  cy="4"  r="1.5" fill="currentColor" stroke="none" />
              <circle cx="10" cy="8"  r="1.5" fill="currentColor" stroke="none" />
              <circle cx="6"  cy="12" r="1.5" fill="currentColor" stroke="none" />
            </svg>
          </button>
        </div>

      </div>
    </div>
  );
}
