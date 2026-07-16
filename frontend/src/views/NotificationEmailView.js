import { useEffect, useState, useMemo, useCallback } from "react";
import {
  Send, Upload, RefreshCw, Users, Loader2, Mail, Trash2, X, CheckCircle2, AlertTriangle,
} from "lucide-react";
import { apiFetch, apiJSON, API } from "@/lib/api";
import RichTextEditor from "../components/RichTextEditor";

const DEFAULT_CC = "manoj@blubridge.com, praveen@blubridge.com";

// Split comma / newline / semicolon separated emails into an array,
// case-insensitive dedupe.
function splitEmails(str) {
  const seen = new Set();
  const out = [];
  for (const raw of (str || "").split(/[,\n;]+/)) {
    const e = raw.trim();
    if (!e || !e.includes("@")) continue;
    const k = e.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(e);
  }
  return out;
}

export default function NotificationEmailView() {
  // --- Roster state ---
  const [depts, setDepts] = useState([]);
  const [selectedDept, setSelectedDept] = useState("");
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState({}); // email -> bool
  const [loadingRoster, setLoadingRoster] = useState(false);

  // --- Compose state ---
  const [ccAddr, setCcAddr]         = useState(DEFAULT_CC);
  const [customRcp, setCustomRcp]   = useState(""); // free-text extra To recipients
  const [subject, setSubject]       = useState("");
  const [html, setHtml]             = useState("");
  const [rteResetKey, setRteResetKey] = useState(0);

  // --- Import / send state ---
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState(null);
  const [sending, setSending]     = useState(false);
  const [sendResult, setSendResult] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const loadDepartments = useCallback(async () => {
    try {
      const r = await apiJSON("/employees/departments");
      setDepts(r.items || []);
    } catch { setDepts([]); }
  }, []);

  const loadEmployees = useCallback(async (dept) => {
    setLoadingRoster(true);
    try {
      const q = dept ? `?department=${encodeURIComponent(dept)}` : "";
      const r = await apiJSON(`/employees${q}`);
      const items = r.items || [];
      setEmployees(items);
      const s = {};
      items.forEach((e) => { s[e.email] = true; });
      setSelected(s);
    } catch {
      setEmployees([]); setSelected({});
    } finally {
      setLoadingRoster(false);
    }
  }, []);

  useEffect(() => { loadDepartments(); }, [loadDepartments]);
  useEffect(() => {
    if (selectedDept) loadEmployees(selectedDept);
    else { setEmployees([]); setSelected({}); }
  }, [selectedDept, loadEmployees]);

  // --- Merged recipient list (roster picked + custom typed) ---
  const rosterPicked = useMemo(
    () => employees.filter((e) => selected[e.email]),
    [employees, selected]
  );
  const customEmails = useMemo(() => splitEmails(customRcp), [customRcp]);

  const recipients = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const e of rosterPicked) {
      const k = e.email.toLowerCase();
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({ email: e.email, name: e.name });
    }
    for (const em of customEmails) {
      const k = em.toLowerCase();
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({ email: em, name: "" });
    }
    return out;
  }, [rosterPicked, customEmails]);

  const totalCount = recipients.length;

  const toggleAll = (checked) => {
    const s = {};
    employees.forEach((e) => { s[e.email] = checked; });
    setSelected(s);
  };

  // --- Import roster ---
  const onImport = async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file) return;
    setImporting(true); setImportMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API}/employees/import`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": (document.cookie.match(/hrcert_csrf=([^;]+)/) || [])[1] || "" },
        body: fd,
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.detail || `HTTP ${res.status}`);
      setImportMsg({ kind: "ok", text: `Roster replaced — ${j.inserted} employees imported.` });
      await loadDepartments();
      if (selectedDept) await loadEmployees(selectedDept);
    } catch (e) {
      setImportMsg({ kind: "err", text: e.message || "Upload failed." });
    } finally { setImporting(false); }
  };

  // --- Send ---
  const canSend = totalCount > 0 && subject.trim() && html.replace(/<[^>]+>/g, "").trim();
  const doSend = async () => {
    setSending(true); setSendResult(null);
    try {
      const payload = {
        subject: subject.trim(),
        html,
        recipients,
        cc: splitEmails(ccAddr),
        department: selectedDept || null,
      };
      const res = await apiFetch("/notification/send", { method: "POST", body: payload });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || `HTTP ${res.status}`);
      setSendResult(j);
      if (j.failed === 0) {
        // Full success: clear the form for the next batch.
        setSubject("");
        setHtml("");
        setRteResetKey((k) => k + 1);
        setCustomRcp("");
      }
    } catch (e) {
      setSendResult({ ok: false, sent: 0, failed: totalCount, total: totalCount, error: e.message });
    } finally {
      setSending(false); setConfirmOpen(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6" data-testid="notification-email-view">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#1a1a1f] flex items-center gap-2">
            <Mail size={20} className="text-[#232369]" />
            Notification Email
          </h1>
          <p className="text-sm text-[#1a1a1f]/60 mt-1">
            Each recipient gets their own individual email (they only see themselves in the To field).
            Owners in CC are copied on every send.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-white border border-[#1a1a1f]/15 text-[#1a1a1f]/75 hover:text-[#232369] hover:border-[#232369]/40 cursor-pointer transition-colors"
            data-testid="notif-upload-label"
            title="Replace roster from an .xlsx file"
          >
            {importing ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
            <span>Replace roster (.xlsx)</span>
            <input
              type="file" accept=".xlsx" disabled={importing}
              onChange={onImport} className="hidden" data-testid="notif-upload-input"
            />
          </label>
          <button
            type="button"
            onClick={() => { loadDepartments(); if (selectedDept) loadEmployees(selectedDept); }}
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-white border border-[#1a1a1f]/15 text-[#1a1a1f]/75 hover:text-[#232369] hover:border-[#232369]/40 transition-colors"
            data-testid="notif-refresh-btn"
          >
            <RefreshCw size={13} /> <span>Refresh</span>
          </button>
        </div>
      </div>

      {importMsg && (
        <div
          data-testid="notif-import-msg"
          className={
            "mb-4 rounded-md px-3 py-2 text-sm border " +
            (importMsg.kind === "ok"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-rose-50 border-rose-200 text-rose-800")
          }
        >
          {importMsg.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-6">
        {/* LEFT — roster picker */}
        <section className="bg-white rounded-xl border border-[#1a1a1f]/10 p-5">
          <label className="block text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide mb-2">
            Department
          </label>
          <select
            data-testid="notif-department"
            value={selectedDept}
            onChange={(e) => setSelectedDept(e.target.value)}
            className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
          >
            <option value="">— Select a department —</option>
            {depts.map((d) => (
              <option key={d.name} value={d.name}>{d.name} ({d.count})</option>
            ))}
          </select>

          <div className="mt-4 flex items-center justify-between gap-2">
            <div className="text-xs text-[#1a1a1f]/60 inline-flex items-center gap-1.5">
              <Users size={13} />
              <span data-testid="notif-selected-count">
                {rosterPicked.length} of {employees.length} selected
              </span>
            </div>
            {employees.length > 0 && (
              <div className="flex items-center gap-2 text-[11px]">
                <button type="button" onClick={() => toggleAll(true)}  data-testid="notif-select-all"  className="text-[#232369] hover:underline">Select all</button>
                <span className="text-[#1a1a1f]/25">·</span>
                <button type="button" onClick={() => toggleAll(false)} data-testid="notif-select-none" className="text-[#1a1a1f]/60 hover:text-[#232369] hover:underline">Clear</button>
              </div>
            )}
          </div>

          <div className="mt-3 border border-[#1a1a1f]/10 rounded-lg overflow-hidden">
            <div className="max-h-[420px] overflow-y-auto divide-y divide-[#1a1a1f]/5">
              {loadingRoster ? (
                <div className="p-6 text-sm text-[#1a1a1f]/55 inline-flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin" /> Loading roster…
                </div>
              ) : !selectedDept ? (
                <div className="p-6 text-sm text-[#1a1a1f]/50">
                  Pick a department above to load its roster.
                </div>
              ) : employees.length === 0 ? (
                <div className="p-6 text-sm text-[#1a1a1f]/50">
                  No employees found in this department.
                </div>
              ) : employees.map((e) => (
                <label key={e.email} className="flex items-start gap-3 px-3 py-2 hover:bg-[#f6f4ef]/60 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!selected[e.email]}
                    onChange={(ev) => setSelected((s) => ({ ...s, [e.email]: ev.target.checked }))}
                    className="mt-0.5 accent-[#232369]"
                    data-testid={`notif-cb-${e.email}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-[#1a1a1f] truncate">{e.name}</div>
                    <div className="text-[11px] text-[#1a1a1f]/55 truncate">{e.email}</div>
                    {(e.team || e.designation) && (
                      <div className="text-[11px] text-[#1a1a1f]/45 mt-0.5 truncate">
                        {[e.team, e.designation].filter(Boolean).join(" · ")}
                      </div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Add custom recipients */}
          <div className="mt-4">
            <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
              Additional recipients (optional)
            </label>
            <textarea
              value={customRcp}
              onChange={(e) => setCustomRcp(e.target.value)}
              rows={2}
              data-testid="notif-custom-recipients"
              placeholder="Extra emails — comma / newline / semicolon separated"
              className="mt-1 w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15 resize-none"
            />
          </div>
        </section>

        {/* RIGHT — compose */}
        <section className="bg-white rounded-xl border border-[#1a1a1f]/10 p-5 space-y-4">
          <div>
            <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
              CC (owners)
            </label>
            <input
              type="text"
              value={ccAddr}
              onChange={(e) => setCcAddr(e.target.value)}
              data-testid="notif-cc"
              placeholder="Comma-separated emails"
              className="mt-1 w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
            />
            <p className="mt-1 text-[11px] text-[#1a1a1f]/50">
              Owners copied on every individual email. Sender is
              <code className="mx-1 px-1 py-0.5 rounded bg-[#f6f4ef] text-[#232369] text-[10.5px]">hr@blubridge.com</code>
              (SendGrid verified).
            </p>
          </div>

          <div>
            <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
              Subject
            </label>
            <input
              type="text" value={subject} onChange={(e) => setSubject(e.target.value)}
              data-testid="notif-subject"
              placeholder="e.g. Team update — July release"
              className="mt-1 w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
                Message
              </label>
              <span className="text-[10.5px] text-[#1a1a1f]/40">
                Tip: use <code className="px-1 rounded bg-[#f6f4ef]">{"{name}"}</code> to insert each recipient&apos;s name.
              </span>
            </div>
            <RichTextEditor
              value={html}
              onChange={setHtml}
              resetKey={rteResetKey}
              testid="notif-rte"
            />
          </div>

          {/* Send bar */}
          <div className="pt-2 border-t border-[#1a1a1f]/5 flex flex-wrap items-center gap-3">
            <div className="text-sm text-[#1a1a1f]/70" data-testid="notif-recipient-summary">
              <span className="font-semibold text-[#232369]">{totalCount}</span> recipient{totalCount === 1 ? "" : "s"}
              {totalCount > 0 && " · each will receive an individual email"}
            </div>
            <button
              type="button"
              disabled={!canSend || sending}
              onClick={() => setConfirmOpen(true)}
              data-testid="notif-send-btn"
              className={
                "ml-auto inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-medium transition-colors " +
                (!canSend || sending
                  ? "bg-[#1a1a1f]/10 text-[#1a1a1f]/40 cursor-not-allowed"
                  : "bg-[#232369] text-white hover:bg-[#1a1a4d]")
              }
            >
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              <span>{sending ? `Sending…` : `Send ${totalCount || ""} email${totalCount === 1 ? "" : "s"}`.trim()}</span>
            </button>
          </div>

          {sendResult && (
            <div
              data-testid="notif-send-result"
              className={
                "rounded-md px-3 py-2.5 text-sm border flex items-start gap-2 " +
                (sendResult.ok
                  ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                  : "bg-amber-50 border-amber-200 text-amber-900")
              }
            >
              {sendResult.ok
                ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600" />
                : <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-600" />}
              <div className="min-w-0">
                <div>
                  Sent <b>{sendResult.sent || 0}</b> of <b>{sendResult.total || 0}</b>
                  {sendResult.failed ? <> · <b>{sendResult.failed}</b> failed</> : null}
                </div>
                {sendResult.details?.failed?.length > 0 && (
                  <ul className="mt-1 text-[11.5px] list-disc pl-5 max-h-24 overflow-y-auto">
                    {sendResult.details.failed.slice(0, 8).map((f, i) => (
                      <li key={i}><code>{f.email}</code> — {f.error}</li>
                    ))}
                  </ul>
                )}
                {sendResult.error && <div className="mt-1 text-[11.5px]">{sendResult.error}</div>}
              </div>
              <button
                type="button"
                onClick={() => setSendResult(null)}
                className="ml-auto text-[#1a1a1f]/45 hover:text-[#1a1a1f]"
                aria-label="Dismiss"
              >
                <X size={14} />
              </button>
            </div>
          )}
        </section>
      </div>

      {/* Confirm dialog */}
      {confirmOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="notif-confirm-modal">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-5">
            <h3 className="text-base font-semibold text-[#1a1a1f]">Send {totalCount} individual email{totalCount === 1 ? "" : "s"}?</h3>
            <p className="mt-2 text-sm text-[#1a1a1f]/70">
              Each recipient sees only their own address in the To field.
              Owners in CC ({splitEmails(ccAddr).length || 0}) are copied on every message.
              This cannot be undone.
            </p>
            <div className="mt-2 text-[12px] text-[#1a1a1f]/55">
              Subject: <b className="text-[#1a1a1f]/85">{subject || "(none)"}</b>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                disabled={sending}
                className="text-sm px-4 py-1.5 rounded-full border border-[#1a1a1f]/15 text-[#1a1a1f]/75 hover:bg-[#f6f4ef]"
                data-testid="notif-confirm-cancel"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={doSend}
                disabled={sending}
                className="text-sm px-4 py-1.5 rounded-full bg-[#232369] text-white hover:bg-[#1a1a4d] disabled:opacity-60 inline-flex items-center gap-2"
                data-testid="notif-confirm-send"
              >
                {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                <span>Yes, send now</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
