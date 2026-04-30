import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { environment } from '../../environments/environment';

export interface PaletteItem {
  id: string;
  title: string;
  sub: string;
  kind: 'asset' | 'org' | 'tx';
}

@Injectable({ providedIn: 'root' })
export class PaletteService {
  private base = environment.apiBase;
  open$ = new BehaviorSubject(false);
  items$ = new BehaviorSubject<PaletteItem[]>([]);
  loading$ = new BehaviorSubject(false);

  toggle() { this.open$.next(!this.open$.value); }
  close() { this.open$.next(false); }

  async search(q: string) {
    if (!q.trim()) { this.items$.next([]); return; }
    this.loading$.next(true);
    try {
      const csrf = this.getCsrf();
      const headers: Record<string, string> = {};
      if (csrf) headers['X-CSRF-Token'] = csrf;
      const res = await fetch(`${this.base}/search?q=${encodeURIComponent(q)}&limit=20`, {
        credentials: 'include', headers
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const items: PaletteItem[] = [];
      (data.assets ?? []).forEach((a: any) => items.push({ id: a.asset_id, title: a.name ?? a.asset_id, sub: a.asset_type ?? '', kind: 'asset' }));
      (data.organizations ?? []).forEach((o: any) => items.push({ id: o.org_id, title: o.name ?? o.org_id, sub: o.type ?? '', kind: 'org' }));
      (data.transactions ?? []).forEach((t: any) => items.push({ id: t.tx_id, title: t.tx_id, sub: t.type ?? '', kind: 'tx' }));
      this.items$.next(items);
    } catch { this.items$.next([]); }
    finally { this.loading$.next(false); }
  }

  private getCsrf(): string | null {
    const match = document.cookie.match(/(?:^|;\s*)rwa_csrf=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : null;
  }
}
