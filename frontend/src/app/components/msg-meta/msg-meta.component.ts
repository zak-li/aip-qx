import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-msg-meta',
  standalone: false,
  template: `
    <div class="msg-info" *ngIf="responseTime || promptTokens">
      <span class="msg-info-item" *ngIf="responseTime">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 15"/></svg>
        <span class="val">{{ responseTime }}s</span>
      </span>
      <span class="msg-info-item" *ngIf="promptTokens">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
        <span class="val">{{ promptTokens }}↑ {{ completionTokens }}↓</span>
      </span>
    </div>
  `
})
export class MsgMetaComponent {
  @Input() responseTime?: number;
  @Input() promptTokens?: number;
  @Input() completionTokens?: number;
  @Input() style?: string;
}
