import { createBrowserRouter, Navigate } from 'react-router-dom';

import AgentPage from '../pages/AgentPage.jsx';

export const router = createBrowserRouter([
  { path: '/',      element: <Navigate to="/agent" replace /> },
  { path: '/agent', element: <AgentPage /> },
  { path: '*',      element: <Navigate to="/agent" replace /> },
]);
