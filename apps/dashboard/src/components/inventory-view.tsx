"use client";

import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, Boxes, PackageCheck, ScanLine } from "lucide-react";
import { DataBoundary, MetricStrip, SourceBadge } from "@/components/enterprise-shared";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEdgeState } from "@/hooks/use-edge";
import { formatDateTime } from "@/lib/format";

export function InventoryView() {
  const { state } = useEdgeState();
  const movements = state.recentEvents.filter((event) => event.type === "inventory_movement" || event.type === "inventory_variance");
  const total = state.inventory.reduce((sum, item) => sum + item.quantity, 0);
  const lowStock = state.inventory.filter((item) => item.quantity <= 3);
  return <div className="page-shell enterprise-page">
    <PageHeader eyebrow="Operations · Stock assurance" title="Inventory" description="See the retained stock position and camera-observed movements without presenting vision estimates as ERP truth." actions={<><SourceBadge mode="simulated" /><StatusBadge tone="warning" label="Oracle not connected" /></>} />
    <DataBoundary mode="simulated">Tagged demonstration products cross configured stock-in and stock-out lines. Final production reconciliation requires the client inventory master and Oracle integration.</DataBoundary>
    <MetricStrip items={[
      { label: "On-hand quantity", value: String(total), note: `Across ${state.inventory.length} tagged SKUs`, icon: <Boxes /> },
      { label: "Low-stock items", value: String(lowStock.length), note: "Demo threshold ≤ 3", tone: lowStock.length ? "warning" : "safe", icon: <AlertTriangle /> },
      { label: "Loaded movements", value: String(movements.length), note: "Current event ledger", icon: <ScanLine /> },
      { label: "Reconciliation", value: "Pending", note: "Oracle access required", tone: "warning", icon: <PackageCheck /> },
    ]} />
    <section className="inventory-layout">
      <article className="panel enterprise-table-panel"><div className="enterprise-panel-heading"><div><span className="eyebrow">Stock position</span><h2>Tagged inventory items</h2><p>Counts are camera-demo quantities, not posted Oracle balances.</p></div></div><Separator /><Table><TableHeader><TableRow><TableHead>SKU</TableHead><TableHead>Item</TableHead><TableHead>Quantity</TableHead><TableHead>State</TableHead></TableRow></TableHeader><TableBody>{state.inventory.map((item) => <TableRow key={item.sku}><TableCell className="mono">{item.sku}</TableCell><TableCell><strong>{item.label}</strong></TableCell><TableCell className="mono">{item.quantity} {item.unit}</TableCell><TableCell><StatusBadge tone={item.quantity <= 3 ? "warning" : "safe"} label={item.quantity <= 3 ? "Low stock" : "Available"} /></TableCell></TableRow>)}</TableBody></Table></article>
      <aside className="panel movement-summary"><div className="enterprise-panel-heading"><div><span className="eyebrow">Vision counting rule</span><h2>Movement logic</h2><p>Direction is calculated when a visible product tag crosses a calibrated line.</p></div></div><Separator /><div className="movement-rule"><span><ArrowDownToLine /></span><div><strong>Stock in</strong><p>Tag crosses the configured boundary into the inventory zone.</p></div></div><div className="movement-rule"><span><ArrowUpFromLine /></span><div><strong>Stock out</strong><p>Tag crosses the boundary away from the inventory zone.</p></div></div><div className="inline-note">Controlled tagging avoids claiming broad shelf recognition. Production item classes require site-specific data capture and acceptance testing.</div></aside>
    </section>
    <section className="panel enterprise-table-panel department-ledger"><div className="enterprise-panel-heading"><div><span className="eyebrow">Movement ledger</span><h2>Recent stock events</h2></div></div><Table><TableHeader><TableRow><TableHead>Movement</TableHead><TableHead>Employee</TableHead><TableHead>Status</TableHead><TableHead>Source</TableHead><TableHead>Occurred</TableHead></TableRow></TableHeader><TableBody>{movements.length ? movements.map((event) => <TableRow key={event.id}><TableCell><strong>{event.title}</strong><small>{event.detail}</small></TableCell><TableCell>{event.employeeName ?? "System"}</TableCell><TableCell><StatusBadge tone={event.type === "inventory_variance" ? "critical" : "safe"} label={event.type === "inventory_variance" ? "Variance" : "Recorded"} /></TableCell><TableCell><SourceBadge mode={event.sourceMode} /></TableCell><TableCell><time className="mono" dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time></TableCell></TableRow>) : <TableRow><TableCell colSpan={5}><div className="enterprise-empty"><Boxes /><strong>No movement records loaded</strong><span>Move a tagged item across the inventory line or use Tools for a simulated movement.</span></div></TableCell></TableRow>}</TableBody></Table></section>
  </div>;
}
