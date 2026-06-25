import { useState, useEffect } from "react";
import { User, Lock, Eye, EyeOff, ArrowRight } from "lucide-react";
import { apiJSON } from "@/lib/api";

export default function Login({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    document.body.classList.add("login-bg");
    return () => document.body.classList.remove("login-bg");
  }, []);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await apiJSON("/auth/login", {
        method: "POST",
        body: { username: username.trim(), password },
      });
      onSuccess();
    } catch (err) {
      setError(err.message || "Invalid username or password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-between bg-[#e8e4dc] py-14 px-6">
      <div className="flex-1 w-full flex flex-col items-center justify-center">
        <div className="mb-10 select-none">
          <img src="/img/blubridge-logo.webp" alt="BluBridge"
               className="w-auto" draggable={false} />
        </div>

        <form onSubmit={onSubmit} data-testid="login-form" autoComplete="off"
              className="w-full max-w-md bg-[#f8f4ee] rounded-2xl shadow-[0_30px_80px_-30px_rgba(20,20,40,0.25)] p-9">
          <h1 className="text-3xl font-bold text-[#0a1024] text-center">Welcome back</h1>
          <p className="text-sm text-[#0a1024]/55 text-center mt-2 mb-8">
            Sign in to your account to continue
          </p>

          <label className="block mb-5">
            <span className="block text-sm font-medium text-[#0a1024]/80 mb-2">Username</span>
            <div className="flex items-stretch bg-[#efe6e0]/70 border border-transparent focus-within:border-[#0a1024]/30 rounded-lg overflow-hidden transition-colors">
              <span className="grid place-items-center w-12 text-[#0a1024]/45"><User size={16} /></span>
              <input data-testid="login-input-username" type="text"
                     autoComplete="username" spellCheck="false"
                     value={username} onChange={(e) => setUsername(e.target.value)}
                     placeholder="Enter your username"
                     className="flex-1 bg-transparent focus:outline-none py-3 pr-3 text-sm text-[#0a1024] placeholder:text-[#0a1024]/40" />
            </div>
          </label>

          <label className="block mb-2">
            <span className="block text-sm font-medium text-[#0a1024]/80 mb-2">Password</span>
            <div className="flex items-stretch bg-[#efe6e0]/70 border border-transparent focus-within:border-[#0a1024]/30 rounded-lg overflow-hidden transition-colors">
              <span className="grid place-items-center w-12 text-[#0a1024]/45"><Lock size={16} /></span>
              <input data-testid="login-input-password"
                     type={showPwd ? "text" : "password"}
                     autoComplete="current-password" spellCheck="false"
                     value={password} onChange={(e) => setPassword(e.target.value)}
                     placeholder="Enter your password"
                     className="flex-1 bg-transparent focus:outline-none py-3 text-sm text-[#0a1024] placeholder:text-[#0a1024]/40" />
              <button type="button" data-testid="login-toggle-password"
                      onClick={() => setShowPwd((s) => !s)}
                      className="grid place-items-center w-12 text-[#0a1024]/45 hover:text-[#0a1024]/80 transition-colors"
                      aria-label={showPwd ? "Hide password" : "Show password"}>
                {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </label>

          <div className="flex justify-end mb-6">
            <button type="button" data-testid="login-forgot-btn"
                    onClick={() => alert("Please contact your HR administrator to reset the BluBridge HRMS password.")}
                    className="text-sm text-[#1652d6] hover:underline">
              Forgot password?
            </button>
          </div>

          {error ? (
            <div data-testid="login-error"
                 className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          ) : null}

          <button type="submit" disabled={submitting} data-testid="login-submit-btn"
                  className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#0a1024] hover:bg-[#171f3f] disabled:opacity-70 transition-colors text-white text-base font-semibold py-3.5">
            {submitting ? "Signing in…" : "Sign In"}
            {!submitting ? <ArrowRight size={18} /> : null}
          </button>
        </form>
      </div>

      <footer className="mt-10 text-xs text-[#0a1024]/55">
        © 2026 BluBridge HRMS. All rights reserved.
      </footer>
    </div>
  );
}
