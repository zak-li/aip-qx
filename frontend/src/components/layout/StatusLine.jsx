import { useApiStatus } from '../../hooks/useApiStatus.js';
import { useAuthStore } from '../../features/auth/hooks/useAuth.js';

export default function StatusLine({ onOpenModal }) {
  const { api, groq, kb } = useApiStatus();
  const token = useAuthStore(s => s.token);

  return (
    <div className="status-line">
      <div className="status-left">
        <span className="brand">HET X</span>
        <span className="divider">/</span>
        <span className="sub-brand">RAG INTELLIGENCE</span>
      </div>
      <div className="status-right">
        <span className="status-meta">{groq}</span>
        <span className="divider">|</span>
        <span className="status-meta">{kb}</span>
        <span className="divider">|</span>
        <span className="status-meta">{api}</span>
        <span className="divider">|</span>
        <span
          className="status-meta"
          style={{ cursor: 'pointer', color: token ? 'var(--green)' : 'var(--accent)' }}
          onClick={onOpenModal}
        >
          {token ? '[ TOKEN ACTIVE ]' : '[ SET TOKEN ]'}
        </span>
      </div>
    </div>
  );
}
