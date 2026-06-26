import { useState } from "react";
import { Download, Loader2, CheckCircle2 } from "lucide-react";
import { apiBlob } from "@/lib/api";

const COMMON_MARKSHEETS = [
  "10th", "12th", "Diploma", "Bachelor's Degree", "Master's Degree",
];

function Field({ label, placeholder, value, onChange, testid, list }) {
  return (
    <label className="block mb-4">
      <span className="block text-xs font-medium text-[#1a1a1f]/70 mb-1.5">
        {label}
      </span>
      <input
        data-testid={testid}
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        list={list}
        className="w-full bg-[#f6f4ef] border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-md px-3 py-2.5 text-sm text-[#1a1a1f] placeholder:text-[#1a1a1f]/35 transition-colors"
      />
    </label>
  );
}

export default function AcknowledgementView() {
  const [form, setForm] = useState({ date: "", name: "", marksheet_type: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const allFilled =
    form.date.trim() && form.name.trim() && form.marksheet_type.trim();

  const onGenerate = async (e) => {
    e.preventDefault();
    if (!allFilled || busy) return;
    setBusy(true);
    setError("");
    try {
      const blob = await apiBlob("/ack/generate", { method: "POST", body: form });
      const safe =
        form.name.replace(/[^A-Za-z0-9 _-]/g, "").trim().replace(/\s+/g, "_") || "Acknowledgement";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Acknowledgement_${safe}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Failed to generate acknowledgement");
    } finally {
      setBusy(false);
    }
  };

  const show = (v, f) => (v && v.trim() ? v : f);

  return (
    <main className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-10">
      <form
        onSubmit={onGenerate}
        autoComplete="off"
        className="rounded-xl border border-[#1a1a1f]/10 bg-white p-6 h-fit"
        data-testid="ack-generator-form"
      >
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55">
          Enter details
        </div>
        <h2 className="text-lg font-semibold mt-1 mb-5">
          Fill the fields, download the Acknowledgement PDF.
        </h2>

        <Field
          label="Date"
          placeholder="e.g. Jan 09, 2026"
          testid="ack-input-date"
          value={form.date}
          onChange={set("date")}
        />
        <Field
          label="Name (appears in 2 places)"
          placeholder="e.g. Dinesh G"
          testid="ack-input-name"
          value={form.name}
          onChange={set("name")}
        />
        <Field
          label="Mark Sheet (e.g. 10th, 12th, Bachelor's Degree)"
          placeholder="e.g. 10th"
          testid="ack-input-marksheet"
          list="marksheet-suggestions"
          value={form.marksheet_type}
          onChange={set("marksheet_type")}
        />
        <datalist id="marksheet-suggestions">
          {COMMON_MARKSHEETS.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>

        {error ? (
          <div
            data-testid="ack-error-msg"
            className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2"
          >
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={!allFilled || busy}
          data-testid="ack-generate-btn"
          className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#232369] hover:bg-[#1a1a55] disabled:bg-[#1a1a1f]/25 disabled:cursor-not-allowed transition-colors text-white text-sm font-medium px-5 py-3"
        >
          {busy ? (
            <><Loader2 size={16} className="animate-spin" /> Generating&hellip;</>
          ) : (
            <><Download size={16} /> Generate &amp; download PDF</>
          )}
        </button>

        <p className="mt-4 text-xs text-[#1a1a1f]/55 leading-relaxed">
          Values are baked directly into the original PDF in Roboto 10pt at the
          exact positions of the source document. Name reflects in both the
          address block and the &ldquo;Dear&rdquo; greeting.
        </p>
      </form>

      <section>
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55 mb-2">
          Live preview
        </div>
        <div
          data-testid="ack-live-preview"
          className="rounded-xl border border-[#1a1a1f]/10 bg-white p-10 shadow-[0_24px_60px_-30px_rgba(20,20,40,0.35)] text-[12.5px] leading-[1.7] text-[#231F20]"
        >
          <div className="text-center font-semibold tracking-tight mb-6 text-[#231F20]">
            LETTER OF ACKNOWLEDGEMENT OF ORIGINAL DOCUMENT
          </div>
          <div>{show(form.date, "____________")}</div>
          <div className="font-bold mt-3">{show(form.name, "____________")}</div>
          <div>Chennai</div>
          <div className="mt-5">
            Dear <span className="font-bold">{show(form.name, "____________")}</span>,
          </div>
          <div className="mt-3">
            Blubridge Technologies Pvt Ltd acknowledges the receipt of your
            original{" "}
            <span>{show(form.marksheet_type, "______")}</span>{" "}
            Mark Sheet. We understand that the company is the bearer of the
            document and will return it to you upon completion of your
            internship period.
          </div>
          <p className="mt-6 text-[10.5px] text-[#1a1a1f]/45">
            Mock preview only &mdash; the downloaded PDF preserves the
            original header, footer, signature block, and confidentiality
            notice exactly.
          </p>
        </div>

        <div className="mt-4 rounded-xl border border-[#1a1a1f]/10 bg-white p-5">
          <div className="text-sm font-medium mb-3">What stays untouched</div>
          <ul className="space-y-2 text-sm text-[#1a1a1f]/75">
            {[
              "Header (logo + company name)",
              "Footer (CIN, phone, email, address)",
              "Confidentiality notice line",
              'Signature block ("Very truly yours, ... Praveen Kumar S, Director")',
              "Font (Roboto), size (10pt), weights, alignment, line spacing",
            ].map((t) => (
              <li key={t} className="flex items-start gap-2">
                <CheckCircle2 size={14} className="mt-0.5 text-[#232369]" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}
