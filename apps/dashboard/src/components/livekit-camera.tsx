"use client";

import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track } from "livekit-client";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

export function LiveKitCamera() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [message, setMessage] = useState("Connecting to secure cloud video…");

  useEffect(() => {
    const room = new Room({ adaptiveStream: true, dynacast: true });
    let cancelled = false;

    async function connect() {
      const supabase = getSupabaseBrowserClient();
      const session = supabase ? (await supabase.auth.getSession()).data.session : null;
      if (!session) throw new Error("A cloud session is required for video.");
      const response = await fetch("/api/livekit/token", {
        method: "POST",
        headers: { authorization: `Bearer ${session.access_token}` },
      });
      if (!response.ok) throw new Error("Cloud video token could not be issued.");
      const payload = await response.json() as { token: string; serverUrl: string };

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Video && videoRef.current) {
          track.attach(videoRef.current);
          setMessage("");
        }
      });
      await room.connect(payload.serverUrl, payload.token);
      if (!cancelled) setMessage("Waiting for Camera 01 to publish…");
    }

    void connect().catch((error: unknown) => {
      if (!cancelled) setMessage(error instanceof Error ? error.message : "Cloud video unavailable.");
    });
    return () => {
      cancelled = true;
      void room.disconnect();
    };
  }, []);

  return (
    <div className="livekit-video">
      <video ref={videoRef} autoPlay muted playsInline aria-label="Live annotated cloud video from Camera 01" />
      {message && <span role="status">{message}</span>}
    </div>
  );
}
