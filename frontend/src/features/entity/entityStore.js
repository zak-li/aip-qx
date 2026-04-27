import { create } from 'zustand';

export const useEntityStore = create((set) => ({
  open: false,
  active: null,   // { kind, id }
  detail: null,   // resolved data from API
  loading: false,
  error: null,

  openEntity(entity) {
    set({ open: true, active: entity, detail: null, loading: true, error: null });
  },
  setDetail(detail) { set({ detail, loading: false, error: null }); },
  setError(error)   { set({ error, loading: false }); },
  close()           { set({ open: false }); },
}));
