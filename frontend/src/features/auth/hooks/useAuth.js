import { create } from 'zustand';

export const useAuthStore = create((set) => ({
  token: localStorage.getItem('rwa_jwt') || '',

  setToken(token) {
    const clean = token.trim().replace(/^Bearer\s+/i, '');
    if (!clean) return false;
    localStorage.setItem('rwa_jwt', clean);
    set({ token: clean });
    return true;
  },

  clearToken() {
    localStorage.removeItem('rwa_jwt');
    set({ token: '' });
  },
}));
