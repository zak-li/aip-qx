import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { router } from './router.jsx';
import Toast from '../components/ui/Toast.jsx';
import { CommandPalette, usePaletteStore } from '../features/palette/index.js';
import { EntityPanel, useEntityStore } from '../features/entity/index.js';
import { useAuthStore } from '../features/auth/hooks/useAuth.js';
import { fetchSearchIndex } from '../services/searchService.js';

export default function App() {
  const togglePalette = usePaletteStore(s => s.toggle);
  const setItems      = usePaletteStore(s => s.setItems);
  const paletteItems  = usePaletteStore(s => s.items);
  const openEntity    = useEntityStore(s => s.openEntity);
  const user          = useAuthStore(s => s.user);

  // Global Cmd+K
  useEffect(() => {
    function onKey(e) {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        togglePalette();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [togglePalette]);

  // Eager-load search index once authenticated (so pills can resolve)
  useEffect(() => {
    if (!user || paletteItems.length > 0) return;
    fetchSearchIndex().then(setItems).catch(() => { /* ignore */ });
  }, [user, paletteItems.length, setItems]);

  // Delegate clicks on entity pills
  useEffect(() => {
    function onClick(e) {
      const pill = e.target.closest?.('.entity-pill');
      if (!pill) return;
      const kind = pill.dataset.kind;
      const id   = pill.dataset.id;
      if (!kind || !id) return;
      e.preventDefault();
      openEntity({ kind, id });
    }
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, [openEntity]);

  // Bridge: palette selection → open entity panel
  useEffect(() => {
    function onSelect(e) {
      const r = e.detail;
      if (r?.kind && r?.id) openEntity({ kind: r.kind, id: r.id });
    }
    window.addEventListener('palette:select', onSelect);
    return () => window.removeEventListener('palette:select', onSelect);
  }, [openEntity]);

  return (
    <>
      <RouterProvider router={router} />
      <CommandPalette />
      <EntityPanel />
      <Toast />
    </>
  );
}
