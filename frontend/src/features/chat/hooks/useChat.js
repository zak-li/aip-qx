import { useCallback } from 'react';
import { useChatStore } from '../store/chatStore.js';
import { useAuthStore } from '../../auth/hooks/useAuth.js';
import { useOptsStore } from '../../settings/store/optsStore.js';
import { useToastStore } from '../../../store/toastStore.js';
import { postChat, buildPayload } from '../../../services/agentService.js';

export function useChat() {
  const { addMessage, updateMessage, setBusy, messages } = useChatStore();
  const token  = useAuthStore(s => s.token);
  const opts   = useOptsStore();
  const toast  = useToastStore(s => s.show);
  const busy   = useChatStore(s => s.busy);

  const history = messages
    .filter(m => !m.streaming && !m.error)
    .map(m => ({ role: m.role, content: m.content }));

  const sendMessage = useCallback(async (text, stream = true) => {
    if (!text.trim() || busy) return;
    if (!token) return toast('TOKEN REQUIS — configure ton JWT', 'warn');

    addMessage({ role: 'user', content: text });
    const msgId = Date.now() + 1;
    addMessage({ id: msgId, role: 'assistant', content: '', streaming: true, meta: null, error: null });
    setBusy(true);

    try {
      const payload = buildPayload(text, [...history, { role: 'user', content: text }], opts, stream);
      const resp    = await postChat(token, payload);

      if (stream) {
        await _consumeStream(resp, msgId, updateMessage);
      } else {
        const data = await resp.json();
        updateMessage(msgId, {
          content: data.answer || '',
          streaming: false,
          meta: { time_ms: data.time_ms, sources: data.sources ?? [] },
        });
      }
    } catch (err) {
      updateMessage(msgId, { content: '', streaming: false, error: err.message });
      toast(`ERREUR: ${err.message}`, 'err');
    } finally {
      setBusy(false);
    }
  }, [busy, token, opts, history, addMessage, updateMessage, setBusy, toast]);

  return { messages, busy, sendMessage };
}

async function _consumeStream(resp, msgId, updateMessage) {
  const reader  = resp.body.getReader();
  const decoder = new TextDecoder();
  let full = '', buf = '', metaData = null;

  outer: while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (raw === '[DONE]') break outer;
      let p; try { p = JSON.parse(raw); } catch { continue; }
      if (p.error) {
        updateMessage(msgId, { content: '', streaming: false, error: p.error });
        return;
      }
      if (p.meta) { metaData = p.meta; continue; }
      if (p.token) {
        full += p.token;
        updateMessage(msgId, { content: full });
      }
    }
  }

  updateMessage(msgId, {
    content:   full,
    streaming: false,
    meta: metaData ? { time_ms: metaData.time_ms, sources: metaData.sources ?? [] } : null,
  });
}
