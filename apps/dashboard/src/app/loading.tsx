import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return <div className="page-shell loading-state" aria-live="polite" aria-busy="true"><div className="loading-heading"><Skeleton /><Skeleton /></div><div className="loading-workspace"><Skeleton /><div><Skeleton /><Skeleton /><Skeleton /></div></div><span className="sr-only">Loading control room</span></div>;
}
