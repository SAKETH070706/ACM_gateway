import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { api } from '../api/client';
import { LogOut, Shield, Users, ArrowLeft, Home, KeyRound } from 'lucide-react';

export default function Navbar({ user, onLogout }) {
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (e) {
      console.error(e);
    }
    if (onLogout) onLogout();
    navigate('/login');
  };

  const isEbmView = location.pathname.startsWith('/ebm/');
  const isAdminView = location.pathname === '/admin';
  const isLoginView = location.pathname === '/login';

  return (
    <header style={{
      background: 'var(--card)',
      borderBottom: '1px solid var(--border)',
      padding: '12px 24px',
      position: 'sticky',
      top: 0,
      zIndex: 100,
      boxShadow: 'var(--shadow-sm)'
    }}>
      <div style={{
        maxWidth: 1280,
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16
      }}>
        {/* Brand & Left Navigation */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36,
              height: 36,
              borderRadius: 'var(--radius)',
              background: 'var(--primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#FFFFFF',
              boxShadow: '0 2px 8px rgba(37, 99, 235, 0.3)'
            }}>
              <span style={{ fontSize: 18 }}>💬</span>
            </div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 16, letterSpacing: '-0.2px', color: 'var(--heading)' }}>
                ACM <span style={{ color: 'var(--primary)' }}>GATEWAY</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: -2 }}>
                WhatsApp Dispatcher & Token Portal
              </div>
            </div>
          </Link>

          {/* Quick Back to Admin if viewing an EBM page */}
          {user?.role === 'admin' && isEbmView && (
            <button
              onClick={() => navigate('/admin')}
              className="btn-back-link"
              title="Return to Master Admin Dashboard"
              style={{ marginLeft: 8 }}
            >
              <ArrowLeft size={15} />
              <span>Back to Master Admin</span>
            </button>
          )}
        </div>

        {/* Right Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {user ? (
            <>
              {user.role === 'admin' ? (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  background: '#EFF6FF',
                  padding: '6px 14px',
                  borderRadius: 9999,
                  border: '1px solid #BFDBFE',
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--primary)'
                }}>
                  <Shield size={15} />
                  <span>Master Admin</span>
                </div>
              ) : (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  background: '#DCFCE7',
                  padding: '6px 14px',
                  borderRadius: 9999,
                  border: '1px solid #BBF7D0',
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--success)'
                }}>
                  <Users size={15} />
                  <span>EBM: {user.name}</span>
                </div>
              )}

              {/* Back to Home / Dashboard Button */}
              {!isAdminView && user.role === 'admin' && (
                <button
                  onClick={() => navigate('/admin')}
                  className="btn btn-secondary btn-sm"
                  title="Go to Admin Dashboard"
                >
                  <Home size={14} />
                  <span>Dashboard</span>
                </button>
              )}

              <button
                onClick={handleLogout}
                className="btn btn-secondary btn-sm"
                title="Log out of this account"
              >
                <LogOut size={14} />
                <span>Logout</span>
              </button>
            </>
          ) : (
            !isLoginView && (
              <button
                onClick={() => navigate('/login')}
                className="btn btn-primary btn-sm"
              >
                <KeyRound size={14} />
                <span>Sign In</span>
              </button>
            )
          )}
        </div>
      </div>
    </header>
  );
}
