import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import {
  Users, UploadCloud, Split, MessageSquare, Settings,
  RefreshCw, Download, Trash2, Plus, Check, Circle, Search,
  ExternalLink, Copy, Shield, AlertTriangle, ArrowRight, Layers,
  ArrowRightLeft, Edit2
} from 'lucide-react';
import Modal from '../components/Modal';
import ProgressBar from '../components/ProgressBar';

export default function AdminDashboard({ showToast }) {
  const [activeTab, setActiveTab] = useState('matrix'); // 'matrix', 'upload', 'students', 'templates', 'settings'
  const [overview, setOverview] = useState(null);
  const [ebms, setEbms] = useState([]);
  const [studentsData, setStudentsData] = useState({ students: [], total: 0, page: 1, total_pages: 1 });
  const [templates, setTemplates] = useState([]);
  const [config, setConfig] = useState({ whatsapp_group_link: '', base_url: '', admin_password: '' });
  const [loading, setLoading] = useState(true);

  // Student Filter & Search States
  const [search, setSearch] = useState('');
  const [filterEbm, setFilterEbm] = useState('');
  const [filterContacted, setFilterContacted] = useState('');
  const [filterJoined, setFilterJoined] = useState('');
  const [filterYear, setFilterYear] = useState('');
  const [filterGoodies, setFilterGoodies] = useState('');
  const [filterBranch, setFilterBranch] = useState('');
  const [filterGender, setFilterGender] = useState('');
  const [availableBranches, setAvailableBranches] = useState([
    'AIDS', 'AIML', 'CIC', 'CIVIL', 'CSBS', 'CSD', 'CSE', 'CSIT', 'ECE', 'EEE', 'IT', 'MECH'
  ]);
  const [currentPage, setCurrentPage] = useState(1);

  // Live ACM DB Sync Modal
  const [syncModalOpen, setSyncModalOpen] = useState(false);
  const [syncForm, setSyncForm] = useState({
    year: '1st Year',
    goodies: 'all',
    generate_tokens: true,
    mode: 'sync',
    loading: false
  });

  // Modals & Forms
  const [renewModal, setRenewModal] = useState({ open: false, student: null });
  const [ebmModal, setEbmModal] = useState({ open: false, isEdit: false, data: { name: '', username: '', password: '', weight: 4 } });
  const [templateModal, setTemplateModal] = useState({ open: false, isEdit: false, data: { title: '', content: '', is_default: false } });
  const [editStudentModal, setEditStudentModal] = useState({ open: false, data: null, saving: false });

  // Manual Batch Adjustment / Transfer Modal
  const [transferModal, setTransferModal] = useState({
    open: false,
    fromEbmId: '',
    toEbmId: '',
    mode: 'quick', // 'quick' or 'specific'
    count: 1,
    selectedStudentIds: [],
    searchFilter: '',
    loadingStudents: false,
    sourceStudents: []
  });

  // Bulk Selection in Student Directory
  const [selectedStudentIds, setSelectedStudentIds] = useState([]);
  const [bulkTargetEbm, setBulkTargetEbm] = useState('');

  // CSV Upload States
  const [studentFile, setStudentFile] = useState(null);
  const [uploadMode, setUploadMode] = useState('overwrite'); // 'overwrite' or 'sync'
  const [generateTokens, setGenerateTokens] = useState(true);
  const [ebmFile, setEbmFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (activeTab === 'students') {
      loadStudents();
    }
  }, [activeTab, search, filterEbm, filterContacted, filterJoined, filterYear, filterGoodies, filterBranch, filterGender, currentPage]);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const [over, ebmRes, tplRes, cfgRes] = await Promise.all([
        api.getOverview(),
        api.getEbms(),
        api.getTemplates(),
        api.getConfig(),
      ]);
      setOverview(over);
      setEbms(ebmRes.ebms || []);
      setTemplates(tplRes.templates || []);
      setConfig(cfgRes);

      api.getFilterOptions().then((opt) => {
        if (opt && opt.branches && opt.branches.length > 0) {
          setAvailableBranches(opt.branches);
        }
      }).catch(() => {});
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadStudents = async () => {
    try {
      const params = {
        page: currentPage,
        limit: 25,
        search,
        ebm_id: filterEbm,
        contacted: filterContacted,
        joined: filterJoined,
        year: filterYear,
        goodies: filterGoodies,
        branch: filterBranch,
        gender: filterGender
      };
      const res = await api.getStudents(params);
      setStudentsData(res);
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // --- Actions: Direct ACM MongoDB Sync ---
  const handleRunSyncDb = async () => {
    if (syncForm.mode === 'overwrite') {
      const confirmed = window.confirm(
        'OVERWRITE MODE WARNING:\n\nThis will replace the student roster in the portal with the matching records from ACE_REG.registrations. Proceed?'
      );
      if (!confirmed) return;
    }

    setSyncForm((prev) => ({ ...prev, loading: true }));
    try {
      const res = await api.syncRegistrations({
        year: syncForm.year,
        goodies: syncForm.goodies,
        generate_tokens: syncForm.generate_tokens,
        mode: syncForm.mode
      });
      showToast(res.message);
      setSyncModalOpen(false);
      loadInitialData();
      if (activeTab === 'students') {
        loadStudents();
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setSyncForm((prev) => ({ ...prev, loading: false }));
    }
  };

  // --- Actions: CSV Upload ---
  const handleUploadStudents = async (e) => {
    e.preventDefault();
    if (!studentFile) return;

    if (uploadMode === 'overwrite') {
      const confirmed = window.confirm(
        'OVERWRITE MODE SELECTED:\n\nThis will replace the student roster in MongoDB. Proceed?'
      );
      if (!confirmed) return;
    }

    setUploading(true);
    const fd = new FormData();
    fd.append('file', studentFile);
    fd.append('mode', uploadMode);
    fd.append('generate_tokens', generateTokens ? 'true' : 'false');

    try {
      const res = await api.uploadStudentsCsv(fd);
      showToast(res.message);
      setStudentFile(null);
      loadInitialData();
      if (activeTab === 'students') loadStudents();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleUploadEbm = async (e) => {
    e.preventDefault();
    if (!ebmFile) return;
    setUploading(true);
    const fd = new FormData();
    fd.append('file', ebmFile);
    try {
      const res = await api.uploadEbmCsv(fd);
      showToast(res.message);
      setEbmFile(null);
      loadInitialData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleSplitBatches = async (reassignAll = false) => {
    const confirmMsg = reassignAll 
      ? 'Are you sure you want to RE-SPLIT all students across EBMs based on weights?' 
      : 'Split all unassigned students across EBMs?';
    if (!window.confirm(confirmMsg)) return;

    try {
      const res = await api.splitBatches(reassignAll);
      showToast(res.message);
      await Promise.all([loadInitialData(), loadStudents()]);
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // --- Actions: Token Renewal ---
  const handleRenewToken = async (action) => {
    if (!renewModal.student) return;
    try {
      const res = await api.renewToken(renewModal.student.id, action);
      showToast(res.message);
      setRenewModal({ open: false, student: null });
      loadStudents();
      loadInitialData();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // --- Actions: EBM Save & Delete ---
  const handleSaveEbm = async (e) => {
    e.preventDefault();
    try {
      if (ebmModal.isEdit) {
        await api.updateEbm(ebmModal.data.id, ebmModal.data);
        showToast('EBM details updated');
      } else {
        await api.createEbm(ebmModal.data);
        showToast('EBM member added');
      }
      setEbmModal({ open: false, isEdit: false, data: { name: '', username: '', password: '', weight: 4 } });
      loadInitialData();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleDeleteEbm = async (id, name) => {
    if (!window.confirm(`Delete EBM ${name}? Their assigned students will become unassigned.`)) return;
    try {
      await api.deleteEbm(id);
      showToast('EBM deleted');
      loadInitialData();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // --- Actions: Weight Quick Change ---
  const handleQuickWeightChange = async (ebmId, newWeight) => {
    if (newWeight < 1) return;
    const targetEbm = ebms.find((e) => e.id === ebmId);
    if (!targetEbm) return;
    try {
      await api.updateEbm(ebmId, { name: targetEbm.name, weight: newWeight });
      setEbms((prev) => prev.map((e) => (e.id === ebmId ? { ...e, weight: newWeight } : e)));
      showToast(`Weight for ${targetEbm.name} updated to ${newWeight}`);
      loadInitialData();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // --- Actions: Transfer / Manual Batch Adjustment Modal ---
  const handleOpenTransferModal = async (fromEbmId = '') => {
    const defaultFrom = fromEbmId !== '' ? String(fromEbmId) : (ebms[0]?.id ? String(ebms[0].id) : 'unassigned');
    const defaultTo = ebms.find((e) => String(e.id) !== String(defaultFrom))?.id 
      ? String(ebms.find((e) => String(e.id) !== String(defaultFrom)).id) 
      : 'unassigned';

    setTransferModal({
      open: true,
      fromEbmId: defaultFrom,
      toEbmId: defaultTo,
      mode: 'quick',
      count: 1,
      selectedStudentIds: [],
      searchFilter: '',
      loadingStudents: true,
      sourceStudents: []
    });

    try {
      const res = await api.getStudents({ ebm_id: defaultFrom, limit: 300 });
      setTransferModal((prev) => ({
        ...prev,
        loadingStudents: false,
        sourceStudents: res.students || []
      }));
    } catch (err) {
      setTransferModal((prev) => ({ ...prev, loadingStudents: false }));
    }
  };

  const handleTransferSourceChange = async (newSourceId) => {
    setTransferModal((prev) => ({
      ...prev,
      fromEbmId: newSourceId,
      loadingStudents: true,
      selectedStudentIds: [],
      sourceStudents: []
    }));
    try {
      const res = await api.getStudents({ ebm_id: newSourceId, limit: 300 });
      setTransferModal((prev) => ({
        ...prev,
        loadingStudents: false,
        sourceStudents: res.students || []
      }));
    } catch (err) {
      setTransferModal((prev) => ({ ...prev, loadingStudents: false }));
    }
  };

  const handleExecuteQuickTransfer = async () => {
    try {
      const res = await api.transferStudents({
        from_ebm_id: transferModal.fromEbmId,
        to_ebm_id: transferModal.toEbmId,
        count: transferModal.count
      });
      showToast(res.message);
      setTransferModal((prev) => ({ ...prev, open: false }));
      loadInitialData();
      if (activeTab === 'students') loadStudents();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleExecuteSpecificTransfer = async () => {
    if (transferModal.selectedStudentIds.length === 0) return;
    try {
      const res = await api.reassignStudents(transferModal.selectedStudentIds, transferModal.toEbmId);
      showToast(res.message);
      setTransferModal((prev) => ({ ...prev, open: false, selectedStudentIds: [] }));
      loadInitialData();
      if (activeTab === 'students') loadStudents();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleToggleTransferStudentId = (studentId) => {
    setTransferModal((prev) => ({
      ...prev,
      selectedStudentIds: prev.selectedStudentIds.includes(studentId)
        ? prev.selectedStudentIds.filter((id) => id !== studentId)
        : [...prev.selectedStudentIds, studentId]
    }));
  };

  const handleSelectAllFilteredStudents = () => {
    const ids = filteredSourceStudents.map((s) => s.id);
    const allSelected = ids.length > 0 && ids.every((id) => transferModal.selectedStudentIds.includes(id));
    setTransferModal((prev) => ({
      ...prev,
      selectedStudentIds: allSelected
        ? prev.selectedStudentIds.filter((id) => !ids.includes(id))
        : Array.from(new Set([...prev.selectedStudentIds, ...ids]))
    }));
  };

  const getSourceStudentCount = () => {
    if (transferModal.fromEbmId === 'unassigned' || !transferModal.fromEbmId) {
      return overview?.stats?.unassigned_students || 0;
    }
    const source = ebms.find((e) => String(e.id) === String(transferModal.fromEbmId));
    return source?.assigned_count || 0;
  };

  const filteredSourceStudents = transferModal.sourceStudents.filter((s) => {
    if (!transferModal.searchFilter) return true;
    const term = transferModal.searchFilter.toLowerCase();
    return (
      (s.name || '').toLowerCase().includes(term) ||
      (s.phone || '').includes(term) ||
      (s.acm_id || '').toLowerCase().includes(term)
    );
  });

  // --- Actions: Inline & Bulk Student Assignment in Directory ---
  const handleInlineStudentAssign = async (studentId, studentName, newEbmId) => {
    try {
      const res = await api.assignStudent(studentId, newEbmId);
      showToast(`${studentName} reassigned to ${res.ebm_name}`);
      setStudentsData((prev) => ({
        ...prev,
        students: prev.students.map((s) =>
          s.id === studentId ? { ...s, ebm_id: res.ebm_id, ebm_name: res.ebm_name } : s
        )
      }));
      loadInitialData();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleToggleSelectStudent = (studentId) => {
    setSelectedStudentIds((prev) =>
      prev.includes(studentId) ? prev.filter((id) => id !== studentId) : [...prev, studentId]
    );
  };

  const handleToggleSelectAllCurrentPage = () => {
    const pageStudentIds = studentsData.students.map((s) => s.id);
    const allSelected = pageStudentIds.length > 0 && pageStudentIds.every((id) => selectedStudentIds.includes(id));
    if (allSelected) {
      setSelectedStudentIds((prev) => prev.filter((id) => !pageStudentIds.includes(id)));
    } else {
      setSelectedStudentIds((prev) => Array.from(new Set([...prev, ...pageStudentIds])));
    }
  };

  const handleApplyBulkReassign = async () => {
    if (selectedStudentIds.length === 0) return;
    try {
      const res = await api.reassignStudents(selectedStudentIds, bulkTargetEbm);
      showToast(res.message);
      setSelectedStudentIds([]);
      loadInitialData();
      loadStudents();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // --- Student Admin CRUD Handlers ---
  const handleToggleStudentStatus = async (studentId, currentContacted) => {
    const newContacted = currentContacted ? 0 : 1;
    // Optimistic UI update (0ms latency)
    setStudentsData((prev) => ({
      ...prev,
      students: prev.students.map((s) =>
        s.id === studentId ? { ...s, is_contacted: newContacted } : s
      )
    }));
    try {
      await api.updateStudentStatus(studentId, { is_contacted: newContacted });
      showToast(newContacted ? 'Student marked as Contacted' : 'Student marked as Not Contacted');
      loadInitialData(); // Refresh summary metrics
    } catch (err) {
      // Revert optimistic update on failure
      setStudentsData((prev) => ({
        ...prev,
        students: prev.students.map((s) =>
          s.id === studentId ? { ...s, is_contacted: currentContacted } : s
        )
      }));
      showToast(err.message || 'Failed to update status', 'error');
    }
  };

  const handleToggleStudentJoin = async (studentId, currentUsed) => {
    const newUsed = currentUsed ? 0 : 1;
    // Optimistic UI update (0ms latency)
    setStudentsData((prev) => ({
      ...prev,
      students: prev.students.map((s) =>
        s.id === studentId ? { ...s, is_used: newUsed } : s
      )
    }));
    try {
      const res = await api.adminToggleJoin(studentId);
      setStudentsData((prev) => ({
        ...prev,
        students: prev.students.map((s) =>
          s.id === studentId ? { ...s, is_used: res.is_used, used_at: res.used_at } : s
        )
      }));
      showToast(res.message || (newUsed ? 'Student marked as Joined WhatsApp Group' : 'Student reset to Pending Join (Link re-enabled)'));
      loadInitialData(); // Refresh summary metrics
    } catch (err) {
      // Revert optimistic update on failure
      setStudentsData((prev) => ({
        ...prev,
        students: prev.students.map((s) =>
          s.id === studentId ? { ...s, is_used: currentUsed } : s
        )
      }));
      showToast(err.message || 'Failed to update join status', 'error');
    }
  };

  const handleDeleteStudent = async (studentId, studentName) => {
    if (!window.confirm(`Are you sure you want to permanently delete "${studentName}"?`)) {
      return;
    }
    try {
      await api.deleteStudent(studentId);
      showToast('Student deleted successfully');
      setStudentsData((prev) => ({
        ...prev,
        students: prev.students.filter((s) => s.id !== studentId),
        total: Math.max(0, prev.total - 1)
      }));
      loadInitialData();
    } catch (err) {
      showToast(err.message || 'Failed to delete student', 'error');
    }
  };

  const handleSaveStudentEdit = async (e) => {
    e.preventDefault();
    if (!editStudentModal.data) return;
    setEditStudentModal((prev) => ({ ...prev, saving: true }));
    try {
      await api.updateStudent(editStudentModal.data.id, editStudentModal.data);
      showToast('Student details updated successfully');
      setStudentsData((prev) => ({
        ...prev,
        students: prev.students.map((s) =>
          s.id === editStudentModal.data.id ? { ...s, ...editStudentModal.data } : s
        )
      }));
      setEditStudentModal({ open: false, data: null, saving: false });
      loadInitialData();
    } catch (err) {
      showToast(err.message || 'Failed to save student details', 'error');
      setEditStudentModal((prev) => ({ ...prev, saving: false }));
    }
  };

  // --- Message Template Variable Insertion & Live Preview Helpers ---
  const templateTextareaRef = useRef(null);

  const insertVariableAtCursor = (variable) => {
    const textarea = templateTextareaRef.current;
    const currentContent = templateModal.data?.content || '';
    if (!textarea) {
      setTemplateModal((prev) => ({
        ...prev,
        data: { ...prev.data, content: currentContent + (currentContent ? ' ' : '') + variable }
      }));
      return;
    }
    const start = textarea.selectionStart ?? currentContent.length;
    const end = textarea.selectionEnd ?? currentContent.length;
    const newContent = currentContent.substring(0, start) + variable + currentContent.substring(end);
    setTemplateModal((prev) => ({
      ...prev,
      data: { ...prev.data, content: newContent }
    }));
    setTimeout(() => {
      textarea.focus();
      const newPos = start + variable.length;
      textarea.setSelectionRange(newPos, newPos);
    }, 10);
  };

  const renderWhatsAppPreview = (rawContent) => {
    if (!rawContent || !rawContent.trim()) {
      return (
        <div style={{ color: '#8696a0', fontStyle: 'italic', fontSize: 13, padding: '12px 0' }}>
          Type your message on the left or click variable badges to see real-time preview...
        </div>
      );
    }

    // Substitute dynamic placeholders with realistic sample student details
    let text = rawContent
      .replace(/\{name\}/g, 'Y Maheswari Devi')
      .replace(/\{acm_id\}/g, '26ACMA001')
      .replace(/\{branch\}/g, 'IT')
      .replace(/\{year\}/g, '1st Year')
      .replace(/\{goodies\}/g, 'Yes (T-Shirt & Kit)')
      .replace(/\{phone\}/g, '+91 98765 43210')
      .replace(/\{link\}/g, 'http://localhost:5000/join/tk_sample_8f92');

    // Escape HTML entities
    const escapeHtml = (str) =>
      str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    let safeText = escapeHtml(text);

    // Format WhatsApp Markdown: *bold*, _italic_, ~strikethrough~, ```code```
    safeText = safeText.replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>');
    safeText = safeText.replace(/_([^_\n]+)_/g, '<em>$1</em>');
    safeText = safeText.replace(/~([^~\n]+)~/g, '<del>$1</del>');
    safeText = safeText.replace(/```([^`]+)```/g, '<code style="background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 3px; font-family: monospace; font-size: 12px;">$1</code>');

    // Highlight links
    safeText = safeText.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<span style="color: #027eb5; text-decoration: underline; word-break: break-all;">$1</span>'
    );

    // Preserve newlines
    safeText = safeText.replace(/\n/g, '<br />');

    return <div dangerouslySetInnerHTML={{ __html: safeText }} />;
  };

  // --- Actions: Template Save & Delete ---
  const handleSaveTemplate = async (e) => {
    e.preventDefault();
    try {
      if (templateModal.isEdit) {
        await api.updateTemplate(templateModal.data.id, templateModal.data);
        showToast('Template updated');
      } else {
        await api.createTemplate(templateModal.data);
        showToast('Template created');
      }
      setTemplateModal({ open: false, isEdit: false, data: { title: '', content: '', is_default: false } });
      const t = await api.getTemplates();
      setTemplates(t.templates || []);
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleSetDefaultTemplate = async (id) => {
    try {
      await api.setDefaultTemplate(id);
      showToast('Default template set');
      const t = await api.getTemplates();
      setTemplates(t.templates || []);
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleDeleteTemplate = async (id) => {
    if (!window.confirm('Delete this message template?')) return;
    try {
      await api.deleteTemplate(id);
      showToast('Template deleted');
      const t = await api.getTemplates();
      setTemplates(t.templates || []);
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // --- Actions: Gateway Config Save ---
  const handleSaveConfig = async (e) => {
    e.preventDefault();
    try {
      await api.saveConfig(config);
      showToast('Gateway configuration saved successfully');
      loadInitialData();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const copyToClipboard = (text) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      showToast('Link copied to clipboard!');
    }
  };

  return (
    <div className="app-container">
      {/* Top Header */}
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <Shield size={26} color="var(--primary)" />
            <span>Master Administration Dashboard</span>
          </h1>
          <p className="page-subtitle">
            Dynamic CSV parsing, weighted batch allocation, token lifecycle controls, and live metrics
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <a
            href="/api/admin/export/links"
            className="btn btn-secondary btn-sm"
            download
          >
            <Download size={15} />
            <span>Export CSV with Links</span>
          </a>
          <button
            onClick={loadInitialData}
            className="btn btn-secondary btn-sm"
            title="Refresh statistics"
          >
            <RefreshCw size={15} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* KPI Stats Cards */}
      {overview && (
        <div className="stats-grid">
          <div className="stat-card primary">
            <span className="stat-label">Total Ingested Students</span>
            <div className="stat-num">{overview.stats.total_students}</div>
            <span className="stat-sub">{overview.stats.unassigned_students} unassigned</span>
          </div>

          <div className="stat-card blue">
            <span className="stat-label">Students Contacted</span>
            <div className="stat-num">{overview.stats.contacted_students}</div>
            <ProgressBar value={overview.stats.contact_rate} color="primary" />
            <span className="stat-sub">{overview.stats.contact_rate}% contacted by EBMs</span>
          </div>

          <div className="stat-card success">
            <span className="stat-label">WhatsApp Group Joined</span>
            <div className="stat-num">{overview.stats.joined_whatsapp}</div>
            <ProgressBar value={overview.stats.join_rate} color="success" />
            <span className="stat-sub">{overview.stats.join_rate}% single-use redeemed</span>
          </div>

          <div className="stat-card purple">
            <span className="stat-label">Active EBM Team</span>
            <div className="stat-num">{overview.stats.total_ebms}</div>
            <span className="stat-sub">Configured dispatchers</span>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="tab-nav">
        <button
          className={`tab-btn ${activeTab === 'matrix' ? 'active' : ''}`}
          onClick={() => setActiveTab('matrix')}
        >
          <Split size={16} />
          <span>Batch Matrix & Team</span>
        </button>
        <button
          className={`tab-btn ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          <UploadCloud size={16} />
          <span>Dynamic CSV Uploads</span>
        </button>
        <button
          className={`tab-btn ${activeTab === 'students' ? 'active' : ''}`}
          onClick={() => setActiveTab('students')}
        >
          <Users size={16} />
          <span>Student Directory & Tokens</span>
        </button>
        <button
          className={`tab-btn ${activeTab === 'templates' ? 'active' : ''}`}
          onClick={() => setActiveTab('templates')}
        >
          <MessageSquare size={16} />
          <span>Message Templates</span>
        </button>
        <button
          className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          <Settings size={16} />
          <span>Gateway Settings</span>
        </button>
      </div>

      {/* ================= TAB 1: BATCH MATRIX & TEAM ================= */}
      {activeTab === 'matrix' && (
        <div>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
            flexWrap: 'wrap',
            gap: 12
          }}>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--heading)' }}>EBM Team Allocation & Weightings</h2>
              <p style={{ fontSize: 13, color: 'var(--muted)' }}>
                Set customizable weightings (e.g. 6 for coordinators / CO-ORD, 4 for regular members) and auto-distribute students.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button
                onClick={() => handleOpenTransferModal('')}
                className="btn btn-secondary"
                title="Manually transfer or reallocate students between team members"
              >
                <ArrowRightLeft size={15} />
                <span>Manual Student Adjustment</span>
              </button>
              <button
                onClick={() => handleSplitBatches(false)}
                className="btn btn-primary"
              >
                <Split size={15} />
                <span>Auto-Split Unassigned</span>
              </button>
              <button
                onClick={() => handleSplitBatches(true)}
                className="btn btn-secondary"
                title="Redistribute entire student list according to weights"
              >
                <span>Re-Split All</span>
              </button>
              <button
                onClick={() => setEbmModal({ open: true, isEdit: false, data: { name: '', username: '', password: 'ebm123', weight: 4 } })}
                className="btn btn-secondary"
              >
                <Plus size={15} />
                <span>Add EBM</span>
              </button>
            </div>
          </div>

          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th style={{ whiteSpace: 'nowrap' }}>EBM Name</th>
                  <th style={{ whiteSpace: 'nowrap' }}>Username</th>
                  <th style={{ textAlign: 'center', whiteSpace: 'nowrap', minWidth: 160 }}>Weight Ratio</th>
                  <th style={{ textAlign: 'center', whiteSpace: 'nowrap', minWidth: 130 }}>Assigned Students</th>
                  <th style={{ textAlign: 'center', whiteSpace: 'nowrap', minWidth: 80 }}>Contacted</th>
                  <th style={{ textAlign: 'center', whiteSpace: 'nowrap', minWidth: 90 }}>Joined WhatsApp</th>
                  <th style={{ minWidth: 130 }}>Progress</th>
                  <th style={{ textAlign: 'right', whiteSpace: 'nowrap', minWidth: 230 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {ebms.length === 0 ? (
                  <tr>
                    <td colSpan="8" style={{ textAlign: 'center', padding: 32, color: 'var(--muted)' }}>
                      No EBM members configured. Upload an EBM CSV or click "Add EBM".
                    </td>
                  </tr>
                ) : (
                  (() => {
                    const totalWeights = ebms.reduce((acc, curr) => acc + (curr.weight || 4), 0);
                    return ebms.map((e) => {
                      const assigned = e.assigned_count || 0;
                      const contacted = e.contacted_count || 0;
                      const joined = e.joined_count || 0;
                      const pct = assigned ? Math.round((contacted / assigned) * 100) : 0;
                      const isCoord = (e.weight || 4) >= 6;
                      const weightPct = totalWeights > 0 ? Math.round(((e.weight || 4) / totalWeights) * 100) : 0;

                      return (
                        <tr key={e.id}>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}>
                              <strong style={{ color: 'var(--heading)' }}>{e.name}</strong>
                              {isCoord && <span className="badge badge-success" style={{ fontSize: 10 }}>CO-ORD (x{e.weight})</span>}
                            </div>
                          </td>
                          <td style={{ fontFamily: 'monospace', color: 'var(--primary)', fontWeight: 600, whiteSpace: 'nowrap' }}>{e.username}</td>
                          <td style={{ textAlign: 'center' }}>
                            <div style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: 6,
                              background: '#F8FAFC',
                              padding: '3px 8px',
                              borderRadius: 8,
                              border: '1px solid var(--border)',
                              whiteSpace: 'nowrap'
                            }}>
                              <button
                                type="button"
                                onClick={() => handleQuickWeightChange(e.id, Math.max(1, (e.weight || 4) - 1))}
                                className="btn btn-secondary btn-sm"
                                style={{ width: 24, height: 24, padding: 0, fontWeight: 700, fontSize: 13, lineHeight: '1' }}
                                title="Decrease weighting"
                                disabled={(e.weight || 4) <= 1}
                              >
                                -
                              </button>
                              <span style={{ minWidth: 46, fontWeight: 700, fontSize: 13, color: 'var(--heading)', textAlign: 'center' }}>
                                x{e.weight || 4}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleQuickWeightChange(e.id, (e.weight || 4) + 1)}
                                className="btn btn-secondary btn-sm"
                                style={{ width: 24, height: 24, padding: 0, fontWeight: 700, fontSize: 13, lineHeight: '1' }}
                                title="Increase weighting"
                              >
                                +
                              </button>
                            </div>
                            <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2, whiteSpace: 'nowrap' }}>
                              {weightPct}% of batch pool
                            </div>
                          </td>
                          <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }}><strong style={{ fontSize: 15, color: 'var(--heading)' }}>{assigned}</strong> students</td>
                          <td style={{ textAlign: 'center' }}><span style={{ color: 'var(--success)', fontWeight: 700 }}>{contacted}</span></td>
                          <td style={{ textAlign: 'center' }}><span style={{ color: 'var(--primary)', fontWeight: 700 }}>{joined}</span></td>
                          <td style={{ width: 140 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div style={{ flex: 1 }}>
                                <ProgressBar value={pct} color="success" />
                              </div>
                              <span style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 600 }}>{pct}%</span>
                            </div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', whiteSpace: 'nowrap' }}>
                              <button
                                onClick={() => handleOpenTransferModal(e.id)}
                                className="btn btn-secondary btn-sm"
                                title="Adjust or transfer students for this EBM"
                              >
                                <ArrowRightLeft size={13} />
                                <span>Adjust</span>
                              </button>
                              <a
                                href={`/ebm/${e.username}`}
                                target="_blank"
                                rel="noreferrer"
                                className="btn btn-secondary btn-sm"
                                title="Open this EBM's Dispatcher View"
                              >
                                <ExternalLink size={13} />
                                <span>View</span>
                              </a>
                              <button
                                onClick={() => setEbmModal({ open: true, isEdit: true, data: e })}
                                className="btn btn-secondary btn-sm"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => handleDeleteEbm(e.id, e.name)}
                                className="btn btn-danger btn-sm"
                                title="Delete EBM"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    });
                  })()
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ================= TAB 2: DYNAMIC CSV UPLOADS ================= */}
      {activeTab === 'upload' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 24 }}>
          {/* Student CSV Dropzone */}
          <div className="card">
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8, color: 'var(--heading)' }}>
              <Users size={20} color="var(--primary)" />
              <span>Upload Student CSV</span>
            </h2>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 20 }}>
              Ingest any number of students without hardcoded limits. The backend automatically maps
              Name, Mobile, ACM ID, Branch, and serializes any extra columns into JSON.
            </p>

            <form onSubmit={handleUploadStudents}>
              {/* Overwrite vs Sync Radio Selection */}
              <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--heading)', marginBottom: 8 }}>
                Upload Behavior &amp; Overwrite Mode:
              </label>
              <div className="radio-group">
                <label className={`radio-option ${uploadMode === 'overwrite' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="upload_mode"
                    value="overwrite"
                    checked={uploadMode === 'overwrite'}
                    onChange={(e) => setUploadMode(e.target.value)}
                  />
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--heading)' }}>
                      Clean Overwrite (Replace All Students)
                    </strong>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                      Recommended for fresh campaigns. Replaces existing student records and generates brand-new single-use tokens.
                    </span>
                  </div>
                </label>

                <label className={`radio-option ${uploadMode === 'sync' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="upload_mode"
                    value="sync"
                    checked={uploadMode === 'sync'}
                    onChange={(e) => setUploadMode(e.target.value)}
                  />
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--heading)' }}>
                      Sync &amp; Update (Preserve Active Tokens)
                    </strong>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                      Matches existing students by ACM ID/Phone/Name and updates details while keeping already-claimed tokens and contact checkmarks intact.
                    </span>
                  </div>
                </label>
              </div>

              <label
                htmlFor="student-file-input"
                className={`dropzone ${studentFile ? 'dragover' : ''}`}
                style={{ marginBottom: 16 }}
              >
                <UploadCloud className="dropzone-icon" />
                {studentFile ? (
                  <div>
                    <strong style={{ color: 'var(--primary)', display: 'block' }}>{studentFile.name}</strong>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                      {(studentFile.size / 1024).toFixed(1)} KB — Click or drag to replace
                    </span>
                  </div>
                ) : (
                  <div>
                    <span style={{ fontWeight: 600, display: 'block', color: 'var(--heading)' }}>Choose Student CSV or drop file here</span>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>Supports any .csv file</span>
                  </div>
                )}
                <input
                  id="student-file-input"
                  type="file"
                  accept=".csv"
                  style={{ display: 'none' }}
                  onChange={(e) => setStudentFile(e.target.files[0])}
                />
              </label>

              {/* Conditional Token Generation Toggle */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  padding: '12px 14px',
                  background: generateTokens ? '#F0FDF4' : '#F8FAFC',
                  border: `1px solid ${generateTokens ? '#BBF7D0' : 'var(--border)'}`,
                  borderRadius: 'var(--radius)',
                  marginBottom: 16,
                  cursor: 'pointer'
                }}
                onClick={() => setGenerateTokens(!generateTokens)}
              >
                <input
                  type="checkbox"
                  id="generate-tokens-toggle"
                  checked={generateTokens}
                  onChange={(e) => setGenerateTokens(e.target.checked)}
                  style={{ marginTop: 2, cursor: 'pointer' }}
                />
                <div>
                  <strong style={{ display: 'block', fontSize: 13, color: 'var(--heading)' }}>
                    Generate One-Time WhatsApp Tokens
                  </strong>
                  <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                    {generateTokens
                      ? 'Secure, single-use tracking tokens will be allocated for each student in MongoDB.'
                      : 'Students will be ingested for viewing/goodies tracking without creating WhatsApp links.'}
                  </span>
                </div>
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%' }}
                disabled={!studentFile || uploading}
              >
                <UploadCloud size={16} />
                <span>{uploading ? 'Processing CSV with Pandas...' : uploadMode === 'overwrite' ? 'Replace Roster in MongoDB' : 'Sync Student Roster in MongoDB'}</span>
              </button>
            </form>
          </div>

          {/* EBM Team CSV Dropzone */}
          <div className="card">
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8, color: 'var(--heading)' }}>
              <Split size={20} color="var(--primary)" />
              <span>Upload EBM Team CSV (Seamless UPSERT)</span>
            </h2>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 20 }}>
              Bulk upload your team members with passwords and custom weightings (Columns: Name, Username, Password, Weight).
              Uses UPSERT to update existing team members without errors. Coordinators (with "coord" or weight 6) auto-default to weight 6 if omitted.
            </p>

            <form onSubmit={handleUploadEbm}>
              <label
                htmlFor="ebm-file-input"
                className={`dropzone ${ebmFile ? 'dragover' : ''}`}
                style={{ marginBottom: 20 }}
              >
                <UploadCloud className="dropzone-icon" />
                {ebmFile ? (
                  <div>
                    <strong style={{ color: 'var(--primary)', display: 'block' }}>{ebmFile.name}</strong>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                      {(ebmFile.size / 1024).toFixed(1)} KB — Click or drag to replace
                    </span>
                  </div>
                ) : (
                  <div>
                    <span style={{ fontWeight: 600, display: 'block', color: 'var(--heading)' }}>Choose EBM Team CSV or drop file here</span>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>Supports .csv files</span>
                  </div>
                )}
                <input
                  id="ebm-file-input"
                  type="file"
                  accept=".csv"
                  style={{ display: 'none' }}
                  onChange={(e) => setEbmFile(e.target.files[0])}
                />
              </label>

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%' }}
                disabled={!ebmFile || uploading}
              >
                <UploadCloud size={16} />
                <span>{uploading ? 'Upserting EBM Team...' : 'Upload & Sync EBM Team'}</span>
              </button>
            </form>
          </div>
        </div>
      )}

      {/* ================= TAB 3: STUDENT DIRECTORY & TOKEN RENEWAL ================= */}
      {activeTab === 'students' && (
        <div>
          <div style={{
            display: 'flex',
            gap: 12,
            marginBottom: 16,
            flexWrap: 'wrap',
            alignItems: 'center'
          }}>
            {/* Search */}
            <div className="search-wrapper">
              <Search className="search-icon" size={16} />
              <input
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setCurrentPage(1); }}
                placeholder="Search by student name, mobile, or ACM ID..."
              />
            </div>

            {/* Filter by EBM */}
            <select
              value={filterEbm}
              onChange={(e) => { setFilterEbm(e.target.value); setCurrentPage(1); }}
              style={{ width: 180 }}
            >
              <option value="">All EBMs</option>
              <option value="unassigned">Unassigned</option>
              {ebms.map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>

            {/* Filter by Contacted */}
            <select
              value={filterContacted}
              onChange={(e) => { setFilterContacted(e.target.value); setCurrentPage(1); }}
              style={{ width: 160 }}
            >
              <option value="">Contacted: All</option>
              <option value="1">Contacted</option>
              <option value="0">Pending</option>
            </select>

            {/* Filter by Joined WhatsApp */}
            <select
              value={filterJoined}
              onChange={(e) => { setFilterJoined(e.target.value); setCurrentPage(1); }}
              style={{ width: 150 }}
            >
              <option value="">Token: All</option>
              <option value="1">Redeemed / Joined</option>
              <option value="0">Active / Unused</option>
            </select>

            {/* Filter by Academic Year */}
            <select
              value={filterYear}
              onChange={(e) => { setFilterYear(e.target.value); setCurrentPage(1); }}
              style={{ width: 130 }}
            >
              <option value="">Year: All</option>
              <option value="1">1st Year</option>
              <option value="2">2nd Year</option>
              <option value="3">3rd Year</option>
              <option value="4">4th Year</option>
            </select>

            {/* Filter by Goodies */}
            <select
              value={filterGoodies}
              onChange={(e) => { setFilterGoodies(e.target.value); setCurrentPage(1); }}
              style={{ width: 140 }}
            >
              <option value="">Goodies: All</option>
              <option value="yes">Eligible (Yes)</option>
              <option value="no">Not Eligible (No)</option>
            </select>

            {/* Filter by Branch */}
            <select
              value={filterBranch}
              onChange={(e) => { setFilterBranch(e.target.value); setCurrentPage(1); }}
              style={{ width: 140 }}
            >
              <option value="">Branch: All</option>
              {availableBranches.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>

            {/* Filter by Gender */}
            <select
              value={filterGender}
              onChange={(e) => { setFilterGender(e.target.value); setCurrentPage(1); }}
              style={{ width: 130 }}
            >
              <option value="">Gender: All</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
            </select>

            <button
              onClick={() => setSyncModalOpen(true)}
              className="btn btn-primary btn-sm"
              style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}
            >
              <RefreshCw size={14} />
              <span>Sync ACM DB</span>
            </button>

            <button
              onClick={() => {
                if (window.confirm('WARNING: Are you sure you want to delete ALL students and associated one-time links?')) {
                  api.clearAllStudents().then((res) => {
                    showToast(res.message);
                    loadInitialData();
                    loadStudents();
                  });
                }
              }}
              className="btn btn-danger btn-sm"
              style={{ whiteSpace: 'nowrap' }}
            >
              <Trash2 size={14} />
              <span>Clear All</span>
            </button>
          </div>

          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 36, textAlign: 'center' }}>
                    <input
                      type="checkbox"
                      checked={studentsData.students.length > 0 && studentsData.students.every((s) => selectedStudentIds.includes(s.id))}
                      onChange={handleToggleSelectAllCurrentPage}
                      title="Select / deselect all on page"
                    />
                  </th>
                  <th>#</th>
                  <th>Student Name</th>
                  <th>Mobile Number</th>
                  <th>ACM ID / Branch</th>
                  <th style={{ minWidth: 170 }}>Assigned EBM</th>
                  <th>One-Time Link Status</th>
                  <th>Contact Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {studentsData.students.length === 0 ? (
                  <tr>
                    <td colSpan="9" style={{ textAlign: 'center', padding: 32, color: 'var(--muted)' }}>
                      No students found matching your filters.
                    </td>
                  </tr>
                ) : (
                  studentsData.students.map((s, idx) => (
                    <tr key={s.id}>
                      <td style={{ textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={selectedStudentIds.includes(s.id)}
                          onChange={() => handleToggleSelectStudent(s.id)}
                        />
                      </td>
                      <td>{(currentPage - 1) * (studentsData.limit || studentsData.per_page || 25) + idx + 1}</td>
                      <td>
                        <strong style={{ color: 'var(--heading)' }}>{s.name}</strong>
                        {s.email && <div style={{ fontSize: 11, color: 'var(--muted)' }}>{s.email}</div>}
                      </td>
                      <td>{s.phone || '—'}</td>
                      <td>
                        <div>{s.acm_id || '—'}</div>
                        <div style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 2 }}>
                          {s.branch && <span style={{ background: '#F1F5F9', color: '#334155', padding: '1px 5px', borderRadius: 4, fontWeight: 600 }}>{s.branch}</span>}
                          {s.gender && <span style={{ background: '#FAF5FF', color: '#7E22CE', padding: '1px 5px', borderRadius: 4, fontWeight: 600 }}>{s.gender}</span>}
                          {s.year && <span style={{ background: '#EFF6FF', color: '#1D4ED8', padding: '1px 5px', borderRadius: 4, fontWeight: 600 }}>{s.year}</span>}
                          {s.goodies && <span style={{ background: String(s.goodies).toLowerCase().startsWith('y') ? '#ECFDF5' : '#F1F5F9', color: String(s.goodies).toLowerCase().startsWith('y') ? '#047857' : '#64748B', padding: '1px 5px', borderRadius: 4, fontWeight: 600 }}>Goodies: {s.goodies}</span>}
                        </div>
                      </td>
                      <td>
                        <select
                          value={s.ebm_id || s.assigned_ebm_id || ''}
                          onChange={(e) => handleInlineStudentAssign(s.id, s.name, e.target.value)}
                          style={{
                            padding: '5px 8px',
                            fontSize: 12,
                            fontWeight: 600,
                            borderRadius: 6,
                            border: (s.ebm_id || s.assigned_ebm_id) ? '1px solid var(--border)' : '1px dashed var(--warning)',
                            background: (s.ebm_id || s.assigned_ebm_id) ? '#F8FAFC' : '#FEF3C7',
                            color: (s.ebm_id || s.assigned_ebm_id) ? 'var(--heading)' : '#B45309',
                            cursor: 'pointer',
                            width: '100%',
                            maxWidth: 170
                          }}
                          title="Click to instantly reassign this student to another EBM"
                        >
                          <option value="">-- Unassigned --</option>
                          {ebms.map((ebm) => (
                            <option key={ebm.id} value={ebm.id}>
                              {ebm.name} ({ebm.assigned_count || 0})
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => handleToggleStudentJoin(s.id, s.is_used)}
                          className={`badge ${s.is_used ? 'badge-danger' : 'badge-success'}`}
                          style={{
                            cursor: 'pointer',
                            border: s.is_used ? '1px solid #DC2626' : '1px solid #16A34A',
                            padding: '4px 8px',
                            fontSize: 11,
                            fontWeight: 600,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                            transition: 'all 0.15s ease'
                          }}
                          title={s.is_used ? "Click to reset token / undo to Pending Join (re-enables link)" : "Click to mark as Joined / Redeemed"}
                        >
                          {s.is_used ? (
                            <>
                              <Check size={12} strokeWidth={2.5} />
                              <span>Redeemed (Joined)</span>
                            </>
                          ) : (
                            <>
                              <Circle size={10} strokeWidth={2.5} />
                              <span>Active (Pending)</span>
                            </>
                          )}
                        </button>
                        {s.is_used && s.used_at ? (
                          <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>
                            {s.used_at}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => handleToggleStudentStatus(s.id, s.is_contacted)}
                          className={`badge ${s.is_contacted ? 'badge-success' : 'badge-neutral'}`}
                          style={{
                            cursor: 'pointer',
                            border: 'none',
                            padding: '4px 10px',
                            fontWeight: 600,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4
                          }}
                          title="Click to toggle status (Contacted / Not Contacted)"
                        >
                          {s.is_contacted ? '✓ Contacted' : '○ Not Contacted'}
                        </button>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            onClick={() => setEditStudentModal({ open: true, data: { ...s }, saving: false })}
                            className="btn btn-secondary btn-sm"
                            title="Edit student information"
                          >
                            <Edit2 size={13} />
                          </button>
                          <button
                            onClick={() => copyToClipboard(s.full_invite_link || s.invite_link)}
                            className="btn btn-secondary btn-sm"
                            title="Copy single-use invite link"
                          >
                            <Copy size={13} />
                          </button>
                          <button
                            onClick={() => setRenewModal({ open: true, student: s })}
                            className="btn btn-secondary btn-sm"
                            title="Reset or renew link for this student"
                          >
                            <RefreshCw size={13} />
                          </button>
                          <button
                            onClick={() => handleDeleteStudent(s.id, s.name)}
                            className="btn btn-secondary btn-sm"
                            style={{ color: '#EF4444' }}
                            title="Delete student record"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Floating Bulk Reassignment Bar */}
          {selectedStudentIds.length > 0 && (
            <div className="floating-bulk-bar">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 700, fontSize: 13, background: 'var(--primary)', color: '#FFFFFF', padding: '3px 10px', borderRadius: 20 }}>
                  {selectedStudentIds.length} Selected
                </span>
                <span style={{ fontSize: 13, opacity: 0.9 }}>Reassign to:</span>
                <select
                  value={bulkTargetEbm}
                  onChange={(e) => setBulkTargetEbm(e.target.value)}
                  style={{
                    width: 190,
                    padding: '6px 10px',
                    fontSize: 13,
                    borderRadius: 6,
                    background: '#0F172A',
                    color: '#FFFFFF',
                    border: '1px solid #334155'
                  }}
                >
                  <option value="">-- Return to Unassigned Pool --</option>
                  {ebms.map((ebm) => (
                    <option key={ebm.id} value={ebm.id}>
                      {ebm.name} ({ebm.assigned_count || 0})
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleApplyBulkReassign}
                  className="btn btn-primary btn-sm"
                  style={{ padding: '6px 14px' }}
                >
                  <Check size={14} />
                  <span>Apply Reassignment</span>
                </button>
              </div>
              <button
                onClick={() => setSelectedStudentIds([])}
                className="btn btn-secondary btn-sm"
                style={{ background: 'transparent', color: '#94A3B8', border: '1px solid #475569' }}
              >
                Cancel
              </button>
            </div>
          )}

          {/* Pagination Controls */}
          {studentsData.total_pages > 1 && (
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: 16,
              fontSize: 13,
              color: 'var(--muted)'
            }}>
              <div>Total: {studentsData.total} students</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="btn btn-secondary btn-sm"
                >
                  Previous
                </button>
                <span style={{ alignSelf: 'center', padding: '0 8px', fontWeight: 600, color: 'var(--heading)' }}>
                  Page {currentPage} of {studentsData.total_pages}
                </span>
                <button
                  disabled={currentPage >= studentsData.total_pages}
                  onClick={() => setCurrentPage((p) => Math.min(studentsData.total_pages, p + 1))}
                  className="btn btn-secondary btn-sm"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ================= TAB 4: MESSAGE TEMPLATES ================= */}
      {activeTab === 'templates' && (
        <div>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
            flexWrap: 'wrap',
            gap: 12
          }}>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--heading)' }}>WhatsApp Message Templates</h2>
              <p style={{ fontSize: 13, color: 'var(--muted)' }}>
                Customize message formats with dynamic placeholders. Used by EBM dispatchers for WhatsApp group joining, goodies, or event invites.
              </p>
            </div>
            <button
              onClick={() => setTemplateModal({ open: true, isEdit: false, data: { title: '', content: '', is_default: false } })}
              className="btn btn-primary"
            >
              <Plus size={15} />
              <span>Create Template</span>
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 20 }}>
            {templates.map((tpl) => (
              <div key={tpl.id} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--heading)' }}>{tpl.title}</h3>
                  {tpl.is_default ? (
                    <span className="badge badge-success">Active Default</span>
                  ) : (
                    <button
                      onClick={() => handleSetDefaultTemplate(tpl.id)}
                      className="btn btn-secondary btn-sm"
                    >
                      Make Default
                    </button>
                  )}
                </div>

                <pre style={{
                  background: '#F8FAFC',
                  border: '1px solid var(--border)',
                  padding: 14,
                  borderRadius: 'var(--radius)',
                  fontSize: 13,
                  color: 'var(--text)',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'inherit',
                  flex: 1,
                  marginBottom: 16
                }}>
                  {tpl.content}
                </pre>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    Placeholders: {'{name}, {link}, {acm_id}, {phone}'}
                  </span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => setTemplateModal({ open: true, isEdit: true, data: tpl })}
                      className="btn btn-secondary btn-sm"
                    >
                      Edit
                    </button>
                    {!tpl.is_default && (
                      <button
                        onClick={() => handleDeleteTemplate(tpl.id)}
                        className="btn btn-danger btn-sm"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ================= TAB 5: GATEWAY CONFIGURATION ================= */}
      {activeTab === 'settings' && (
        <div style={{ maxWidth: 600 }}>
          <div className="card">
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, color: 'var(--heading)' }}>Gateway &amp; Server Configuration</h2>
            <form onSubmit={handleSaveConfig}>
              <div className="form-group">
                <label>Official WhatsApp Group Invite Link</label>
                <input
                  type="text"
                  value={config.whatsapp_group_link || ''}
                  onChange={(e) => setConfig({ ...config, whatsapp_group_link: e.target.value })}
                  placeholder="https://chat.whatsapp.com/XXXXX"
                  required
                />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  This secret destination link is revealed only during verified one-time redirections.
                </span>
              </div>

              <div className="form-group">
                <label>Base Server URL (Public Domain / Cloudflare URL)</label>
                <input
                  type="text"
                  value={config.base_url || ''}
                  onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
                  placeholder="https://your-domain.com"
                  required
                />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  Used when generating student one-time links: e.g. {'https://your-domain.com/join/<token>'}
                </span>
              </div>

              <div className="form-group">
                <label>Change Master Admin Password</label>
                <input
                  type="password"
                  value={config.admin_password || ''}
                  onChange={(e) => setConfig({ ...config, admin_password: e.target.value })}
                  placeholder="Enter new admin password"
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ marginTop: 8 }}>
                Save Configuration
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Renew Token */}
      <Modal
        isOpen={renewModal.open}
        title="Renew / Reset Invite Token"
        onClose={() => setRenewModal({ open: false, student: null })}
      >
        {renewModal.student && (
          <div>
            <p style={{ fontSize: 14, color: 'var(--text)', marginBottom: 16 }}>
              Choose an action for <strong>{renewModal.student.name}</strong> ({renewModal.student.phone || 'No phone'}):
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <button
                onClick={() => handleRenewToken('reset')}
                className="btn btn-primary"
                style={{ justifyContent: 'flex-start', padding: 14 }}
              >
                <div>
                  <div style={{ fontWeight: 700 }}>Reset Existing Link (Keep Same URL)</div>
                  <div style={{ fontSize: 12, opacity: 0.9, marginTop: 2 }}>
                    Clears the device-bound lock and allows the recipient to open their existing URL again.
                  </div>
                </div>
              </button>

              <button
                onClick={() => handleRenewToken('new_token')}
                className="btn btn-secondary"
                style={{ justifyContent: 'flex-start', padding: 14 }}
              >
                <div>
                  <div style={{ fontWeight: 700 }}>Generate Brand New Cryptographic Token</div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>
                    Invalidates the previous URL completely and issues a brand new invite link.
                  </div>
                </div>
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Modal: Add/Edit EBM */}
      <Modal
        isOpen={ebmModal.open}
        title={ebmModal.isEdit ? 'Edit EBM Team Member' : 'Add New EBM Team Member'}
        onClose={() => setEbmModal({ open: false, isEdit: false, data: {} })}
      >
        <form onSubmit={handleSaveEbm}>
          <div className="form-group">
            <label>Full Name</label>
            <input
              type="text"
              value={ebmModal.data.name || ''}
              onChange={(e) => setEbmModal({ ...ebmModal, data: { ...ebmModal.data, name: e.target.value } })}
              placeholder="e.g. EBM Coordinator One"
              required
            />
          </div>

          <div className="form-group">
            <label>Username (Login ID)</label>
            <input
              type="text"
              value={ebmModal.data.username || ''}
              onChange={(e) => setEbmModal({ ...ebmModal, data: { ...ebmModal.data, username: e.target.value.toLowerCase() } })}
              placeholder="e.g. ebm_coord_1"
              disabled={ebmModal.isEdit}
              required
            />
          </div>

          <div className="form-group">
            <label>{ebmModal.isEdit ? 'Change Password (Leave blank to keep current)' : 'Password'}</label>
            <input
              type="password"
              value={ebmModal.data.password || ''}
              onChange={(e) => setEbmModal({ ...ebmModal, data: { ...ebmModal.data, password: e.target.value } })}
              placeholder={ebmModal.isEdit ? 'Keep unchanged' : 'Password'}
              required={!ebmModal.isEdit}
            />
          </div>

          <div className="form-group">
            <label>Allocation Weight (Higher ratio receives more students)</label>
            <input
              type="number"
              min="1"
              max="20"
              value={ebmModal.data.weight || 4}
              onChange={(e) => setEbmModal({ ...ebmModal, data: { ...ebmModal.data, weight: parseInt(e.target.value) || 1 } })}
              required
            />
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>
              Example: Coordinators / CO-ORD (weight 6), regular members (weight 4).
            </span>
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: 8 }}>
            {ebmModal.isEdit ? 'Save Changes' : 'Create EBM Member'}
          </button>
        </form>
      </Modal>

      {/* Modal: Add/Edit Message Template with Real-Time WhatsApp Live Preview */}
      <Modal
        isOpen={templateModal.open}
        maxWidth="980px"
        title={templateModal.isEdit ? 'Edit Message Template' : 'Create New Message Template'}
        onClose={() => setTemplateModal({ open: false, isEdit: false, data: {} })}
      >
        <form onSubmit={handleSaveTemplate}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
            gap: 24,
            alignItems: 'start'
          }}>
            {/* Left Side: Editor & Variable Chips */}
            <div>
              <div className="form-group" style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--heading)', marginBottom: 6, display: 'block' }}>
                  Template Title
                </label>
                <input
                  type="text"
                  value={templateModal.data.title || ''}
                  onChange={(e) => setTemplateModal({ ...templateModal, data: { ...templateModal.data, title: e.target.value } })}
                  placeholder="e.g. Official WhatsApp Group Invitation"
                  required
                  style={{ width: '100%', padding: '9px 12px', fontSize: 14 }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--heading)', margin: 0 }}>
                    Message Content
                  </label>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    {(templateModal.data.content || '').length} characters
                  </span>
                </div>

                {/* Variable Quick-Insert Chips */}
                <div style={{
                  background: 'var(--bg)',
                  padding: '10px',
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                  marginBottom: 10
                }}>
                  <div style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: 'var(--muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    marginBottom: 6
                  }}>
                    Click badge to insert variable at cursor:
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {[
                      { ph: '{name}', label: 'Name' },
                      { ph: '{link}', label: 'Token Link' },
                      { ph: '{acm_id}', label: 'ACM ID' },
                      { ph: '{branch}', label: 'Branch' },
                      { ph: '{year}', label: 'Year' },
                      { ph: '{goodies}', label: 'Goodies' },
                      { ph: '{phone}', label: 'Phone' }
                    ].map((item) => (
                      <button
                        key={item.ph}
                        type="button"
                        onClick={() => insertVariableAtCursor(item.ph)}
                        className="btn btn-secondary btn-sm"
                        style={{
                          fontSize: 11,
                          padding: '4px 8px',
                          borderRadius: 14,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4
                        }}
                        title={`Insert ${item.label}`}
                      >
                        <span style={{ color: 'var(--primary)', fontWeight: 700 }}>+</span>
                        <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{item.ph}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <textarea
                  ref={templateTextareaRef}
                  rows="9"
                  value={templateModal.data.content || ''}
                  onChange={(e) => setTemplateModal({ ...templateModal, data: { ...templateModal.data, content: e.target.value } })}
                  placeholder="Hello {name}, welcome to SRKR ACM Student Chapter! Here is your exclusive, single-use token to join our official WhatsApp community: {link}..."
                  required
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    fontSize: 13,
                    lineHeight: 1.5,
                    fontFamily: 'inherit',
                    resize: 'vertical'
                  }}
                />

                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginTop: 6,
                  fontSize: 11,
                  color: 'var(--muted)'
                }}>
                  <span>WhatsApp formatting: <strong>*bold*</strong>, <em>_italic_</em>, <del>~strike~</del>, <code>```code```</code></span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ flex: 1 }}
                  onClick={() => setTemplateModal({ open: false, isEdit: false, data: {} })}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ flex: 1.5 }}
                >
                  {templateModal.isEdit ? 'Save Changes' : 'Create Template'}
                </button>
              </div>
            </div>

            {/* Right Side: WhatsApp Live Preview Phone Mockup */}
            <div>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 6
              }}>
                <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--heading)', margin: 0 }}>
                  Live WhatsApp Preview
                </label>
                <span style={{
                  fontSize: 10,
                  fontWeight: 700,
                  background: '#DCFCE7',
                  color: '#15803D',
                  padding: '2px 8px',
                  borderRadius: 10
                }}>
                  REAL-TIME
                </span>
              </div>

              {/* Phone Mockup Frame */}
              <div style={{
                borderRadius: 14,
                overflow: 'hidden',
                border: '1px solid #D1D5DB',
                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1)',
                background: '#ECE5DD'
              }}>
                {/* WhatsApp Chat Header */}
                <div style={{
                  background: '#075E54',
                  padding: '10px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  color: '#FFFFFF'
                }}>
                  <div style={{
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    background: '#25D366',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    fontSize: 14,
                    color: '#FFFFFF'
                  }}>
                    MD
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.2 }}>
                      Y Maheswari Devi
                    </div>
                    <div style={{ fontSize: 11, opacity: 0.85 }}>
                      online &bull; SRKR ACM Fresher
                    </div>
                  </div>
                </div>

                {/* WhatsApp Chat Body */}
                <div style={{
                  padding: '16px 12px',
                  minHeight: 280,
                  maxHeight: 380,
                  overflowY: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10
                }}>
                  {/* Date Badge */}
                  <div style={{
                    alignSelf: 'center',
                    background: 'rgba(255, 255, 255, 0.9)',
                    padding: '3px 10px',
                    borderRadius: 10,
                    fontSize: 10,
                    fontWeight: 600,
                    color: '#54656F',
                    boxShadow: '0 1px 1px rgba(0,0,0,0.08)',
                    marginBottom: 4
                  }}>
                    TODAY
                  </div>

                  {/* Outgoing Message Bubble */}
                  <div style={{
                    alignSelf: 'flex-end',
                    maxWidth: '92%',
                    background: '#E7FFDB',
                    color: '#111B21',
                    borderRadius: '8px 0px 8px 8px',
                    padding: '8px 12px 6px 12px',
                    boxShadow: '0 1px 1px rgba(11,20,26,.13)',
                    fontSize: 13,
                    lineHeight: 1.45,
                    wordBreak: 'break-word',
                    position: 'relative'
                  }}>
                    {/* Rendered Text */}
                    {renderWhatsAppPreview(templateModal.data.content)}

                    {/* WhatsApp Rich Link Card Preview (if link tag exists) */}
                    {(templateModal.data.content || '').includes('{link}') && (
                      <div style={{
                        marginTop: 8,
                        borderRadius: 6,
                        background: '#FFFFFF',
                        border: '1px solid #D1D7DB',
                        overflow: 'hidden',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                      }}>
                        <div style={{
                          background: 'linear-gradient(135deg, #128C7E 0%, #075E54 100%)',
                          padding: '8px 10px',
                          color: '#FFFFFF',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8
                        }}>
                          <span style={{ fontSize: 16 }}>💬</span>
                          <div>
                            <div style={{ fontSize: 12, fontWeight: 700, lineHeight: 1.2 }}>
                              ACE Fresher Community 2026
                            </div>
                            <div style={{ fontSize: 10, opacity: 0.85 }}>
                              WhatsApp Group Invite &bull; Verified
                            </div>
                          </div>
                        </div>
                        <div style={{ padding: '6px 10px', background: '#F8F9FA' }}>
                          <div style={{ fontSize: 11, color: '#027eb5', fontWeight: 600 }}>
                            chat.whatsapp.com/sample_tk_8f92
                          </div>
                          <div style={{ fontSize: 10, color: '#667781', marginTop: 1 }}>
                            Click to join official WhatsApp group
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Message Time and Blue Double Checkmarks */}
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'flex-end',
                      gap: 4,
                      marginTop: 4,
                      fontSize: 10,
                      color: '#667781'
                    }}>
                      <span>10:42 AM</span>
                      <span style={{ color: '#53BDEB', fontWeight: 700, letterSpacing: -1.5 }}>
                        ✓✓
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div style={{
                fontSize: 11,
                color: 'var(--muted)',
                marginTop: 8,
                textAlign: 'center'
              }}>
                ✨ Preview updates automatically with sample student details.
              </div>
            </div>
          </div>
        </form>
      </Modal>

      {/* Modal: Edit Student Record */}
      <Modal
        isOpen={editStudentModal.open}
        maxWidth="600px"
        title="Edit Student Information"
        onClose={() => setEditStudentModal({ open: false, data: null, saving: false })}
      >
        {editStudentModal.data && (
          <form onSubmit={handleSaveStudentEdit}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>Full Name</label>
                <input
                  type="text"
                  value={editStudentModal.data.name || ''}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, name: e.target.value }
                  })}
                  required
                />
              </div>

              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>Mobile Number (WhatsApp)</label>
                <input
                  type="text"
                  value={editStudentModal.data.phone || ''}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, phone: e.target.value }
                  })}
                  placeholder="e.g. 9876543210"
                  required
                />
              </div>

              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>ACM ID / Confirmation</label>
                <input
                  type="text"
                  value={editStudentModal.data.acm_id || ''}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, acm_id: e.target.value }
                  })}
                />
              </div>

              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>Branch</label>
                <input
                  type="text"
                  value={editStudentModal.data.branch || ''}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, branch: e.target.value }
                  })}
                  placeholder="e.g. IT, CSE, ECE"
                />
              </div>

              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>Academic Year</label>
                <select
                  value={editStudentModal.data.year || '1'}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, year: e.target.value }
                  })}
                >
                  <option value="1">1st Year</option>
                  <option value="2">2nd Year</option>
                  <option value="3">3rd Year</option>
                  <option value="4">4th Year</option>
                </select>
              </div>

              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>Goodies Status</label>
                <select
                  value={editStudentModal.data.goodies || 'Yes'}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, goodies: e.target.value }
                  })}
                >
                  <option value="Yes">Yes (Eligible)</option>
                  <option value="No">No (Not Eligible)</option>
                </select>
              </div>

              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>Section</label>
                <input
                  type="text"
                  value={editStudentModal.data.section || ''}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, section: e.target.value }
                  })}
                  placeholder="e.g. A, B, C"
                />
              </div>

              <div className="form-group">
                <label style={{ fontSize: 13, fontWeight: 600 }}>Domain</label>
                <input
                  type="text"
                  value={editStudentModal.data.domain || ''}
                  onChange={(e) => setEditStudentModal({
                    ...editStudentModal,
                    data: { ...editStudentModal.data, domain: e.target.value }
                  })}
                  placeholder="e.g. Web Dev, AI/ML"
                />
              </div>
            </div>

            <div className="form-group" style={{ marginTop: 14 }}>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Assigned EBM Member</label>
              <select
                value={editStudentModal.data.assigned_ebm_id || ''}
                onChange={(e) => setEditStudentModal({
                  ...editStudentModal,
                  data: { ...editStudentModal.data, assigned_ebm_id: e.target.value }
                })}
              >
                <option value="">-- Unassigned --</option>
                {ebms.map((ebm) => (
                  <option key={ebm.id} value={ebm.id}>
                    {ebm.name} ({ebm.assigned_count || 0})
                  </option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setEditStudentModal({ open: false, data: null, saving: false })}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                style={{ flex: 1 }}
                disabled={editStudentModal.saving}
              >
                {editStudentModal.saving ? 'Saving...' : 'Save Student Changes'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      {/* Modal: Manual Student Adjustment & Batch Transfer */}
      <Modal
        isOpen={transferModal.open}
        title="Manual Student Adjustment & Batch Transfer"
        onClose={() => setTransferModal({ ...transferModal, open: false })}
      >
        <div>
          <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
            Transfer students between team members or adjust allocations if an EBM or student is not comfortable.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 700 }}>Source (Transfer From):</label>
              <select
                value={transferModal.fromEbmId}
                onChange={(e) => handleTransferSourceChange(e.target.value)}
                style={{ fontSize: 13 }}
              >
                <option value="unassigned">Unassigned Pool ({overview?.stats?.unassigned_students || 0})</option>
                {ebms.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name} ({e.assigned_count || 0} students)
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 700 }}>Destination (Transfer To):</label>
              <select
                value={transferModal.toEbmId}
                onChange={(e) => setTransferModal({ ...transferModal, toEbmId: e.target.value })}
                style={{ fontSize: 13 }}
              >
                <option value="unassigned">Return to Unassigned Pool</option>
                {ebms.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name} ({e.assigned_count || 0} students)
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Mode Switch Tabs */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, borderBottom: '1px solid var(--border)', paddingBottom: 8 }}>
            <button
              type="button"
              className={`btn btn-sm ${transferModal.mode === 'quick' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTransferModal({ ...transferModal, mode: 'quick' })}
            >
              Quick Count Transfer
            </button>
            <button
              type="button"
              className={`btn btn-sm ${transferModal.mode === 'specific' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTransferModal({ ...transferModal, mode: 'specific' })}
            >
              Select Specific Students ({transferModal.sourceStudents.length})
            </button>
          </div>

          {transferModal.mode === 'quick' ? (
            <div>
              <div className="form-group">
                <label>Number of Students to Move (Max {getSourceStudentCount()}):</label>
                <input
                  type="number"
                  min="1"
                  max={getSourceStudentCount() || 1}
                  value={transferModal.count}
                  onChange={(e) => setTransferModal({ ...transferModal, count: parseInt(e.target.value) || 1 })}
                />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  Prioritizes uncontacted students first to avoid disrupting active outreach.
                </span>
              </div>

              <button
                type="button"
                className="btn btn-primary"
                style={{ width: '100%', marginTop: 8 }}
                onClick={handleExecuteQuickTransfer}
                disabled={getSourceStudentCount() === 0}
              >
                Transfer {transferModal.count} Student(s)
              </button>
            </div>
          ) : (
            <div>
              <div style={{ marginBottom: 10, display: 'flex', gap: 8, alignItems: 'center' }}>
                <div className="search-wrapper" style={{ flex: 1 }}>
                  <Search className="search-icon" size={14} />
                  <input
                    type="text"
                    placeholder="Search source students..."
                    value={transferModal.searchFilter}
                    onChange={(e) => setTransferModal({ ...transferModal, searchFilter: e.target.value })}
                    style={{ padding: '6px 10px 6px 32px', fontSize: 12 }}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleSelectAllFilteredStudents}
                >
                  Toggle All
                </button>
              </div>

              {transferModal.loadingStudents ? (
                <div style={{ textAlign: 'center', padding: 24, color: 'var(--muted)', fontSize: 13 }}>
                  Loading students...
                </div>
              ) : filteredSourceStudents.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 24, color: 'var(--muted)', fontSize: 13 }}>
                  No students found in this source.
                </div>
              ) : (
                <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 8, padding: 8 }}>
                  {filteredSourceStudents.map((s) => (
                    <label
                      key={s.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 8px',
                        borderBottom: '1px solid #F1F5F9',
                        cursor: 'pointer',
                        fontSize: 13,
                        margin: 0
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={transferModal.selectedStudentIds.includes(s.id)}
                          onChange={() => handleToggleTransferStudentId(s.id)}
                        />
                        <div>
                          <strong>{s.name}</strong>
                          <span style={{ color: 'var(--muted)', marginLeft: 6, fontSize: 12 }}>{s.phone || ''}</span>
                        </div>
                      </div>
                      {s.is_contacted ? (
                        <span className="badge badge-success" style={{ fontSize: 10 }}>Contacted</span>
                      ) : (
                        <span className="badge badge-neutral" style={{ fontSize: 10 }}>Pending</span>
                      )}
                    </label>
                  ))}
                </div>
              )}

              <button
                type="button"
                className="btn btn-primary"
                style={{ width: '100%', marginTop: 12 }}
                onClick={handleExecuteSpecificTransfer}
                disabled={transferModal.selectedStudentIds.length === 0}
              >
                Transfer {transferModal.selectedStudentIds.length} Selected Student(s)
              </button>
            </div>
          )}
        </div>
      </Modal>

      {/* Live ACM DB Sync Modal */}
      <Modal
        isOpen={syncModalOpen}
        onClose={() => !syncForm.loading && setSyncModalOpen(false)}
        title="Sync from Live ACM MongoDB (registrations)"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
            Query your main cloud ACM MongoDB cluster (<code>ACE_REG.registrations</code>) and ingest student records directly into the dispatching portal.
          </p>

          <div>
            <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--heading)', display: 'block', marginBottom: 6 }}>
              Target Academic Year:
            </label>
            <select
              value={syncForm.year}
              onChange={(e) => setSyncForm({ ...syncForm, year: e.target.value })}
              style={{ width: '100%' }}
            >
              <option value="all">All Academic Years (Entire Roster)</option>
              <option value="1st Year">1st Year Only (Freshers)</option>
              <option value="2nd Year">2nd Year Only</option>
              <option value="3rd Year">3rd Year Only</option>
              <option value="4th Year">4th Year Only</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--heading)', display: 'block', marginBottom: 6 }}>
              Goodies Eligibility:
            </label>
            <select
              value={syncForm.goodies}
              onChange={(e) => setSyncForm({ ...syncForm, goodies: e.target.value })}
              style={{ width: '100%' }}
            >
              <option value="all">All (Both Eligible &amp; Non-Eligible)</option>
              <option value="yes">Goodies: Yes Only (Eligible)</option>
              <option value="no">Goodies: No Only (Not Eligible)</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--heading)', display: 'block', marginBottom: 6 }}>
              Sync Mode:
            </label>
            <div className="radio-group" style={{ margin: 0 }}>
              <label className={`radio-option ${syncForm.mode === 'sync' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="sync_mode"
                  value="sync"
                  checked={syncForm.mode === 'sync'}
                  onChange={(e) => setSyncForm({ ...syncForm, mode: e.target.value })}
                />
                <div>
                  <strong style={{ display: 'block', fontSize: 13, color: 'var(--heading)' }}>
                    Sync &amp; Merge (Safe)
                  </strong>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    Preserves current EBM assignments and contact statuses. Adds newly registered students.
                  </span>
                </div>
              </label>

              <label className={`radio-option ${syncForm.mode === 'overwrite' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="sync_mode"
                  value="overwrite"
                  checked={syncForm.mode === 'overwrite'}
                  onChange={(e) => setSyncForm({ ...syncForm, mode: e.target.value })}
                />
                <div>
                  <strong style={{ display: 'block', fontSize: 13, color: 'var(--heading)' }}>
                    Clean Overwrite (Reset Portal)
                  </strong>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    Cleans the portal student table and re-imports matching registrations from scratch.
                  </span>
                </div>
              </label>
            </div>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, margin: 0 }}>
            <input
              type="checkbox"
              checked={syncForm.generate_tokens}
              onChange={(e) => setSyncForm({ ...syncForm, generate_tokens: e.target.checked })}
            />
            <span>Generate single-use WhatsApp join tokens for synced students</span>
          </label>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setSyncModalOpen(false)}
              disabled={syncForm.loading}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleRunSyncDb}
              disabled={syncForm.loading}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              {syncForm.loading && <RefreshCw className="spin" size={14} />}
              <span>{syncForm.loading ? 'Syncing...' : 'Run Sync Now'}</span>
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
