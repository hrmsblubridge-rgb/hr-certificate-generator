import { useState } from "react";
import { Loader2, FileText, Download, X } from "lucide-react";
import { apiFetch } from "@/lib/api";

// Reuse the SAME form UX from OfferLetterEmailView (Title/Name/Email/Phone/
// Letter Date/Joining Date/Ref Number/Designation/Address 1-3/CTC) but the
// PRIMARY ACTION here is to generate the .docx + .pdf for download — not
// the HTML email.

const inputCls =
  "w-full bg-[#f6f4ef] border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-md px-3 py-2.5 text-sm text-[#1a1a1f] placeholder:text-[#1a1a1f]/35 transition-colors";
const selectArrow = "appearance-none bg-no-repeat bg-[right_0.75rem_center] pr-9";
const selectArrowStyle = {
  backgroundImage:
    "url(\"data:image/svg+xml;charset=US-ASCII,%3Csvg width='12' height='8' viewBox='0 0 12 8' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%231a1a1f' stroke-opacity='0.55' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
};

const TITLES = ["Mr.", "Ms.", "Mrs.", "Dr."];
const DESIGNATIONS = [
  "Research Scientist", "AI Research Analyst", "AI Research Intern",
  "Software Engineer", "Senior Software Engineer", "Data Scientist",
  "Data Analyst", "Product Manager", "HR Executive",
];

function Field({ label, required, children }) {
  return (
    <label className="block mb-4">
      <span className="block text-sm font-semibold text-[#1a1a1f] mb-1.5">
        {label}{required && <span className="text-red-600 ml-0.5">*</span>}
      </span>
      {children}
    </label>
  );
}

// ISO yyyy-mm-dd → "08-June-2026" (matches the source-doc style exactly)
function isoToWordDate(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso || "";
  const months = ["January","February","March","April","May","June",
                  "July","August","September","October","November","December"];
  const [y, m, d] = iso.split("-");
  return `${d}-${months[parseInt(m,10)-1]}-${y}`;
}

function isoToday() { return new Date().toISOString().slice(0, 10); }

// Modal: preview PDF + DOCX/PDF download
function PreviewModal({ pdfBlobUrl, payload, filename, onClose }) {
  const [busy, setBusy] = useState(null); // 'docx' | 'pdf' | null

  const downloadBlob = (blob, name) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  const download = async (kind) => {
    if (busy) return;
    setBusy(kind);
    try {
      const res = await apiFetch(`/offer-appointment/${kind}`, {
        method: "POST",
        body: payload,
      });
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { const j = await res.json(); msg = j.detail || msg; } catch { /* keep msg */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      downloadBlob(blob, `${filename}.${kind}`);
    } catch (e) {
      alert(`Download failed: ${e.message}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      data-testid="oa-preview-modal"
      className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm grid place-items-center p-3 sm:p-6"
    >
      <div className="w-full max-w-5xl h-[88vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#1a1a1f]/10 bg-[#f6f4ef] gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#1a1a1f]">
            <FileText size={16} className="text-[#232369]" />
            Offer of Appointment — preview
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              data-testid="oa-download-docx"
              onClick={() => download("docx")}
              disabled={busy !== null}
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border border-[#1a1a1f]/15 hover:bg-white disabled:opacity-50"
            >
              {busy === "docx" ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
              Download DOCX
            </button>
            <button
              data-testid="oa-download-pdf"
              onClick={() => download("pdf")}
              disabled={busy !== null}
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-[#232369] text-white hover:bg-[#1a1a55] disabled:opacity-50"
            >
              {busy === "pdf" ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
              Download PDF
            </button>
            <button
              data-testid="oa-preview-close"
              onClick={onClose}
              className="ml-1 p-1.5 rounded-full text-[#1a1a1f]/55 hover:text-[#1a1a1f] hover:bg-white"
              aria-label="Close preview"
            >
              <X size={16} />
            </button>
          </div>
        </div>
        <iframe
          data-testid="oa-preview-iframe"
          title="Offer of Appointment Preview"
          src={pdfBlobUrl}
          className="flex-1 w-full border-0 bg-white"
        />
      </div>
    </div>
  );
}

export default function OfferOfAppointmentView() {
  const [form, setForm] = useState({
    title: "", name: "", email: "", phone: "",
    cur_date_iso: isoToday(),
    date_iso: "",
    reference_number: "CHN/2025/Res/1-",
    designation: "",
    address_line1: "", address_line2: "", address_line3: "",
    ctc_yearly: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);

  const set = (k) => (e) => { setForm({ ...form, [k]: e.target.value }); if (error) setError(""); };
  const allFilled =
    form.title && form.name.trim() && form.email.trim() && form.phone.trim() &&
    form.cur_date_iso && form.date_iso && form.reference_number.trim() &&
    form.designation && form.address_line1.trim() &&
    form.ctc_yearly && Number(form.ctc_yearly) > 0;

  const buildPayload = () => ({
    title:            form.title,
    name:             form.name.trim(),
    email:            form.email.trim(),
    phone:            form.phone.trim(),
    cur_date:         isoToWordDate(form.cur_date_iso),
    date:             isoToWordDate(form.date_iso),
    reference_number: form.reference_number.trim(),
    designation:      form.designation,
    address_line1:    form.address_line1.trim(),
    address_line2:    form.address_line2.trim(),
    address_line3:    form.address_line3.trim(),
    ctc_yearly:       Number(form.ctc_yearly),
  });

  const onPreview = async (e) => {
    e.preventDefault();
    if (busy || !allFilled) return;
    setBusy(true); setError("");
    try {
      const payload = buildPayload();
      // Fetch the PDF inline for the iframe
      const res = await apiFetch("/offer-appointment/pdf?inline=true", {
        method: "POST",
        body: payload,
      });
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { const j = await res.json(); msg = j.detail || msg; } catch { /* keep msg */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const stem = `Offer_of_Appointment_${form.title.replace(".","")}_${form.name.replace(/\s+/g,"_")}`;
      setPreview({ url, payload, filename: stem });
    } catch (e2) {
      setError(e2.message || "Failed to generate preview");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="max-w-6xl mx-auto px-6 py-10" data-testid="offer-appointment-view">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55 mb-1">
        Offer of Appointment
      </div>
      <h2 className="text-2xl font-semibold text-[#1a1a1f] mb-6">
        Generate offer letter (DOCX / PDF)
      </h2>

      <form
        onSubmit={onPreview}
        autoComplete="off"
        data-testid="offer-appointment-form"
        className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-2 rounded-xl border border-[#1a1a1f]/10 bg-white p-6 sm:p-8"
      >
        <div>
          <Field label="Title" required>
            <select data-testid="oa-title" value={form.title} onChange={set("title")}
                    className={`${inputCls} ${selectArrow}`} style={selectArrowStyle}>
              <option value="" disabled>Select</option>
              {TITLES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Name" required>
            <input data-testid="oa-name" type="text" value={form.name} onChange={set("name")} className={inputCls} />
          </Field>
          <Field label="Email ID" required>
            <input data-testid="oa-email" type="email" value={form.email} onChange={set("email")} className={inputCls} />
          </Field>
          <Field label="Phone" required>
            <input data-testid="oa-phone" type="tel" value={form.phone} onChange={set("phone")} className={inputCls} />
          </Field>
          <Field label="Letter Date" required>
            <input data-testid="oa-cur-date" type="date" value={form.cur_date_iso} onChange={set("cur_date_iso")} className={inputCls} />
          </Field>
          <Field label="Joining Date" required>
            <input data-testid="oa-joining-date" type="date" value={form.date_iso} onChange={set("date_iso")} className={inputCls} />
          </Field>
          <Field label="Reference Number" required>
            <input data-testid="oa-ref-number" type="text" value={form.reference_number} onChange={set("reference_number")} className={inputCls} />
          </Field>
        </div>

        <div className="md:border-l md:border-[#1a1a1f]/10 md:pl-10">
          <Field label="Designation" required>
            <select data-testid="oa-designation" value={form.designation} onChange={set("designation")}
                    className={`${inputCls} ${selectArrow}`} style={selectArrowStyle}>
              <option value="" disabled>Select</option>
              {DESIGNATIONS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </Field>
          <Field label="Address Line 1" required>
            <input data-testid="oa-addr1" type="text" value={form.address_line1} onChange={set("address_line1")} className={inputCls} />
          </Field>
          <Field label="Address Line 2">
            <input data-testid="oa-addr2" type="text" value={form.address_line2} onChange={set("address_line2")} className={inputCls} />
          </Field>
          <Field label="Address Line 3">
            <input data-testid="oa-addr3" type="text" value={form.address_line3} onChange={set("address_line3")} className={inputCls} />
          </Field>
          <Field label="CTC (Yearly)" required>
            <input data-testid="oa-ctc" type="number" min="1" step="1" value={form.ctc_yearly} onChange={set("ctc_yearly")} placeholder="e.g. 660000" className={inputCls} />
          </Field>
          <p className="text-xs text-[#1a1a1f]/55 -mt-2 mb-4">
            Annexure-A line items scale proportionally from the source template; Tier is auto-derived.
          </p>

          {error && (
            <div data-testid="oa-error" className="mb-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}
          {!allFilled && !error && (
            <div data-testid="oa-missing-hint" className="mb-3 text-xs text-[#1a1a1f]/65 bg-[#fff8e6] border border-amber-200 rounded-md px-3 py-2">
              Fill all required fields (<span className="text-red-600 font-semibold">*</span>) to enable preview.
            </div>
          )}
          <button
            type="submit" disabled={!allFilled || busy} data-testid="oa-submit"
            className="w-full inline-flex items-center justify-center gap-2 rounded-md bg-[#3d4a78] hover:bg-[#2c3661] disabled:bg-[#1a1a1f]/25 disabled:cursor-not-allowed transition-colors text-white text-sm font-semibold tracking-wider uppercase px-5 py-3.5"
          >
            {busy
              ? <><Loader2 size={16} className="animate-spin" /> Generating&hellip;</>
              : "Preview & Download"}
          </button>
        </div>
      </form>

      {preview && (
        <PreviewModal
          pdfBlobUrl={preview.url}
          payload={preview.payload}
          filename={preview.filename}
          onClose={() => { URL.revokeObjectURL(preview.url); setPreview(null); }}
        />
      )}
    </main>
  );
}
