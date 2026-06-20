import { useState } from "react";
import { Download, Loader2, CheckCircle2 } from "lucide-react";
import { apiBlob } from "@/lib/api";

function Field({ label, placeholder, value, onChange, testid }) {
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
        className="w-full bg-[#f6f4ef] border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-md px-3 py-2.5 text-sm text-[#1a1a1f] placeholder:text-[#1a1a1f]/35 transition-colors"
      />
    </label>
  );
}

function Preview({ values }) {
  const show = (v, fallback) => (v && v.trim() ? v : fallback);
  return (
    <div
      data-testid="cert-live-preview"
      className="rounded-xl border border-[#1a1a1f]/10 bg-white p-8 shadow-[0_24px_60px_-30px_rgba(20,20,40,0.35)]"
    >
      <div className="text-[#232369] text-center font-semibold text-xl tracking-tight mb-6">
        Internship Certificate
      </div>
      <p className="text-[13px] leading-[1.85] text-[#1a1a1f]">
        This is to certify that{" "}
        <span className="font-bold">{show(values.name, "____________________")}</span>{" "}
        has completed his internship as an{" "}
        <span className="font-bold">{show(values.designation, "____________________")}</span>{" "}
        with Blubridge Technologies Pvt Ltd. His internship tenure commenced on{" "}
        <span className="font-bold">{show(values.commenced, "__________")}</span>{" "}
        and concluded on{" "}
        <span className="font-bold">{show(values.concluded, "__________")}</span>.
      </p>
      <p className="text-[13px] leading-[1.85] text-[#1a1a1f] mt-4">
        During his internship, he demonstrated professionalism, enthusiasm, and
        valuable contributions to our research initiatives.
      </p>
      <p className="text-[13px] leading-[1.85] text-[#1a1a1f] mt-4">
        We wish him all the best in him future endeavors.
      </p>
      <p className="text-[11px] text-[#1a1a1f]/45 mt-6">
        Mock preview only &mdash; header, footer, logo, signature appear in the
        downloaded PDF exactly as in the original.
      </p>
    </div>
  );
}

export default function CertificateView() {
  const [form, setForm] = useState({
    name: "",
    designation: "",
    commenced: "",
    concluded: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const allFilled =
    form.name.trim() &&
    form.designation.trim() &&
    form.commenced.trim() &&
    form.concluded.trim();

  const onGenerate = async (e) => {
    e.preventDefault();
    if (!allFilled || busy) return;
    setBusy(true);
    setError("");
    try {
      const blob = await apiBlob("/template/generate", { method: "POST", body: form });
      const safeName =
        form.name.replace(/[^A-Za-z0-9 _-]/g, "").trim().replace(/\s+/g, "_") || "Certificate";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Internship_Certificate_${safeName}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Failed to generate certificate");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-10">
      <form
        onSubmit={onGenerate}
        autoComplete="off"
        className="rounded-xl border border-[#1a1a1f]/10 bg-white p-6 h-fit"
        data-testid="cert-generator-form"
      >
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55">
          Enter details
        </div>
        <h2 className="text-lg font-semibold mt-1 mb-5">
          Fill the four fields, download the PDF.
        </h2>

        <Field
          label="Name"
          placeholder="e.g. Mr. Rishimithan Kannan"
          testid="cert-input-name"
          value={form.name}
          onChange={set("name")}
        />
        <Field
          label="Designation"
          placeholder="e.g. AI Research Intern"
          testid="cert-input-designation"
          value={form.designation}
          onChange={set("designation")}
        />
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Commenced on Date"
            placeholder="e.g. 28.07.2025"
            testid="cert-input-commenced"
            value={form.commenced}
            onChange={set("commenced")}
          />
          <Field
            label="Concluded on Date"
            placeholder="e.g. 24.11.2025"
            testid="cert-input-concluded"
            value={form.concluded}
            onChange={set("concluded")}
          />
        </div>

        {error ? (
          <div
            data-testid="cert-error-msg"
            className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2"
          >
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={!allFilled || busy}
          data-testid="cert-generate-btn"
          className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#232369] hover:bg-[#1a1a55] disabled:bg-[#1a1a1f]/25 disabled:cursor-not-allowed transition-colors text-white text-sm font-medium px-5 py-3"
        >
          {busy ? (
            <><Loader2 size={16} className="animate-spin" /> Generating&hellip;</>
          ) : (
            <><Download size={16} /> Generate &amp; download PDF</>
          )}
        </button>

        <p className="mt-4 text-xs text-[#1a1a1f]/55 leading-relaxed">
          Values are baked directly into the PDF in Roboto-Bold 10pt at the
          exact original positions &mdash; no form fields, no editable chrome.
        </p>
      </form>

      <section>
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55 mb-2">
          Live preview
        </div>
        <Preview values={form} />
        <div className="mt-4 rounded-xl border border-[#1a1a1f]/10 bg-white p-5">
          <div className="text-sm font-medium mb-3">What stays untouched</div>
          <ul className="space-y-2 text-sm text-[#1a1a1f]/75">
            {[
              "Header, footer, logo, watermark",
              "Signature block (Praveen Kumar S, Director)",
              "Company address, CIN, phone, email",
              "Font, size, weight, alignment, spacing, margins",
              "All surrounding wording \u2014 not a single word changed",
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
