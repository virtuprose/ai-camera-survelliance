"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ALERT_SOUND_STORAGE_KEY, unseenViolations } from "@/lib/alert-sound";
import { useEvents } from "@/hooks/use-edge";

interface AlertSoundContextValue {
  enabled: boolean;
  armed: boolean;
  supported: boolean;
  setEnabled: (enabled: boolean) => void;
  testSound: () => Promise<boolean>;
}

const AlertSoundContext = createContext<AlertSoundContextValue | null>(null);

type AudioWindow = Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext };

export function AlertSoundProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { events, connected } = useEvents();
  const [enabled, setEnabledState] = useState(false);
  const [armed, setArmed] = useState(false);
  const [supported, setSupported] = useState(true);
  const [announcement, setAnnouncement] = useState("");
  const audioContextRef = useRef<AudioContext | null>(null);
  const initializedRef = useRef(false);
  const seenIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const initial = window.setTimeout(() => {
      const audioWindow = window as AudioWindow;
      setSupported(Boolean(window.AudioContext || audioWindow.webkitAudioContext));
      setEnabledState(window.localStorage.getItem(ALERT_SOUND_STORAGE_KEY) === "true");
    }, 0);
    return () => window.clearTimeout(initial);
  }, []);

  const ensureAudioContext = useCallback(async () => {
    const audioWindow = window as AudioWindow;
    const AudioContextConstructor = window.AudioContext || audioWindow.webkitAudioContext;
    if (!AudioContextConstructor) {
      setSupported(false);
      return null;
    }
    const context = audioContextRef.current ?? new AudioContextConstructor();
    audioContextRef.current = context;
    if (context.state === "suspended") await context.resume();
    setArmed(context.state === "running");
    return context;
  }, []);

  const testSound = useCallback(async () => {
    try {
      const context = await ensureAudioContext();
      if (!context) return false;
      const now = context.currentTime;
      const gain = context.createGain();
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.linearRampToValueAtTime(0.04, now + 0.018);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.26);
      gain.connect(context.destination);

      const first = context.createOscillator();
      first.type = "sine";
      first.frequency.setValueAtTime(660, now);
      first.connect(gain);
      first.start(now);
      first.stop(now + 0.12);

      const second = context.createOscillator();
      second.type = "sine";
      second.frequency.setValueAtTime(880, now + 0.13);
      second.connect(gain);
      second.start(now + 0.13);
      second.stop(now + 0.26);
      setArmed(true);
      return true;
    } catch {
      setArmed(false);
      return false;
    }
  }, [ensureAudioContext]);

  const setEnabled = useCallback((next: boolean) => {
    setEnabledState(next);
    window.localStorage.setItem(ALERT_SOUND_STORAGE_KEY, String(next));
    if (next) {
      void testSound().then((played) => {
        if (!played) toast.warning("Sound needs permission", { description: "Use Test sound after interacting with the page." });
      });
    } else {
      setArmed(false);
    }
  }, [testSound]);

  useEffect(() => {
    if (!enabled || armed) return;
    const arm = () => void ensureAudioContext();
    window.addEventListener("pointerdown", arm, { once: true });
    window.addEventListener("keydown", arm, { once: true });
    return () => {
      window.removeEventListener("pointerdown", arm);
      window.removeEventListener("keydown", arm);
    };
  }, [armed, enabled, ensureAudioContext]);

  useEffect(() => {
    if (!connected) return;
    if (!initializedRef.current) {
      seenIdsRef.current = new Set(events.map((event) => event.id));
      initializedRef.current = true;
      return;
    }
    const violations = unseenViolations(events, seenIdsRef.current);
    events.forEach((event) => seenIdsRef.current.add(event.id));
    const newest = violations[0];
    if (!newest) return;

    const source = newest.sourceMode === "simulated" ? "Simulated violation" : "New violation";
    setAnnouncement(`${source}: ${newest.title}`);
    toast.error(newest.title, {
      description: `${newest.zone ?? "System"} · ${source}`,
      action: { label: "Review", onClick: () => router.push("/events") },
      duration: 7_000,
    });
    if (enabled) void testSound();
  }, [connected, enabled, events, router, testSound]);

  useEffect(() => () => { void audioContextRef.current?.close(); }, []);

  const value = useMemo(() => ({ enabled, armed, supported, setEnabled, testSound }), [enabled, armed, supported, setEnabled, testSound]);
  return (
    <AlertSoundContext.Provider value={value}>
      {children}
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
    </AlertSoundContext.Provider>
  );
}

export function useAlertSound() {
  const context = useContext(AlertSoundContext);
  if (!context) throw new Error("useAlertSound must be used within AlertSoundProvider");
  return context;
}
