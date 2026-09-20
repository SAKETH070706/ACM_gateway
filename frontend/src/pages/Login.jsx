import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { Shield, Users, KeyRound, AlertCircle, CheckCircle, X, Lock } from 'lucide-react';

export default function Login({ onLoginSuccess }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [ebmName, setEbmName] = useState('');
  const [ebmPassword, setEbmPassword] = useState('');
  const [ebmList, setEbmList] = useState([]);
  const [fetchingEbms, setFetchingEbms] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [loading, setLoading] = useState(false);

  // Secret Admin Modal State
  const [adminModalOpen, setAdminModalOpen] = useState(false);
  const [adminPassword, setAdminPassword] = useState('');
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminError, setAdminError] = useState('');

  const navigate = useNavigate();
  const clickCountRef = useRef(0);
  const clickTimerRef = useRef(null);

  useEffect(() => {
    fetchEbmNames();

    // Check if redirected with ?admin=1
    if (searchParams.get('admin') === '1') {
      setAdminModalOpen(true);
    }
  }, [searchParams]);

  // Global Keyboard Shortcut: Ctrl + Shift + A (or Cmd + Shift + A) & Esc
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Check for Ctrl+Shift+A or Cmd+Shift+A
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'A' || e.key === 'a')) {
        e.preventDefault();
        setAdminModalOpen((prev) => !prev);
        setAdminError('');
        setAdminPassword('');
      } else if (e.key === 'Escape') {
        setAdminModalOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Triple-click trigger on title/header
  const handleTitleClick = () => {
    clickCountRef.current += 1;
    if (clickTimerRef.current) clearTimeout(clickTimerRef.current);

    if (clickCountRef.current >= 3) {
      setAdminModalOpen(true);
      setAdminError('');
      setAdminPassword('');
      clickCountRef.current = 0;
    } else {
      clickTimerRef.current = setTimeout(() => {
        clickCountRef.current = 0;
      }, 500);
    }
  };

  const fetchEbmNames = async () => {
    setFetchingEbms(true);
    try {
      const res = await api.getEbmNames();
      const list = res.ebms || [];
      setEbmList(list);
      if (list.length > 0 && !ebmName) {
        setEbmName(list[0].name);
      }
    } catch (err) {
      console.error('Failed to load EBM names:', err);
    } finally {
      setFetchingEbms(false);
    }
  };

  const handleEbmLogin = async (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');
    if (!ebmName) {
      setError('Please select your registered name from the list');
      return;
    }
    setLoading(true);
    try {
      const res = await api.loginEbm(ebmName, ebmPassword);
      if (onLoginSuccess) onLoginSuccess(res.user);
      navigate('/ebm/dashboard');
    } catch (err) {
      setError(err.message || 'Invalid name or password. Please recheck your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleAdminLoginSubmit = async (e) => {
    e.preventDefault();
    setAdminError('');
    setAdminLoading(true);
    try {
      const res = await api.loginAdmin(adminPassword);
      if (onLoginSuccess) onLoginSuccess(res.user);
      setAdminModalOpen(false);
      // Clean query params
      if (searchParams.get('admin')) {
        searchParams.delete('admin');
        setSearchParams(searchParams, { replace: true });
      }
      navigate('/admin');
    } catch (err) {
      setAdminError(err.message || 'Incorrect admin secret key. Access denied.');
    } finally {
      setAdminLoading(false);
    }
  };

  const closeAdminModal = () => {
    setAdminModalOpen(false);
    setAdminError('');
    setAdminPassword('');
    if (searchParams.get('admin')) {
      searchParams.delete('admin');
      setSearchParams(searchParams, { replace: true });
    }
  };

  return (
    <div style={{
      minHeight: '85vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 16px'
    }}>
      <div className="card" style={{ maxWidth: 440, width: '100%', padding: '36px 28px', boxShadow: 'var(--shadow-md)' }}>
        {/* Header with triple-click touch target */}
        <div
          onClick={handleTitleClick}
          title="EBM Access Portal"
          style={{ textAlign: 'center', marginBottom: 28, cursor: 'default', userSelect: 'none' }}
        >
          <div style={{
            width: 56,
            height: 56,
            borderRadius: 'var(--radius)',
            background: '#DCFCE7',
            border: '1px solid #BBF7D0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px',
            color: 'var(--success)'
          }}>
            <Users size={28} />
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--heading)' }}>
            EBM Team Member Login
          </h1>
          <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>
            Select your profile to access your assigned student WhatsApp queue
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '12px 14px',
            background: '#FEF2F2',
            border: '1px solid #F87171',
            borderRadius: 'var(--radius)',
            color: '#B91C1C',
            fontSize: 13,
            marginBottom: 20
          }}>
            <AlertCircle size={18} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Success Alert */}
        {successMsg && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '12px 14px',
            background: '#F0FDF4',
            border: '1px solid #86EFAC',
            borderRadius: 'var(--radius)',
            color: '#15803D',
            fontSize: 13,
            marginBottom: 20
          }}>
            <CheckCircle size={18} style={{ flexShrink: 0 }} />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleEbmLogin}>
          <div className="form-group">
            <label style={{ fontWeight: 600, fontSize: 13, color: 'var(--heading)', marginBottom: 6, display: 'block' }}>
              Select Your Name
            </label>

            {fetchingEbms ? (
              <div style={{
                padding: '10px 12px',
                fontSize: 13,
                color: 'var(--muted)',
                background: '#F8FAFC',
                borderRadius: 6,
                border: '1px solid var(--border)'
              }}>
                Loading registered team members...
              </div>
            ) : ebmList.length > 0 ? (
              <select
                value={ebmName}
                onChange={(e) => setEbmName(e.target.value)}
                required
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                  fontSize: 14,
                  background: '#FFFFFF',
                  color: 'var(--heading)',
                  outline: 'none'
                }}
              >
                <option value="">-- Choose your registered name --</option>
                {ebmList.map((item) => (
                  <option key={item.id} value={item.name}>
                    {item.name}{item.weight && item.weight >= 6 ? ' (Coordinator)' : ''}
                  </option>
                ))}
              </select>
            ) : (
              <div style={{
                padding: '12px',
                background: '#FFFBEB',
                border: '1px solid #FDE68A',
                borderRadius: 6,
                color: '#B45309',
                fontSize: 13,
                lineHeight: 1.4
              }}>
                No EBM members have been registered yet. Please contact the administrator.
              </div>
            )}
          </div>

          <div className="form-group" style={{ marginTop: 16 }}>
            <label style={{ fontWeight: 600, fontSize: 13, color: 'var(--heading)', marginBottom: 6, display: 'block' }}>
              Password
            </label>
            <input
              type="password"
              value={ebmPassword}
              onChange={(e) => setEbmPassword(e.target.value)}
              placeholder="Enter your EBM password"
              required
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                fontSize: 14,
                outline: 'none'
              }}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', marginTop: 22, padding: '11px 16px', fontSize: 14, fontWeight: 600 }}
            disabled={loading || (ebmList.length === 0 && !ebmName)}
          >
            <KeyRound size={16} />
            <span>{loading ? 'Logging in...' : 'Access My Student Queue'}</span>
          </button>
        </form>

        {/* Discreet footer notice */}
        <div style={{
          textAlign: 'center',
          marginTop: 24,
          paddingTop: 16,
          borderTop: '1px solid var(--border)',
          fontSize: 12,
          color: 'var(--muted)'
        }}>
          SRKR ACM Student Chapter &bull; Authorized EBM Dispatcher
        </div>
      </div>

      {/* Secret Master Admin Modal Dialog */}
      {adminModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 16,
            animation: 'modalIn 0.2s ease-out'
          }}
          onClick={closeAdminModal}
        >
          <div
            className="card"
            style={{
              maxWidth: 420,
              width: '100%',
              padding: '30px 26px',
              position: 'relative',
              background: '#0F172A',
              border: '1px solid #334155',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={closeAdminModal}
              title="Close (Esc)"
              style={{
                position: 'absolute',
                top: 16,
                right: 16,
                background: 'none',
                border: 'none',
                color: '#94A3B8',
                cursor: 'pointer',
                padding: 4
              }}
            >
              <X size={20} />
            </button>

            <div style={{ textAlign: 'center', marginBottom: 22 }}>
              <div style={{
                width: 52,
                height: 52,
                borderRadius: '50%',
                background: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                color: '#60A5FA',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 12px'
              }}>
                <Shield size={26} />
              </div>
              <div style={{
                display: 'inline-block',
                background: 'rgba(239, 68, 68, 0.2)',
                color: '#F87171',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '1px',
                padding: '2px 8px',
                borderRadius: 4,
                marginBottom: 8,
                textTransform: 'uppercase'
              }}>
                Restricted Admin Access
              </div>
              <h2 style={{ fontSize: 19, fontWeight: 700, color: '#F8FAFC' }}>
                Master Control Authentication
              </h2>
              <p style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
                Enter the master administrator key to manage system settings, MongoDB records, and EBM allocations.
              </p>
            </div>

            {adminError && (
              <div style={{
                padding: '10px 12px',
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid #EF4444',
                borderRadius: 6,
                color: '#FCA5A5',
                fontSize: 13,
                marginBottom: 16,
                display: 'flex',
                alignItems: 'center',
                gap: 8
              }}>
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span>{adminError}</span>
              </div>
            )}

            <form onSubmit={handleAdminLoginSubmit}>
              <div className="form-group" style={{ marginBottom: 18 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#CBD5E1', marginBottom: 6, display: 'block' }}>
                  Admin Password
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type="password"
                    value={adminPassword}
                    onChange={(e) => setAdminPassword(e.target.value)}
                    placeholder="Enter master password"
                    required
                    autoFocus
                    style={{
                      width: '100%',
                      padding: '11px 12px 11px 38px',
                      borderRadius: 6,
                      background: '#1E293B',
                      border: '1px solid #475569',
                      color: '#FFFFFF',
                      fontSize: 14,
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                  <Lock size={16} style={{ position: 'absolute', left: 12, top: 13, color: '#64748B' }} />
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{
                    flex: 1,
                    background: '#1E293B',
                    borderColor: '#334155',
                    color: '#94A3B8'
                  }}
                  onClick={closeAdminModal}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{
                    flex: 1,
                    background: '#2563EB',
                    borderColor: '#1D4ED8'
                  }}
                  disabled={adminLoading}
                >
                  <Shield size={16} />
                  <span>{adminLoading ? 'Verifying...' : 'Unlock Portal'}</span>
                </button>
              </div>
            </form>

            <div style={{ textAlign: 'center', marginTop: 14, fontSize: 11, color: '#64748B' }}>
              Press <kbd style={{ background: '#334155', padding: '1px 5px', borderRadius: 3, color: '#E2E8F0' }}>Esc</kbd> to close &bull; Shortcut: <kbd style={{ background: '#334155', padding: '1px 5px', borderRadius: 3, color: '#E2E8F0' }}>Ctrl+Shift+A</kbd>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
