import { useState } from "react";
import { Download, Loader2, CheckCircle2 } from "lucide-react";
import { apiBlob } from "@/lib/api";

function Field({ label, placeholder, value, onChange, testid, listId }) {
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
        list={listId}
        className="w-full bg-[#f6f4ef] border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-md px-3 py-2.5 text-sm text-[#1a1a1f] placeholder:text-[#1a1a1f]/35 transition-colors"
      />
    </label>
  );
}

// Curated list of internship designations used by Blubridge HR.
// `<datalist>` gives a dropdown suggestion while still allowing free typing
// (so custom designations like "AI Research Analyst II" remain possible).
const DESIGNATIONS = [
  "AI Research Intern",
  "AI Research Analyst",
  "AI Intern",
  "Machine Learning Intern",
  "Data Science Intern",
  "Data Engineering Intern",
  "Software Engineering Intern",
  "Backend Developer Intern",
  "Frontend Developer Intern",
  "Full Stack Developer Intern",
  "Mobile App Developer Intern",
  "DevOps Intern",
  "Cloud Engineering Intern",
  "Cybersecurity Intern",
  "QA Engineer Intern",
  "UI/UX Design Intern",
  "Product Management Intern",
  "Business Analyst Intern",
  "Marketing Intern",
  "HR Intern",
  "Research Intern",
];

// Convert ISO date "YYYY-MM-DD" → "DD.MM.YYYY" (the format baked into the PDF).
// Returns "" for empty / invalid input.
function toDMY(iso) {
  if (!iso || typeof iso !== "string") return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

function DateField({ label, value, onChange, testid }) {
  return (
    <label className="block mb-4">
      <span className="block text-xs font-medium text-[#1a1a1f]/70 mb-1.5">
        {label}
      </span>
      <input
        data-testid={testid}
        type="date"
        value={value}
        onChange={onChange}
        className="w-full bg-[#f6f4ef] border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-md px-3 py-2.5 text-sm text-[#1a1a1f] transition-colors"
      />
    </label>
  );
}

function SelectField({ label, value, onChange, testid, children }) {
  return (
    <label className="block mb-4">
      <span className="block text-xs font-medium text-[#1a1a1f]/70 mb-1.5">
        {label}
      </span>
      <select
        data-testid={testid}
        value={value}
        onChange={onChange}
        className="w-full bg-[#f6f4ef] border border-[#1a1a1f]/15 focus:border-[#232369] focus:outline-none rounded-md px-3 py-2.5 text-sm text-[#1a1a1f] transition-colors appearance-none bg-no-repeat bg-[right_0.75rem_center] pr-9"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;charset=US-ASCII,%3Csvg width='12' height='8' viewBox='0 0 12 8' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%231a1a1f' stroke-opacity='0.55' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
        }}
      >
        {children}
      </select>
    </label>
  );
}

// Pronoun map driving the live preview (mirrors the backend logic).
const PRONOUNS = {
  male:   { his: "his", His: "His", he: "he", him: "him" },
  female: { his: "her", His: "Her", he: "she", him: "her" },
};

function Preview({ values }) {
  const p = PRONOUNS[values.gender] || PRONOUNS.male;
  // Gender-driven title: strip any user-typed title first, then prepend the
  // correct one. Mirrors the backend logic in _build_filled_pdf.
  const TITLE_RE = /^(mr|mrs|ms|miss)\.?\s+/i;
  const titleFor = values.gender === "female" ? "Ms." : values.gender === "male" ? "Mr." : "";
  const baseName = (values.name || "").replace(TITLE_RE, "").trim();
  const displayName = titleFor && baseName ? `${titleFor} ${baseName}` : baseName;
  const show = (v, fallback) => (v && v.trim() ? v : fallback);
  const commencedDMY = toDMY(values.commenced);
  const concludedDMY = toDMY(values.concluded);
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
        <span className="font-bold">{show(displayName, "____________________")}</span>{" "}
        has completed {p.his} internship as an{" "}
        <span className="font-bold">{show(values.designation, "____________________")}</span>{" "}
        with Blubridge Technologies Pvt Ltd. {p.His} internship tenure commenced on{" "}
        <span className="font-bold">{show(commencedDMY, "__________")}</span>{" "}
        and concluded on{" "}
        <span className="font-bold">{show(concludedDMY, "__________")}</span>.
      </p>
      <p className="text-[13px] leading-[1.85] text-[#1a1a1f] mt-4">
        During {p.his} internship, {p.he} demonstrated professionalism, enthusiasm, and
        valuable contributions to our research initiatives.
      </p>
      <p className="text-[13px] leading-[1.85] text-[#1a1a1f] mt-4">
        We wish {p.him} all the best in {p.his} future endeavors.
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
    gender: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const allFilled =
    form.name.trim() &&
    form.designation.trim() &&
    form.commenced.trim() &&
    form.concluded.trim() &&
    form.gender;

  const onGenerate = async (e) => {
    e.preventDefault();
    if (busy) return;
    if (!form.gender) {
      setError("Please select gender");
      return;
    }
    if (!allFilled) return;
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...form,
        commenced: toDMY(form.commenced),
        concluded: toDMY(form.concluded),
      };
      const blob = await apiBlob("/template/generate", { method: "POST", body: payload });
      const TITLE_RE = /^(mr|mrs|ms|miss)\.?\s+/i;
      const titlePrefix = form.gender === "female" ? "Ms" : "Mr";
      const bareName = form.name.replace(TITLE_RE, "").trim();
      const safeName =
        bareName.replace(/[^A-Za-z0-9 _-]/g, "").trim().replace(/\s+/g, "_") || "Certificate";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Internship_Certificate_${titlePrefix}_${safeName}.pdf`;
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
          Fill the fields, download the PDF.
        </h2>

        <Field
          label="Name"
          placeholder="e.g. Rishimithan Kannan (no Mr./Ms.)"
          testid="cert-input-name"
          value={form.name}
          onChange={set("name")}
        />
        <Field
          label="Designation"
          placeholder="Pick from list or type your own"
          testid="cert-input-designation"
          value={form.designation}
          onChange={set("designation")}
          listId="cert-designation-list"
        />
        <datalist id="cert-designation-list" data-testid="cert-designation-options">
          {DESIGNATIONS.map((d) => (
            <option key={d} value={d} />
          ))}
        </datalist>
        <SelectField
          label="Gender"
          testid="cert-input-gender"
          value={form.gender}
          onChange={(e) => {
            setForm({ ...form, gender: e.target.value });
            if (error === "Please select gender") setError("");
          }}
        >
          <option value="" disabled>Select gender</option>
          <option value="male">Male</option>
          <option value="female">Female</option>
        </SelectField>
        <div className="grid grid-cols-2 gap-3">
          <DateField
            label="Commenced on Date"
            testid="cert-input-commenced"
            value={form.commenced}
            onChange={set("commenced")}
          />
          <DateField
            label="Concluded on Date"
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
              "All surrounding wording \u2014 only pronouns change with gender",
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
