import { API_BASE } from '../config/env.js';

export async function checkHealth() {
  const r = await fetch('/health');
  if (!r.ok) throw new Error('unreachable');
}

export async function getAgentStatus(token) {
  const r = await fetch(`${API_BASE}/agent/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
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

export async function postChat(token, payload) {
  const r = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r;
}
