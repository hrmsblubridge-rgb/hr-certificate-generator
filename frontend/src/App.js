import { useState, useEffect } from "react";
import "@/App.css";
import CertificateView from "./views/CertificateView";
import OfferLetterView from "./views/OfferLetterView";
import OfferLetterEmailView from "./views/OfferLetterEmailView";
import OfferOfAppointmentView from "./views/OfferOfAppointmentView";
import AcknowledgementView from "./views/AcknowledgementView";
import NotificationEmailView from "./views/NotificationEmailView";
import HistoryView from "./views/HistoryView";
import DocView from "./views/DocView";
import Login from "./views/Login";
import ChangePasswordModal from "./views/ChangePasswordModal";
import { apiFetch, apiJSON } from "@/lib/api";
import { FileText, FileSignature, FileCheck, History, LogOut, KeyRound, Mail, FileType, Send, FileBox } from "lucide-react";

const MENU = [
  { id: "certificate",   label: "Internship Certificate", icon: FileText },
  { id: "offer",         label: "Offer Letter",            icon: FileSignature },
  { id: "offer-email",   label: "Offer Letter (Email)",    icon: Mail },
  { id: "offer-appoint", label: "Offer of Appointment",    icon: FileType },
  { id: "ack",           label: "Acknowledgement",         icon: FileCheck },
  { id: "notif-email",   label: "Notification Email",      icon: Send },
  { id: "history",       label: "History",                  icon: History },
  { id: "doc",           label: "Doc",                      icon: FileBox },
];

function App() {
  const [authState, setAuthState] = useState("checking"); // checking | in | out
  const [slowBoot, setSlowBoot] = useState(false);
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

  useEffect(() => {
    refreshAuth();
    // If the host is cold-starting, tell the user instead of showing a bare
    // "Loading…" forever.
    const t = setTimeout(() => setSlowBoot(true), 2500);
    return () => clearTimeout(t);
  }, []);

  const logout = async () => {
    try { await apiFetch("/auth/logout", { method: "POST" }); } catch { /* ignore */ }
    setAuthState("out");
  };

  if (authState === "checking") {
    return (
      <div
        data-testid="app-loading"
        className="min-h-screen grid place-items-center bg-[#e8e4dc] text-[#1a1a1f]/55 text-sm"
      >
        <div className="flex flex-col items-center gap-3">
          <span className="w-6 h-6 rounded-full border-2 border-[#232369]/25 border-t-[#232369] animate-spin" />
          <span>{slowBoot ? "Waking up the server — one moment…" : "Loading…"}</span>
        </div>
      </div>
    );
  }
  if (authState === "out") return <Login onSuccess={() => setAuthState("in")} />;

  return (
    <div className="min-h-screen bg-[#f6f4ef] text-[#1a1a1f]">
      <header className="border-b border-[#1a1a1f]/10 bg-[#f6f4ef]/95 backdrop-blur sticky top-0 z-10">
        {/* Row 1 — brand + account chip */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-3 pb-2 flex items-center gap-4">
          <div className="flex items-center gap-3 shrink-0">
            <img
              src="/img/blubridge-logo.webp"
              alt="BluBridge"
              className="w-auto"
              draggable={false}
            />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <div
              data-testid="user-chip"
              className="hidden sm:inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-[#1a1a1f]/10 text-xs font-medium text-[#1a1a1f]/80"
              title={`Signed in as ${username || "admin"}`}
            >
              <span
                aria-hidden="true"
                className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[#232369] text-white text-[10px] font-bold uppercase"
              >
                {(username || "A").charAt(0)}
              </span>
              <span>{username || "admin"}</span>
            </div>
            <button
              data-testid="change-password-btn"
              onClick={() => setShowChangePw(true)}
              title="Change password"
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full text-[#1a1a1f]/75 hover:text-[#1a1a1f] bg-white border border-[#1a1a1f]/10 hover:border-[#232369]/40 transition-colors whitespace-nowrap"
            >
              <KeyRound size={13} />
              <span className="hidden lg:inline">Change password</span>
            </button>
            <button
              data-testid="logout-btn"
              onClick={logout}
              title="Sign out"
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full text-[#1a1a1f]/75 hover:text-white hover:bg-[#232369] bg-white border border-[#1a1a1f]/10 hover:border-[#232369] transition-colors whitespace-nowrap"
            >
              <LogOut size={13} />
              <span className="hidden lg:inline">Sign out</span>
            </button>
          </div>
        </div>

        {/* Row 2 — primary navigation (clean tab bar with active underline) */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <nav
            data-testid="primary-nav"
            className="flex items-stretch justify-center gap-0.5 overflow-x-auto -mb-px"
          >
            {MENU.map((m) => {
              const Icon = m.icon;
              const active = view === m.id;
              return (
                <button
                  key={m.id}
                  data-testid={`menu-${m.id}`}
                  onClick={() => setView(m.id)}
                  title={m.label}
                  aria-current={active ? "page" : undefined}
                  className={
                    "relative inline-flex items-center gap-2 text-[13px] font-medium px-3.5 py-3 transition-colors whitespace-nowrap shrink-0 border-b-2 " +
                    (active
                      ? "text-[#232369] border-[#232369]"
                      : "text-[#1a1a1f]/60 hover:text-[#1a1a1f] border-transparent hover:border-[#1a1a1f]/15")
                  }
                >
                  <Icon size={15} className={active ? "text-[#232369]" : "text-[#1a1a1f]/55"} />
                  <span>{m.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      {view === "certificate" ? <CertificateView />
        : view === "offer"        ? <OfferLetterView />
        : view === "offer-email"  ? <OfferLetterEmailView />
        : view === "offer-appoint" ? <OfferOfAppointmentView />
        : view === "ack"          ? <AcknowledgementView />
        : view === "notif-email"  ? <NotificationEmailView />
        : view === "doc"          ? <DocView />
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
