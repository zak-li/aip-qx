import { createBrowserRouter, Navigate } from 'react-router-dom';
import AgentPage    from '../pages/AgentPage.jsx';
import NotFoundPage from '../pages/NotFoundPage.jsx';

export const router = createBrowserRouter([
  { path: '/',      element: <Navigate to="/agent" replace /> },
  { path: '/agent', element: <AgentPage /> },
  { path: '*',      element: <NotFoundPage /> },
]);
