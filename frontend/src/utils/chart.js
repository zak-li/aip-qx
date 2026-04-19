export const TYPE_LABELS = {
  bar:       'Bar Chart',
  line:      'Line / Area',
  pie:       'Pie Chart',
  doughnut:  'Donut Chart',
  radar:     'Radar Chart',
  polarArea: 'Polar Area',
  bubble:    'Bubble Chart',
  scatter:   'Scatter Plot',
};

const PALETTE = [
  { bg: 'rgba(79,143,252,0.75)',  border: '#4f8ffc' },
  { bg: 'rgba(70,167,88,0.75)',   border: '#46a758' },
  { bg: 'rgba(229,72,77,0.75)',   border: '#e5484d' },
  { bg: 'rgba(245,166,35,0.75)',  border: '#f5a623' },
  { bg: 'rgba(155,89,182,0.75)',  border: '#9b59b6' },
  { bg: 'rgba(23,162,184,0.75)',  border: '#17a2b8' },
  { bg: 'rgba(255,105,180,0.75)', border: '#ff69b4' },
  { bg: 'rgba(100,200,150,0.75)', border: '#64c896' },
];

export function applyChartDefaults(cfg) {
  const isPie    = ['pie', 'doughnut'].includes(cfg.type);
  const isPolar  = cfg.type === 'polarArea';
  const isRadar  = cfg.type === 'radar';
  const isLine   = cfg.type === 'line';
  const isScatter = cfg.type === 'scatter';
  const isBubble  = cfg.type === 'bubble';

  cfg.data?.datasets?.forEach((ds, i) => {
    const c = PALETTE[i % PALETTE.length];
    if (isPie || isPolar) {
      ds.backgroundColor ??= PALETTE.map(p => p.bg);
      ds.borderColor      ??= 'rgba(6,7,11,0.8)';
      ds.borderWidth = 2;
      if (isPie) ds.hoverOffset = 10;
    } else if (isLine) {
      ds.borderColor      ??= c.border;
      ds.backgroundColor  ??= ds.fill ? c.bg.replace('0.75','0.12') : 'transparent';
      ds.borderWidth          = ds.borderWidth ?? 2;
      ds.pointRadius          = ds.pointRadius ?? 4;
      ds.pointHoverRadius     = 6;
      ds.pointBackgroundColor = c.border;
      ds.pointBorderColor     = 'rgba(6,7,11,0.6)';
      ds.pointBorderWidth     = 1.5;
      ds.tension              = ds.tension ?? 0.38;
    } else if (isRadar) {
      ds.backgroundColor ??= c.bg.replace('0.75','0.18');
      ds.borderColor     ??= c.border;
      ds.borderWidth          = 2;
      ds.pointBackgroundColor = c.border;
      ds.pointRadius          = 3;
    } else if (isScatter || isBubble) {
      ds.backgroundColor ??= c.bg;
      ds.borderColor     ??= c.border;
      ds.borderWidth = 1;
    } else {
      ds.backgroundColor ??= c.bg;
      ds.borderColor     ??= c.border;
      ds.borderWidth   = ds.borderWidth ?? 1;
      ds.borderRadius  = ds.borderRadius ?? 3;
      ds.borderSkipped = false;
    }
  });

  cfg.options ??= {};
  cfg.options.responsive          = true;
  cfg.options.maintainAspectRatio = true;
  cfg.options.animation = { duration: 700, easing: 'easeInOutQuart' };

  cfg.options.plugins ??= {};
  cfg.options.plugins.tooltip = Object.assign({
    backgroundColor: 'rgba(8,9,13,0.96)',
    borderColor:     'rgba(79,143,252,0.2)',
    borderWidth:     1,
    titleColor:      '#e2e4ea',
    bodyColor:       '#8b8fa4',
    padding:         10,
    cornerRadius:    0,
    displayColors:   true,
    boxWidth: 8, boxHeight: 8, boxPadding: 4,
  }, cfg.options.plugins.tooltip ?? {});

  cfg.options.plugins.legend = Object.assign({
    labels: { color: '#8b8fa4', boxWidth: 10, padding: 18, font: { size: 10 } },
  }, cfg.options.plugins.legend ?? {});

  if (!isPie && !isPolar) {
    cfg.options.scales ??= {};
    if (isRadar) {
      cfg.options.scales.r = Object.assign({
        grid:        { color: 'rgba(255,255,255,0.05)' },
        angleLines:  { color: 'rgba(255,255,255,0.05)' },
        ticks:       { color: '#4e5264', backdropColor: 'transparent', font: { size: 9 } },
        pointLabels: { color: '#8b8fa4', font: { size: 10 } },
      }, cfg.options.scales.r ?? {});
    } else {
      ['x', 'y'].forEach(ax => {
        cfg.options.scales[ax] = Object.assign({
          grid:   { color: 'rgba(255,255,255,0.04)', drawBorder: false },
          ticks:  { color: '#4e5264', font: { size: 10 } },
          border: { color: 'rgba(255,255,255,0.06)' },
        }, cfg.options.scales[ax] ?? {});
      });
    }
  }
  return cfg;
}

export function parseContentSegments(raw) {
  const segments = [];
  const chartRe  = /```chart\s*\n([\s\S]*?)```/g;
  let last = 0, m;

  while ((m = chartRe.exec(raw)) !== null) {
    if (m.index > last) segments.push({ type: 'text', content: raw.slice(last, m.index) });
    try {
      segments.push({ type: 'chart', config: JSON.parse(m[1].trim()) });
    } catch {
      segments.push({ type: 'text', content: m[0] });
    }
    last = m.index + m[0].length;
  }
  if (last < raw.length) segments.push({ type: 'text', content: raw.slice(last) });
  return segments;
}
