import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { RefreshCw } from 'lucide-react';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="state-box state-loading" style={{ margin: '80px auto', minHeight: '60vh' }}>
        <RefreshCw
          size={32}
          className="spin-icon"
          style={{ animation: 'spin 1s linear infinite' }}
        />
        <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-muted)' }}>
          Restoring RouteWise secure session...
        </span>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Preserve intended deep-link destination for post-login redirect
    return <Navigate to="/" state={{ from: location.pathname }} replace />;
  }

  return children;
}
