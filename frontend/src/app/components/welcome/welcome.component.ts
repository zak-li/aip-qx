import { Component } from '@angular/core';

@Component({
  selector: 'app-welcome',
  standalone: false,
  template: `
    <div class="welcome">
      <div class="welcome-title">RWA Intelligence</div>
      <div class="welcome-sub">Institutional asset management · Compliance · Blockchain</div>
    </div>
  `
})
export class WelcomeComponent {}
