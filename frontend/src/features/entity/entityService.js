import { API_BASE } from '../../config/env.js';

async function getJSON(path) {
  const r = await fetch(`${API_BASE}${path}`, { credentials: 'include' });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

export async function fetchEntityDetail({ kind, id }) {
  switch (kind) {
    case 'asset':
      return getJSON(`/assets/${encodeURIComponent(id)}`);
    case 'org':
      return getJSON(`/organizations/${encodeURIComponent(id)}/portfolio`);
    case 'tx':
      return getJSON(`/transactions/${encodeURIComponent(id)}`);
    default:
      throw new Error(`Unknown entity kind: ${kind}`);
  }
}
