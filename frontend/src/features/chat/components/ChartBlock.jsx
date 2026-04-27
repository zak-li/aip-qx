import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';
import { applyChartDefaults, TYPE_LABELS } from '../../../utils/chart.js';

const RADAR_TYPES = new Set(['pie', 'doughnut', 'polarArea', 'radar']);

export default function ChartBlock({ config }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const cfg = applyChartDefaults(JSON.parse(JSON.stringify(config)));
    if (cfg.options?.plugins?.title) cfg.options.plugins.title.display = false;
    const chart = new Chart(canvasRef.current, cfg);
    return () => chart.destroy();
  }, [config]);

  const resolvedType = RADAR_TYPES.has(config.type) ? 'radar' : 'line';
  const typeLabel    = TYPE_LABELS[resolvedType];

  return (
    <div className="chart-wrap">
      <div className="chart-header">
        <span className="chart-type">{typeLabel}</span>
      </div>
      <div className="chart-body">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
