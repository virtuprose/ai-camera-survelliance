"use client";

import { BellOff, BellRing, Volume2 } from "lucide-react";
import { useAlertSound } from "@/components/alert-sound-provider";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";

export function AlertSoundControl() {
  const { enabled, armed, supported, setEnabled, testSound } = useAlertSound();
  const label = !enabled ? "Violation sound off" : armed ? "Violation sound on" : "Sound on · awaiting interaction";
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button className="sound-trigger" variant="outline" size="sm" aria-label={label} title={label}>
          {enabled ? <BellRing /> : <BellOff />}
          <span className="sound-trigger-label">{enabled ? "Sound on" : "Sound off"}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="sound-popover" align="end">
        <div className="sound-popover-intro">
          <span className="popover-icon"><BellRing /></span>
          <div><strong>Violation alert sound</strong><p>One quiet chime for new PPE or unsafe-temperature violations.</p></div>
        </div>
        <div className="sound-setting-row">
          <label htmlFor="violation-sound">Play alert chime</label>
          <Switch id="violation-sound" checked={enabled} disabled={!supported} onCheckedChange={setEnabled} />
        </div>
        <Button variant="outline" className="w-full" disabled={!enabled || !supported} onClick={() => void testSound()}>
          <Volume2 /> Test sound
        </Button>
        <p className="sound-help">{!supported ? "This browser does not support Web Audio." : enabled && !armed ? "Interact once with the page to arm browser audio." : "Camera audio recording remains disabled."}</p>
      </PopoverContent>
    </Popover>
  );
}
