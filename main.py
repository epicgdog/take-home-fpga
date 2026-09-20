import cv2
from insightface.app import FaceAnalysis

CAMERA_INDEX = 0
DETECTION_SIZE = (640, 640)


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

            cv2.imshow("InsightFace webcam detection", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
