"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { safeReturnPath, storeAuthTokens, type AuthTokens } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        setError(response.status === 401 || response.status === 403 ? "邮箱或密码不正确，或账户不可用。" : "登录服务暂时不可用，请稍后重试。");
        return;
      }
      const tokens = await response.json() as AuthTokens;
      if (!tokens.access_token || !tokens.refresh_token) throw new Error("Invalid session");
      storeAuthTokens(tokens);
      router.replace(safeReturnPath(new URLSearchParams(window.location.search).get("returnTo")));
    } catch { setError("登录服务暂时不可用，请稍后重试。"); }
    finally { setPassword(""); setBusy(false); }
  }
  return <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
    <form onSubmit={submit} className="w-full max-w-md space-y-6 rounded-2xl border bg-card p-6 sm:p-8">
      <div><h1 className="text-2xl font-semibold">登录刷题工作台</h1><p className="mt-2 text-sm text-muted-foreground">使用你的学生账户登录。</p></div>
      <div className="space-y-2"><label htmlFor="email">邮箱</label><input id="email" type="email" required autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} className="w-full rounded-lg border bg-background p-3" /></div>
      <div className="space-y-2"><label htmlFor="password">密码</label><input id="password" type="password" required autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} className="w-full rounded-lg border bg-background p-3" /></div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <button type="submit" disabled={busy} className="w-full rounded-lg bg-primary p-3 font-medium text-primary-foreground disabled:opacity-50">{busy ? "正在登录…" : "登录"}</button>
    </form>
  </div>;
}
