import { Component, OnInit } from '@angular/core';
import { EntityService } from '../../services/entity.service';

@Component({
  selector: 'app-entity-panel',
  standalone: false,
  template: `
    <ng-container *ngIf="open">
      <div class="entity-overlay" (click)="entity.close()"></div>
      <div class="entity-panel">
        <div class="entity-head">
          <div class="entity-title-wrap">
            <span class="entity-kind-tag">{{ kind?.toUpperCase() }}</span>
            <span class="entity-title">{{ id }}</span>
          </div>
          <button class="entity-close" (click)="entity.close()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="entity-body">
          <div *ngIf="loading" class="entity-empty">Loading...</div>
          <div *ngIf="error" class="entity-empty entity-err">{{ error }}</div>
          <div *ngIf="detail && !loading" class="entity-table">
            <div class="entity-row" *ngFor="let entry of entries">
              <span class="entity-k">{{ entry.key }}</span>
              <span class="entity-v">{{ entry.value }}</span>
            </div>
          </div>
        </div>
      </div>
    </ng-container>
  `
})
export class EntityPanelComponent implements OnInit {
  open = false;
  id: string | null = null;
  kind: string | null = null;
  detail: any = null;
  loading = false;
  error: string | null = null;
  entries: { key: string; value: string }[] = [];

  constructor(public entity: EntityService) {}

  ngOnInit() {
    this.entity.open$.subscribe(v => this.open = v);
    this.entity.activeId$.subscribe(v => this.id = v);
    this.entity.activeKind$.subscribe(v => this.kind = v);
    this.entity.loading$.subscribe(v => this.loading = v);
    this.entity.error$.subscribe(v => this.error = v);
    this.entity.detail$.subscribe(d => {
      this.detail = d;
      this.entries = d
        ? Object.entries(d).map(([k, v]) => ({ key: k, value: typeof v === 'object' ? JSON.stringify(v) : String(v) }))
        : [];
    });
  }
}
