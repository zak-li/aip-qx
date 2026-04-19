import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';
import { applyChartDefaults, TYPE_LABELS } from '../../../utils/chart.js';

export default function ChartBlock({ config }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const cfg   = applyChartDefaults(JSON.parse(JSON.stringify(config)));
    const chart = new Chart(canvasRef.current, cfg);
    return () => chart.destroy();
  }, [config]);

  const title     = config.options?.plugins?.title?.text || '';
  const typeLabel = TYPE_LABELS[config.type] || config.type || 'Chart';

  return (
    <div className="chart-wrap">
      <div className="chart-header">
        <span className="chart-type">{typeLabel}</span>
        {title && <span className="chart-title">{title}</span>}
      </div>
      <div className="chart-body">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
