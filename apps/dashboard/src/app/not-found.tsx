import Link from "next/link";
import { ArrowLeft, MapPinOff } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return <div className="centered-state"><span className="centered-state-icon"><MapPinOff /></span><span className="eyebrow">404 · workspace route</span><h1>This control-room page does not exist</h1><p>Return to the live camera workspace to continue monitoring.</p><Button asChild><Link href="/"><ArrowLeft />Open live operations</Link></Button></div>;
}
