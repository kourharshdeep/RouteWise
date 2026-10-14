import React, { createContext, useContext, useState, useEffect } from 'react';
import { loginUser, registerUser, loginGuest, fetchCurrentUser } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('routewise_token') || null);
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('routewise_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  // Validate token on mount
  useEffect(() => {
    async function checkAuth() {
      if (!token) {
        setIsLoading(false);
        return;
      }
      try {
        const profile = await fetchCurrentUser();
        setUser(profile);
        localStorage.setItem('routewise_user', JSON.stringify(profile));
      } catch (err) {
        console.warn('Session expired or invalid:', err);
        logout();
      } finally {
        setIsLoading(false);
      }
    }
    checkAuth();
  }, [token]);

  const login = async (email, password) => {
    setAuthError(null);
    try {
      const data = await loginUser(email, password);
      setToken(data.access_token);
      setUser(data.user);
      localStorage.setItem('routewise_token', data.access_token);
      localStorage.setItem('routewise_user', JSON.stringify(data.user));
      return data.user;
    } catch (err) {
      setAuthError(err.message || 'Login failed');
      throw err;
    }
  };

  const register = async (payload) => {
    setAuthError(null);
    try {
      const data = await registerUser(payload);
      setToken(data.access_token);
      setUser(data.user);
      localStorage.setItem('routewise_token', data.access_token);
      localStorage.setItem('routewise_user', JSON.stringify(data.user));
      return data.user;
    } catch (err) {
      setAuthError(err.message || 'Registration failed');
      throw err;
    }
  };

  const loginAsGuest = async () => {
    setAuthError(null);
    try {
      const data = await loginGuest();
      setToken(data.access_token);
      setUser(data.user);
      localStorage.setItem('routewise_token', data.access_token);
      localStorage.setItem('routewise_user', JSON.stringify(data.user));
      return data.user;
    } catch (err) {
      setAuthError(err.message || 'Guest access failed');
      throw err;
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setAuthError(null);
    localStorage.removeItem('routewise_token');
    localStorage.removeItem('routewise_user');
  };

  const updateLocalUser = (updatedProfile) => {
    setUser(updatedProfile);
    localStorage.setItem('routewise_user', JSON.stringify(updatedProfile));
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        isAuthenticated: !!token && !!user,
        isGuest: user?.role === 'guest',
        isLoading,
        authError,
        login,
        register,
        loginAsGuest,
        logout,
        updateLocalUser,
        setAuthError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
