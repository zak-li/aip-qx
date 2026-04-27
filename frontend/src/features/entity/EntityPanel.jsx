import { useEffect } from 'react';
import { useEntityStore } from './entityStore.js';
import { useAuthStore }   from '../auth/hooks/useAuth.js';
import { fetchEntityDetail } from './entityService.js';

const KIND_LABEL = { asset: 'ASSET', org: 'ORGANIZATION', tx: 'TRANSACTION' };

function fmtKey(k) {
  return k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function Row({ k, v }) {
  if (v === null || v === undefined || v === '') return null;
  let display = v;
  if (typeof v === 'object') display = JSON.stringify(v);
  else if (typeof v === 'boolean') display = v ? 'YES' : 'NO';
  return (
    <div className="entity-row">
      <span className="entity-k">{fmtKey(k)}</span>
      <span className="entity-v">{String(display)}</span>
    </div>
  );
}

export default function EntityPanel() {
  const open    = useEntityStore(s => s.open);
  const active  = useEntityStore(s => s.active);
  const detail  = useEntityStore(s => s.detail);
  const loading = useEntityStore(s => s.loading);
  const error   = useEntityStore(s => s.error);
  const setDetail = useEntityStore(s => s.setDetail);
  const setError  = useEntityStore(s => s.setError);
  const close     = useEntityStore(s => s.close);
  const user      = useAuthStore(s => s.user);

  useEffect(() => {
    if (!open || !active || !user) return;
    let cancelled = false;
    fetchEntityDetail(active)
      .then(d => { if (!cancelled) setDetail(d); })
      .catch(e => { if (!cancelled) setError(String(e?.message || e)); });
    return () => { cancelled = true; };
  }, [open, active, user, setDetail, setError]);

  useEffect(() => {
    if (!open) return;
    function onKey(e) { if (e.key === 'Escape') close(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, close]);

  if (!open || !active) return null;

  const entries = detail && typeof detail === 'object' && !Array.isArray(detail)
    ? Object.entries(detail).filter(([k]) => !k.startsWith('_'))
    : [];

  return (
    <>
      <div className="entity-overlay" onClick={close} />
      <aside className="entity-panel" role="dialog" aria-label="Entity details">
        <div className="entity-head">
          <div className="entity-title-wrap">
            <span className="entity-kind-tag">{KIND_LABEL[active.kind] || active.kind}</span>
            <span className="entity-title">{active.id}</span>
          </div>
          <button className="entity-close" onClick={close} aria-label="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6"  y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div className="entity-body">
          {loading && <div className="entity-empty">Loading...</div>}
          {error   && <div className="entity-empty entity-err">{error}</div>}
          {!loading && !error && !entries.length && (
            <div className="entity-empty">No data.</div>
          )}
          {!loading && !error && entries.length > 0 && (
            <div className="entity-table">
              {entries.map(([k, v]) => <Row key={k} k={k} v={v} />)}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
