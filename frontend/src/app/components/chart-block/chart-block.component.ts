import { Component, Input, AfterViewInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

@Component({
  selector: 'app-chart-block',
  standalone: false,
  template: `
    <div class="chart-wrap">
      <div class="chart-header">
        <span class="chart-type">{{ spec.type?.toUpperCase() }} CHART</span>
        <span class="chart-title">{{ spec.title || '' }}</span>
      </div>
      <div class="chart-body">
        <canvas #chartCanvas></canvas>
      </div>
    </div>
  `
})
export class ChartBlockComponent implements AfterViewInit, OnDestroy {
  @Input() spec: any = {};
  @ViewChild('chartCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;
  private chart?: Chart;

  ngAfterViewInit() {
    const ctx = this.canvasRef.nativeElement.getContext('2d');
    if (!ctx) return;
    try {
      this.chart = new Chart(ctx, {
        type: this.spec.type || 'bar',
        data: this.spec.data || { labels: [], datasets: [] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#9097a8', font: { family: 'Space Mono', size: 11 } } } },
          scales: {
            x: { ticks: { color: '#555a6b' }, grid: { color: 'rgba(255,255,255,0.04)' } },
            y: { ticks: { color: '#555a6b' }, grid: { color: 'rgba(255,255,255,0.04)' } }
          },
          ...(this.spec.options || {})
        }
      });
    } catch {}
  }

  ngOnDestroy() { this.chart?.destroy(); }
}
