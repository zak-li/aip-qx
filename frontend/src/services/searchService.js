import { API_BASE } from '../config/env.js';

async function fetchJSON(path) {
  const r = await fetch(`${API_BASE}${path}`, { credentials: 'include' });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

function normAsset(a) {
  return {
    kind: 'asset',
    id:   a.asset_id,
    title: a.asset_name || a.asset_id,
    sub:  [a.asset_type, a.isin, a.status].filter(Boolean).join(' · '),
    raw:  a,
    haystack: [a.asset_id, a.asset_name, a.isin, a.asset_type, a.status]
      .filter(Boolean).join(' ').toLowerCase(),
  };
}
function normOrg(o) {
  return {
    kind: 'org',
    id:   o.id || o.org_id,
    title: o.name || o.org_name || o.legal_name || o.msp_id || o.id,
    sub:  [o.msp_id, o.lei, o.country].filter(Boolean).join(' · '),
    raw:  o,
    haystack: [o.id, o.org_id, o.name, o.org_name, o.legal_name, o.msp_id, o.lei, o.country]
      .filter(Boolean).join(' ').toLowerCase(),
  };
}
function normTx(t) {
  return {
    kind: 'tx',
    id:   t.tx_ref || t.id,
    title: t.tx_ref || t.id,
    sub:  [t.tx_type, t.fabric_block_number && `block ${t.fabric_block_number}`].filter(Boolean).join(' · '),
    raw:  t,
    haystack: [t.tx_ref, t.id, t.fabric_tx_id, t.tx_type]
      .filter(Boolean).join(' ').toLowerCase(),
  };
}

export async function fetchSearchIndex() {
  const [assets, orgs, txs] = await Promise.all([
    fetchJSON('/assets?limit=100').catch(() => []),
    fetchJSON('/organizations').catch(() => []),
    fetchJSON('/transactions?limit=100').catch(() => []),
  ]);
  const a = (Array.isArray(assets) ? assets : assets?.items || []).map(normAsset);
  const o = (Array.isArray(orgs)   ? orgs   : orgs?.items   || []).map(normOrg);
  const t = (Array.isArray(txs)    ? txs    : txs?.items    || []).map(normTx);
  return [...a, ...o, ...t];
}

export function searchIndex(items, query, limit = 40) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items.slice(0, limit);
  const tokens = q.split(/\s+/).filter(Boolean);

  const scored = [];
  for (const it of items) {
    let score = 0;
    let matched = true;
    for (const tok of tokens) {
      const idx = it.haystack.indexOf(tok);
      if (idx < 0) { matched = false; break; }
      score += idx === 0 ? 4 : 1;
      if (it.title.toLowerCase().includes(tok)) score += 3;
      if (String(it.id).toLowerCase().includes(tok)) score += 5;
    }
    if (matched) scored.push({ it, score });
  }
  scored.sort((x, y) => y.score - x.score);
  return scored.slice(0, limit).map(s => s.it);
}
