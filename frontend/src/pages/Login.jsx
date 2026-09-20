import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { Shield, Users, Lock, KeyRound, AlertCircle, UserPlus, CheckCircle, X } from 'lucide-react';

export default function Login({ onLoginSuccess }) {
  const [activeTab, setActiveTab] = useState('ebm'); // 'admin' or 'ebm'
  const [adminPassword, setAdminPassword] = useState('');
  const [ebmName, setEbmName] = useState('');
  const [ebmPassword, setEbmPassword] = useState('');
  const [ebmList, setEbmList] = useState([]);
  const [fetchingEbms, setFetchingEbms] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [loading, setLoading] = useState(false);

  // Registration Modal State
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [regName, setRegName] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regLoading, setRegLoading] = useState(false);
  const [regError, setRegError] = useState('');

  const navigate = useNavigate();

  useEffect(() => {
    fetchEbmNames();
  }, []);

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

  const handleAdminLogin = async (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');
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
    setSuccessMsg('');
    if (!ebmName) {
      setError('Please select your name from the dropdown');
      return;
    }
    setLoading(true);
    try {
      const res = await api.loginEbm(ebmName, ebmPassword);
      if (onLoginSuccess) onLoginSuccess(res.user);
      navigate('/ebm/dashboard');
    } catch (err) {
      setError(err.message || 'Invalid name or password');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterEbm = async (e) => {
    e.preventDefault();
    setRegError('');
    setRegLoading(true);
    try {
      const res = await api.registerEbm({ name: regName, password: regPassword, weight: 4 });
      setSuccessMsg(res.message || `Welcome ${regName}! You can now sign in.`);
      setShowRegisterModal(false);
      setRegName('');
      setRegPassword('');
      // Refresh dropdown and auto-select registered name
      await fetchEbmNames();
      setEbmName(regName);
    } catch (err) {
      setRegError(err.message || 'Failed to register EBM');
    } finally {
      setRegLoading(false);
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
            {activeTab === 'admin' ? 'Manage gateway, MongoDB records, and batch allocation' : 'Select your profile and access your assigned student queue'}
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
            onClick={() => { setActiveTab('ebm'); setError(''); setSuccessMsg(''); }}
            style={{
              padding: '8px 12px',
              border: 'none',
              background: activeTab === 'ebm' ? 'var(--card)' : 'transparent',
              color: activeTab === 'ebm' ? 'var(--heading)' : 'var(--muted)',
              fontWeight: 700,
              fontSize: 13,
              borderRadius: 6,
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            EBM Member
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('admin'); setError(''); setSuccessMsg(''); }}
            style={{
              padding: '8px 12px',
              border: 'none',
              background: activeTab === 'admin' ? 'var(--card)' : 'transparent',
              color: activeTab === 'admin' ? 'var(--heading)' : 'var(--muted)',
              fontWeight: 700,
              fontSize: 13,
              borderRadius: 6,
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            Master Admin
          </button>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <label style={{ margin: 0 }}>Select Your Name</label>
                <button
                  type="button"
                  onClick={() => { setShowRegisterModal(true); setRegError(''); }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary)',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4
                  }}
                >
                  <UserPlus size={13} />
                  <span>+ Register New EBM</span>
                </button>
              </div>

              {fetchingEbms ? (
                <div style={{ padding: '10px 12px', fontSize: 13, color: 'var(--muted)', background: '#F8FAFC', borderRadius: 6, border: '1px solid var(--border)' }}>
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
                    color: 'var(--heading)'
                  }}
                >
                  <option value="">-- Choose your registered name --</option>
                  {ebmList.map((item) => (
                    <option key={item.id} value={item.name}>
                      {item.name}
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
                  No EBMs registered yet. Click <strong>+ Register New EBM</strong> above to add your profile.
                </div>
              )}
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
              disabled={loading || (ebmList.length === 0 && !ebmName)}
            >
              <KeyRound size={16} />
              <span>{loading ? 'Logging in...' : 'Access My Student Queue'}</span>
            </button>
          </form>
        )}
      </div>

      {/* Register EBM Modal */}
      {showRegisterModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(15, 23, 42, 0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: 16
        }}>
          <div className="card" style={{ maxWidth: 400, width: '100%', padding: '28px 24px', position: 'relative' }}>
            <button
              type="button"
              onClick={() => setShowRegisterModal(false)}
              style={{
                position: 'absolute',
                top: 16,
                right: 16,
                background: 'none',
                border: 'none',
                color: 'var(--muted)',
                cursor: 'pointer'
              }}
            >
              <X size={20} />
            </button>

            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <div style={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                background: '#DCFCE7',
                color: '#16A34A',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 12px'
              }}>
                <UserPlus size={24} />
              </div>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--heading)' }}>EBM Team Registration</h2>
              <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>
                Join the team dispatcher. Your password will be securely hashed in MongoDB Atlas.
              </p>
            </div>

            {regError && (
              <div style={{
                padding: '10px 12px',
                background: '#FEF2F2',
                border: '1px solid #F87171',
                borderRadius: 6,
                color: '#B91C1C',
                fontSize: 13,
                marginBottom: 16
              }}>
                {regError}
              </div>
            )}

            <form onSubmit={handleRegisterEbm}>
              <div className="form-group">
                <label>Full Name / Display Name</label>
                <input
                  type="text"
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  placeholder="e.g. EBM Lead One"
                  required
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label>Choose a Password</label>
                <input
                  type="password"
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  placeholder="Enter a secure password"
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ flex: 1 }}
                  onClick={() => setShowRegisterModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ flex: 1 }}
                  disabled={regLoading}
                >
                  {regLoading ? 'Registering...' : 'Register Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
