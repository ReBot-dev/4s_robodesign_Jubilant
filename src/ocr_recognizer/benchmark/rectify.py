"""photos/ の写真を、四隅の ArUco マーカーで正対補正して rectified/ に保存する。

マーカーの印刷位置（mm）は test_docs/make_docs.py と同じ。
マーカー ID から紙の向きが決まるので、横向き・逆さまの写真も正立する。
"""
from pathlib import Path

import cv2
import numpy as np

import dataset

HERE = dataset.HERE
PHOTOS = dataset.PHOTOS
OUT = dataset.RECTIFIED

MARKER_MM, INSET_MM = 25, 10
PX_PER_MM = 10  # 254 dpi 相当
LANDSCAPE = {'03'}


def marker_corners_mm(page_w, page_h):
    far_x, far_y = page_w - INSET_MM - MARKER_MM, page_h - INSET_MM - MARKER_MM
    tl = {0: (INSET_MM, INSET_MM), 1: (far_x, INSET_MM), 2: (far_x, far_y), 3: (INSET_MM, far_y)}
    s = MARKER_MM
    return {i: np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], np.float32)
            for i, (x, y) in tl.items()}


def main(photos=PHOTOS, out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    for photo in sorted(photos.glob('*.jpg')):
        doc = photo.stem.split('_')[0]
        page_w, page_h = (297, 210) if doc in LANDSCAPE else (210, 297)
        img = cv2.imread(str(photo))
        corners, ids, _ = detector.detectMarkers(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        found = sorted(ids.flatten().tolist()) if ids is not None else []
        ref = marker_corners_mm(page_w, page_h)
        src, dst = [], []
        for c, i in zip(corners, found and ids.flatten()):
            if int(i) in ref:
                src.extend(c.reshape(4, 2))
                dst.extend(ref[int(i)] * PX_PER_MM)
        if len(src) < 8:
            print(f'{photo.name}: マーカー不足 {found} → スキップ')
            continue
        H, _ = cv2.findHomography(np.array(src), np.array(dst), cv2.RANSAC, 5.0)
        warped = cv2.warpPerspective(img, H, (page_w * PX_PER_MM, page_h * PX_PER_MM),
                                     flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
        cv2.imwrite(str(out / f'{photo.stem}.png'), warped)
        print(f'{photo.name}: マーカー {found} → {photo.stem}.png')


if __name__ == '__main__':
    main()
