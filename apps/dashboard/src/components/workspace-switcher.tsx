"use client";

import { Check, ChevronDown, CookingPot, Package, Snowflake, Truck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { useEnterprise } from "@/hooks/use-enterprise";

const icons = { production: CookingPot, receiving: Truck, cold_chain: Snowflake, inventory: Package } as const;
const routeByDepartment = { production: "/live", receiving: "/inventory", cold_chain: "/cold-chain", inventory: "/inventory" } as const;

export function WorkspaceSwitcher({ mobile = false }: { mobile?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { context, workspaceId, setWorkspaceId } = useEnterprise();
  const active = context.workspaces.find((item) => item.id === workspaceId) ?? context.workspaces[0];
  const activeSite = context.sites.find((site) => site.id === active?.siteId) ?? context.sites[0];
  function choose(id: string, departmentType: string) {
    setWorkspaceId(id);
    setOpen(false);
    router.push(routeByDepartment[departmentType as keyof typeof routeByDepartment] ?? "/");
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          className="workspace-trigger"
          variant="outline"
          aria-label="Change active workspace"
        >
          <span className="workspace-status-dot" aria-hidden="true" />
          <span className="workspace-trigger-copy">
            <small>Active workspace</small>
            <strong>{active?.name ?? "Kitchen 01"}</strong>
          </span>
          <span className="workspace-trigger-meta">
            <span className="mono">{active?.mode === "live" ? active.deviceCode : "SIM"}</span>
            <ChevronDown aria-hidden="true" />
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="workspace-popover" align={mobile ? "center" : "start"} sideOffset={8} aria-label="Operational workspaces">
        <PopoverHeader>
          <PopoverTitle>Operational workspaces</PopoverTitle>
          <PopoverDescription>{activeSite.name} · select a live or simulated department.</PopoverDescription>
        </PopoverHeader>
        <ul className="workspace-list" aria-label="Available workspaces">
          {context.workspaces.map((workspace) => {
            const Icon = icons[workspace.departmentType as keyof typeof icons] ?? CookingPot;
            const selected = workspace.id === workspaceId;
            return <li key={workspace.id}>
              <button type="button" className="workspace-option" onClick={() => choose(workspace.id, workspace.departmentType)} aria-current={selected ? "true" : undefined}>
                <span className="workspace-option-icon"><Icon aria-hidden="true" /></span>
                <span className="workspace-option-copy"><strong>{workspace.name}</strong><small>{workspace.deviceCode ?? workspace.departmentType.replaceAll("_", " ")}</small></span>
                <span className={workspace.mode === "live" ? "workspace-option-state is-active" : "workspace-option-state tone-simulated"}>{selected && <Check aria-hidden="true" />}{workspace.mode}</span>
              </button>
            </li>
          })}
          {context.sites.filter((site) => site.mode === "planned").map((site) => <li key={site.id}><button type="button" className="workspace-option" disabled><span className="workspace-option-icon"><CookingPot /></span><span className="workspace-option-copy"><strong>{site.name}</strong><small>Future facility</small></span><span className="workspace-option-state">Planned</span></button></li>)}
        </ul>
        <p className="workspace-note">Simulated departments are interactive demonstration environments. Planned facilities contain no operational data.</p>
      </PopoverContent>
    </Popover>
  );
}
