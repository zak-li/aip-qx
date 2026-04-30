import { Component, Input, AfterViewInit, ViewChild, ElementRef } from '@angular/core';
import mermaid from 'mermaid';

mermaid.initialize({ startOnLoad: false, theme: 'dark', themeVariables: { background: '#000000', primaryColor: '#4f8ffc', primaryTextColor: '#e6e8ef', lineColor: 'rgba(255,255,255,0.12)', fontSize: '12px' } });

@Component({
  selector: 'app-mermaid-block',
  standalone: false,
  template: `
    <div class="mermaid-wrap">
      <div class="mermaid-header"><span class="mermaid-type">DIAGRAM</span></div>
      <div class="mermaid-body">
        <div class="mermaid-svg" #container>
          <pre *ngIf="error" class="mermaid-err">{{ error }}</pre>
        </div>
      </div>
    </div>
  `
})
export class MermaidBlockComponent implements AfterViewInit {
  @Input() code = '';
  @ViewChild('container') containerRef!: ElementRef<HTMLDivElement>;
  error = '';

  async ngAfterViewInit() {
    try {
      const id = 'mermaid-' + Math.random().toString(36).slice(2);
      const { svg } = await mermaid.render(id, this.code);
      this.containerRef.nativeElement.innerHTML = svg;
    } catch (e: any) {
      this.error = e.message || 'Render error';
    }
  }
}
