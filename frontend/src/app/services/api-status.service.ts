import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiStatusService implements OnDestroy {
  private base = environment.apiBase;
  apiOk$ = new BehaviorSubject(false);
  agentReady$ = new BehaviorSubject(false);
  agentModel$ = new BehaviorSubject('');
  agentProvider$ = new BehaviorSubject('');
  private interval: any;

  constructor() {
    this.poll();
    this.interval = setInterval(() => this.poll(), 30000);
  }

  private async poll() {
    try {
      const [health, status] = await Promise.all([
        fetch(`${this.base}/health`, { credentials: 'include' }).then(r => r.ok),
        fetch(`${this.base}/agent/status`, { credentials: 'include' }).then(r => r.ok ? r.json() : null)
      ]);
      this.apiOk$.next(health);
      if (status) {
        this.agentReady$.next(status.ready ?? false);
        this.agentModel$.next(status.model ?? '');
        this.agentProvider$.next(status.provider ?? '');
      }
    } catch { this.apiOk$.next(false); }
  }

  ngOnDestroy() { clearInterval(this.interval); }
}
