import { Component, Input, OnInit } from '@angular/core';
import { OptsService } from '../../services/opts.service';

@Component({
  selector: 'app-options-panel',
  standalone: false,
  template: `
    <div class="opts-panel" [class.open]="open">
      <div class="opts-body">
        <div class="opt-group">
          <div class="opt-label">Temperature <span>{{ opts.temperature }}</span></div>
          <input class="opt-slider" type="range" min="0" max="2" step="0.05"
            [value]="opts.temperature" (input)="update('temperature', $event)" />
        </div>
        <div class="opt-group">
          <div class="opt-label">Top P <span>{{ opts.topP }}</span></div>
          <input class="opt-slider" type="range" min="0" max="1" step="0.05"
            [value]="opts.topP" (input)="update('topP', $event)" />
        </div>
        <div class="opt-group">
          <div class="opt-label">Max Tokens <span>{{ opts.maxTokens }}</span></div>
          <input class="opt-slider" type="range" min="256" max="8192" step="256"
            [value]="opts.maxTokens" (input)="update('maxTokens', $event)" />
        </div>
        <div class="opt-group">
          <div class="opt-label">Presence Penalty <span>{{ opts.presencePenalty }}</span></div>
          <input class="opt-slider" type="range" min="-2" max="2" step="0.1"
            [value]="opts.presencePenalty" (input)="update('presencePenalty', $event)" />
        </div>
        <div class="opt-group">
          <div class="opt-label">Frequency Penalty <span>{{ opts.frequencyPenalty }}</span></div>
          <input class="opt-slider" type="range" min="-2" max="2" step="0.1"
            [value]="opts.frequencyPenalty" (input)="update('frequencyPenalty', $event)" />
        </div>
        <div class="opt-group opts-full-row">
          <div class="opt-label">Style</div>
          <div class="seg">
            <button class="seg-btn" [class.active]="opts.style === 'concise'" (click)="optsService.update({style: 'concise'})">Concise</button>
            <button class="seg-btn" [class.active]="opts.style === 'precise'" (click)="optsService.update({style: 'precise'})">Precise</button>
            <button class="seg-btn" [class.active]="opts.style === 'verbose'" (click)="optsService.update({style: 'verbose'})">Verbose</button>
          </div>
        </div>
        <div class="opt-group opts-full-row">
          <div class="opt-label">RAG</div>
          <div class="seg">
            <button id="ragOn" class="seg-btn" [class.active]="opts.ragEnabled" (click)="optsService.update({ragEnabled: true})">On</button>
            <button id="ragOff" class="seg-btn" [class.active]="!opts.ragEnabled" (click)="optsService.update({ragEnabled: false})">Off</button>
          </div>
        </div>
        <div class="opt-actions opts-full-row">
          <button class="opt-act danger" (click)="optsService.reset()">Reset to defaults</button>
        </div>
      </div>
    </div>
  `
})
export class OptionsPanelComponent implements OnInit {
  @Input() open = false;
  opts: any = {};

  constructor(public optsService: OptsService) {}

  ngOnInit() {
    this.optsService.opts$.subscribe(o => this.opts = o);
  }

  update(key: string, event: Event) {
    const val = parseFloat((event.target as HTMLInputElement).value);
    this.optsService.update({ [key]: val } as any);
  }
}
