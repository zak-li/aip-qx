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
          <span>RAG_CONSOLE // LLAMA-3.3-70B</span>
        </div>

        {/* Input row */}
        <div className="input-main">
          <div className="term-indicator">HET-X $</div>
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
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 8H13" />
              <path d="M17 8L20 8" />
              <path d="M11 16L20 16" />
              <path d="M4 16H7" />
              <circle cx="9" cy="16" r="2" />
              <circle cx="15" cy="8" r="2" />
            </svg>
          </button>
        </div>

      </div>
    </div>
  );
}
