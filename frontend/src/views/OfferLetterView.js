import { useState } from "react";
import { Download, Loader2, CheckCircle2 } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const EMPTY = {
  ref_code: "",
  date: "",
  name: "",
  addr1: "",
  addr2: "",
  addr3: "",
  phone: "",
  email: "",
  designation: "",
  salary_amount: "",
  salary_words: "",
};

function Field({ label, placeholder, value, onChange, testid, prefix }) {
  return (
    <label className="block mb-4">
      <span className="block text-xs font-medium text-[#1a1a1f]/70 mb-1.5">
        {label}
      </span>
      <div className="flex items-stretch bg-[#f6f4ef] border border-[#1a1a1f]/15 focus-within:border-[#232369] rounded-md transition-colors overflow-hidden">
        {prefix ? (
          <span className="px-3 py-2.5 text-sm text-[#1a1a1f]/55 font-mono bg-[#1a1a1f]/[0.03] border-r border-[#1a1a1f]/10">
            {prefix}
          </span>
        ) : null}
        <input
          data-testid={testid}
          type="text"
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          className="w-full bg-transparent focus:outline-none px-3 py-2.5 text-sm text-[#1a1a1f] placeholder:text-[#1a1a1f]/35"
        />
      </div>
    </label>
  );
}

export default function OfferLetterView() {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const required = [
    "ref_code", "date", "name", "addr1", "addr2", "addr3",
    "phone", "email", "designation", "salary_amount", "salary_words",
  ];
  const allFilled = required.every((k) => form[k].trim());

  const onGenerate = async (e) => {
    e.preventDefault();
    if (!allFilled || busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${API}/offer/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const blob = await res.blob();
      const safeName =
        form.name.replace(/[^A-Za-z0-9 _-]/g, "").trim().replace(/\s+/g, "_") ||
        "Offer";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Offer_Letter_${safeName}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Failed to generate offer letter");
    } finally {
      setBusy(false);
    }
  };

  const show = (v, fallback) => (v && v.trim() ? v : fallback);

  return (
    <main className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-1 lg:grid-cols-[440px_1fr] gap-10">
      <form
        onSubmit={onGenerate}
        className="rounded-xl border border-[#1a1a1f]/10 bg-white p-6 h-fit"
        data-testid="offer-generator-form"
      >
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55">
          Enter details
        </div>
        <h2 className="text-lg font-semibold mt-1 mb-5">
          Fill the fields, download the Offer Letter PDF.
        </h2>

        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Ref Code"
            placeholder="092"
            prefix="CHN/2026/INT/1-"
            testid="offer-input-ref"
            value={form.ref_code}
            onChange={set("ref_code")}
          />
          <Field
            label="Date"
            placeholder="10-06-2026"
            testid="offer-input-date"
            value={form.date}
            onChange={set("date")}
          />
        </div>

        <Field
          label="Name (used in 2 places)"
          placeholder="Mr. Riswan Ahamed Mohamed Ibrahim"
          testid="offer-input-name"
          value={form.name}
          onChange={set("name")}
        />
        <Field
          label="Address Line 1"
          placeholder="17, Arulanandha nagar,"
          testid="offer-input-addr1"
          value={form.addr1}
          onChange={set("addr1")}
        />
        <Field
          label="Address Line 2"
          placeholder="VNS Garden, 3rd Cross,"
          testid="offer-input-addr2"
          value={form.addr2}
          onChange={set("addr2")}
        />
        <Field
          label="Address Line 3"
          placeholder="Thanjavur-613001"
          testid="offer-input-addr3"
          value={form.addr3}
          onChange={set("addr3")}
        />

        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Phone No"
            placeholder="7418540369"
            testid="offer-input-phone"
            value={form.phone}
            onChange={set("phone")}
          />
          <Field
            label="Email ID"
            placeholder="name@example.com"
            testid="offer-input-email"
            value={form.email}
            onChange={set("email")}
          />
        </div>

        <Field
          label="Designation"
          placeholder="AI Research Intern"
          testid="offer-input-designation"
          value={form.designation}
          onChange={set("designation")}
        />

        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Salary Amount (used in 2 places)"
            placeholder="25,000"
            prefix={"\u20b9"}
            testid="offer-input-salary-amount"
            value={form.salary_amount}
            onChange={set("salary_amount")}
          />
          <Field
            label="Salary in Words"
            placeholder="Twenty Five Thousand"
            testid="offer-input-salary-words"
            value={form.salary_words}
            onChange={set("salary_words")}
          />
        </div>

        {error ? (
          <div
            data-testid="offer-error-msg"
            className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2"
          >
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={!allFilled || busy}
          data-testid="offer-generate-btn"
          className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#232369] hover:bg-[#1a1a55] disabled:bg-[#1a1a1f]/25 disabled:cursor-not-allowed transition-colors text-white text-sm font-medium px-5 py-3"
        >
          {busy ? (
            <><Loader2 size={16} className="animate-spin" /> Generating&hellip;</>
          ) : (
            <><Download size={16} /> Generate &amp; download PDF</>
          )}
        </button>

        <p className="mt-4 text-xs text-[#1a1a1f]/55 leading-relaxed">
          Values are baked directly into the original 7-page PDF in Arial 11pt
          at the exact same positions. Name and Date reflect in their two
          locations; Salary Amount reflects in body paragraph &amp; annexure.
        </p>
      </form>

      <section>
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55 mb-2">
          Live preview &mdash; page 1 (top)
        </div>
        <div
          data-testid="offer-live-preview"
          className="rounded-xl border border-[#1a1a1f]/10 bg-white p-10 shadow-[0_24px_60px_-30px_rgba(20,20,40,0.35)] text-[12.5px] leading-[1.7] text-black"
        >
          <div className="flex items-start justify-between mb-4">
            <div>
              <span className="font-bold">Ref: </span>
              <span className="font-mono">
                CHN/2026/INT/1-{show(form.ref_code, "____")}
              </span>
            </div>
            <div>
              <span className="font-bold">Date: </span>
              <span>{show(form.date, "__________")}</span>
            </div>
          </div>

          <div className="font-bold">{show(form.name, "_______________________")},</div>
          <div>{show(form.addr1, "_______________________")}</div>
          <div>{show(form.addr2, "_______________________")}</div>
          <div>{show(form.addr3, "_______________________")}</div>
          <div>{show(form.phone, "___________")}</div>
          <div>{show(form.email, "_______________________")}</div>

          <div className="mt-4">
            Dear <span className="font-bold">{show(form.name, "_______________________")}</span>,
          </div>
          <div className="mt-3">
            It is our pleasure to welcome you to BluBridge Technologies Private
            Limited (hereinafter referred to as &ldquo;the Company&rdquo;).
          </div>
          <div className="mt-3">
            With reference to our discussions, we are pleased to offer you an
            Internship in our Organization as an{" "}
            <span>{show(form.designation, "____________________")}</span>,
            operating out of our Besant Nagar, Chennai office.
          </div>
          <div className="mt-3">
            Your monthly internship stipend shall be{" "}
            <span className="font-bold">
              &#8377;{show(form.salary_amount, "_______")}/-
            </span>{" "}
            (Indian Rupees{" "}
            <span>{show(form.salary_words, "____________________")}</span> only).
          </div>
          <div className="mt-3">
            Your internship engagement shall commence on{" "}
            <span>{show(form.date, "__________")}</span> and shall continue
            until such time...
          </div>
          <p className="mt-6 text-[10.5px] text-[#1a1a1f]/45">
            Mock preview only &mdash; the downloaded 7-page PDF preserves every
            other element exactly: header, footer, signature, annexure pages,
            font, alignment, spacing, margins.
          </p>
        </div>

        <div className="mt-4 rounded-xl border border-[#1a1a1f]/10 bg-white p-5">
          <div className="text-sm font-medium mb-3">What stays untouched</div>
          <ul className="space-y-2 text-sm text-[#1a1a1f]/75">
            {[
              "Page count, layout, margins, header, footer",
              "Annexure A &mdash; Internship Terms & Conditions (pages 3\u20137)",
              "Signature block (Praveen Kumar S, Director)",
              "Font (Arial), size (11pt), weights, alignment, line spacing",
              "All surrounding wording &mdash; not a single word changed",
            ].map((t) => (
              <li key={t} className="flex items-start gap-2">
                <CheckCircle2 size={14} className="mt-0.5 text-[#232369]" />
                <span dangerouslySetInnerHTML={{ __html: t }} />
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}
