import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PRODUCT_NAME } from "@/lib/brand";
import "./globals.css";

export const metadata: Metadata = {
  title: `${PRODUCT_NAME} — Food Safety Control Room`,
  description: `${PRODUCT_NAME} controlled single-camera food-safety operations demonstration.`,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <TooltipProvider delayDuration={250}><AppShell>{children}</AppShell></TooltipProvider>
      </body>
    </html>
  );
}
