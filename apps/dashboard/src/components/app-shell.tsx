"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BellRing, Boxes, ChartNoAxesCombined, ClipboardCheck, Gauge, Menu, Radio, ShieldCheck, SlidersHorizontal, Thermometer, UsersRound } from "lucide-react";
import { AlertSoundControl } from "@/components/alert-sound-control";
import { AlertSoundProvider } from "@/components/alert-sound-provider";
import { BrandLockup } from "@/components/brand-lockup";
import { CloudAuthGate } from "@/components/cloud-auth-gate";
import { PersonaSwitcher } from "@/components/persona-switcher";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Toaster } from "@/components/ui/sonner";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { EnterpriseDataProvider, useEnterprise } from "@/hooks/use-enterprise";
import { OperationsDataProvider, useEdgeState } from "@/hooks/use-edge";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const navigation = [
  { group: "Monitor", href: "/", label: "Command center", short: "Overview", icon: Gauge, roles: ["executive", "qa_supervisor", "operations", "it"] },
  { group: "Monitor", href: "/live", label: "Live operations", short: "Live", icon: Radio, roles: ["operations", "qa_supervisor"] },
  { group: "Assurance", href: "/food-safety", label: "Food safety & PPE", short: "Food safety", icon: ShieldCheck, roles: ["qa_supervisor"] },
  { group: "Assurance", href: "/processes", label: "Process assurance", short: "Processes", icon: ClipboardCheck, roles: ["qa_supervisor", "operations"] },
  { group: "Operations", href: "/staff", label: "Staff visibility", short: "Staff", icon: UsersRound, roles: ["executive", "qa_supervisor", "operations"] },
  { group: "Operations", href: "/cold-chain", label: "Cold chain", short: "Cold chain", icon: Thermometer, roles: ["operations", "qa_supervisor"] },
  { group: "Operations", href: "/inventory", label: "Inventory", short: "Inventory", icon: Boxes, roles: ["operations"] },
  { group: "Assurance", href: "/incidents", label: "Incidents & evidence", short: "Incidents", icon: BellRing, roles: ["executive", "qa_supervisor", "operations"] },
  { group: "Assurance", href: "/reports", label: "Reports & audit", short: "Reports", icon: ChartNoAxesCombined, roles: ["executive", "qa_supervisor"] },
  { group: "Administration", href: "/platform", label: "Platform", short: "Platform", icon: SlidersHorizontal, roles: ["it"] },
] as const;

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  const { persona } = useEnterprise();
  const visible = navigation.filter((item) => (item.roles as readonly string[]).includes(persona));
  return <nav className={mobile ? "mobile-nav-list" : "sidebar-nav"} aria-label={mobile ? "Mobile navigation" : "Primary navigation"}>{visible.map(({ group, href, label, icon: Icon }, index) => {
    const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
    const showGroup = index === 0 || visible[index - 1]?.group !== group;
    return <span className="nav-entry" key={href}>{showGroup && <span className="nav-group-label">{group}</span>}<Link className={cn("nav-link", active && "is-active")} href={href} aria-current={active ? "page" : undefined}><Icon aria-hidden="true" /><span>{label}</span></Link></span>;
  })}</nav>;
}

function ShellFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const current = navigation.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)) ?? navigation[0];
  const { state, connected } = useEdgeState();
  const { context, workspaceId } = useEnterprise();
  const workspace = context.workspaces.find((item) => item.id === workspaceId) ?? context.workspaces[0];
  return <div className="app-shell">
    <aside className="app-sidebar"><BrandLockup /><WorkspaceSwitcher /><Navigation /><PersonaSwitcher /></aside>
    <div className="app-content">
      <header className="app-topbar">
        <div className="topbar-context"><Sheet><SheetTrigger asChild><Button className="mobile-menu-button" variant="outline" size="icon" aria-label="Open navigation"><Menu /></Button></SheetTrigger><SheetContent side="left" className="mobile-navigation-sheet"><SheetHeader><SheetTitle><BrandLockup /></SheetTitle><SheetDescription>{context.organization.name} enterprise workspace</SheetDescription></SheetHeader><Separator /><WorkspaceSwitcher mobile /><PersonaSwitcher /><Navigation mobile /></SheetContent></Sheet><div><span>{workspace.name} · {context.activeShift.name}</span><strong>{current.short}</strong></div></div>
        <div className="topbar-actions"><span className="freshness-label">Updated {formatRelative(state.health.updatedAt)}</span><StatusBadge tone={connected ? "safe" : "critical"} label={connected ? "Edge online" : "Edge offline"} /><AlertSoundControl /></div>
      </header>
      <main id="main-content">{children}</main>
    </div>
    <Toaster theme="light" position="top-right" richColors closeButton />
  </div>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return <CloudAuthGate><OperationsDataProvider><EnterpriseDataProvider><AlertSoundProvider><ShellFrame>{children}</ShellFrame></AlertSoundProvider></EnterpriseDataProvider></OperationsDataProvider></CloudAuthGate>;
}
