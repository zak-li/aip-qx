import { useState, useEffect } from 'react';
import { checkHealth, getAgentStatus } from '../services/agentService.js';
import { useAuthStore } from '../features/auth/hooks/useAuth.js';

export function useApiStatus() {
  const token = useAuthStore(s => s.token);
  const [status, setStatus] = useState({ api: '—', groq: '—', kb: '—' });

  async function refresh() {
    try {
      await checkHealth();
      setStatus(s => ({ ...s, api: 'API OK' }));
    } catch {
      setStatus(s => ({ ...s, api: 'API ERR' }));
      return;
    }
    if (!token) return;
    try {
      const d = await getAgentStatus(token);
      setStatus(s => ({
        ...s,
        groq: d.groq_configured ? 'GROQ OK' : 'GROQ ⚠',
        kb:   `KB ${d.knowledge_base_docs}`,
      }));
    } catch {
      setStatus(s => ({ ...s, groq: 'GROQ ERR', kb: 'KB —' }));
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [token]);

  return status;
}
