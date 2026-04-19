import { create } from 'zustand';

export const useChatStore = create((set) => ({
  messages: [],
  busy: false,

  addMessage(msg) {
    set(s => ({ messages: [...s.messages, { id: Date.now(), ...msg }] }));
  },

  updateMessage(id, patch) {
    set(s => ({
      messages: s.messages.map(m => (m.id === id ? { ...m, ...patch } : m)),
    }));
  },

  clearMessages() { set({ messages: [], busy: false }); },
  setBusy(busy)   { set({ busy }); },
}));
