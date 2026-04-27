export const TYPE_LABELS = {
  line:  'Line Chart',
  radar: 'Radar Chart',
};

const RADAR_FALLBACKS = new Set(['pie', 'doughnut', 'polarArea', 'radar']);

function normalizeType(type) {
  if (type === 'radar') return 'radar';
  if (RADAR_FALLBACKS.has(type)) return 'radar';
  return 'line';
}

const PALETTE = [
  { border: '#4f8ffc', rgb: '79,143,252' },
];

function makeGradient(rgb) {
  return (ctx) => {
    const chart = ctx.chart;
    const area  = chart.chartArea;
    if (!area) return `rgba(${rgb},0.18)`;
    const g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
    g.addColorStop(0, `rgba(${rgb},0.45)`);
    g.addColorStop(0.55, `rgba(${rgb},0.12)`);
    g.addColorStop(1, `rgba(${rgb},0)`);
    return g;
  };
}

const FONT = "'Space Grotesk', ui-sans-serif, system-ui, sans-serif";
const MONO = "'Space Mono', ui-monospace, monospace";

export function applyChartDefaults(cfg) {
  cfg.type = normalizeType(cfg.type);
  const isRadar = cfg.type === 'radar';
  const isLine  = cfg.type === 'line';

  if (!cfg.data) cfg.data = { labels: [], datasets: [] };

  if (isRadar && Array.isArray(cfg.data.datasets)) {
    cfg.data.datasets = cfg.data.datasets.map(ds => {
      if (Array.isArray(ds.data) && typeof ds.data[0] === 'object' && ds.data[0] !== null) {
        return { ...ds, data: ds.data.map(p => p.y ?? p.r ?? p.v ?? 0) };
      }
      return ds;
    });
  }

  cfg.data.datasets?.forEach((ds, i) => {
    const c = PALETTE[i % PALETTE.length];
    if (isLine) {
      ds.borderColor      ??= c.border;
      ds.backgroundColor    = makeGradient(c.rgb);
      ds.fill              = ds.fill ?? true;
      ds.borderWidth       = ds.borderWidth ?? 2.5;
      ds.pointRadius       = ds.pointRadius ?? 4;
      ds.pointHoverRadius  = 8;
      ds.pointBackgroundColor = c.border;
      ds.pointBorderColor     = '#000';
      ds.pointBorderWidth     = 2;
      ds.pointHoverBorderWidth = 2.5;
      ds.pointHoverBackgroundColor = '#fff';
      ds.pointStyle           = 'circle';
      ds.tension              = ds.tension ?? 0.35;
    } else {
      ds.borderColor      ??= c.border;
      ds.backgroundColor    = makeGradient(c.rgb);
      ds.borderWidth       = 2.5;
      ds.pointBackgroundColor = c.border;
      ds.pointBorderColor     = '#000';
      ds.pointBorderWidth     = 2;
      ds.pointRadius          = 4;
      ds.pointHoverRadius     = 7;
      ds.pointHoverBackgroundColor = '#fff';
      ds.pointStyle           = 'circle';
    }
  });

  cfg.options = {
    responsive:          true,
    maintainAspectRatio: false,
    animation:           { duration: 900, easing: 'easeOutCubic' },
    layout:              { padding: 0 },
    interaction:         { mode: isLine ? 'index' : 'nearest', intersect: false },
    plugins: {
      title:  { display: false },
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(0,0,0,0.96)',
        borderColor:     'rgba(79,143,252,0.4)',
        borderWidth:     1,
        titleColor:      '#e6e8ef',
        titleFont:       { family: FONT, size: 12, weight: '600' },
        bodyColor:       '#b8bcc9',
        bodyFont:        { family: MONO, size: 11, weight: '400' },
        padding:         12,
        cornerRadius:    0,
        displayColors:   true,
        boxWidth: 10, boxHeight: 10, boxPadding: 6,
        usePointStyle:   true,
        caretSize:       6,
      },
    },
    scales: isRadar
      ? {
          r: {
            grid:        { color: 'rgba(255,255,255,0.06)', circular: false },
            angleLines:  { color: 'rgba(255,255,255,0.06)' },
            ticks:       { display: false, backdropColor: 'transparent', showLabelBackdrop: false },
            pointLabels: { display: false },
          },
        }
      : {
          x: { display: false, grid: { display: false }, ticks: { display: false }, border: { display: false } },
          y: { display: false, grid: { display: false }, ticks: { display: false }, border: { display: false } },
        },
  };
  return cfg;
}

function isChartConfig(obj) {
  if (!obj || typeof obj !== 'object') return false;
  if (typeof obj.type !== 'string') return false;
  if (!obj.data || typeof obj.data !== 'object') return false;
  const ds = obj.data.datasets;
  return Array.isArray(ds) && ds.length > 0 && ds.some(d => Array.isArray(d?.data));
}

export function parseContentSegments(raw) {
  const segments = [];
  const blockRe = /```(chart|json|mermaid)\s*\n([\s\S]*?)```/g;
  let last = 0, m;

  while ((m = blockRe.exec(raw)) !== null) {
    if (m.index > last) segments.push({ type: 'text', content: raw.slice(last, m.index) });
    const [full, fence, body] = m;

    if (fence === 'mermaid') {
      segments.push({ type: 'mermaid', code: body });
      last = m.index + full.length;
      continue;
    }

    let parsed = null;
    try { parsed = JSON.parse(body.trim()); } catch { /* ignore */ }

    if (fence === 'chart' && parsed) {
      segments.push({ type: 'chart', config: parsed });
    } else if (fence === 'json' && isChartConfig(parsed)) {
      segments.push({ type: 'chart', config: parsed });
    } else {
      segments.push({ type: 'text', content: full });
    }
    last = m.index + full.length;
  }
  if (last < raw.length) segments.push({ type: 'text', content: raw.slice(last) });
  return segments;
}
