import { useState, useEffect } from "react";
import "@/App.css";
import CertificateView from "./views/CertificateView";
import OfferLetterView from "./views/OfferLetterView";
import OfferLetterEmailView from "./views/OfferLetterEmailView";
import AcknowledgementView from "./views/AcknowledgementView";
import HistoryView from "./views/HistoryView";
import Login from "./views/Login";
import ChangePasswordModal from "./views/ChangePasswordModal";
import { apiFetch, apiJSON } from "@/lib/api";
import { FileText, FileSignature, FileCheck, History, LogOut, KeyRound, Mail } from "lucide-react";

const MENU = [
  { id: "certificate", label: "Internship Certificate", icon: FileText },
  { id: "offer",       label: "Offer Letter",            icon: FileSignature },
  { id: "offer-email", label: "Offer Letter (Email)",    icon: Mail },
  { id: "ack",         label: "Acknowledgement",         icon: FileCheck },
  { id: "history",     label: "History",                  icon: History },
];

function App() {
  const [authState, setAuthState] = useState("checking"); // checking | in | out
  const [view, setView] = useState("certificate");
  const [username, setUsername] = useState("");
  const [showChangePw, setShowChangePw] = useState(false);

  const refreshAuth = async () => {
    try {
      const { user } = await apiJSON("/auth/me");
      setUsername(user?.username || "");
      setAuthState("in");
    } catch {
      setAuthState("out");
    }
  };

  useEffect(() => { refreshAuth(); }, []);

  const logout = async () => {
    try { await apiFetch("/auth/logout", { method: "POST" }); } catch { /* ignore */ }
    setAuthState("out");
  };

  if (authState === "checking") {
    return (
      <div className="min-h-screen grid place-items-center bg-[#e8e4dc] text-[#1a1a1f]/55 text-sm">
        Loading…
      </div>
    );
  }
  if (authState === "out") return <Login onSuccess={() => setAuthState("in")} />;

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
              data-testid="change-password-btn"
              onClick={() => setShowChangePw(true)}
              title="Change password"
              className="inline-flex items-center gap-2 text-sm font-medium px-3 py-2 rounded-full text-[#1a1a1f]/70 hover:text-[#1a1a1f] hover:bg-white border border-transparent hover:border-[#1a1a1f]/10 transition-colors"
            >
              <KeyRound size={14} />
              <span className="hidden sm:inline">Change password</span>
            </button>
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
        : view === "offer"        ? <OfferLetterView />
        : view === "offer-email"  ? <OfferLetterEmailView />
        : view === "ack"          ? <AcknowledgementView />
        :                            <HistoryView />}

      {showChangePw && (
        <ChangePasswordModal
          username={username}
          onClose={() => setShowChangePw(false)}
          onSuccess={() => { setShowChangePw(false); setAuthState("out"); }}
        />
      )}
    </div>
  );
}

export default App;
