import { useCallback, useMemo, useRef, useState } from "react";
import {
  Upload, FileText, Loader2, Download, Printer, Eye, ZoomIn, ZoomOut,
  Maximize2, ChevronUp, ChevronDown, AlertTriangle,
} from "lucide-react";
import { apiFetch, apiJSON, API } from "@/lib/api";
import RichTextEditor from "../components/RichTextEditor";

const PAGE_W = 595.276;   // A4 pt — preview images keep this aspect

export default function DocView() {
  const [docName, setDocName] = useState("");
  const [html, setHtml] = useState("");
  const [rteKey, setRteKey] = useState(0);
  const [includeSig, setIncludeSig] = useState(true);
  const [sigStyle, setSigStyle] = useState("seal");
  const [sigLeft, setSigLeft] = useState({ label: "RECIPIENT / ADVISOR", name: "", title: "Director" });
  const [sigRight, setSigRight] = useState({ label: "BLUBRIDGE TECHNOLOGIES PRIVATE LIMITED", name: "", title: "Director" });
  const [sigDate, setSigDate] = useState(() => {
    const d = new Date();
    return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
  });

  const [importing, setImporting] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);
  const [pages, setPages] = useState([]);
  const [zoom, setZoom] = useState(0.9);
  const [current, setCurrent] = useState(0);

  const scrollRef = useRef(null);
  const pageRefs = useRef([]);
  const fileRef = useRef(null);

  const plainLength = useMemo(
    () => html.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").trim().length,
    [html]
  );
  const canRender = plainLength > 0 && !rendering;

  const onImport = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const csrf = document.cookie.match(/hrcert_csrf=([^;]*)/);
      const r = await fetch(`${API}/doc/import`, {
        method: "POST",
        credentials: "include",
        headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf[1]) } : {},
        body: fd,
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
      setHtml(j.html || "");
      setRteKey((k) => k + 1);
      if (!docName) setDocName((file.name || "").replace(/\.[^.]+$/, ""));
      setPages([]);
    } catch (err) {
      setError(err.message || "Could not import that file.");
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, [docName]);

  const sigPayload = useMemo(() => ({
    include_signature: includeSig,
    signature_style: sigStyle,
    sig_left: sigLeft,
    sig_right: sigRight,
    sig_date: sigDate,
  }), [includeSig, sigStyle, sigLeft, sigRight, sigDate]);

  const onPreview = useCallback(async () => {
    setRendering(true); setError(null);
    try {
      const j = await apiJSON("/doc/preview", {
        method: "POST",
        body: { name: docName, html, ...sigPayload },
      });
      setPages(j.pages || []);
      setCurrent(0);
      pageRefs.current = [];
    } catch (err) {
      setError(err.message || "Could not render the preview.");
      setPages([]);
    } finally {
      setRendering(false);
    }
  }, [docName, html, sigPayload]);

  const getPdf = useCallback(async () => {
    const res = await apiFetch("/doc/generate", {
      method: "POST",
      body: { name: docName, html, ...sigPayload },
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { const j = await res.json(); detail = j.detail || detail; } catch { /* ignore */ }
      throw new Error(detail);
    }
    const disp = res.headers.get("Content-Disposition") || "";
    const m = disp.match(/filename="?([^"]+)"?/);
    return { blob: await res.blob(), filename: m ? m[1] : "BluBridge_Document.pdf" };
  }, [docName, html, sigPayload]);

  const onDownload = useCallback(async () => {
    setDownloading(true); setError(null);
    try {
      const { blob, filename } = await getPdf();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Download failed.");
    } finally {
      setDownloading(false);
    }
  }, [getPdf]);

  const onPrint = useCallback(async () => {
    setError(null);
    try {
      const { blob } = await getPdf();
      const url = URL.createObjectURL(blob);
      const w = window.open(url, "_blank", "noopener,noreferrer");
      if (w) setTimeout(() => { try { w.print(); } catch { /* user can print manually */ } }, 900);
    } catch (err) {
      setError(err.message || "Print failed.");
    }
  }, [getPdf]);

  const goto = (idx) => {
    const clamped = Math.min(Math.max(idx, 0), pages.length - 1);
    setCurrent(clamped);
    pageRefs.current[clamped]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const fitWidth = () => {
    const w = scrollRef.current?.clientWidth || PAGE_W;
    setZoom(Math.max(0.3, Math.min(2, (w - 40) / PAGE_W)));
  };

  return (
    <main className="max-w-6xl mx-auto px-6 py-10" data-testid="doc-view">
      <div className="flex items-center gap-2 mb-1">
        <FileText size={18} className="text-[#232369]" />
        <h1 className="text-2xl font-semibold">Doc</h1>
      </div>
      <p className="text-sm text-[#1a1a1f]/60 mb-6">
        Type or upload content — it is formatted onto the official BluBridge letterhead,
        paragraph-safe page breaks included.
      </p>

      <section className="bg-white rounded-xl border border-[#1a1a1f]/10 p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr] gap-4">
          <div>
            <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
              Document name
            </label>
            <input
              type="text"
              value={docName}
              onChange={(e) => setDocName(e.target.value)}
              data-testid="doc-name"
              placeholder="e.g. Employment Confirmation Letter"
              className="mt-1 w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#232369]/60 focus:ring-2 focus:ring-[#232369]/15"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
              Upload document
            </label>
            <div className="mt-1">
              <input
                ref={fileRef}
                type="file"
                accept=".docx,.pdf,.txt"
                onChange={onImport}
                disabled={importing}
                data-testid="doc-upload"
                className="hidden"
                id="doc-upload-input"
              />
              <label
                htmlFor="doc-upload-input"
                className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-md border border-[#1a1a1f]/15 bg-white hover:border-[#232369]/50 cursor-pointer"
              >
                {importing
                  ? (<><Loader2 size={14} className="animate-spin" /> Reading…</>)
                  : (<><Upload size={14} /> Choose .docx / .pdf / .txt</>)}
              </label>
            </div>
          </div>
        </div>

        <div>
          <label className="text-xs font-semibold text-[#1a1a1f]/70 uppercase tracking-wide">
            Document editor
          </label>
          <div className="mt-1">
            <RichTextEditor
              value={html}
              resetKey={rteKey}
              onChange={setHtml}
              testid="doc-rte"
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeSig}
            onChange={(e) => setIncludeSig(e.target.checked)}
            data-testid="doc-include-signature"
            className="w-4 h-4 accent-[#232369]"
          />
          Include Company Seal &amp; Director Signature
        </label>

        {includeSig && (
          <div className="rounded-md border border-[#1a1a1f]/10 bg-[#f6f4ef] p-3 space-y-3">
            <div className="flex items-center gap-5 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="radio" name="sig-style" value="seal"
                  checked={sigStyle === "seal"}
                  onChange={() => setSigStyle("seal")}
                  data-testid="doc-sig-style-seal"
                  className="w-4 h-4 accent-[#232369]"
                />
                Scanned seal &amp; signature
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio" name="sig-style" value="table"
                  checked={sigStyle === "table"}
                  onChange={() => setSigStyle("table")}
                  data-testid="doc-sig-style-table"
                  className="w-4 h-4 accent-[#232369]"
                />
                Two-column signature block
              </label>
            </div>

            {sigStyle === "table" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[["left", sigLeft, setSigLeft], ["right", sigRight, setSigRight]].map(
                  ([side, val, set]) => (
                    <div key={side} className="space-y-2">
                      <input
                        type="text" value={val.label}
                        onChange={(e) => set({ ...val, label: e.target.value })}
                        data-testid={`doc-sig-${side}-label`}
                        placeholder="Party heading"
                        className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm"
                      />
                      <input
                        type="text" value={val.name}
                        onChange={(e) => set({ ...val, name: e.target.value })}
                        data-testid={`doc-sig-${side}-name`}
                        placeholder="Name"
                        className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm"
                      />
                      <input
                        type="text" value={val.title}
                        onChange={(e) => set({ ...val, title: e.target.value })}
                        data-testid={`doc-sig-${side}-title`}
                        placeholder="Title"
                        className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm"
                      />
                    </div>
                  )
                )}
                <input
                  type="text" value={sigDate}
                  onChange={(e) => setSigDate(e.target.value)}
                  data-testid="doc-sig-date"
                  placeholder="Date (dd/mm/yyyy)"
                  className="w-full md:w-48 rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm"
                />
              </div>
            )}
          </div>
        )}

        {error && (
          <div
            data-testid="doc-error"
            className="text-xs rounded-md px-3 py-2 border bg-red-50 border-red-200 text-red-700 flex items-start gap-2"
          >
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {error}
          </div>
        )}

        <div className="flex items-center justify-between gap-3 flex-wrap">
          <span className="text-[11px] text-[#1a1a1f]/45">
            A4 · Arial 11pt · content stays between the header rule and the footer
          </span>
          <button
            type="button"
            onClick={onPreview}
            disabled={!canRender}
            data-testid="doc-generate-preview"
            className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wider px-5 py-2.5 rounded-md bg-[#3d4a78] text-white hover:bg-[#2c3661] disabled:bg-[#1a1a1f]/25 disabled:cursor-not-allowed"
          >
            {rendering
              ? (<><Loader2 size={14} className="animate-spin" /> Rendering…</>)
              : (<><Eye size={14} /> Generate preview</>)}
          </button>
        </div>
      </section>

      {pages.length > 0 && (
        <section className="mt-6 bg-white rounded-xl border border-[#1a1a1f]/10 overflow-hidden" data-testid="doc-preview">
          <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-b border-[#1a1a1f]/10 bg-[#f6f4ef]">
            <div className="flex items-center gap-2 text-xs text-[#1a1a1f]/70">
              <span className="font-semibold uppercase tracking-wider">Document preview</span>
              <span data-testid="doc-page-count">
                Page {current + 1} of {pages.length}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => goto(current - 1)} disabled={current === 0}
                data-testid="doc-prev-page" title="Previous page"
                className="w-8 h-8 grid place-items-center rounded-md hover:bg-white disabled:opacity-35">
                <ChevronUp size={15} />
              </button>
              <button type="button" onClick={() => goto(current + 1)} disabled={current >= pages.length - 1}
                data-testid="doc-next-page" title="Next page"
                className="w-8 h-8 grid place-items-center rounded-md hover:bg-white disabled:opacity-35">
                <ChevronDown size={15} />
              </button>
              <span className="w-px h-5 bg-[#1a1a1f]/10 mx-1" />
              <button type="button" onClick={() => setZoom((z) => Math.max(0.3, z - 0.15))}
                data-testid="doc-zoom-out" title="Zoom out"
                className="w-8 h-8 grid place-items-center rounded-md hover:bg-white">
                <ZoomOut size={15} />
              </button>
              <span className="text-xs w-10 text-center tabular-nums" data-testid="doc-zoom-level">
                {Math.round(zoom * 100)}%
              </span>
              <button type="button" onClick={() => setZoom((z) => Math.min(2, z + 0.15))}
                data-testid="doc-zoom-in" title="Zoom in"
                className="w-8 h-8 grid place-items-center rounded-md hover:bg-white">
                <ZoomIn size={15} />
              </button>
              <button type="button" onClick={fitWidth}
                data-testid="doc-fit-width" title="Fit width"
                className="w-8 h-8 grid place-items-center rounded-md hover:bg-white">
                <Maximize2 size={15} />
              </button>
            </div>
          </div>

          <div
            ref={scrollRef}
            className="max-h-[70vh] overflow-auto bg-[#e8e4dc] px-4 py-5"
          >
            <div className="flex flex-col items-center gap-5">
              {pages.map((src, i) => (
                <img
                  key={i}
                  ref={(el) => { pageRefs.current[i] = el; }}
                  src={src}
                  alt={`Page ${i + 1}`}
                  data-testid={`doc-preview-page-${i + 1}`}
                  onClick={() => setCurrent(i)}
                  style={{ width: `${PAGE_W * zoom}px` }}
                  className="shadow-lg bg-white"
                />
              ))}
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#1a1a1f]/10 bg-[#f6f4ef]">
            <button
              type="button" onClick={onPrint} data-testid="doc-print"
              className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-md border border-[#1a1a1f]/15 bg-white hover:border-[#232369]/50"
            >
              <Printer size={14} /> Print
            </button>
            <button
              type="button" onClick={onDownload} disabled={downloading} data-testid="doc-download"
              className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wider px-5 py-2 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {downloading
                ? (<><Loader2 size={14} className="animate-spin" /> Preparing…</>)
                : (<><Download size={14} /> Download PDF</>)}
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
