import { useOptsStore } from '../../settings/store/optsStore.js';

export default function MsgMeta({ meta, content }) {
  const stylePreset = useOptsStore(s => s.stylePreset);

  const tokEst   = Math.round((content || '').length / 4);
  const srcCount = Array.isArray(meta?.sources) ? meta.sources.length : 0;
  const timeStr  = meta?.time_ms ? `${(meta.time_ms / 1000).toFixed(2)}s` : '—';

  return (
    <div className="msg-info">
      <span className="msg-info-item">
        <span className="lbl">TIME</span>
        <span className="val">{timeStr}</span>
      </span>
      <span className="msg-info-sep">·</span>
      <span className="msg-info-item">
        <span className="lbl">~TOKENS</span>
        <span className="val">{tokEst}</span>
      </span>
      <span className="msg-info-sep">·</span>
      <span className="msg-info-item">
        <span className="lbl">KB SRC</span>
        <span className="val">{srcCount}</span>
      </span>
      {stylePreset !== 'auto' && (
        <>
          <span className="msg-info-sep">·</span>
          <span className="msg-info-item">
            <span className="lbl">STYLE</span>
            <span className="val">{stylePreset.toUpperCase()}</span>
          </span>
        </>
      )}
    </div>
  );
}
