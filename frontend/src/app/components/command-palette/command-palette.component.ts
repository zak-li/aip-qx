import { Component, OnInit, HostListener } from '@angular/core';
import { PaletteService, PaletteItem } from '../../services/palette.service';
import { EntityService } from '../../services/entity.service';

@Component({
  selector: 'app-command-palette',
  standalone: false,
  template: `
    <div class="palette-overlay" *ngIf="open" (click)="close()">
      <div class="palette" (click)="$event.stopPropagation()">
        <div class="palette-input-wrap">
          <span class="palette-prompt">&gt;</span>
          <input class="palette-input"
            #searchInput
            placeholder="Search assets, organizations, transactions..."
            (input)="onSearch($event)"
            (keydown)="onKey($event)"
            autofocus />
          <span class="palette-hint">ESC</span>
        </div>
        <div class="palette-list">
          <ng-container *ngIf="items.length > 0; else emptyState">
            <button class="palette-item"
              *ngFor="let item of items; let i = index"
              [class.active]="i === cursor"
              (click)="pick(item)"
              (mouseenter)="cursor = i">
              <span class="palette-icon">
                <svg *ngIf="item.kind === 'asset'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="7" width="20" height="14" rx="2"/>
                  <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
                </svg>
                <svg *ngIf="item.kind === 'org'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                  <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                </svg>
                <svg *ngIf="item.kind === 'tx'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="17 1 21 5 17 9"/>
                  <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
                  <polyline points="7 23 3 19 7 15"/>
                  <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
                </svg>
              </span>
              <div class="palette-main">
                <div class="palette-title">{{ item.title }}</div>
                <div class="palette-sub">{{ item.sub }}</div>
              </div>
              <span class="palette-kind">{{ item.kind.toUpperCase() }}</span>
            </button>
          </ng-container>
          <ng-template #emptyState>
            <div class="palette-empty">
              {{ loading ? 'Searching...' : 'Type to search' }}
            </div>
          </ng-template>
        </div>
        <div class="palette-footer">
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  `
})
export class CommandPaletteComponent implements OnInit {
  open = false;
  items: PaletteItem[] = [];
  loading = false;
  cursor = 0;
  private debounce: any;

  constructor(private palette: PaletteService, private entity: EntityService) {}

  ngOnInit() {
    this.palette.open$.subscribe(v => { this.open = v; this.cursor = 0; });
    this.palette.items$.subscribe(v => { this.items = v; this.cursor = 0; });
    this.palette.loading$.subscribe(v => this.loading = v);
  }

  @HostListener('document:keydown', ['$event'])
  onGlobalKey(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      this.palette.toggle();
    }
  }

  close() { this.palette.close(); }

  onSearch(e: Event) {
    clearTimeout(this.debounce);
    const q = (e.target as HTMLInputElement).value;
    this.debounce = setTimeout(() => this.palette.search(q), 250);
  }

  onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') { this.palette.close(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); this.cursor = Math.min(this.cursor + 1, this.items.length - 1); }
    if (e.key === 'ArrowUp') { e.preventDefault(); this.cursor = Math.max(this.cursor - 1, 0); }
    if (e.key === 'Enter' && this.items[this.cursor]) this.pick(this.items[this.cursor]);
  }

  pick(item: PaletteItem) {
    this.palette.close();
    this.entity.open(item.id, item.kind);
  }
}
