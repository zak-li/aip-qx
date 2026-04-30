import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../environments/environment';

export interface User { id: string; email: string; role: string; }

@Injectable({ providedIn: 'root' })
export class AuthService {
  private base = environment.apiBase;
  user$ = new BehaviorSubject<User | null>(null);
  checked$ = new BehaviorSubject(false);

  constructor(private http: HttpClient) {}

  async hydrate() {
    try {
      const user = await this.http.get<User>(`${this.base}/auth/me`, { withCredentials: true }).toPromise();
      this.user$.next(user ?? null);
    } catch {
      this.user$.next(null);
    } finally {
      this.checked$.next(true);
    }
  }

  async login(username: string, password: string, mfaToken?: string): Promise<{ mfa_required?: boolean }> {
    const csrf = this.getCsrf();
    const res = await this.http.post<any>(`${this.base}/auth/login`, { username, password, mfa_token: mfaToken }, {
      withCredentials: true,
      headers: csrf ? { 'X-CSRF-Token': csrf } : {}
    }).toPromise();
    if (res?.mfa_required) return { mfa_required: true };
    await this.hydrate();
    return {};
  }

  async logout() {
    const csrf = this.getCsrf();
    try {
      await this.http.post(`${this.base}/auth/logout`, {}, {
        withCredentials: true,
        headers: csrf ? { 'X-CSRF-Token': csrf } : {}
      }).toPromise();
    } catch {}
    this.user$.next(null);
  }

  private getCsrf(): string | null {
    const match = document.cookie.match(/(?:^|;\s*)rwa_csrf=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : null;
  }
}
