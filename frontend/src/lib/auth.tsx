"use client";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setCsrfToken, setUnauthorizedHandler } from "./api";

interface AuthState {
  email: string | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const toLogin = useCallback(() => {
    setCsrfToken(null);
    setEmail(null);
    const next = pathname && pathname !== "/login" ? `?next=${encodeURIComponent(pathname)}` : "";
    router.replace(`/login${next}`);
  }, [pathname, router]);

  useEffect(() => {
    setUnauthorizedHandler(toLogin);
    return () => setUnauthorizedHandler(null);
  }, [toLogin]);

  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((s) => {
        if (!alive) return;
        setCsrfToken(s.csrf_token);
        setEmail(s.email);
        setLoading(false);
      })
      .catch(() => {
        if (alive) toLogin();
      });
    return () => {
      alive = false;
    };
    // run once when the protected shell mounts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signIn = useCallback(async (e: string, p: string) => {
    const s = await api.login(e, p);
    setCsrfToken(s.csrf_token);
    setEmail(s.email);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setCsrfToken(null);
      setEmail(null);
      router.replace("/login");
    }
  }, [router]);

  const value = useMemo(() => ({ email, loading, signIn, signOut }), [email, loading, signIn, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
