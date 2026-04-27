import { useEffect, useRef, useState } from 'react';

import { useToastStore } from '../../../store/toastStore.js';
import { useAuthStore } from '../hooks/useAuth.js';

export default function LoginForm({ open, onClose }) {
  const login   = useAuthStore(s => s.login);
  const loading = useAuthStore(s => s.loading);
  const error   = useAuthStore(s => s.error);
  const toast   = useToastStore(s => s.show);

  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode]   = useState('');
  const [needsMfa, setNeedsMfa] = useState(false);

  const emailRef = useRef(null);
  const mfaRef   = useRef(null);

  useEffect(() => {
    if (open && !needsMfa) emailRef.current?.focus();
    if (open && needsMfa)  mfaRef.current?.focus();
  }, [open, needsMfa]);

  // Reset when the modal closes so a re-open starts clean.
  useEffect(() => {
    if (!open) {
      setEmail('');
      setPassword('');
      setMfaCode('');
      setNeedsMfa(false);
    }
  }, [open]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) return;
    if (needsMfa && !mfaCode) return;

    const res = await login({ email, password, mfaCode: needsMfa ? mfaCode : undefined });

    if (res.ok) {
      toast('LOGGED IN', 'ok');
      onClose();
      return;
    }
    if (res.mfaRequired) {
      setNeedsMfa(true);
      toast('MFA REQUIRED', 'warn');
    }
    // Otherwise the store's `error` field renders below.
  }

  function onOverlayClick(e) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div className={`modal-overlay${open ? ' open' : ''}`} onClick={onOverlayClick}>
      <div className="modal">
        <div className="modal-head">[ AUTHENTICATION // SIGN IN ]</div>
        <p>
          Sign in with your platform credentials. The session is stored in a
          secure httpOnly cookie that JavaScript cannot read.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="field-label">Email</div>
          <input
            ref={emailRef}
            type="email"
            className="field-input"
            value={email}
            onChange={e => setEmail(e.target.value)}
            autoComplete="username"
            disabled={loading || needsMfa}
            required
          />

          <div className="field-label" style={{ marginTop: '0.6rem' }}>Password</div>
          <input
            type="password"
            className="field-input"
            value={password}
            onChange={e => setPassword(e.target.value)}
            autoComplete="current-password"
            disabled={loading || needsMfa}
            required
            minLength={8}
          />

          {needsMfa && (
            <>
              <div className="field-label" style={{ marginTop: '0.6rem' }}>
                MFA Code (6 digits)
              </div>
              <input
                ref={mfaRef}
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                className="field-input"
                value={mfaCode}
                onChange={e => setMfaCode(e.target.value.replace(/\D/g, ''))}
                autoComplete="one-time-code"
                disabled={loading}
                required
              />
            </>
          )}

          {error && (
            <div style={{ color: 'var(--red, #ef4444)', fontSize: '12px', marginTop: '0.6rem' }}>
              {error}
            </div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="btn-modal ghost"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button type="submit" className="btn-modal primary" disabled={loading}>
              {loading ? 'Signing in…' : needsMfa ? 'Verify code' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
