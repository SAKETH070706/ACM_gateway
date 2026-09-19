import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { api } from './api/client';
import Navbar from './components/Navbar';
import Toast from './components/Toast';
import Login from './pages/Login';
import AdminDashboard from './pages/AdminDashboard';
import EbmDashboard from './pages/EbmDashboard';

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState({ message: '', type: 'success' });

  useEffect(() => {
    checkSession();
  }, []);

  const checkSession = async () => {
    try {
      const res = await api.getMe();
      if (res.authenticated) {
        setUser({ ...res.user, role: res.role });
      } else {
        setUser(null);
      }
    } catch (err) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => {
      setToast({ message: '', type: 'success' });
    }, 3500);
  };

  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0c1317',
        color: '#25d366',
        fontSize: 18,
        fontWeight: 600
      }}>
        Loading ACM Portal...
      </div>
    );
  }

  return (
    <BrowserRouter>
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Navbar user={user} onLogout={() => setUser(null)} />

        <main style={{ flex: 1 }}>
          <Routes>
            <Route
              path="/login"
              element={
                user?.role === 'admin' ? (
                  <Navigate to="/admin" replace />
                ) : user?.role === 'ebm' ? (
                  <Navigate to="/ebm/dashboard" replace />
                ) : (
                  <Login onLoginSuccess={(u) => setUser(u)} />
                )
              }
            />

            {/* Admin Dashboard */}
            <Route
              path="/admin"
              element={
                user?.role === 'admin' ? (
                  <AdminDashboard showToast={showToast} />
                ) : (
                  <Navigate to="/login" replace />
                )
              }
            />

            {/* EBM Dynamic Route by Username */}
            <Route
              path="/ebm/:username"
              element={<EbmDashboard user={user} showToast={showToast} />}
            />

            {/* EBM Default Route */}
            <Route
              path="/ebm/dashboard"
              element={
                user?.role === 'ebm' ? (
                  <EbmDashboard user={user} showToast={showToast} />
                ) : user?.role === 'admin' ? (
                  <Navigate to="/admin" replace />
                ) : (
                  <Navigate to="/login" replace />
                )
              }
            />

            {/* Default Route */}
            <Route
              path="*"
              element={
                user?.role === 'admin' ? (
                  <Navigate to="/admin" replace />
                ) : user?.role === 'ebm' ? (
                  <Navigate to="/ebm/dashboard" replace />
                ) : (
                  <Navigate to="/login" replace />
                )
              }
            />
          </Routes>
        </main>

        <div className="toast-container">
          <Toast
            message={toast.message}
            type={toast.type}
            onClose={() => setToast({ message: '', type: 'success' })}
          />
        </div>
      </div>
    </BrowserRouter>
  );
}
