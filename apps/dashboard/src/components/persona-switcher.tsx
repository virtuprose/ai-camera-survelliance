"use client";

import { Eye, UserRoundCog } from "lucide-react";
import { useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useEnterprise } from "@/hooks/use-enterprise";
import type { DemoPersona } from "@/lib/types";

const labels: Record<DemoPersona, string> = {
  executive: "Executive",
  qa_supervisor: "QA Supervisor",
  operations: "Operations",
  it: "IT",
};

export function PersonaSwitcher({ compact = false }: { compact?: boolean }) {
  const { persona, setPersona } = useEnterprise();
  const [open, setOpen] = useState(false);
  return <div className={compact ? "persona-switcher is-compact" : "persona-switcher"}>
    {!compact && <span><Eye aria-hidden="true" />View as · Demo</span>}
    <Select open={open} onOpenChange={setOpen} value={persona} onValueChange={(value) => setPersona(value as DemoPersona)}>
      <SelectTrigger aria-label="Change demo view"><UserRoundCog aria-hidden="true" /><SelectValue /></SelectTrigger>
      <SelectContent>{Object.entries(labels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
    </Select>
  </div>;
}
