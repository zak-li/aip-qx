const SUGGESTIONS = [
  "Résumé du portefeuille d'actifs tokenisés",
  "Analyse AML/KYC des utilisateurs à risque élevé",
  "Transactions des 30 derniers jours",
  "Liste des actifs gelés et leur valeur totale",
  "Schéma JSON complet d'un actif RWA",
  "Score de risque AML moyen par catégorie",
  "Organisations Hyperledger Fabric actives",
  "Rapports SAR en attente de traitement",
  "Top 5 actifs par valeur actuelle",
  "Transactions flagguées réglementaires ce mois",
  "Analyse de fraude Neo4j — flux circulaires",
  "Conformité MiCA — statut des émetteurs",
  "Structure et politique d'endorsement des canaux",
  "Transferts P2P récents entre organisations",
  "Statistiques globales de la plateforme",
];

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function highlight(text, q) {
  if (!q) return esc(text);
  const lo  = text.toLowerCase();
  const idx = lo.indexOf(q.toLowerCase());
  if (idx < 0) return esc(text);
  return esc(text.slice(0, idx)) + '<em>' + esc(text.slice(idx, idx + q.length)) + '</em>' + esc(text.slice(idx + q.length));
}

export default function Suggestions({ query, onPick }) {
  const filtered = query
    ? SUGGESTIONS.filter(s => s.toLowerCase().includes(query.toLowerCase())).slice(0, 7)
    : SUGGESTIONS.slice(0, 7);

  const open = filtered.length > 0;

  return (
    <div className={`sug-panel${open ? ' open' : ''}`}>
      <div className="sug-list">
        {filtered.map((s, i) => (
          <div
            key={i}
            className="sug-item"
            onMouseDown={e => { e.preventDefault(); onPick(s); }}
            dangerouslySetInnerHTML={{
              __html: highlight(s, query) + '<span class="sug-hint">↵</span>',
            }}
          />
        ))}
      </div>
    </div>
  );
}
