import { useEffect, useState } from 'react';

import InputBar    from '../components/layout/InputBar/index.jsx';
import StatusLine  from '../components/layout/StatusLine.jsx';
import { LoginForm } from '../features/auth/index.js';
import { useAuthStore } from '../features/auth/hooks/useAuth.js';
import { MessageList, useChat, Welcome } from '../features/chat/index.js';

export default function AgentPage() {
  const [modalOpen, setModalOpen] = useState(false);

  const user        = useAuthStore(s => s.user);
  const initialized = useAuthStore(s => s.initialized);
  const hydrate     = useAuthStore(s => s.hydrate);

  const { messages, busy, sendMessage } = useChat();

  // Resolve the cookie-backed session once on mount.
  useEffect(() => { hydrate(); }, [hydrate]);

  // Open the login modal once we know the user is unauthenticated.
  useEffect(() => {
    if (!initialized) return;
    if (!user) {
      const handle = setTimeout(() => setModalOpen(true), 400);
      return () => clearTimeout(handle);
    }
    setModalOpen(false);
  }, [initialized, user]);

  const hasMessages = messages.length > 0;

  return (
    <div className="page-shell">
      <StatusLine onOpenLogin={() => setModalOpen(true)} />

      <div className="layout">
        <div className="chat">

          <header className="shrink-0 h-16 border-b border-white/5 flex items-center px-6 bg-slate-900/50 backdrop-blur-md">
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-slate-100">HET X RegTech Copilot</h1>
              <p className="text-xs text-slate-400">Agentic AI powered by Groq</p>
            </div>
          </header>

          <div className="chat-scroll" id="scroll">
            {hasMessages
              ? <MessageList messages={messages} />
              : <Welcome />
            }
          </div>

          <InputBar onSend={sendMessage} busy={busy} />

        </div>
      </div>

      <LoginForm open={modalOpen} onClose={() => setModalOpen(false)} />

    </div>
  );
}
