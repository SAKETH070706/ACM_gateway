// Client API wrapper for communicating with Flask backend
// Reads dynamically from Vite environment variable in decoupled production (e.g. Vercel -> Render)
// Falls back to empty string for relative paths/local proxy
const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

function getResolvedBaseUrl() {
  if (typeof window !== 'undefined' && rawBaseUrl) {
    try {
      const parsed = new URL(rawBaseUrl);
      const isLocalPage = ['localhost', '127.0.0.1'].includes(window.location.hostname);
      const isLocalApi = ['localhost', '127.0.0.1'].includes(parsed.hostname);
      // If loaded directly from the local backend on the same port, use relative path to prevent CORS mismatch
      if (isLocalPage && isLocalApi && (window.location.port === parsed.port || !parsed.port)) {
        return '';
      }
    } catch (e) {
      // Ignore parse error
    }
  }
  return rawBaseUrl;
}

export const API_BASE_URL = getResolvedBaseUrl();

export async function apiRequest(endpoint, options = {}) {
  const config = {
    credentials: 'include', // Crucial for cross-origin session cookies (Vercel <-> Render)
    ...options,
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      ...(options.headers || {}),
    },
  };

  // If body is plain object and not FormData, stringify JSON
  if (config.body && !(config.body instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json';
    config.body = JSON.stringify(config.body);
  }

  // Prepend API_BASE_URL if endpoint is a relative path
  const targetUrl = endpoint.startsWith('http://') || endpoint.startsWith('https://')
    ? endpoint
    : `${API_BASE_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const response = await fetch(targetUrl, config);
  const contentType = response.headers.get('content-type');

  let data;
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const errorMsg = data?.error || data?.message || response.statusText || 'An error occurred';
    const error = new Error(errorMsg);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export const api = {
  // Auth
  loginAdmin: (password) => apiRequest('/api/auth/admin/login', { method: 'POST', body: { password } }),
  loginEbm: (name, password) => apiRequest('/api/auth/ebm/login', { method: 'POST', body: { name, password } }),
  getEbmNames: () => apiRequest('/api/ebm/list-names'),
  registerEbm: (data) => apiRequest('/api/auth/ebm/register', { method: 'POST', body: data }),
  getMe: () => apiRequest('/api/auth/me'),
  logout: () => apiRequest('/api/auth/logout', { method: 'POST' }),

  // Admin Overview & Settings
  getOverview: () => apiRequest('/api/admin/overview'),
  getConfig: () => apiRequest('/api/admin/config'),
  saveConfig: (config) => apiRequest('/api/admin/config', { method: 'POST', body: config }),

  // CSV Uploads
  uploadStudentsCsv: (formData) => apiRequest('/api/admin/upload/students', { method: 'POST', body: formData }),
  uploadEbmCsv: (formData) => apiRequest('/api/admin/upload/ebm', { method: 'POST', body: formData }),

  // EBM Management
  getEbms: () => apiRequest('/api/admin/ebm/list'),
  createEbm: (ebmData) => apiRequest('/api/admin/ebm', { method: 'POST', body: ebmData }),
  updateEbm: (id, ebmData) => apiRequest(`/api/admin/ebm/${id}`, { method: 'PUT', body: ebmData }),
  deleteEbm: (id) => apiRequest(`/api/admin/ebm/${id}`, { method: 'DELETE' }),

  // Batch Splitting & Reassignment
  splitBatches: (reassignAll = false) => apiRequest('/api/admin/batch/split', { method: 'POST', body: { reassign_all: reassignAll } }),
  reassignStudents: (studentIds, ebmId) => apiRequest('/api/admin/batch/reassign', { method: 'POST', body: { student_ids: studentIds, ebm_id: ebmId } }),
  transferStudents: (transferData) => apiRequest('/api/admin/batch/transfer', { method: 'POST', body: transferData }),
  assignStudent: (studentId, ebmId) => apiRequest(`/api/admin/students/${studentId}/assign`, { method: 'POST', body: { ebm_id: ebmId } }),

  // Student Directory & Tokens
  getStudents: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`/api/admin/students?${query}`);
  },
  getFilterOptions: () => apiRequest('/api/admin/filter-options'),
  syncRegistrations: (payload = {}) => apiRequest('/api/admin/sync/registrations', { method: 'POST', body: payload }),
  updateStudent: (studentId, studentData) => apiRequest(`/api/admin/students/${studentId}`, { method: 'PUT', body: studentData }),
  updateStudentStatus: (studentId, statusData) => apiRequest(`/api/admin/students/${studentId}/status`, { method: 'PATCH', body: statusData }),
  renewToken: (studentId, action = 'reset') => apiRequest(`/api/admin/tokens/renew/${studentId}`, { method: 'POST', body: { action } }),
  deleteStudent: (studentId) => apiRequest(`/api/admin/students/${studentId}`, { method: 'DELETE' }),
  clearAllStudents: () => apiRequest('/api/admin/students/clear-all', { method: 'POST' }),

  // Templates
  getTemplates: () => apiRequest('/api/templates'),
  createTemplate: (template) => apiRequest('/api/templates', { method: 'POST', body: template }),
  updateTemplate: (id, template) => apiRequest(`/api/templates/${id}`, { method: 'PUT', body: template }),
  setDefaultTemplate: (id) => apiRequest(`/api/templates/${id}/set-default`, { method: 'POST' }),
  deleteTemplate: (id) => apiRequest(`/api/templates/${id}`, { method: 'DELETE' }),

  // EBM Dashboard
  getEbmDashboard: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`/api/ebm/dashboard?${query}`);
  },
  toggleContact: (studentId) => apiRequest(`/api/ebm/students/${studentId}/toggle-contact`, { method: 'POST' }),
};
