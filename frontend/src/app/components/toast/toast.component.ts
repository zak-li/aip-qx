import { Component, OnInit } from '@angular/core';
import { ToastService, Toast } from '../../services/toast.service';

@Component({
  selector: 'app-toast',
  standalone: false,
  template: `
    <div class="toast" [class.show]="toast !== null" [class.ok]="toast?.type === 'ok'" [class.err]="toast?.type === 'err'" [class.warn]="toast?.type === 'warn'">
      {{ toast?.message }}
    </div>
  `
})
export class ToastComponent implements OnInit {
  toast: Toast | null = null;

  constructor(private toastService: ToastService) {}

  ngOnInit() {
    this.toastService.toast$.subscribe(t => this.toast = t);
  }
}
