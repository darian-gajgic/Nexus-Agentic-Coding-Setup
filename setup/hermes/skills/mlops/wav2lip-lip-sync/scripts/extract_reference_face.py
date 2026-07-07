#!/usr/bin/env python3
"""Extract the best front-facing, well-lit reference face from a video.
Uses dlib face detection + sharpness/brightness/centrality scoring.
Outputs a 512x512 square crop centered on the face.

Usage:
    python3 extract_reference_face.py <video_path> <output_path> [num_candidates]

Example:
    python3 extract_reference_face.py /home/user/face.mp4 /home/user/reference.jpg 60

Requirements:
    pip install dlib opencv-python numpy
"""
import cv2
import numpy as np
import os
import sys
import dlib


def extract_reference_face(video_path, output_path, num_candidates=60):
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    detector = dlib.get_frontal_face_detector()

    def score_face(gray, rect):
        x1, y1, x2, y2 = rect.left(), rect.top(), rect.right(), rect.bottom()
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(gray.shape[1], x2), min(gray.shape[0], y2)

        face_crop = gray[y1c:y2c, x1c:x2c]
        if face_crop.size == 0:
            return -1

        # Sharpness (variance of Laplacian)
        sharpness = cv2.Laplacian(face_crop, cv2.CV_64F).var()

        # Brightness — prefer well-lit (mean around 100-180)
        brightness = np.mean(face_crop)
        brightness_score = -abs(brightness - 140) * 0.5

        # Face size
        face_area = (x2c - x1c) * (y2c - y1c)

        # Centrality
        cx = (x1c + x2c) / 2
        cy = (y1c + y2c) / 2
        frame_cx = gray.shape[1] / 2
        frame_cy = gray.shape[0] / 2
        centrality = -np.sqrt((cx - frame_cx)**2 + (cy - frame_cy)**2) * 0.01

        # Face aspect ratio — prefer roughly square faces
        fw, fh = x2c - x1c, y2c - y1c
        aspect = min(fw, fh) / max(fw, fh) if max(fw, fh) > 0 else 0

        return sharpness + brightness_score + centrality + face_area * 0.0001 + aspect * 100

    def crop_and_resize(frame, rect, size=512):
        h, w = frame.shape[:2]

        x1, y1, x2, y2 = rect.left(), rect.top(), rect.right(), rect.bottom()
        fcx = (x1 + x2) / 2
        fcy = (y1 + y2) / 2
        face_w = x2 - x1
        face_h = y2 - y1

        crop_size = max(face_w, face_h) * 2.2
        crop_cx = fcx
        crop_cy = fcy - face_h * 0.15  # slightly above center for forehead/hair

        cx1 = int(crop_cx - crop_size / 2)
        cy1 = int(crop_cy - crop_size / 2)
        cx2 = int(crop_cx + crop_size / 2)
        cy2 = int(crop_cy + crop_size / 2)

        cx1 = max(0, cx1)
        cy1 = max(0, cy1)
        cx2 = min(w, cx2)
        cy2 = min(h, cy2)

        crop = frame[cy1:cy2, cx1:cx2]

        # Pad to square if needed
        ch, cw = crop.shape[:2]
        if ch != cw:
            target = max(ch, cw)
            pad_top = (target - ch) // 2
            pad_bottom = target - ch - pad_top
            pad_left = (target - cw) // 2
            pad_right = target - cw - pad_left
            crop = cv2.copyMakeBorder(crop, pad_top, pad_bottom, pad_left,
                                      pad_right, cv2.BORDER_REFLECT)

        return cv2.resize(crop, (size, size), interpolation=cv2.INTER_LANCZOS4)

    # Open video
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Video: {total_frames} frames, {fps:.1f} fps")

    if total_frames == 0:
        print("ERROR: Could not read video frames!")
        cap.release()
        return False

    step = max(1, total_frames // num_candidates)
    best_score = -1
    best_frame = None
    best_face = None
    best_frame_idx = -1
    candidates_found = 0

    for idx in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector(gray, 1)

        if len(faces) == 0:
            continue

        candidates_found += 1
        for face in faces:
            s = score_face(gray, face)
            if s > best_score:
                best_score = s
                best_frame = frame.copy()
                best_face = face
                best_frame_idx = idx

    cap.release()

    if best_frame is None:
        print(f"ERROR: No faces detected in any of {num_candidates} sampled frames!")
        return False

    print(f"Scanned {candidates_found} frames with faces, "
          f"best at frame {best_frame_idx} (score {best_score:.1f})")

    result = crop_and_resize(best_frame, best_face, 512)
    cv2.imwrite(output_path, result, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"Saved: {output_path} shape={result.shape}")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 extract_reference_face.py <video> <output.jpg> [num_candidates]")
        sys.exit(1)

    video = sys.argv[1]
    output = sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 60

    success = extract_reference_face(video, output, n)
    sys.exit(0 if success else 1)
