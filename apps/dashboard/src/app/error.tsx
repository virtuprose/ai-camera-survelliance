"use client";

import { CircleAlert, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="centered-state"><span className="centered-state-icon is-critical"><CircleAlert /></span><span className="eyebrow">Connection recovery</span><h1>The control room could not load</h1><p>The camera and stored events are safe. Retry the dashboard connection.</p><Button onClick={reset}><RotateCw />Retry dashboard</Button></div>;
}
