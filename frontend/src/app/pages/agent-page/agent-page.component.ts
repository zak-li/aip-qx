import { Component, OnInit } from '@angular/core';
import { AuthService } from '../../services/auth.service';
import { ChatService, Message } from '../../services/chat.service';

@Component({
  selector: 'app-agent-page',
  standalone: false,
  template: `
    <div class="page-shell">
      <app-status-line></app-status-line>
      <div class="layout">
        <div class="chat">
          <app-message-list [messages]="messages"></app-message-list>
          <app-input-bar></app-input-bar>
        </div>
      </div>
      <app-command-palette></app-command-palette>
      <app-entity-panel></app-entity-panel>
      <app-toast></app-toast>
      <app-login-form *ngIf="showLogin" (success)="onLogin()"></app-login-form>
    </div>
  `
})
export class AgentPageComponent implements OnInit {
  messages: Message[] = [];
  showLogin = false;

  constructor(private auth: AuthService, private chat: ChatService) {}

  async ngOnInit() {
    await this.auth.hydrate();
    this.auth.checked$.subscribe(checked => {
      if (checked && this.auth.user$.value === null) this.showLogin = true;
    });
    this.auth.user$.subscribe(u => {
      if (u !== null) this.showLogin = false;
    });
    this.chat.messages$.subscribe(m => this.messages = m);
  }

  onLogin() { this.showLogin = false; }
}
