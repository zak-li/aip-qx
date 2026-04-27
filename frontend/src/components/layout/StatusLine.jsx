import { useAuthStore } from '../../features/auth/hooks/useAuth.js';
import { useApiStatus } from '../../hooks/useApiStatus.js';

export default function StatusLine({ onOpenLogin }) {
  const { api } = useApiStatus();
  const user    = useAuthStore(s => s.user);
  const logout  = useAuthStore(s => s.logout);

  return (
    <header className="header">
      <div className="header-left">
        <div className="header-brand">
          <span className="header-name">RWA Intelligence</span>
          <span className="header-tag">Blockchain · AI · Compliance</span>
        </div>
      </div>

      <div className="header-right">
        {api && <span className="header-api">{api}</span>}
        <div className="header-divider" />

        {user ? (
          <>
            <span
              className="header-api"
              title={`${user.role} · org ${user.org_id}`}
              style={{ maxWidth: '14rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {user.email}
            </span>
            <button
              className="status-icon status-icon--bare status-icon--ok"
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </>
        ) : (
          <button
            className="status-icon status-icon--bare status-icon--warn"
            onClick={onOpenLogin}
            title="Sign in"
            aria-label="Sign in"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
              <polyline points="10 17 15 12 10 7" />
              <line x1="15" y1="12" x2="3" y2="12" />
            </svg>
          </button>
        )}
      </div>
    </header>
  );
}
