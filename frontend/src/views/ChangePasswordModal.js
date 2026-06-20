import { useState, useEffect, useRef } from "react";
import { apiJSON } from "@/lib/api";
import { X, KeyRound, Eye, EyeOff } from "lucide-react";

export default function ChangePasswordModal({ username, onClose, onSuccess }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showCur, setShowCur] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const firstInputRef = useRef(null);

  useEffect(() => { firstInputRef.current?.focus(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (next.length < 8) { setErr("New password must be at least 8 characters."); return; }
    if (next !== confirm) { setErr("New password and confirmation do not match."); return; }
    if (next === current) { setErr("New password must differ from the current one."); return; }
    setBusy(true);
    try {
      await apiJSON("/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      onSuccess?.();
    } catch (e2) {
      setErr(e2.message || "Could not change password.");
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="change-password-modal"
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
    >
      <form
        onSubmit={submit}
        autoComplete="off"
        className="w-full max-w-md bg-[#f6f4ef] border border-[#1a1a1f]/10 rounded-2xl shadow-2xl p-6"
      >
        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-full bg-[#232369] text-white grid place-items-center">
              <KeyRound size={16} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-[#1a1a1f]">Change password</h2>
              <p className="text-xs text-[#1a1a1f]/55">Signed in as <span className="font-medium">{username}</span></p>
            </div>
          </div>
          <button
            type="button"
            data-testid="change-password-close"
            onClick={onClose}
            className="text-[#1a1a1f]/55 hover:text-[#1a1a1f] -mt-1"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {err && (
          <div
            data-testid="change-password-error"
            className="mb-4 text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2"
          >
            {err}
          </div>
        )}

        <label className="block text-xs font-medium text-[#1a1a1f]/70 mb-1">Current password</label>
        <div className="relative mb-3">
          <input
            ref={firstInputRef}
            data-testid="cp-current"
            type={showCur ? "text" : "password"}
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 pr-9 text-sm outline-none focus:border-[#232369]"
            autoComplete="current-password"
            required
          />
          <button type="button" onClick={() => setShowCur((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[#1a1a1f]/55 hover:text-[#1a1a1f]"
                  aria-label={showCur ? "Hide password" : "Show password"}>
            {showCur ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>

        <label className="block text-xs font-medium text-[#1a1a1f]/70 mb-1">New password</label>
        <div className="relative mb-3">
          <input
            data-testid="cp-new"
            type={showNew ? "text" : "password"}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            minLength={8}
            className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 pr-9 text-sm outline-none focus:border-[#232369]"
            autoComplete="new-password"
            required
          />
          <button type="button" onClick={() => setShowNew((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[#1a1a1f]/55 hover:text-[#1a1a1f]"
                  aria-label={showNew ? "Hide password" : "Show password"}>
            {showNew ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>

        <label className="block text-xs font-medium text-[#1a1a1f]/70 mb-1">Confirm new password</label>
        <input
          data-testid="cp-confirm"
          type={showNew ? "text" : "password"}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          minLength={8}
          className="w-full rounded-md border border-[#1a1a1f]/15 bg-white px-3 py-2 text-sm outline-none focus:border-[#232369]"
          autoComplete="new-password"
          required
        />

        <p className="mt-4 text-[11px] text-[#1a1a1f]/55 leading-relaxed">
          You will be signed out and asked to log in again with the new password.
        </p>

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            data-testid="cp-cancel"
            onClick={onClose}
            className="text-sm font-medium px-4 py-2 rounded-full text-[#1a1a1f]/70 hover:text-[#1a1a1f] hover:bg-white border border-transparent hover:border-[#1a1a1f]/10"
          >
            Cancel
          </button>
          <button
            type="submit"
            data-testid="cp-submit"
            disabled={busy}
            className="text-sm font-medium px-5 py-2 rounded-full bg-[#232369] text-white hover:bg-[#1a1a4f] disabled:opacity-60"
          >
            {busy ? "Updating…" : "Update password"}
          </button>
        </div>
      </form>
    </div>
  );
}
