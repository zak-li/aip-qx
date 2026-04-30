import { Component, OnInit } from '@angular/core';
import { AuthService } from '../../services/auth.service';
import { ApiStatusService } from '../../services/api-status.service';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-status-line',
  standalone: false,
  template: `
    <header class="header">
      <div class="header-left">
        <div class="header-brand">
          <span class="header-name">RWA Platform</span>
          <span class="header-tag">INSTITUTIONAL · AI · AGENT</span>
        </div>
      </div>
      <div class="header-right">
        <span class="header-api">{{ apiLabel }}</span>
        <div class="header-divider"></div>
        <ng-container *ngIf="user">
          <button class="header-btn" (click)="logout()">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            {{ user.email }}
          </button>
        </ng-container>
        <button class="status-icon" [class.status-icon--ok]="apiOk" [class.status-icon--warn]="!apiOk" title="{{ apiOk ? 'API online' : 'API offline' }}">
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="6"/></svg>
        </button>
      </div>
    </header>
  `
})
export class StatusLineComponent implements OnInit {
  user: any = null;
  apiOk = false;
  agentModel = '';

  get apiLabel(): string {
    return this.apiOk ? (this.agentModel ? `MODEL · ${this.agentModel.toUpperCase()}` : 'API · ONLINE') : 'API · OFFLINE';
  }

  constructor(
    private auth: AuthService,
    private apiStatus: ApiStatusService,
    private toast: ToastService
  ) {}

  ngOnInit() {
    this.auth.user$.subscribe(u => this.user = u);
    this.apiStatus.apiOk$.subscribe(v => this.apiOk = v);
    this.apiStatus.agentModel$.subscribe(v => this.agentModel = v);
  }

  async logout() {
    await this.auth.logout();
    this.toast.show('Signed out', 'ok');
  }
}
