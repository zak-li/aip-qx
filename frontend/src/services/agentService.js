import { API_BASE } from '../config/env.js';

// CSRF cookie is readable from JS (httpOnly OFF on this cookie only).
// We echo it via X-CSRF-Token so the backend matches the double-submit pattern.
function readCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

function csrfHeaders() {
  const csrf = readCookie('rwa_csrf');
  return csrf ? { 'X-CSRF-Token': csrf } : {};
}

export async function checkHealth() {
  const r = await fetch('/health', { credentials: 'include' });
  if (!r.ok) throw new Error('unreachable');
}

export async function getAgentStatus() {
  const r = await fetch(`${API_BASE}/agent/status`, { credentials: 'include' });
  if (!r.ok) throw new Error('status fetch failed');
  return r.json();
}

export function buildPayload(msg, history, opts, stream) {
  return {
    message: msg,
    history: history.slice(-(opts.ctxDepth * 2), -1),
    stream,
    temperature:       opts.temperature,
    max_tokens:        opts.maxTokens,
    top_p:             opts.topP,
    frequency_penalty: opts.freqPenalty,
    presence_penalty:  opts.presPenalty,
    n_results:         opts.nResults,
    use_rag:           opts.useRag,
    style_preset:      opts.stylePreset,
  };
}

export async function postChat(payload) {
  const r = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r;
}
