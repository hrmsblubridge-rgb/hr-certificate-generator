import { useState, useEffect } from "react";
import "@/App.css";
import CertificateView from "./views/CertificateView";
import OfferLetterView from "./views/OfferLetterView";
import AcknowledgementView from "./views/AcknowledgementView";
import Login from "./views/Login";
import { FileText, FileSignature, FileCheck, LogOut } from "lucide-react";

const MENU = [
  { id: "certificate", label: "Internship Certificate", icon: FileText },
  { id: "offer",       label: "Offer Letter",            icon: FileSignature },
  { id: "ack",         label: "Acknowledgement",         icon: FileCheck },
];

function App() {
  const [authed, setAuthed] = useState(false);
  const [view, setView] = useState("certificate");

  useEffect(() => {
    try {
      if (localStorage.getItem("bb_auth") === "1") setAuthed(true);
    } catch {}
  }, []);

  const logout = () => {
    try { localStorage.removeItem("bb_auth"); } catch {}
    setAuthed(false);
  };

  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;

  return (
    <div className="min-h-screen bg-[#f6f4ef] text-[#1a1a1f]">
      <header className="border-b border-[#1a1a1f]/10 bg-[#f6f4ef]/95 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <img
              src="/img/blubridge-logo.webp"
              alt="BluBridge"
              className="w-auto"
              draggable={false}
            />
            
          </div>
          <div className="flex items-center gap-2">
            <nav className="flex items-center gap-1 bg-white border border-[#1a1a1f]/10 rounded-full p-1">
              {MENU.map((m) => {
                const Icon = m.icon;
                const active = view === m.id;
                return (
                  <button
                    key={m.id}
                    data-testid={`menu-${m.id}`}
                    onClick={() => setView(m.id)}
                    className={
                      "inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full transition-colors " +
                      (active
                        ? "bg-[#232369] text-white"
                        : "text-[#1a1a1f]/70 hover:text-[#1a1a1f]")
                    }
                  >
                    <Icon size={14} />
                    <span className="hidden sm:inline">{m.label}</span>
                  </button>
                );
              })}
            </nav>
            <button
              data-testid="logout-btn"
              onClick={logout}
              title="Sign out"
              className="ml-1 inline-flex items-center gap-2 text-sm font-medium px-3 py-2 rounded-full text-[#1a1a1f]/70 hover:text-[#1a1a1f] hover:bg-white border border-transparent hover:border-[#1a1a1f]/10 transition-colors"
            >
              <LogOut size={14} />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      {view === "certificate" ? <CertificateView />
        : view === "offer"   ? <OfferLetterView />
        :                      <AcknowledgementView />}
    </div>
  );
}

export default App;
