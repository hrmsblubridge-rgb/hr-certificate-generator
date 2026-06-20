import { useEffect, useState, useCallback } from "react";
import {
  Download, Trash2, RefreshCw, FileText, FileSignature, FileCheck,
  Search, Clock, Loader2,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const TYPE_META = {
  certificate: { label: "Internship Certificate", icon: FileText,      color: "#232369" },
  offer:       { label: "Offer Letter",            icon: FileSignature, color: "#1e6f59" },
  ack:         { label: "Acknowledgement",         icon: FileCheck,     color: "#7a4119" },
};

const FILTERS = [
  { id: "",            label: "All documents"   },
  { id: "certificate", label: "Certificates"    },
  { id: "offer",       label: "Offer Letters"   },
  { id: "ack",         label: "Acknowledgements"},
];

function formatBytes(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function formatSummary(type, summary) {
  if (!summary) return "";
  if (type === "certificate")
    return `${summary.designation} · ${summary.commenced} – ${summary.concluded}`;
  if (type === "offer")
    return `Ref ${summary.ref_code} · ${summary.date} · ${summary.designation} · ₹${summary.salary_amount}/-`;
  if (type === "ack")
    return `${summary.date} · ${summary.marksheet_type} Mark Sheet`;
  return JSON.stringify(summary);
}

export default function HistoryView() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState("");
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterType) params.set("type", filterType);
      if (query.trim()) params.set("q", query.trim());
      const res = await fetch(`${API}/history?${params.toString()}`);
      const data = await res.json();
      setItems(data.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, [filterType, query]);

  useEffect(() => { load(); }, [load]);

  const onDownload = (entry) => {
    window.open(`${API}/history/${entry.id}/download`, "_blank");
  };

  const onDelete = async (entry) => {
    if (!confirm(`Remove "${entry.filename}" from history?`)) return;
    await fetch(`${API}/history/${entry.id}`, { method: "DELETE" });
    load();
  };

  return (
    <main className="max-w-6xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-5 gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">
            Generated documents
          </h2>
          <p className="text-sm text-[#1a1a1f]/55 mt-0.5">
            Every certificate, offer letter and acknowledgement generated is
            stored here for one-click re-download.
          </p>
        </div>
        <button
          data-testid="history-refresh-btn"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-2 text-sm font-medium px-3 py-2 rounded-full border border-[#1a1a1f]/15 hover:border-[#1a1a1f]/40 transition-colors"
        >
          {loading
            ? <Loader2 size={14} className="animate-spin" />
            : <RefreshCw size={14} />}
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        <div className="inline-flex items-center gap-1 bg-white border border-[#1a1a1f]/10 rounded-full p-1">
          {FILTERS.map((f) => {
            const active = filterType === f.id;
            return (
              <button
                key={f.id || "all"}
                data-testid={`history-filter-${f.id || "all"}`}
                onClick={() => setFilterType(f.id)}
                className={
                  "text-xs font-medium px-3.5 py-1.5 rounded-full transition-colors " +
                  (active
                    ? "bg-[#232369] text-white"
                    : "text-[#1a1a1f]/70 hover:text-[#1a1a1f]")
                }
              >
                {f.label}
              </button>
            );
          })}
        </div>
        <div className="flex-1 min-w-[200px] relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[#1a1a1f]/40"
          />
          <input
            data-testid="history-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name…"
            className="w-full pl-9 pr-3 py-2 bg-white border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-full text-sm transition-colors"
          />
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="py-20 text-center text-[#1a1a1f]/50">
          <Loader2 size={20} className="inline animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <div
          data-testid="history-empty"
          className="rounded-xl border border-dashed border-[#1a1a1f]/15 bg-white py-16 text-center text-[#1a1a1f]/50"
        >
          <Clock size={28} className="mx-auto mb-3 opacity-40" />
          No generated documents yet. Create one from the other tabs and it
          will appear here.
        </div>
      ) : (
        <ul data-testid="history-list" className="space-y-2">
          {items.map((entry) => {
            const meta = TYPE_META[entry.type] ||
              { label: entry.type, icon: FileText, color: "#1a1a1f" };
            const Icon = meta.icon;
            return (
              <li
                key={entry.id}
                data-testid={`history-item-${entry.id}`}
                className="flex items-center gap-4 rounded-xl border border-[#1a1a1f]/10 bg-white p-4 hover:border-[#1a1a1f]/25 transition-colors"
              >
                <div
                  className="w-10 h-10 rounded-md grid place-items-center shrink-0"
                  style={{ background: `${meta.color}14`, color: meta.color }}
                >
                  <Icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-sm font-medium truncate">
                      {entry.name}
                    </span>
                    <span
                      className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded font-medium"
                      style={{ background: `${meta.color}14`, color: meta.color }}
                    >
                      {meta.label}
                    </span>
                  </div>
                  <div className="text-xs text-[#1a1a1f]/55 mt-0.5 truncate">
                    {formatSummary(entry.type, entry.summary)}
                  </div>
                  <div className="text-[11px] text-[#1a1a1f]/45 mt-1 flex items-center gap-2">
                    <Clock size={11} />
                    {formatDate(entry.created_at)}
                    <span>·</span>
                    <span>{formatBytes(entry.size_bytes)}</span>
                  </div>
                </div>
                <button
                  data-testid={`history-download-${entry.id}`}
                  onClick={() => onDownload(entry)}
                  className="inline-flex items-center gap-1.5 rounded-full bg-[#232369] hover:bg-[#1a1a55] text-white text-xs font-medium px-3 py-2 transition-colors"
                  title="Download"
                >
                  <Download size={13} /> Download
                </button>
                <button
                  data-testid={`history-delete-${entry.id}`}
                  onClick={() => onDelete(entry)}
                  className="inline-flex items-center justify-center w-9 h-9 rounded-full text-[#1a1a1f]/45 hover:text-red-600 hover:bg-red-50 transition-colors"
                  title="Remove"
                >
                  <Trash2 size={14} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
