import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { Shield, Users, Lock, KeyRound, AlertCircle, ArrowLeft } from 'lucide-react';

export default function Login({ onLoginSuccess }) {
  const [activeTab, setActiveTab] = useState('ebm'); // 'admin' or 'ebm'
  const [adminPassword, setAdminPassword] = useState('');
  const [ebmUsername, setEbmUsername] = useState('');
  const [ebmPassword, setEbmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleAdminLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.loginAdmin(adminPassword);
      if (onLoginSuccess) onLoginSuccess(res.user);
      navigate('/admin');
    } catch (err) {
      setError(err.message || 'Incorrect admin password');
    } finally {
      setLoading(false);
    }
  };

  const handleEbmLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.loginEbm(ebmUsername, ebmPassword);
      if (onLoginSuccess) onLoginSuccess(res.user);
      navigate('/ebm/dashboard');
    } catch (err) {
      setError(err.message || 'Invalid username or password');
    } finally {
      setLoading(false);
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
      <div className="card" style={{ maxWidth: 420, width: '100%', padding: '36px 28px', boxShadow: 'var(--shadow-md)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{
            width: 56,
            height: 56,
            borderRadius: 'var(--radius)',
            background: activeTab === 'admin' ? '#EFF6FF' : '#DCFCE7',
            border: `1px solid ${activeTab === 'admin' ? '#BFDBFE' : '#BBF7D0'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px',
            color: activeTab === 'admin' ? 'var(--primary)' : 'var(--success)'
          }}>
            {activeTab === 'admin' ? (
              <Shield size={28} />
            ) : (
              <Users size={28} />
            )}
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--heading)' }}>
            {activeTab === 'admin' ? 'Master Admin Access' : 'EBM Team Member Login'}
          </h1>
          <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>
            {activeTab === 'admin' ? 'Manage gateway, CSVs, and batch allocation' : 'Access your assigned student batch and WhatsApp launcher'}
          </p>
        </div>

        {/* Role Toggle Tabs */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          background: '#F1F5F9',
          borderRadius: 'var(--radius)',
          padding: 4,
          marginBottom: 24,
          border: '1px solid var(--border)'
        }}>
          <button
            type="button"
            onClick={() => { setActiveTab('ebm'); setError(''); }}
            style={{
              padding: '8px 12px',
              border: 'none',
              background: activeTab === 'ebm' ? 'var(--card)' : 'transparent',
              color: activeTab === 'ebm' ? 'var(--heading)' : 'var(--muted)',
              fontWeight: 700,
              fontSize: 13,
              borderRadius: 8,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              boxShadow: activeTab === 'ebm' ? 'var(--shadow-sm)' : 'none',
              transition: 'all 0.15s ease'
            }}
          >
            <Users size={15} color={activeTab === 'ebm' ? 'var(--success)' : 'currentColor'} />
            <span>EBM Portal</span>
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('admin'); setError(''); }}
            style={{
              padding: '8px 12px',
              border: 'none',
              background: activeTab === 'admin' ? 'var(--card)' : 'transparent',
              color: activeTab === 'admin' ? 'var(--heading)' : 'var(--muted)',
              fontWeight: 700,
              fontSize: 13,
              borderRadius: 8,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              boxShadow: activeTab === 'admin' ? 'var(--shadow-sm)' : 'none',
              transition: 'all 0.15s ease'
            }}
          >
            <Shield size={15} color={activeTab === 'admin' ? 'var(--primary)' : 'currentColor'} />
            <span>Master Admin</span>
          </button>
        </div>

        {error && (
          <div style={{
            background: '#FEE2E2',
            border: '1px solid #FECACA',
            color: 'var(--danger)',
            padding: '10px 14px',
            borderRadius: 'var(--radius)',
            fontSize: 13,
            marginBottom: 18,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontWeight: 500
          }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {activeTab === 'admin' ? (
          <form onSubmit={handleAdminLogin}>
            <div className="form-group">
              <label>Master Admin Password</label>
              <input
                type="password"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                placeholder="Enter password (default: admin)"
                required
                autoFocus
              />
            </div>
            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 8 }}
              disabled={loading}
            >
              <Lock size={16} />
              <span>{loading ? 'Authenticating...' : 'Sign In to Dashboard'}</span>
            </button>
          </form>
        ) : (
          <form onSubmit={handleEbmLogin}>
            <div className="form-group">
              <label>EBM Username</label>
              <input
                type="text"
                value={ebmUsername}
                onChange={(e) => setEbmUsername(e.target.value)}
                placeholder="Enter your EBM username"
                required
                autoFocus
              />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input
                type="password"
                value={ebmPassword}
                onChange={(e) => setEbmPassword(e.target.value)}
                placeholder="Enter your EBM password"
                required
              />
            </div>
            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 8 }}
              disabled={loading}
            >
              <KeyRound size={16} />
              <span>{loading ? 'Logging in...' : 'Access My Student Queue'}</span>
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
