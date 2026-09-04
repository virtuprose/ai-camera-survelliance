import Image from "next/image";
import { PRODUCT_LINE, PRODUCT_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function BrandLockup({ className }: { className?: string }) {
  return (
    <div className={cn("brand-lockup", className)} aria-label={PRODUCT_NAME}>
      <span className="orvia-logo-lockup">
        <Image className="orvia-logo" src="/brand/orvia-logo.png" width={100} height={28} alt="ORVIA" priority />
        <sup aria-label="Trademark">TM</sup>
      </span>
      <span className="brand-product-copy">
        <strong>{PRODUCT_LINE}</strong>
      </span>
    </div>
  );
}
