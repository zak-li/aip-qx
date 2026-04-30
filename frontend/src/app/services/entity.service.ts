import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class EntityService {
  private base = environment.apiBase;
  open$ = new BehaviorSubject(false);
  activeId$ = new BehaviorSubject<string | null>(null);
  activeKind$ = new BehaviorSubject<'asset' | 'org' | 'tx' | null>(null);
  detail$ = new BehaviorSubject<Record<string, any> | null>(null);
  loading$ = new BehaviorSubject(false);
  error$ = new BehaviorSubject<string | null>(null);

  async open(id: string, kind: 'asset' | 'org' | 'tx') {
    this.open$.next(true);
    this.activeId$.next(id);
    this.activeKind$.next(kind);
    this.detail$.next(null);
    this.error$.next(null);
    this.loading$.next(true);
    try {
      const path = kind === 'asset' ? `assets/${id}` : kind === 'org' ? `organizations/${id}` : `transactions/${id}`;
      const res = await fetch(`${this.base}/${path}`, { credentials: 'include' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.detail$.next(await res.json());
    } catch (e: any) {
      this.error$.next(e.message);
    } finally {
      this.loading$.next(false);
    }
  }

  close() {
    this.open$.next(false);
  }
}
