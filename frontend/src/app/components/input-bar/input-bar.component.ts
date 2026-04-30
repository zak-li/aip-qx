import { Component, OnInit, ViewChild } from '@angular/core';
import { ChatService } from '../../services/chat.service';
import { OptsService } from '../../services/opts.service';
import { SuggestionsComponent } from '../suggestions/suggestions.component';

@Component({
  selector: 'app-input-bar',
  standalone: false,
  template: `
    <div class="input-area">
      <div class="input-shell">
        <div class="terminal-bar">
          <span>AGENT TERMINAL · RWA-01</span>
          <span>{{ busy ? 'PROCESSING...' : 'READY' }}</span>
        </div>
        <app-suggestions #sug (selected)="onSuggestion($event)"></app-suggestions>
        <div class="input-main">
          <span class="term-indicator">&gt;_</span>
          <textarea
            [(ngModel)]="text"
            placeholder="Ask about assets, compliance, blockchain..."
            [disabled]="busy"
            (keydown.enter)="onEnter($event)"
            (keydown.arrowup)="onArrowUp($event)"
            rows="1"
            (input)="autoResize($event)"
          ></textarea>
          <button class="btn-send" [disabled]="busy || !text.trim()" (click)="send()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <div class="input-footer">
          <label class="stream-toggle">
            <input type="checkbox" [checked]="opts.stream" (change)="toggleStream($event)" />
            Stream
          </label>
          <div style="display:flex;align-items:center;gap:10px">
            <button class="opts-toggle" [class.active]="optsPanelOpen" (click)="toggleOpts()" title="Options">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
              </svg>
            </button>
            <button class="opts-toggle" (click)="sug.toggle()" title="Suggestions">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="8" y1="6" x2="21" y2="6"/>
                <line x1="8" y1="12" x2="21" y2="12"/>
                <line x1="8" y1="18" x2="21" y2="18"/>
                <line x1="3" y1="6" x2="3.01" y2="6"/>
                <line x1="3" y1="12" x2="3.01" y2="12"/>
                <line x1="3" y1="18" x2="3.01" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
        <app-options-panel [open]="optsPanelOpen"></app-options-panel>
      </div>
    </div>
  `
})
export class InputBarComponent implements OnInit {
  @ViewChild('sug') sugRef!: SuggestionsComponent;
  text = '';
  busy = false;
  opts: any = {};
  optsPanelOpen = false;

  constructor(private chat: ChatService, private optsService: OptsService) {}

  ngOnInit() {
    this.chat.busy$.subscribe(b => this.busy = b);
    this.optsService.opts$.subscribe(o => this.opts = o);
  }

  send() {
    if (!this.text.trim() || this.busy) return;
    this.chat.send(this.text.trim(), this.optsService.snapshot);
    this.text = '';
  }

  onEnter(event: Event) {
    const ke = event as KeyboardEvent;
    if (ke.shiftKey) return;
    event.preventDefault();
    this.send();
  }

  onSuggestion(s: string) { this.text = s; }

  onArrowUp(event: Event) {
    if (!this.text && !this.busy) {
      event.preventDefault();
      this.sugRef.toggle();
    }
  }

  toggleStream(event: Event) {
    this.optsService.update({ stream: (event.target as HTMLInputElement).checked });
  }

  toggleOpts() { this.optsPanelOpen = !this.optsPanelOpen; }

  autoResize(event: Event) {
    const el = event.target as HTMLTextAreaElement;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  }
}
