import { useState, useEffect } from 'react';
import StatusLine from '../components/layout/StatusLine.jsx';
import InputBar   from '../components/layout/InputBar/index.jsx';
import { MessageList, Welcome, useChat } from '../features/chat/index.js';
import { TokenModal }                    from '../features/auth/index.js';
import { useAuthStore }                  from '../features/auth/hooks/useAuth.js';

export default function AgentPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const token       = useAuthStore(s => s.token);
  const { messages, busy, sendMessage } = useChat();

  useEffect(() => {
    if (!token) setTimeout(() => setModalOpen(true), 800);
  }, []);

  const hasMessages = messages.length > 0;

  return (
    <div className="page-shell">

      <StatusLine onOpenModal={() => setModalOpen(true)} />

      <div className="layout">
        <div className="chat">

          <div className="chat-scroll" id="scroll">
            {hasMessages
              ? <MessageList messages={messages} />
              : <Welcome />
            }
          </div>

          <InputBar onSend={sendMessage} busy={busy} />

        </div>
      </div>

      <TokenModal open={modalOpen} onClose={() => setModalOpen(false)} />

    </div>
  );
}
