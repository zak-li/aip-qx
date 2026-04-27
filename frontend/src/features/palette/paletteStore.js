import { create } from 'zustand';

export const usePaletteStore = create((set) => ({
  open: false,
  items: [],
  loading: false,
  error: null,

  show()   { set({ open: true  }); },
  hide()   { set({ open: false }); },
  toggle() { set(s => ({ open: !s.open })); },
  setItems(items) { set({ items, loading: false, error: null }); },
  setLoading(loading) { set({ loading }); },
  setError(error)     { set({ error, loading: false }); },
}));
