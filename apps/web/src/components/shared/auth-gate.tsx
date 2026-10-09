"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearAuthTokens, fetchWithAuth, buildAuthHeaders, getStoredAccessToken } from "@/lib/auth";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [state, setState] = useState<"checking" | "open" | "authenticated" | "error">("checking");

  useEffect(() => {
    let active = true;
    const login = () => {
      setState("checking");
      router.replace(`/login?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    };
    const check = async () => {
      setState("checking");
      try {
        const healthResponse = await fetch("/api/health", { credentials: "include" });
        if (!healthResponse.ok) throw new Error("Unavailable");
        const health = await healthResponse.json() as { auth_enabled?: boolean };
        if (typeof health.auth_enabled !== "boolean") throw new Error("Missing auth configuration");
        if (!active) return;
        if (!health.auth_enabled) { setState("open"); return; }
        if (pathname === "/login") { setState("open"); return; }
        if (!getStoredAccessToken()) { login(); return; }
        const response = await fetchWithAuth("/api/auth/me", { headers: buildAuthHeaders(), credentials: "include" });
        if (!active) return;
        if (response.status === 401) { login(); return; }
        if (!response.ok) throw new Error("Unavailable");
        setState("authenticated");
      } catch {
        if (active) setState("error");
      }
    };
    void check();
    window.addEventListener("opentutor:logout", login);
    return () => { active = false; window.removeEventListener("opentutor:logout", login); };
  }, [pathname, router]);

  if (state === "error") return <div className="mx-auto max-w-md p-8" role="alert">无法连接服务，请稍后重试。<button className="ml-3 underline" onClick={() => window.location.reload()}>重试</button></div>;
  if (state === "checking") return <div className="p-8" role="status">正在检查登录状态…</div>;
  return <>{state === "authenticated" && <div className="flex justify-end border-b px-4 py-2"><button type="button" className="text-sm underline" onClick={clearAuthTokens}>退出登录</button></div>}{children}</>;
}
