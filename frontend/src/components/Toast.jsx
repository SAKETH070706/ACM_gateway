import React from 'react';
import { CheckCircle, AlertCircle, X } from 'lucide-react';

export default function Toast({ message, type = 'success', onClose }) {
  if (!message) return null;

  return (
    <div className={`toast ${type === 'error' ? 'error' : ''}`}>
      {type === 'error' ? (
        <AlertCircle size={18} color="#ea4335" />
      ) : (
        <CheckCircle size={18} color="#25d366" />
      )}
      <span style={{ flex: 1 }}>{message}</span>
      {onClose && (
        <button
          onClick={onClose}
          style={{ background: 'transparent', border: 'none', color: '#8696a0', cursor: 'pointer', display: 'flex' }}
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}
