import asyncio
import threading
from contextlib import asynccontextmanager

import cv2
import numpy as np
import uvicorn
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from av import VideoFrame
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from insightface.app import FaceAnalysis
from pydantic import BaseModel

CAMERA_INDEX = 0
DETECTION_SIZE = (640, 640)


# holds the latest frame, we use a locking mechanism in order to do this
class LatestFrame:
    def __init__(self) -> None:
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()

    def set(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame.copy()

    def get(self) -> np.ndarray | None:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()


class CameraWorker:
    """Capture and annotate frames without blocking FastAPI's event loop."""

    def __init__(self, output: LatestFrame) -> None:
        self.output = output
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        detector = FaceAnalysis(allowed_modules=["detection"])
        detector.prepare(ctx_id=0, det_size=DETECTION_SIZE)

        camera = cv2.VideoCapture(CAMERA_INDEX)
        if not camera.isOpened():
            print(f"Could not open camera at index {CAMERA_INDEX}")
            return

        print("Camera and face detection are running.")

        try:
            while not self._stop_event.is_set():
                ok, frame = camera.read()
                if not ok:
                    print("Could not read a frame from the camera.")
                    break

                faces = detector.get(frame)

                for face in faces:
                    x1, y1, x2, y2 = face.bbox.astype(int)
                    confidence = float(face.det_score)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        frame,
                        f"face {confidence:.2f}",
                        (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                        cv2.LINE_AA,
                    )

                self.output.set(frame)
        finally:
            camera.release()


# a track that we can send over to the frontend via WebRTC
# We must extend VideoStreamTrack as that is what the library we are using sends
class CameraVideoTrack(VideoStreamTrack):
    def __init__(self, latest_frame: LatestFrame) -> None:
        super().__init__()
        self.latest_frame = latest_frame

    # aiortc calls recv whenever it needs the next frame to encode and send.
    async def recv(self) -> VideoFrame:
        frame = self.latest_frame.get()
        while frame is None:
            await asyncio.sleep(0.01)
            frame = self.latest_frame.get()

        pts, time_base = await self.next_timestamp()
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


latest_frame = LatestFrame()
camera_worker = CameraWorker(latest_frame)
peer_connections: set[RTCPeerConnection] = set()


class WebRTCOffer(BaseModel):
    sdp: str
    type: str


# this starts/cleans up the camera worker along with the server.
@asynccontextmanager
async def lifespan(app: FastAPI):
    camera_worker.start()
    try:
        yield
    finally:
        camera_worker.stop()
        await asyncio.gather(
            *(peer.close() for peer in peer_connections),
            return_exceptions=True,
        )
        peer_connections.clear()


app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@app.post("/offer")
async def offer(request: WebRTCOffer) -> dict[str, str]:
    peer = RTCPeerConnection()
    peer_connections.add(peer)

    @peer.on("connectionstatechange")
    async def connection_state_changed() -> None:
        if peer.connectionState in {"failed", "closed"}:
            await peer.close()
            peer_connections.discard(peer)

    try:
        # get the offer from the browser to see wjhat they support basically
        remote_offer = RTCSessionDescription(sdp=request.sdp, type=request.type)
        await peer.setRemoteDescription(remote_offer)

        # add the current local camera track to the WebRTC stream.
        peer.addTrack(CameraVideoTrack(latest_frame))

        # we answer back based on the browser's offer (peer.createAnswer()) and set our own offer back to the browser
        await peer.setLocalDescription(await peer.createAnswer())
    except Exception:
        peer_connections.discard(peer)
        await peer.close()
        raise

    return {
        "sdp": peer.localDescription.sdp,
        "type": peer.localDescription.type,
    }


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
