import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="not-found">
      <div className="not-found-code">404 // NOT FOUND</div>
      <div className="not-found-msg">Cette route n'existe pas.</div>
      <Link to="/agent" className="not-found-link">← RETOUR AU TERMINAL</Link>
    </div>
  );
}
