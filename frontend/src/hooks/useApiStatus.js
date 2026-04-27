import { useEffect, useState } from 'react';

import { useAuthStore } from '../features/auth/hooks/useAuth.js';
import { checkHealth, getAgentStatus } from '../services/agentService.js';

export function useApiStatus() {
  const user = useAuthStore(s => s.user);
  const [status, setStatus] = useState({ api: '—', groq: '—', kb: '—' });

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        await checkHealth();
        if (!cancelled) setStatus(s => ({ ...s, api: 'API OK' }));
      } catch {
        if (!cancelled) setStatus(s => ({ ...s, api: 'API ERR' }));
        return;
      }
      if (!user) return;
      try {
        const d = await getAgentStatus();
        if (!cancelled) setStatus(s => ({
          ...s,
          groq: d.groq_configured ? 'GROQ OK' : 'GROQ ⚠',
          kb:   `KB ${d.knowledge_base_docs}`,
        }));
      } catch {
        if (!cancelled) setStatus(s => ({ ...s, groq: 'GROQ ERR', kb: 'KB —' }));
      }
    }

    refresh();
    const id = setInterval(refresh, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [user]);

  return status;
}
