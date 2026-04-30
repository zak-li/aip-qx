import { Component, EventEmitter, Output } from '@angular/core';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-login-form',
  standalone: false,
  template: `
    <div class="modal-overlay open">
      <div class="modal">
        <div class="modal-head">Authentication Required</div>
        <p>Sign in to access the RWA platform.</p>
        <ng-container *ngIf="!mfaRequired">
          <div class="field-label">Username</div>
          <input class="field-input" type="text" [(ngModel)]="username" placeholder="username" (keydown.enter)="submit()" />
          <div class="field-label">Password</div>
          <input class="field-input" type="password" [(ngModel)]="password" placeholder="••••••••" (keydown.enter)="submit()" />
        </ng-container>
        <ng-container *ngIf="mfaRequired">
          <div class="field-label">MFA Token</div>
          <input class="field-input" type="text" [(ngModel)]="mfaToken" placeholder="000000" (keydown.enter)="submit()" />
        </ng-container>
        <div *ngIf="error" style="color:var(--red);font-size:11px;margin-bottom:16px;font-family:var(--mono)">{{ error }}</div>
        <div class="modal-actions">
          <button class="btn-modal primary" (click)="submit()" [disabled]="loading">
            {{ loading ? 'Signing in...' : (mfaRequired ? 'Verify' : 'Sign In') }}
          </button>
        </div>
      </div>
    </div>
  `
})
export class LoginFormComponent {
  @Output() success = new EventEmitter<void>();
  username = '';
  password = '';
  mfaToken = '';
  mfaRequired = false;
  loading = false;
  error = '';

  constructor(private auth: AuthService, private toast: ToastService) {}

  async submit() {
    if (this.loading) return;
    this.loading = true;
    this.error = '';
    try {
      const res = await this.auth.login(this.username, this.password, this.mfaRequired ? this.mfaToken : undefined);
      if (res.mfa_required) {
        this.mfaRequired = true;
      } else {
        this.toast.show('Signed in', 'ok');
        this.success.emit();
      }
    } catch (e: any) {
      this.error = e?.error?.detail ?? e?.message ?? 'Login failed';
    } finally {
      this.loading = false;
    }
  }
}
