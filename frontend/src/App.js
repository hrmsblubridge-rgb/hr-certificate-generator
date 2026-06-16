import { useState } from "react";
import "@/App.css";
import { Download, FileText, ArrowLeftRight, CheckCircle2 } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const FIELDS = [
  { label: "Name", original: "Mr. Aravind Krishna P M" },
  { label: "Designation", original: "AI Research Analyst" },
  { label: "Commenced on Date", original: "28.07.2025" },
  { label: "Concluded on Date", original: "24.11.2025" },
];

function App() {
  const [view, setView] = useState("template"); // "template" | "original"
  const src = view === "template"
    ? `${API}/template/preview`
    : `${API}/template/original`;

  return (
    <div className="min-h-screen bg-[#f6f4ef] text-[#1a1a1f]">
      {/* Header */}
      <header className="border-b border-[#1a1a1f]/10 bg-[#f6f4ef]/90 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-md bg-[#232369] grid place-items-center text-white">
              <FileText size={18} />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/60">
                BluBridge HR
              </div>
              <div className="text-base font-semibold tracking-tight">
                Internship Certificate · Editable Template
              </div>
            </div>
          </div>
          <a
            data-testid="download-template-btn"
            href={`${API}/template/download`}
            className="inline-flex items-center gap-2 rounded-full bg-[#232369] hover:bg-[#1a1a55] transition-colors text-white text-sm font-medium px-5 py-2.5"
          >
            <Download size={16} /> Download editable PDF
          </a>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-7xl mx-auto px-6 py-10 grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-10">
        {/* Preview */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-[#1a1a1f]/60">Viewing:</span>
              <span data-testid="current-view-label" className="font-medium">
                {view === "template" ? "Editable Template" : "Original Certificate"}
              </span>
            </div>
            <button
              data-testid="toggle-view-btn"
              onClick={() => setView(view === "template" ? "original" : "template")}
              className="inline-flex items-center gap-2 text-sm font-medium rounded-full border border-[#1a1a1f]/15 hover:border-[#1a1a1f]/40 px-4 py-2 transition-colors"
            >
              <ArrowLeftRight size={14} />
              {view === "template" ? "Compare with original" : "Back to template"}
            </button>
          </div>

          <div className="rounded-xl overflow-hidden border border-[#1a1a1f]/10 shadow-[0_24px_60px_-30px_rgba(20,20,40,0.35)] bg-white">
            <iframe
              data-testid="pdf-preview-iframe"
              key={view}
              title="certificate-preview"
              src={src}
              className="w-full h-[1100px] bg-white"
            />
          </div>

          <p className="text-xs text-[#1a1a1f]/55 mt-3 leading-relaxed">
            Note: most browsers render PDFs as a flat view and don&apos;t expose form
            fields. To <em>fill in</em> the editable fields, download the PDF and
            open it in Adobe Acrobat Reader, Foxit Reader, Preview (macOS), or any
            desktop PDF editor — the four placeholders will appear as editable text
            boxes.
          </p>
        </section>

        {/* Sidebar */}
        <aside>
          <div className="rounded-xl border border-[#1a1a1f]/10 bg-white p-6">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[#1a1a1f]/55">
              Editable fields
            </div>
            <h2 className="text-lg font-semibold mt-1 mb-4">
              Four placeholders HR can fill
            </h2>
            <ul className="space-y-3" data-testid="fields-list">
              {FIELDS.map((f) => (
                <li
                  key={f.label}
                  className="flex items-start gap-3 rounded-lg border border-[#1a1a1f]/10 p-3"
                >
                  <CheckCircle2
                    size={16}
                    className="mt-0.5 text-[#232369] shrink-0"
                  />
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{f.label}</div>
                    <div className="text-xs text-[#1a1a1f]/55 truncate">
                      was: <span className="font-mono">{f.original}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-[#1a1a1f]/10 bg-[#232369] text-white p-6 mt-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-white/60">
              Guarantee
            </div>
            <h3 className="text-base font-semibold mt-1">
              Original layout preserved
            </h3>
            <ul className="text-sm text-white/85 space-y-2 mt-3 leading-relaxed">
              <li>Same font, size, weight, color</li>
              <li>Same alignment, spacing, margins</li>
              <li>Header, footer, logo, signature untouched</li>
              <li>Only the four values are now blank &amp; fillable</li>
            </ul>
          </div>

          <a
            data-testid="download-template-btn-secondary"
            href={`${API}/template/download`}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#1a1a1f] hover:bg-black transition-colors text-white text-sm font-medium px-5 py-3"
          >
            <Download size={16} /> Download editable PDF
          </a>
          <a
            data-testid="download-original-btn"
            href={`${API}/template/original`}
            className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-full border border-[#1a1a1f]/20 hover:border-[#1a1a1f]/50 text-sm font-medium px-5 py-3"
          >
            Download original (reference)
          </a>
        </aside>
      </main>

      <footer className="max-w-7xl mx-auto px-6 pb-10 text-xs text-[#1a1a1f]/50">
        Generated by preserving the source PDF exactly &mdash; only four values
        were redacted and replaced with AcroForm text widgets.
      </footer>
    </div>
  );
}

export default App;
