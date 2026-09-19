import React from 'react';

export default function ProgressBar({
  value = 0,
  max = 100,
  color = 'var(--primary)',
  height = 8,
  showLabel = false,
  label = '',
}) {
  const percentage = Math.min(100, Math.max(0, Math.round((value / max) * 100)));

  // Resolve color shortcut
  let barColor = color;
  if (color === 'primary') barColor = 'var(--primary)';
  if (color === 'success') barColor = 'var(--success)';
  if (color === 'warning') barColor = 'var(--warning)';
  if (color === 'danger') barColor = 'var(--danger)';

  return (
    <div style={{ width: '100%' }}>
      {showLabel && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 12,
          fontWeight: 600,
          color: 'var(--muted)',
          marginBottom: 4
        }}>
          <span>{label || 'Progress'}</span>
          <span style={{ color: 'var(--heading)' }}>{percentage}%</span>
        </div>
      )}
      <div
        className="progress-container"
        style={{ height }}
      >
        <div
          className="progress-bar"
          style={{
            width: `${percentage}%`,
            background: barColor,
          }}
        />
      </div>
    </div>
  );
}
