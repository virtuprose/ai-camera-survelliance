from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable

import cv2
import numpy as np

from .settings import Settings

logger = logging.getLogger(__name__)


class LiveKitPublisher:
    """Publish annotated silent frames as a backend-generated LiveKit track."""

    def __init__(self, settings: Settings, frame_provider: Callable[[], np.ndarray | None]):
        self.settings = settings
        self.frame_provider = frame_provider
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.online = False
        self.last_error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.livekit_url and self.settings.livekit_api_key and self.settings.livekit_api_secret
        )

    def start(self) -> None:
        if not self.configured:
            return
        self.thread = threading.Thread(target=self._thread_main, name="livekit-publisher", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._publish())
        except Exception as error:
            self.online = False
            self.last_error = str(error)
            logger.exception("LiveKit publishing stopped")

    async def _publish(self) -> None:
        from livekit import api, rtc

        token = (
            api.AccessToken(self.settings.livekit_api_key, self.settings.livekit_api_secret)
            .with_identity("edge-CAM-01")
            .with_name("Kitchen 01 annotated camera")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=self.settings.livekit_room,
                    can_publish=True,
                    can_subscribe=False,
                )
            )
            .to_jwt()
        )
        room = rtc.Room()
        await room.connect(self.settings.livekit_url, token)
        source = rtc.VideoSource(self.settings.camera_width, self.settings.camera_height)
        track = rtc.LocalVideoTrack.create_video_track("camera-01-annotated", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA, simulcast=False)
        await room.local_participant.publish_track(track, options)
        self.online = True
        self.last_error = None
        period = 1 / max(1, self.settings.process_fps)
        try:
            while not self.stop_event.is_set():
                frame = self.frame_provider()
                if frame is None:
                    await asyncio.sleep(period)
                    continue
                rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                video_frame = rtc.VideoFrame(
                    self.settings.camera_width,
                    self.settings.camera_height,
                    rtc.VideoBufferType.RGBA,
                    rgba.tobytes(),
                )
                source.capture_frame(video_frame)
                await asyncio.sleep(period)
        finally:
            self.online = False
            await room.disconnect()
