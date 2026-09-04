"use client";

import { RotateCw } from "lucide-react";
import { PRODUCT_NAME } from "@/lib/brand";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <html lang="en"><body><main className="centered-state"><span className="eyebrow">Safe recovery</span><h1>{PRODUCT_NAME} needs to restart</h1><p>No events have been deleted. Reload the application to reconnect.</p><button className="fallback-button" onClick={reset}><RotateCw />Reload application</button></main></body></html>;
}
