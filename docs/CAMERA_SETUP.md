# Camera setup

## FaceTime camera

1. Open **System Settings → Privacy & Security → Camera**.
2. Allow camera access for the terminal/application running the edge service.
3. Run `bun run camera:soak`; the required acceptance duration is 10 minutes now and 30 minutes before presentation.
4. Create `services/edge/.env` from `.env.example`; keep `CAMERA_KIND=avfoundation` and `CAMERA_SOURCE=0`.

## FaceTime and Camo runtime selection

The local demo can change between the built-in FaceTime camera and an iPhone supplied through Camo Studio without restarting either service.

1. For Camo, open Camo Studio and confirm the iPhone preview is moving before the meeting. Camo Camera must appear in the macOS camera list.
2. Start the standard local path with `bun run local`; camera analysis and the dashboard start together.
3. Open **Live Operations** and select **Change source** in the camera command bar.
4. Choose **FaceTime HD Camera** or **Camo Camera**. The requested camera must produce a fresh frame before the edge service commits the change.
5. Confirm the selected source shows **Active**, camera status is **Online**, processed FPS rises above zero, and **Last frame** remains fresh.

If Camo is registered but Camo Studio or the iPhone is not providing frames, the switch is rejected and FaceTime remains active. Camera indexes may change while macOS opens and releases virtual cameras; the demo tracks the stable camera label rather than assuming a permanent numeric index. Camera audio is never captured.

## TP-Link VIGI C340-W (4 mm)

1. Use a unique camera administrator password and reserve the camera IP in the LAN router.
2. Keep the camera on the local LAN; do not expose RTSP port 554 to the internet.
3. Disable audio, set H.264, 1920×1080, 15 fps, fixed exposure where possible, and a fixed mounting position.
4. Verify the high-quality stream in VLC: `rtsp://USERNAME:PASSWORD@CAMERA_IP:554/stream1`.
5. Set the edge `.env` values:

```dotenv
CAMERA_KIND=rtsp
CAMERA_SOURCE=rtsp://USERNAME:PASSWORD@CAMERA_IP:554/stream1
CAMERA_LABEL=VIGI C340-W Kitchen 01
CAMERA_WIDTH=1280
CAMERA_HEIGHT=720
CAMERA_FPS=15
```

6. Restart the edge service, redraw normalized zones if the camera angle changed, and run the full scenario plus 30-minute soak.

The password stays only in ignored `.env`; never commit or display it in screenshots.
