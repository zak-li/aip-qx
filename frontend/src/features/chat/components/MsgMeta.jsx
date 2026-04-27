import { useOptsStore } from '../../settings/store/optsStore.js';

export default function MsgMeta({ meta, content }) {
  const stylePreset = useOptsStore(s => s.stylePreset);

  const tokEst   = Math.round((content || '').length / 4);
  const timeStr  = meta?.time_ms ? `${(meta.time_ms / 1000).toFixed(2)}s` : '—';

  return (
    <div className="msg-info">
      <span className="msg-info-item" title="Response time">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <polyline points="12 7 12 12 15 14" />
        </svg>
        <span className="val">{timeStr}</span>
      </span>
      <span className="msg-info-item" title="Estimated tokens">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="4"  y1="9"  x2="20" y2="9" />
          <line x1="4"  y1="15" x2="20" y2="15" />
          <line x1="10" y1="3"  x2="8"  y2="21" />
          <line x1="16" y1="3"  x2="14" y2="21" />
        </svg>
        <span className="val">{tokEst}</span>
      </span>
      {stylePreset !== 'auto' && (
        <span className="msg-info-item" title="Style">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M20.59 13.41 13.41 20.59a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
            <line x1="7" y1="7" x2="7.01" y2="7" />
          </svg>
          <span className="val">{stylePreset.toUpperCase()}</span>
        </span>
      )}
    </div>
  );
}
