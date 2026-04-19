import { useRef } from 'react';
import { useAuthStore } from '../hooks/useAuth.js';
import { useToastStore } from '../../../store/toastStore.js';

export default function TokenModal({ open, onClose }) {
  const inputRef = useRef(null);
  const setToken = useAuthStore(s => s.setToken);
  const toast    = useToastStore(s => s.show);

  function save() {
    const ok = setToken(inputRef.current?.value || '');
    if (ok) { toast('TOKEN SAVED', 'ok'); onClose(); }
  }

  function onOverlayClick(e) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div className={`modal-overlay${open ? ' open' : ''}`} onClick={onOverlayClick}>
      <div className="modal">
        <div className="modal-head">[ AUTHENTICATION // JWT ]</div>
        <p>
          Paste your Bearer token obtained via{' '}
          <code style={{ color: 'var(--accent)' }}>POST /api/v1/auth/login</code>.
          <br />Stored locally — expires after 30 min.
        </p>
        <div className="field-label">Bearer Token</div>
        <input
          ref={inputRef}
          type="text"
          className="field-input"
          placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
          onKeyDown={e => e.key === 'Enter' && save()}
          autoFocus={open}
        />
        <div className="modal-actions">
          <button className="btn-modal ghost" onClick={onClose}>Cancel</button>
          <button className="btn-modal primary" onClick={save}>Save Token</button>
        </div>
      </div>
    </div>
  );
}
