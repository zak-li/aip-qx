import { useEffect, useId, useRef, useState } from 'react';
import mermaid from 'mermaid';

let initialized = false;
function initMermaid() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: 'base',
    securityLevel: 'strict',
    fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif",
    themeVariables: {
      background:        '#000000',
      primaryColor:      '#0a0a0a',
      primaryTextColor:  '#e6e8ef',
      primaryBorderColor:'#4f8ffc',
      secondaryColor:    '#0a0a0a',
      tertiaryColor:     '#0a0a0a',
      lineColor:         '#3a4150',
      textColor:         '#b8bcc9',
      mainBkg:           '#0a0a0a',
      nodeBorder:        '#4f8ffc',
      clusterBkg:        '#050505',
      clusterBorder:     '#2a2f3a',
      titleColor:        '#e6e8ef',
      edgeLabelBackground:'#000000',
      actorBkg:          '#0a0a0a',
      actorBorder:       '#4f8ffc',
      actorTextColor:    '#e6e8ef',
      actorLineColor:    '#3a4150',
      signalColor:       '#b8bcc9',
      signalTextColor:   '#b8bcc9',
      labelBoxBkgColor:  '#0a0a0a',
      labelBoxBorderColor:'#4f8ffc',
      labelTextColor:    '#e6e8ef',
      loopTextColor:     '#b8bcc9',
      noteBkgColor:      'rgba(79,143,252,0.08)',
      noteBorderColor:   'rgba(79,143,252,0.4)',
      noteTextColor:     '#e6e8ef',
    },
    flowchart:        { curve: 'basis', padding: 18, useMaxWidth: true },
    sequence:         { useMaxWidth: true, diagramMarginX: 30, diagramMarginY: 18 },
    er:               { useMaxWidth: true },
  });
  initialized = true;
}

export default function MermaidBlock({ code }) {
  const ref    = useRef(null);
  const id     = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function render() {
      try {
        initMermaid();
        const { svg } = await mermaid.render(`mmd-${id}`, code.trim());
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          setErr(null);
        }
      } catch (e) {
        if (!cancelled) setErr(e?.message || 'Mermaid render error');
      }
    }
    render();
    return () => { cancelled = true; };
  }, [code, id]);

  return (
    <div className="mermaid-wrap">
      <div className="mermaid-header">
        <span className="mermaid-type">DIAGRAM</span>
      </div>
      <div className="mermaid-body">
        {err
          ? <pre className="mermaid-err">{err}\n\n{code}</pre>
          : <div ref={ref} className="mermaid-svg" />}
      </div>
    </div>
  );
}
