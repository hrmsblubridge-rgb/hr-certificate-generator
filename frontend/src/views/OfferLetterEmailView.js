import { useState, useEffect, useRef } from "react";
import { Loader2, FileText, Download, ExternalLink, X, Pencil, Check } from "lucide-react";
import { apiJSON } from "@/lib/api";

// ---- shared field components --------------------------------------------
function Field({ label, required, children, testid }) {
  return (
    <label className="block mb-4" data-testid={testid ? `${testid}-wrap` : undefined}>
      <span className="block text-sm font-semibold text-[#1a1a1f] mb-1.5">
        {label}{required && <span className="text-red-600 ml-0.5" aria-label="required">*</span>}
      </span>
      {children}
    </label>
  );
}

const inputCls =
  "w-full bg-[#f6f4ef] border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-md px-3 py-2.5 text-sm text-[#1a1a1f] placeholder:text-[#1a1a1f]/35 transition-colors";
const selectArrow =
  "appearance-none bg-no-repeat bg-[right_0.75rem_center] pr-9";
const selectArrowStyle = {
  backgroundImage:
    "url(\"data:image/svg+xml;charset=US-ASCII,%3Csvg width='12' height='8' viewBox='0 0 12 8' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%231a1a1f' stroke-opacity='0.55' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
};

// ---- preview modal ------------------------------------------------------
function PreviewModal({ html: initialHtml, filename, onClose }) {
  // HTML can be MUTATED via the inline edit-content feature, so we hold it
  // in state. Download / Open / Re-render all read the latest value.
  const [html, setHtml] = useState(initialHtml);
  const [editing, setEditing] = useState(false);
  const iframeRef = useRef(null);

  // Toggle the iframe body's contenteditable when entering / leaving edit
  // mode. Reads back the edited document on Save so subsequent actions use
  // the modified HTML.
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const apply = () => {
      const doc = iframe.contentDocument;
      if (!doc || !doc.body) return;
      doc.body.contentEditable = editing ? "true" : "false";
      doc.body.style.outline = editing ? "2px dashed #232369" : "";
      doc.body.style.outlineOffset = editing ? "-2px" : "";
      doc.body.style.cursor = editing ? "text" : "";
      if (editing) doc.body.focus();
    };
    if (iframe.contentDocument?.readyState === "complete") apply();
    else iframe.addEventListener("load", apply, { once: true });
    return () => iframe.removeEventListener("load", apply);
  }, [editing, html]);

  const onToggleEdit = () => {
    if (editing) {
      // Saving — capture the edited HTML out of the iframe and strip the
      // visual edit affordance so it doesn't bleed into the downloaded copy.
      const doc = iframeRef.current?.contentDocument;
      if (doc?.documentElement) {
        doc.body.style.outline = "";
        doc.body.style.outlineOffset = "";
        doc.body.style.cursor = "";
        doc.body.contentEditable = "false";
        setHtml("<!DOCTYPE html>" + doc.documentElement.outerHTML);
      }
    }
    setEditing((v) => !v);
  };

  const open = () => {
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    // URL.revokeObjectURL is intentionally NOT called immediately — the new
    // tab needs the blob to remain reachable. Browsers garbage-collect on tab
    // close.
  };
  const download = () => {
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename || "Offer_Letter.html";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };
  return (
    <div
      data-testid="oe-preview-modal"
      className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm grid place-items-center p-3 sm:p-6"
    >
      <div className="w-full max-w-5xl h-[88vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#1a1a1f]/10 bg-[#f6f4ef] gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#1a1a1f]">
            <FileText size={16} className="text-[#232369]" />
            Offer Letter preview
            {editing && (
              <span
                data-testid="oe-edit-indicator"
                className="ml-2 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#232369]/10 text-[#232369]"
              >
                editing
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              data-testid="oe-preview-edit"
              onClick={onToggleEdit}
              title={editing ? "Save edits" : "Click to edit content"}
              className={
                "inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border transition-colors " +
                (editing
                  ? "bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700"
                  : "border-[#1a1a1f]/15 hover:bg-white text-[#1a1a1f]")
              }
            >
              {editing
                ? (<><Check size={13} /> Save</>)
                : (<><Pencil size={13} /> Edit content</>)}
            </button>
            <button
              data-testid="oe-preview-open"
              onClick={open}
              disabled={editing}
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border border-[#1a1a1f]/15 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ExternalLink size={13} /> Open in new tab
            </button>
            <button
              data-testid="oe-preview-download"
              onClick={download}
              disabled={editing}
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-[#232369] text-white hover:bg-[#1a1a55] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Download size={13} /> Download HTML
            </button>
            <button
              data-testid="oe-preview-close"
              onClick={onClose}
              className="ml-1 p-1.5 rounded-full text-[#1a1a1f]/55 hover:text-[#1a1a1f] hover:bg-white"
              aria-label="Close preview"
            >
              <X size={16} />
            </button>
          </div>
        </div>
        <iframe
          ref={iframeRef}
          data-testid="oe-preview-iframe"
          title="Offer Letter Preview"
          srcDoc={html}
          className="flex-1 w-full border-0 bg-white"
          sandbox="allow-same-origin"
        />
        {editing && (
          <div
            data-testid="oe-edit-help"
            className="px-5 py-2 text-[11px] text-[#1a1a1f]/70 bg-[#fff8e6] border-t border-amber-200"
          >
            Click anywhere in the preview to edit. Press <strong>Save</strong> when done &mdash; Download and Open in new tab will then use your edited copy.
          </div>
        )}
      </div>
    </div>
  );
}

// ---- main view ----------------------------------------------------------
const TITLES = ["Mr.", "Ms.", "Mrs.", "Dr."];
const DESIGNATIONS = [
  "Research Scientist",
  "AI Research Analyst",
  "AI Research Intern",
  "Software Engineer",
  "Senior Software Engineer",
  "Data Scientist",
  "Data Analyst",
  "Product Manager",
  "HR Executive",
];

function isoDateToday() {
  return new Date().toISOString().slice(0, 10);
}
function isoToDotted(iso) {
  // 2026-06-25 -> 25.06.2026
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso || "";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

export default function OfferLetterEmailView() {
  const [form, setForm] = useState({
    title: "",
    name: "",
    email: "",
    phone: "",
    cur_date_iso: isoDateToday(),
    date_iso: "",
    reference_number: "CHN/2025/Res/1-",
    designation: "",
    address_line1: "",
    address_line2: "",
    address_line3: "",
    mode: "standard",
    ctc_yearly: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null); // { html, filename }

  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.value });
    if (error) setError("");
  };

  const allFilled =
    form.title &&
    form.name.trim() &&
    form.email.trim() &&
    form.phone.trim() &&
    form.cur_date_iso &&
    form.date_iso &&
    form.reference_number.trim() &&
    form.designation &&
    form.address_line1.trim() &&
    (form.mode !== "standard" || (form.ctc_yearly && Number(form.ctc_yearly) > 0));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setError("");
    if (!allFilled) {
      setError("Please fill all required fields.");
      return;
    }
    if (form.mode === "customized") {
      setError("Customized mode arrives in the next iteration. Use Standard for now.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        title:            form.title,
        name:             form.name.trim(),
        email:            form.email.trim(),
        phone:            form.phone.trim(),
        cur_date:         isoToDotted(form.cur_date_iso),
        date:             isoToDotted(form.date_iso),
        reference_number: form.reference_number.trim(),
        designation:      form.designation,
        address_line1:    form.address_line1.trim(),
        address_line2:    form.address_line2.trim(),
        address_line3:    form.address_line3.trim(),
        mode:             "standard",
        ctc_yearly:       Number(form.ctc_yearly),
      };
      const { html, filename } = await apiJSON("/offer-email/preview", {
        method: "POST",
        body: payload,
      });
      setPreview({ html, filename });
    } catch (e2) {
      setError(e2.message || "Failed to render offer letter.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="max-w-6xl mx-auto px-6 py-10" data-testid="offer-email-view">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55 mb-1">
        Offer Letter — Email Edition
      </div>
      <h2 className="text-2xl font-semibold text-[#1a1a1f] mb-6">Offer Letter Form</h2>

      <form
        onSubmit={onSubmit}
        autoComplete="off"
        data-testid="offer-email-form"
        className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-2 rounded-xl border border-[#1a1a1f]/10 bg-white p-6 sm:p-8"
      >
        {/* LEFT column */}
        <div>
          <Field label="Title" required>
            <select
              data-testid="oe-title"
              value={form.title}
              onChange={set("title")}
              className={`${inputCls} ${selectArrow}`}
              style={selectArrowStyle}
            >
              <option value="" disabled>Select</option>
              {TITLES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>

          <Field label="Name" required>
            <input
              data-testid="oe-name"
              type="text"
              value={form.name}
              onChange={set("name")}
              className={inputCls}
            />
          </Field>

          <Field label="Email ID" required>
            <input
              data-testid="oe-email"
              type="email"
              value={form.email}
              onChange={set("email")}
              className={inputCls}
            />
          </Field>

          <Field label="Phone" required>
            <input
              data-testid="oe-phone"
              type="tel"
              value={form.phone}
              onChange={set("phone")}
              className={inputCls}
            />
          </Field>

          <Field label="Date (Letter)" required>
            <input
              data-testid="oe-cur-date"
              type="date"
              value={form.cur_date_iso}
              onChange={set("cur_date_iso")}
              className={inputCls}
            />
          </Field>

          <Field label="Joining Date" required>
            <input
              data-testid="oe-joining-date"
              type="date"
              value={form.date_iso}
              onChange={set("date_iso")}
              className={inputCls}
            />
          </Field>

          <Field label="Reference Number" required>
            <input
              data-testid="oe-ref-number"
              type="text"
              value={form.reference_number}
              onChange={set("reference_number")}
              placeholder="CHN/2025/Res/1-001"
              className={inputCls}
            />
          </Field>

          <Field label="Designation" required>
            <select
              data-testid="oe-designation"
              value={form.designation}
              onChange={set("designation")}
              className={`${inputCls} ${selectArrow}`}
              style={selectArrowStyle}
            >
              <option value="" disabled>Select</option>
              {DESIGNATIONS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </Field>

          <Field label="Address Line 1" required>
            <input
              data-testid="oe-addr1"
              type="text"
              value={form.address_line1}
              onChange={set("address_line1")}
              className={inputCls}
            />
          </Field>

          <Field label="Address Line 2">
            <input
              data-testid="oe-addr2"
              type="text"
              value={form.address_line2}
              onChange={set("address_line2")}
              className={inputCls}
            />
          </Field>

          <Field label="Address Line 3">
            <input
              data-testid="oe-addr3"
              type="text"
              value={form.address_line3}
              onChange={set("address_line3")}
              className={inputCls}
            />
          </Field>
        </div>

        {/* RIGHT column — compensation mode + CTC + submit */}
        <div className="md:border-l md:border-[#1a1a1f]/10 md:pl-10">
          <div className="space-y-3 mb-5">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                data-testid="oe-mode-standard"
                type="radio"
                name="oe-mode"
                value="standard"
                checked={form.mode === "standard"}
                onChange={set("mode")}
                className="accent-[#232369] w-4 h-4"
              />
              <span className="text-sm font-medium text-[#1a1a1f]">
                Standard (enter yearly CTC)
              </span>
            </label>
            <label className="flex items-center gap-3 cursor-not-allowed opacity-60">
              <input
                data-testid="oe-mode-customized"
                type="radio"
                name="oe-mode"
                value="customized"
                checked={form.mode === "customized"}
                onChange={set("mode")}
                className="accent-[#232369] w-4 h-4"
                disabled
              />
              <span className="text-sm font-medium text-[#1a1a1f]">
                Customized <span className="text-[#1a1a1f]/45">(next iteration)</span>
              </span>
            </label>
          </div>

          <Field label="CTC (Yearly)" required>
            <input
              data-testid="oe-ctc"
              type="number"
              min="1"
              step="1"
              value={form.ctc_yearly}
              onChange={set("ctc_yearly")}
              placeholder="e.g. 660000"
              className={inputCls}
              disabled={form.mode !== "standard"}
            />
          </Field>
          <p className="text-xs text-[#1a1a1f]/55 -mt-2 mb-5">
            Enter yearly CTC for Standard mode. Annexure-A line items scale
            proportionally from the reference template; Tier is auto-derived
            from the resulting Fixed Compensation.
          </p>

          {error && (
            <div
              data-testid="oe-error"
              className="mb-4 text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2"
            >
              {error}
            </div>
          )}

          {!allFilled && !error && (
            <div
              data-testid="oe-missing-hint"
              className="mb-3 text-xs text-[#1a1a1f]/65 bg-[#fff8e6] border border-amber-200 rounded-md px-3 py-2"
            >
              Fill all required fields (marked <span className="text-red-600 font-semibold">*</span>) to enable preview.
            </div>
          )}

          <button
            type="submit"
            disabled={!allFilled || busy}
            data-testid="oe-submit"
            className="w-full inline-flex items-center justify-center gap-2 rounded-md bg-[#3d4a78] hover:bg-[#2c3661] disabled:bg-[#1a1a1f]/25 disabled:cursor-not-allowed transition-colors text-white text-sm font-semibold tracking-wider uppercase px-5 py-3.5"
          >
            {busy ? (
              <><Loader2 size={16} className="animate-spin" /> Generating&hellip;</>
            ) : (
              <>Preview Offer</>
            )}
          </button>
        </div>
      </form>

      {preview && (
        <PreviewModal
          html={preview.html}
          filename={preview.filename}
          onClose={() => setPreview(null)}
        />
      )}
    </main>
  );
}
