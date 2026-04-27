import { useOptsStore } from '../store/optsStore.js';

const STYLES   = ['auto', 'synthese', 'technique', 'bullet', 'json', 'risque'];
const STYLE_LBL = { auto: 'AUTO', synthese: 'SYNTHÈSE', technique: 'TECHNIQUE', bullet: 'BULLET', json: 'JSON', risque: 'RISQUE' };
const TOKEN_OPTS = [512, 1024, 2048, 4096, 8192];
const TOKEN_LBL  = { 512: '512', 1024: '1K', 2048: '2K', 4096: '4K', 8192: '8K' };
const CTX_OPTS   = [5, 10, 20, 50];
const CTX_LBL    = { 5: '5', 10: '10', 20: '20', 50: 'MAX' };

function Seg({ options, labels, active, onChange }) {
  return (
    <div className="seg">
      {options.map(v => (
        <button
          key={v}
          className={`seg-btn${active === v ? ' active' : ''}`}
          onClick={() => onChange(v)}
        >
          {labels[v] ?? v}
        </button>
      ))}
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange, display }) {
  return (
    <div className="opt-group">
      <label className="opt-label">
        {label} <span>{display ?? value}</span>
      </label>
      <input
        type="range" className="opt-slider"
        min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
      />
    </div>
  );
}

export default function OptionsPanel({ open }) {
  const opts = useOptsStore();

  return (
    <div className={`opts-panel${open ? ' open' : ''}`}>
      <div className="opts-body">

        <Slider label="Température"  value={opts.temperature} min={0} max={1} step={0.05}
          display={opts.temperature.toFixed(2)}
          onChange={v => opts.set({ temperature: v })} />

        <Slider label="Top-P" value={opts.topP} min={0} max={1} step={0.05}
          display={opts.topP.toFixed(2)}
          onChange={v => opts.set({ topP: v })} />

        <div className="opt-group">
          <label className="opt-label">Max tokens <span>{opts.maxTokens}</span></label>
          <Seg options={TOKEN_OPTS} labels={TOKEN_LBL} active={opts.maxTokens}
            onChange={v => opts.set({ maxTokens: v })} />
        </div>

        <div className="opt-group">
          <label className="opt-label">Mode retrieval</label>
          <div className="seg">
            <button className={`seg-btn${opts.useRag ? ' active' : ''}`} id="ragOn"  onClick={() => opts.set({ useRag: true  })}>KB + LLM</button>
            <button className={`seg-btn${!opts.useRag ? ' active' : ''}`} id="ragOff" onClick={() => opts.set({ useRag: false })}>LLM SEUL</button>
          </div>
        </div>

        <Slider label="Freq. Penalty" value={opts.freqPenalty} min={-2} max={2} step={0.1}
          display={opts.freqPenalty.toFixed(2)}
          onChange={v => opts.set({ freqPenalty: v })} />

        <Slider label="Pres. Penalty" value={opts.presPenalty} min={-2} max={2} step={0.1}
          display={opts.presPenalty.toFixed(2)}
          onChange={v => opts.set({ presPenalty: v })} />

        <Slider label="Résultats KB" value={opts.nResults} min={1} max={15} step={1}
          onChange={v => opts.set({ nResults: parseInt(v) })} />

        <div className="opt-group">
          <label className="opt-label">Profondeur contexte</label>
          <Seg options={CTX_OPTS} labels={CTX_LBL} active={opts.ctxDepth}
            onChange={v => opts.set({ ctxDepth: v })} />
        </div>

        <hr className="opts-section-sep" />

        <div className="opt-group opts-full-row">
          <label className="opt-label">Style preset</label>
          <div className="seg wrap">
            {STYLES.map(s => (
              <button key={s} className={`seg-btn${opts.stylePreset === s ? ' active' : ''}`}
                onClick={() => opts.set({ stylePreset: s })}>
                {STYLE_LBL[s]}
              </button>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
