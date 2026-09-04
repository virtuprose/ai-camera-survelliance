"use client";

import { FormEvent, useEffect, useState } from "react";
import { LockKeyhole, ShieldCheck } from "lucide-react";
import { BrandLockup } from "@/components/brand-lockup";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { PRODUCT_NAME } from "@/lib/brand";

type AuthState = "disabled" | "loading" | "signed-out" | "signed-in";

export function CloudAuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>(() => isSupabaseConfigured() ? "loading" : "disabled");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const client = getSupabaseBrowserClient();
    if (!client) return;
    void client.auth.getSession().then(({ data }) => setState(data.session ? "signed-in" : "signed-out"));
    const { data } = client.auth.onAuthStateChange((_event, session) => setState(session ? "signed-in" : "signed-out"));
    return () => data.subscription.unsubscribe();
  }, []);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const client = getSupabaseBrowserClient();
    if (!client) return;
    setSubmitting(true); setMessage(null);
    const { error } = await client.auth.signInWithPassword({ email, password });
    setSubmitting(false);
    if (error) setMessage("Sign-in failed. Check the supervisor account and try again.");
  }

  if (state === "disabled" || state === "signed-in") return children;
  if (state === "loading") return <div className="auth-loading" role="status"><span className="auth-loading-mark"><ShieldCheck /></span><strong>Securing operations workspace</strong><span>Checking the cloud session…</span></div>;

  return <main className="auth-page"><BrandLockup className="auth-brand" /><Card className="auth-panel"><CardHeader><span className="eyebrow">Protected operations workspace</span><CardTitle>Sign in to {PRODUCT_NAME}</CardTitle><CardDescription>Use the supervisor account configured in the connected Supabase project.</CardDescription></CardHeader><CardContent><form onSubmit={(event) => void signIn(event)}><label htmlFor="auth-email">Email</label><Input id="auth-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /><label htmlFor="auth-password">Password</label><Input id="auth-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />{message && <Alert variant="destructive"><LockKeyhole /><AlertTitle>Could not sign in</AlertTitle><AlertDescription>{message}</AlertDescription></Alert>}<Button type="submit" size="lg" disabled={submitting}><LockKeyhole />{submitting ? "Signing in…" : "Sign in securely"}</Button></form><p className="auth-footnote">Local camera processing continues if this browser session ends.</p></CardContent></Card></main>;
}
