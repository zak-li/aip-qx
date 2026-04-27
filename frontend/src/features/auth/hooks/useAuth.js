import { create } from 'zustand';

import { API_BASE } from '../../../config/env.js';

// Auth state lives on the server. The browser holds an httpOnly session
// cookie that we cannot read; the only way to know "am I logged in" is to
// hit /auth/me. We cache that response in the store so the UI doesn't
// re-fetch on every render.
//
// Login posts to /auth/login, which sets the cookies via Set-Cookie. From
// then on every fetch with `credentials: 'include'` is authenticated.
//
// localStorage is no longer used for any auth material — it is XSS-readable
// and the JWT now lives in an httpOnly cookie that JS cannot touch.
export const useAuthStore = create((set, get) => ({
  user: null,            // { id, email, role, org_id, mfa_enabled }
  initialized: false,    // true once /me has been attempted at least once
  loading: false,
  error: '',

  async hydrate() {
    if (get().initialized) return;
    set({ loading: true });
    try {
      const r = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
      if (r.ok) {
        const user = await r.json();
        set({ user, initialized: true, loading: false, error: '' });
      } else {
        set({ user: null, initialized: true, loading: false });
      }
    } catch {
      set({ user: null, initialized: true, loading: false });
    }
  },

  async login({ email, password, mfaCode }) {
    set({ loading: true, error: '' });
    try {
      const body = { email, password };
      if (mfaCode) body.mfa_code = mfaCode;

      const r = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await r.json().catch(() => ({}));

      if (!r.ok) {
        const detail = typeof data?.detail === 'string' ? data.detail : 'Login failed';
        set({ loading: false, error: detail });
        return { ok: false, mfaRequired: false };
      }

      // Backend signals "MFA needed" by returning expires_in:0, mfa_required:true
      // and an empty access_token. The cookies are NOT set in that case.
      if (data?.mfa_required) {
        set({ loading: false, error: '' });
        return { ok: false, mfaRequired: true };
      }

      // Cookies are set; pull the user record so the UI knows who's logged in.
      const me = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
      const user = me.ok ? await me.json() : null;
      set({ user, initialized: true, loading: false, error: '' });
      return { ok: true, mfaRequired: false };
    } catch (err) {
      set({ loading: false, error: err?.message || 'Network error' });
      return { ok: false, mfaRequired: false };
    }
  },

  async logout() {
    try {
      // CSRF: the cookie is named rwa_csrf and must be echoed.
      const csrf = document.cookie
        .split('; ')
        .find(c => c.startsWith('rwa_csrf='))
        ?.split('=')[1];
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {},
      });
    } catch {
      /* ignore — we still drop local state */
    }
    set({ user: null });
  },
}));
