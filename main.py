import asyncio
import threading

import cv2
import numpy as np
from aiortc import VideoStreamTrack
from av import VideoFrame
from insightface.app import FaceAnalysis

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


# a track that we can send over to the frontend via WebRTC
# We must extend VideoStreamTrack as that is what the library we are using sends
class CameraVideoTrack(VideoStreamTrack):
    def __init__(self, latest_frame: LatestFrame) -> None:
        super().__init__()
        self.latest_frame = latest_frame

    # this function basically takes our video frame and converts it to bgr24, something that can be streamed over WebRTc
    async def recv(self) -> VideoFrame:

        # pts: number of clcok ticks per second
        # time_base: how long in between each tick
        # pts * time_base = presentation tiem, how long it would take to display the frame
        pts, time_base = await self.next_timestamp()

        frame = self.latest_frame.get()
        while frame is None:
            await asyncio.sleep(0.01)
            frame = self.latest_frame.get()

        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


latest_frame = LatestFrame()


def main() -> None:
    detector = FaceAnalysis(allowed_modules=["detection"])
    detector.prepare(ctx_id=0, det_size=DETECTION_SIZE)

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        raise RuntimeError(f"Could not open camera at index {CAMERA_INDEX}")

    print("Face detection is running. Press 'q' or Escape to quit.")

    try:
        while True:
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

            latest_frame.set(frame)
            cv2.imshow("InsightFace webcam detection", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
