"use client";

import { useCallback, useState } from "react";
import { Check, ChevronsUpDown, Laptop, LoaderCircle, Monitor, RefreshCw, Smartphone, Video, VideoOff } from "lucide-react";
import { toast } from "sonner";
import { getCameraCatalog, selectCamera } from "@/hooks/use-edge";
import type { CameraCatalog, CameraOption } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";

function SourceIcon({ option }: { option: CameraOption }) {
  if (option.id === "camo") return <Smartphone aria-hidden="true" />;
  if (option.id === "facetime") return <Laptop aria-hidden="true" />;
  if (option.kind === "avfoundation" && /samsung|monitor|display|slimfit/i.test(option.label)) return <Monitor aria-hidden="true" />;
  if (option.kind === "avfoundation") return <Video aria-hidden="true" />;
  return <VideoOff aria-hidden="true" />;
}

interface CameraSourceControlProps {
  activeId: string;
  currentLabel: string;
  disabled?: boolean;
  onSwitched: () => Promise<void> | void;
}

export function CameraSourceControl({ activeId, currentLabel, disabled, onSwitched }: CameraSourceControlProps) {
  const [open, setOpen] = useState(false);
  const [catalog, setCatalog] = useState<CameraCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const detectedCameraCount = catalog?.options.filter((option) => option.kind === "avfoundation" && option.registered).length ?? 0;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCatalog(await getCameraCatalog());
      setMessage(null);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Camera sources could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (nextOpen) void load();
  }

  async function switchTo(option: CameraOption) {
    if (option.active || !option.registered || switchingId) return;
    setSwitchingId(option.id);
    setMessage(`Checking ${option.label} for a fresh frame…`);
    try {
      const next = await selectCamera(option.id);
      setCatalog(next);
      setMessage(next.message ?? `${option.label} is active.`);
      await onSwitched();
      toast.success(`${option.label} is now active`, {
        description: "The live preview and edge analysis have moved to this source.",
      });
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Camera switch failed.";
      toast.error("Camera source unchanged", { description: detail });
      await load();
      setMessage(detail);
    } finally {
      setSwitchingId(null);
    }
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          className="camera-source-trigger"
          variant="ghost"
          size="sm"
          disabled={disabled}
          aria-label={`Change camera source. Current source: ${currentLabel}`}
        >
          Change source <ChevronsUpDown aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="camera-source-popover" align="start" sideOffset={8} aria-label="Camera source selection">
        <PopoverHeader>
          <PopoverTitle>Camera source</PopoverTitle>
          <PopoverDescription>
            Select any camera currently exposed to macOS for live preview and local AI analysis.
          </PopoverDescription>
        </PopoverHeader>

        {catalog && !loading && (
          <p className="camera-source-summary" role="status">
            {detectedCameraCount === 0
              ? "No connected cameras detected by macOS."
              : `${detectedCameraCount} connected ${detectedCameraCount === 1 ? "camera" : "cameras"} detected by macOS.`}
          </p>
        )}

        <div className="camera-source-list" aria-live="polite" aria-busy={loading || Boolean(switchingId)}>
          {loading && !catalog ? (
            <div className="camera-source-loading"><LoaderCircle className="spin" />Checking connected cameras…</div>
          ) : catalog?.options.map((option) => {
            const isActive = option.id === (catalog.activeId || activeId);
            const isSwitching = switchingId === option.id;
            return (
              <button
                type="button"
                className={`camera-source-option${isActive ? " is-active" : ""}`}
                key={option.id}
                onClick={() => void switchTo(option)}
                disabled={isActive || !option.registered || Boolean(switchingId)}
                aria-current={isActive ? "true" : undefined}
              >
                <span className="camera-source-icon"><SourceIcon option={option} /></span>
                <span className="camera-source-copy">
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
                <span className={`camera-source-state${!option.registered ? " is-unavailable" : ""}`}>
                  {isSwitching ? <><LoaderCircle className="spin" />Switching</> : isActive ? <><Check />Active</> : option.registered ? "Available" : "Unavailable"}
                </span>
              </button>
            );
          })}
        </div>

        {message && <p className="camera-source-message" role="status">{message}</p>}
        <div className="camera-source-note">
          <VideoOff aria-hidden="true" />
          <span>A new source must provide a fresh frame before it replaces the current feed. Camera audio remains disabled.</span>
        </div>
        <div className="camera-source-note camera-source-help">
          <Monitor aria-hidden="true" />
          <span>Missing a monitor camera? Connect its USB data or USB-C cable and allow camera access in macOS. HDMI or DisplayPort alone usually does not expose the webcam.</span>
        </div>
        <Button className="camera-source-refresh" variant="ghost" size="sm" onClick={() => void load()} disabled={loading || Boolean(switchingId)}>
          <RefreshCw className={loading ? "spin" : undefined} />Refresh cameras
        </Button>
      </PopoverContent>
    </Popover>
  );
}
