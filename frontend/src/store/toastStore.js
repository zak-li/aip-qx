import { create } from 'zustand';

let _timer = null;

export const useToastStore = create((set) => ({
  message: '',
  type: '',
  visible: false,

  show(message, type = '') {
    clearTimeout(_timer);
    set({ message, type, visible: true });
    _timer = setTimeout(() => set({ visible: false }), 3200);
  },
}));
