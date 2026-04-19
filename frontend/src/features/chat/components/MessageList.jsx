import { useEffect, useRef, useMemo } from 'react';
import { parseContentSegments } from '../../../utils/chart.js';
import { renderMarkdown } from '../../../utils/markdown.js';
import ChartBlock from './ChartBlock.jsx';
import MsgMeta from './MsgMeta.jsx';

/* ── Markdown block with copy buttons on <pre> ── */
function MarkdownBlock({ html }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.querySelectorAll('pre').forEach(pre => {
      if (pre.querySelector('.pre-copy')) return;
      pre.style.position = 'relative';
      const btn = document.createElement('button');
      btn.className   = 'pre-copy';
      btn.textContent = 'COPY';
      btn.onclick = () => {
        navigator.clipboard.writeText(pre.querySelector('code')?.innerText || pre.innerText);
        btn.textContent = 'COPIED';
        setTimeout(() => (btn.textContent = 'COPY'), 2000);
      };
      pre.prepend(btn);
    });
    ref.current.querySelectorAll('table').forEach(table => {
      if (table.parentElement?.classList.contains('table-wrap')) return;
      const w = document.createElement('div');
      w.className = 'table-wrap';
      table.parentNode.insertBefore(w, table);
      w.appendChild(table);
    });
  }, [html]);

  return <div ref={ref} dangerouslySetInnerHTML={{ __html: html }} />;
}

/* ── Single AI message body ── */
function AIBody({ content }) {
  const segments = useMemo(() => parseContentSegments(content), [content]);

  return (
    <>
      {segments.map((seg, i) =>
        seg.type === 'chart'
          ? <ChartBlock key={i} config={seg.config} />
          : <MarkdownBlock key={i} html={renderMarkdown(seg.content)} />
      )}
    </>
  );
}

/* ── Single message group ── */
function MessageGroup({ msg }) {
  const isUser = msg.role === 'user';

  function copyRaw() {
    navigator.clipboard.writeText(msg.content);
  }

  return (
    <div className="msg-group">
      <div className={`msg-label${isUser ? ' user-label' : ''}`}>
        {isUser ? '[ OPERATOR // ROOT ]' : (
          <>
            [ HET-X // SECURE_SHELL ]
            {msg.streaming && (
              <span style={{ color: 'var(--t3)', fontWeight: 400, fontSize: '9px', letterSpacing: '.5px' }}>
                &nbsp;PROCESSING
              </span>
            )}
          </>
        )}
      </div>

      {isUser ? (
        <div className="user-msg">{msg.content}</div>
      ) : (
        <div className="ai-msg">
          {msg.error ? (
            <span style={{ color: 'var(--red)', fontSize: '12px' }}>ERROR // {msg.error}</span>
          ) : msg.streaming ? (
            <>
              <div className="stream-raw">{msg.content}</div>
              <span className="cursor" />
            </>
          ) : (
            <AIBody content={msg.content} />
          )}
        </div>
      )}

      {!isUser && !msg.streaming && !msg.error && msg.meta && (
        <MsgMeta meta={msg.meta} content={msg.content} />
      )}

      {!isUser && !msg.streaming && !msg.error && msg.content && (
        <button className="msg-copy" onClick={copyRaw}>COPY</button>
      )}
    </div>
  );
}

/* ── Message list ── */
export default function MessageList({ messages }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <>
      {messages.map(msg => (
        <MessageGroup key={msg.id} msg={msg} />
      ))}
      <div ref={bottomRef} />
    </>
  );
}
