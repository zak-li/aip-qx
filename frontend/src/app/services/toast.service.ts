import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface Toast { message: string; type: 'ok' | 'err' | 'warn'; }

@Injectable({ providedIn: 'root' })
export class ToastService {
  toast$ = new BehaviorSubject<Toast | null>(null);

  show(message: string, type: Toast['type'] = 'ok') {
    this.toast$.next({ message, type });
    setTimeout(() => this.toast$.next(null), 3000);
  }
}
