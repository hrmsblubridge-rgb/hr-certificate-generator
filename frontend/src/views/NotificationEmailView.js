import { useEffect, useState, useMemo, useCallback } from "react";
import {
  Send, Copy, Check, Upload, RefreshCw, Users, Loader2, Mail,
  ExternalLink, Trash2,
} from "lucide-react";
import { apiFetch, apiJSON, API } from "@/lib/api";

const DEFAULT_FROM = "hr@blubridge.com";
const DEFAULT_CC   = "manoj@blubridge.com, praveen@blubridge.com";

function CopyButton({ text, label = "Copy", testid }) {
  const [ok, setOk] = useState(false);
  const onClick = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setOk(true);
      setTimeout(() => setOk(false), 1200);
    } catch { /* clipboard blocked */ }
  };
  return (
    <button
      type="button"
      data-testid={testid}
      onClick={onClick}
      disabled={!text}
      className={
        "inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-md border transition-colors " +
        (ok
          ? "bg-emerald-50 border-emerald-300 text-emerald-700"
          : "bg-white border-[#1a1a1f]/15 text-[#1a1a1f]/70 hover:border-[#232369]/40 hover:text-[#232369] disabled:opacity-40 disabled:cursor-not-allowed")
      }
    >
      {ok ? <Check size={12} /> : <Copy size={12} />}
      <span>{ok ? "Copied" : label}</span>
    </button>
  );
}

export default function NotificationEmailView() {
  // --- Roster state ---
  const [depts, setDepts] = useState([]);
  const [selectedDept, setSelectedDept] = useState("");
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState({}); // email -> bool
  const [loadingRoster, setLoadingRoster] = useState(false);

  // --- Compose state ---
  const [fromAddr, setFromAddr] = useState(DEFAULT_FROM);
  const [ccAddr, setCcAddr]     = useState(DEFAULT_CC);
  const [customBcc, setCustomBcc] = useState("");   // free-text extra recipients
  const [subject, setSubject]   = useState("");
  const [body, setBody]         = useState("");

  // --- Import state ---
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState(null);

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
      // Auto-select every visible employee when the dept changes.
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

  // --- Derived recipient string ---
  // Split custom-BCC on commas / newlines / semicolons, trim, drop empties &
  // anything without an "@", lowercase for a case-insensitive dedupe.
  const customEmails = useMemo(() => {
    return customBcc
      .split(/[,\n;]+/)
      .map((s) => s.trim())
      .filter((s) => s && s.includes("@"));
  }, [customBcc]);

  const bccList = useMemo(() => {
    const seen = new Set();
    const out = [];
    const rosterPicked = employees.filter((e) => selected[e.email]).map((e) => e.email);
    for (const em of [...rosterPicked, ...customEmails]) {
      const key = em.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(em);
    }
    return out;
  }, [employees, selected, customEmails]);
  const bccString = bccList.join(", ");
  const rosterSelectedCount = useMemo(
    () => employees.filter((e) => selected[e.email]).length,
    [employees, selected]
  );
  const totalCount = bccList.length;

  const toggleAll = (checked) => {
    const s = {};
    employees.forEach((e) => { s[e.email] = checked; });
    setSelected(s);
  };

  // --- Gmail deep-link ---
  const gmailUrl = useMemo(() => {
    if (!bccList.length) return "";
    const p = new URLSearchParams();
    p.set("view", "cm");
    p.set("fs", "1");
    if (fromAddr) p.set("to", fromAddr);
    if (ccAddr)   p.set("cc", ccAddr);
    p.set("bcc", bccString);
    if (subject)  p.set("su", subject);
    if (body)     p.set("body", body);
    return `https://mail.google.com/mail/?${p.toString()}`;
  }, [bccList.length, fromAddr, ccAddr, bccString, subject, body]);

  // --- mailto: fallback (opens default mail client) ---
  const mailtoUrl = useMemo(() => {
    if (!bccList.length) return "";
    const p = new URLSearchParams();
    if (ccAddr)  p.set("cc",  ccAddr);
    p.set("bcc", bccString);
    if (subject) p.set("subject", subject);
    if (body)    p.set("body", body);
    return `mailto:${encodeURIComponent(fromAddr)}?${p.toString()}`;
  }, [bccList.length, fromAddr, ccAddr, bccString, subject, body]);

  // --- Roster upload ---
  const onImport = async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";  // allow re-selecting the same file
    if (!file) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      // apiFetch adds CSRF header; skip Content-Type so browser sets multipart boundary.
      const res = await fetch(`${API}/employees/import`, {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRF-Token": (document.cookie.match(/hrcert_csrf=([^;]+)/) || [])[1] || "",
        },
        body: fd,
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.detail || `HTTP ${res.status}`);
      setImportMsg({ kind: "ok", text: `Roster replaced — ${j.inserted} employees imported.` });
      await loadDepartments();
      if (selectedDept) await loadEmployees(selectedDept);
    } catch (e) {
      setImportMsg({ kind: "err", text: e.message || "Upload failed." });
    } finally {
      setImporting(false);
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
            Compose a departmental notification. This app does not send —
            copy the recipients or open Gmail to review and send yourself.
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
              type="file"
              accept=".xlsx"
              disabled={importing}
              onChange={onImport}
              className="hidden"
              data-testid="notif-upload-input"
            />
          </label>
          <button
            type="button"
            onClick={() => { loadDepartments(); if (selectedDept) loadEmployees(selectedDept); }}
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-white border border-[#1a1a1f]/15 text-[#1a1a1f]/75 hover:text-[#232369] hover:border-[#232369]/40 transition-colors"
            data-testid="notif-refresh-btn"
          >
            <RefreshCw size={13} />
            <span>Refresh</span>
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

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-6">
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
              <option key={d.name} value={d.name}>
                {d.name} ({d.count})
              </option>
            ))}
          </select>

          <div className="mt-4 flex items-center justify-between gap-2">
            <div className="text-xs text-[#1a1a1f]/60 inline-flex items-center gap-1.5">
              <Users size={13} />
              <span data-testid="notif-selected-count">
                {rosterSelectedCount} of {employees.length} selected
              </span>
            </div>
            {employees.length > 0 && (
              <div className="flex items-center gap-2 text-[11px]">
                <button
                  type="button"
                  onClick={() => toggleAll(true)}
                  data-testid="notif-select-all"
                  className="text-[#232369] hover:underline"
                >
                  Select all
                </button>
                <span className="text-[#1a1a1f]/25">·</span>
                <button
                  type="button"
                  onClick={() => toggleAll(false)}
                  data-testid="notif-select-none"
                  className="text-[#1a1a1f]/60 hover:text-[#232369] hover:underline"
                >
                  Clear
                </button>
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
                <label
                  key={e.email}
                  className="flex items-start gap-3 px-3 py-2 hover:bg-[#f6f4ef]/60 cursor-pointer"
                >
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
        </section>

        {/* RIGHT — compose + copy fields */}
        <section className="bg-white rounded-xl border border-[#1a1a1f]/10 p-5 space-y-4">
          {/* From */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
                From / To (your address)
              </label>
              <CopyButton text={fromAddr} testid="notif-copy-from" />
            </div>
            <input
              type="text"
              value={fromAddr}
              onChange={(e) => setFromAddr(e.target.value)}
              data-testid="notif-from"
              className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
            />
            <p className="mt-1 text-[11px] text-[#1a1a1f]/50">
              Put your own email here — Gmail will reply-to yourself when the BCC list opens.
            </p>
          </div>

          {/* CC */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
                CC (owners)
              </label>
              <CopyButton text={ccAddr} testid="notif-copy-cc" />
            </div>
            <input
              type="text"
              value={ccAddr}
              onChange={(e) => setCcAddr(e.target.value)}
              data-testid="notif-cc"
              placeholder="Comma-separated emails"
              className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
            />
          </div>

          {/* BCC (generated + custom) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
                BCC — {totalCount} recipient{totalCount === 1 ? "" : "s"}
                {customEmails.length > 0 && (
                  <span className="ml-1.5 font-normal text-[#1a1a1f]/50 normal-case">
                    ({rosterSelectedCount} roster + {customEmails.length} custom)
                  </span>
                )}
              </label>
              <div className="flex items-center gap-2">
                <CopyButton text={bccString} label="Copy list" testid="notif-copy-bcc" />
                {bccString && (
                  <button
                    type="button"
                    onClick={() => { toggleAll(false); setCustomBcc(""); }}
                    className="inline-flex items-center gap-1 text-[11px] text-[#1a1a1f]/60 hover:text-rose-600"
                    data-testid="notif-clear-bcc"
                    title="Deselect all + clear custom emails"
                  >
                    <Trash2 size={11} /> Clear
                  </button>
                )}
              </div>
            </div>

            {/* Free-text custom-BCC input — add anyone outside the roster */}
            <textarea
              value={customBcc}
              onChange={(e) => setCustomBcc(e.target.value)}
              rows={2}
              data-testid="notif-custom-bcc"
              placeholder="Custom emails (comma, newline, or semicolon separated) — e.g. legal@blubridge.com, external@partner.com"
              className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15 resize-none mb-2"
            />

            {/* Read-only preview of the final merged BCC list */}
            <textarea
              readOnly
              aria-readonly="true"
              value={bccString}
              rows={4}
              data-testid="notif-bcc"
              placeholder="Select employees on the left, or add custom emails above…"
              className="w-full rounded-md border border-[#1a1a1f]/15 bg-[#f6f4ef]/50 px-3 py-2 text-[12px] font-mono text-[#1a1a1f]/80 focus:outline-none resize-none break-all"
            />
          </div>

          {/* Subject */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
                Subject
              </label>
              <CopyButton text={subject} testid="notif-copy-subject" />
            </div>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              data-testid="notif-subject"
              placeholder="e.g. Team update — July release"
              className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
            />
          </div>

          {/* Body */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
                Message
              </label>
              <CopyButton text={body} testid="notif-copy-body" />
            </div>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={8}
              data-testid="notif-body"
              placeholder="Type the notification content…"
              className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
            />
          </div>

          {/* Actions */}
          <div className="pt-2 border-t border-[#1a1a1f]/5 flex flex-wrap items-center gap-2">
            <a
              href={gmailUrl || "#"}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => { if (!gmailUrl) e.preventDefault(); }}
              data-testid="notif-open-gmail"
              className={
                "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors " +
                (gmailUrl
                  ? "bg-[#232369] text-white hover:bg-[#1a1a4d]"
                  : "bg-[#1a1a1f]/10 text-[#1a1a1f]/40 cursor-not-allowed pointer-events-none")
              }
            >
              <Send size={14} />
              <span>Open in Gmail</span>
              {gmailUrl && <ExternalLink size={12} />}
            </a>
            <a
              href={mailtoUrl || "#"}
              onClick={(e) => { if (!mailtoUrl) e.preventDefault(); }}
              data-testid="notif-open-mailto"
              className={
                "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium border transition-colors " +
                (mailtoUrl
                  ? "border-[#1a1a1f]/15 text-[#1a1a1f]/75 hover:text-[#232369] hover:border-[#232369]/40"
                  : "border-[#1a1a1f]/10 text-[#1a1a1f]/35 cursor-not-allowed pointer-events-none")
              }
            >
              Open in default mail client
            </a>
            <span className="text-[11px] text-[#1a1a1f]/50 ml-auto">
              Gmail limits URLs to ~8 KB — for larger rosters copy the BCC field manually.
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}
