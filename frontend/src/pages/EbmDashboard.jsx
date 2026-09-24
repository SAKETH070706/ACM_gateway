import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import {
  Users, CheckCircle2, Circle, Send, Copy, Search,
  ExternalLink, Check, RefreshCw, MessageSquare, ArrowLeft, LogOut
} from 'lucide-react';
import ProgressBar from '../components/ProgressBar';

export default function EbmDashboard({ user, showToast }) {
  const { username } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // 'all', 'pending', 'contacted', 'joined'

  useEffect(() => {
    loadDashboard();
  }, [username]);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const params = {};
      if (username) params.username = username;
      const res = await api.getEbmDashboard(params);
      setData(res);
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleContact = async (studentId) => {
    // 1. Optimistic UI update immediately (0ms delay)
    let previousState = null;
    setData((prev) => {
      if (!prev) return prev;
      previousState = prev;
      const target = prev.students.find((s) => s.id === studentId);
      const newStatus = target && target.is_contacted ? 0 : 1;
      const updatedStudents = prev.students.map((s) => {
        if (s.id === studentId) {
          return {
            ...s,
            is_contacted: newStatus
          };
        }
        return s;
      });

      const contactedCount = updatedStudents.filter((s) => s.is_contacted).length;
      const total = updatedStudents.length;

      return {
        ...prev,
        students: updatedStudents,
        stats: {
          ...prev.stats,
          contacted: contactedCount,
          pending: total - contactedCount,
          progress_percent: total ? Math.round((contactedCount / total) * 100) : 0
        }
      };
    });

    // 2. Persist to server
    try {
      const res = await api.toggleContact(studentId);
      setData((prev) => {
        if (!prev) return prev;
        const updatedStudents = prev.students.map((s) => {
          if (s.id === studentId) {
            return {
              ...s,
              is_contacted: res.is_contacted,
              contacted_at: res.contacted_at
            };
          }
          return s;
        });

        const contactedCount = updatedStudents.filter((s) => s.is_contacted).length;
        const total = updatedStudents.length;

        return {
          ...prev,
          students: updatedStudents,
          stats: {
            ...prev.stats,
            contacted: contactedCount,
            pending: total - contactedCount,
            progress_percent: total ? Math.round((contactedCount / total) * 100) : 0
          }
        };
      });
      showToast(res.is_contacted ? 'Marked as contacted' : 'Unmarked contact status');
    } catch (err) {
      // Revert if error
      if (previousState) setData(previousState);
      showToast(err.message || 'Failed to update contact status', 'error');
    }
  };

  const handleToggleJoin = async (studentId) => {
    // 1. Optimistic UI update immediately (0ms delay)
    let previousState = null;
    setData((prev) => {
      if (!prev) return prev;
      previousState = prev;
      const target = prev.students.find((s) => s.id === studentId);
      const newStatus = target && target.is_used ? 0 : 1;
      const updatedStudents = prev.students.map((s) => {
        if (s.id === studentId) {
          return {
            ...s,
            is_used: newStatus
          };
        }
        return s;
      });

      const joinedCount = updatedStudents.filter((s) => s.is_used).length;

      return {
        ...prev,
        students: updatedStudents,
        stats: {
          ...prev.stats,
          joined_whatsapp: joinedCount
        }
      };
    });

    // 2. Persist to server
    try {
      const res = await api.toggleJoin(studentId);
      setData((prev) => {
        if (!prev) return prev;
        const updatedStudents = prev.students.map((s) => {
          if (s.id === studentId) {
            return {
              ...s,
              is_used: res.is_used,
              used_at: res.used_at
            };
          }
          return s;
        });

        const joinedCount = updatedStudents.filter((s) => s.is_used).length;

        return {
          ...prev,
          students: updatedStudents,
          stats: {
            ...prev.stats,
            joined_whatsapp: joinedCount
          }
        };
      });
      showToast(res.message || (res.is_used ? 'Marked as Joined WhatsApp Group' : 'Reset to Pending Join'));
    } catch (err) {
      if (previousState) setData(previousState);
      showToast(err.message || 'Failed to update join status', 'error');
    }
  };

  const copyMessage = (text, studentName) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      showToast(`Copied WhatsApp message for ${studentName}!`);
    }
  };

  const copyLink = (link) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(link);
      showToast('Copied single-use link!');
    }
  };

  if (loading && !data) {
    return (
      <div className="app-container" style={{ textAlign: 'center', padding: '80px 20px' }}>
        <RefreshCw className="spin" size={32} color="var(--primary)" />
        <div style={{ marginTop: 16, color: 'var(--muted)', fontWeight: 500 }}>
          Loading your assigned student batch...
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="app-container" style={{ textAlign: 'center', padding: '80px 20px' }}>
        <div className="card" style={{ maxWidth: 440, margin: '0 auto', padding: 36 }}>
          <h2 style={{ color: 'var(--danger)', marginBottom: 8 }}>Profile Not Found</h2>
          <p style={{ color: 'var(--muted)', marginBottom: 20 }}>
            Could not load the requested EBM portal.
          </p>
          <button onClick={() => navigate('/login')} className="btn btn-primary">
            <ArrowLeft size={16} />
            <span>Go to Login</span>
          </button>
        </div>
      </div>
    );
  }

  const { ebm, stats, students, template } = data;

  // Filter students
  const filteredStudents = students.filter((s) => {
    const q = search.toLowerCase();
    const matchSearch =
      !q ||
      s.name.toLowerCase().includes(q) ||
      (s.phone && s.phone.includes(q)) ||
      (s.acm_id && s.acm_id.toLowerCase().includes(q));

    if (!matchSearch) return false;

    if (filter === 'pending') return !s.is_contacted;
    if (filter === 'contacted') return !!s.is_contacted;
    if (filter === 'joined') return !!s.is_used;
    return true;
  });

  return (
    <div className="app-container">
      {/* Prominent Global Navigation Bar */}
      <div className="action-back-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {user?.role === 'admin' ? (
            <button
              onClick={() => navigate('/admin')}
              className="btn-back-link"
              title="Return to Master Admin Dashboard"
            >
              <ArrowLeft size={16} />
              <span>Back to Master Admin Dashboard</span>
            </button>
          ) : (
            <button
              onClick={() => navigate('/login')}
              className="btn-back-link"
              title="Return to Login"
            >
              <ArrowLeft size={16} />
              <span>Switch Account / Login</span>
            </button>
          )}
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>&bull;</span>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            Viewing batch assigned to <strong style={{ color: 'var(--heading)' }}>{ebm.name}</strong>
          </span>
        </div>

        <button onClick={loadDashboard} className="btn btn-secondary btn-sm">
          <RefreshCw size={14} />
          <span>Sync Live Data</span>
        </button>
      </div>

      {/* Header Profile & KPI Banner */}
      <div className="card" style={{ marginBottom: 24, padding: '24px 28px' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 46,
                height: 46,
                borderRadius: 'var(--radius)',
                background: '#EFF6FF',
                border: '1px solid #BFDBFE',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--primary)'
              }}>
                <Users size={24} />
              </div>
              <div>
                <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--heading)' }}>
                  {ebm.name}
                </h1>
                <div style={{ fontSize: 13, color: 'var(--muted)' }}>
                  EBM Dispatcher &bull; Allocation Weight: <strong style={{ color: 'var(--primary)' }}>{ebm.weight}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
            <span style={{ fontWeight: 600, color: 'var(--heading)' }}>
              Batch Contact Progress: {stats.contacted} of {stats.total_assigned} Students Contacted
            </span>
            <span style={{ fontWeight: 700, color: 'var(--success)' }}>
              {stats.progress_percent}% Complete
            </span>
          </div>
          <ProgressBar value={stats.progress_percent} color="success" height={10} />
        </div>

        {/* KPI Mini-Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 12,
          marginTop: 20
        }}>
          <div style={{ background: '#F8FAFC', padding: '12px 16px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>Total Assigned</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--heading)', marginTop: 4 }}>{stats.total_assigned}</div>
          </div>
          <div style={{ background: '#F8FAFC', padding: '12px 16px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>Pending Contact</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--warning)', marginTop: 4 }}>{stats.pending}</div>
          </div>
          <div style={{ background: '#F8FAFC', padding: '12px 16px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>Contacted</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--success)', marginTop: 4 }}>{stats.contacted}</div>
          </div>
          <div style={{ background: '#F8FAFC', padding: '12px 16px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>Joined WhatsApp</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--primary)', marginTop: 4 }}>{stats.joined_whatsapp}</div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 20,
        flexWrap: 'wrap',
        gap: 14
      }}>
        {/* Quick Filter Tabs */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[
            { id: 'all', label: `All (${students.length})` },
            { id: 'pending', label: `Pending (${stats.pending})` },
            { id: 'contacted', label: `Contacted (${stats.contacted})` },
            { id: 'joined', label: `Joined (${stats.joined_whatsapp})` }
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setFilter(t.id)}
              className={`btn btn-sm ${filter === t.id ? 'btn-primary' : 'btn-secondary'}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Search Input */}
        <div className="search-wrapper" style={{ maxWidth: 320 }}>
          <Search className="search-icon" size={16} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search students in this batch..."
          />
        </div>
      </div>

      {/* Student List Table */}
      <div className="table-responsive">
        <table>
          <thead>
            <tr>
              <th style={{ width: 60 }}>Done</th>
              <th>Student Name</th>
              <th>Mobile Number</th>
              <th>ACM ID / Branch</th>
              <th>WhatsApp Action</th>
              <th>Copy Message</th>
              <th>Group Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredStudents.length === 0 ? (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: 36, color: 'var(--muted)' }}>
                  No students match your filter or search query.
                </td>
              </tr>
            ) : (
              filteredStudents.map((s) => {
                const isDone = !!s.is_contacted;
                return (
                  <tr
                    key={s.id}
                    style={{
                      backgroundColor: isDone ? '#F0FDF4' : 'inherit'
                    }}
                  >
                    <td>
                      <button
                        onClick={() => handleToggleContact(s.id)}
                        className={`checkbox-btn ${isDone ? 'checked' : ''}`}
                        title={isDone ? 'Click to unmark' : 'Click to mark as contacted'}
                      >
                        {isDone ? (
                          <CheckCircle2 size={18} color="var(--success)" />
                        ) : (
                          <Circle size={18} color="#94A3B8" />
                        )}
                      </button>
                    </td>

                    <td>
                      <strong style={{ fontSize: 14, color: isDone ? 'var(--muted)' : 'var(--heading)' }}>
                        {s.name}
                      </strong>
                    </td>

                    <td style={{ fontFamily: 'monospace' }}>
                      {s.phone ? (
                        <span style={{ color: 'var(--primary)', fontWeight: 600 }}>{s.phone}</span>
                      ) : (
                        <span style={{ color: 'var(--muted)' }}>No phone</span>
                      )}
                    </td>

                    <td>
                      <div style={{ fontWeight: 500 }}>{s.acm_id || '—'}</div>
                      <div style={{ fontSize: 11, color: 'var(--muted)' }}>{s.branch || ''}</div>
                    </td>

                    <td>
                      {s.whatsapp_url ? (
                        <a
                          href={s.whatsapp_url}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-whatsapp btn-sm"
                          onClick={() => {
                            if (!s.is_contacted) handleToggleContact(s.id);
                          }}
                        >
                          <Send size={13} />
                          <span>Chat on WhatsApp</span>
                        </a>
                      ) : (
                        <span style={{ fontSize: 12, color: 'var(--muted)' }}>No phone</span>
                      )}
                    </td>

                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          onClick={() => copyMessage(s.formatted_message, s.name)}
                          className="btn btn-secondary btn-sm"
                          title="Copy personalized invitation text"
                        >
                          <MessageSquare size={13} />
                          <span>Copy Text</span>
                        </button>
                        <button
                          onClick={() => copyLink(s.full_invite_link)}
                          className="btn btn-secondary btn-sm"
                          title="Copy single-use invite link only"
                        >
                          <Copy size={13} />
                        </button>
                      </div>
                    </td>

                    <td>
                      <button
                        type="button"
                        onClick={() => handleToggleJoin(s.id)}
                        className={`badge ${s.is_used ? 'badge-success' : 'badge-warning'}`}
                        style={{
                          cursor: 'pointer',
                          border: s.is_used ? '1px solid #16A34A' : '1px solid #D97706',
                          padding: '5px 10px',
                          fontSize: 12,
                          fontWeight: 600,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 5,
                          transition: 'all 0.15s ease'
                        }}
                        title={s.is_used ? "Click to undo -> Reset to Pending Join (re-enables link)" : "Click to manually mark as Joined Group (marks link redeemed)"}
                      >
                        {s.is_used ? (
                          <>
                            <Check size={13} strokeWidth={2.5} />
                            <span>Joined Group</span>
                          </>
                        ) : (
                          <>
                            <Circle size={11} strokeWidth={2.5} color="#D97706" />
                            <span>Pending Join</span>
                          </>
                        )}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
