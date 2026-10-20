"""スマホ写真を D435i のカラーカメラ相当（1920×1080 = 約 207 万画素）に落とし、正対補正する。

縦横比は写真のまま、総画素数だけを D435i に合わせる（紙が画面いっぱいに写っている想定）。
出力: d435/photos/*.jpg（縮小した写真）、d435/rectified/*.png（それを ArUco で正対補正したもの）
"""
import math

import cv2

import dataset
import rectify

D435_PIXELS = 1920 * 1080
OUT = dataset.D435


def main():
    (OUT / 'photos').mkdir(parents=True, exist_ok=True)
    for photo in sorted(rectify.PHOTOS.glob('*.jpg')):
        img = cv2.imread(str(photo))
        h, w = img.shape[:2]
        s = math.sqrt(D435_PIXELS / (w * h))
        small = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(OUT / 'photos' / photo.name), small, [cv2.IMWRITE_JPEG_QUALITY, 90])
    rectify.main(OUT / 'photos', OUT / 'rectified')


if __name__ == '__main__':
    main()
