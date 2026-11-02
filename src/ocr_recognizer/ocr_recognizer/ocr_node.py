# ros2 package
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

# AruCo detect
import cv2
import numpy as np

MARKER_MM, INSET_MM = 25, 10
PX_PER_MM = 10  # 254dpi 相当
PAGE_W, PAGE_H = 210, 297  # ひとまず A4 縦に決め打ち


# AruCo
def marker_corners_mm(page_w, page_h):
    far_x, far_y = page_w - INSET_MM - MARKER_MM, page_h - INSET_MM - MARKER_MM
    tl = {0: (INSET_MM, INSET_MM), 1: (far_x, INSET_MM), 2: (far_x, far_y), 3: (INSET_MM, far_y)}
    s = MARKER_MM
    return {i: np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], np.float32)
            for i, (x, y) in tl.items()}


# ros2 package
class OcrNode(Node):
    def __init__(self):
        super().__init__('ocr_node')
        self.bridge = CvBridge()
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.ref = marker_corners_mm(PAGE_W, PAGE_H)
        self.create_subscription(Image, '/camera/camera/color/image_raw', self.on_image, 10)
        self.get_logger().info('画像を待っています')

    def on_image(self, msg):
        img = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

        # マーカーを探す（OpenCV 4.6 の書き方）
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, self.dictionary)
        found = sorted(ids.flatten().tolist()) if ids is not None else []
        if found != [0, 1, 2, 3]:
            self.get_logger().info(f'マーカー不足 {found}')
            return

        # 画像上の角の位置と、紙の上での位置（mm × 10px）を対応させる
        src, dst = [], []
        for c, i in zip(corners, ids.flatten()):
            src.extend(c.reshape(4, 2))
            dst.extend(self.ref[int(i)] * PX_PER_MM)

        # 真上から見た平らな画像にする
        H, _ = cv2.findHomography(np.array(src), np.array(dst), cv2.RANSAC, 5.0)
        warped = cv2.warpPerspective(img, H, (PAGE_W * PX_PER_MM, PAGE_H * PX_PER_MM),
                                     flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
        cv2.imwrite('/tmp/rectified.png', warped)
        self.get_logger().info(f'マーカー {found} → /tmp/rectified.png')


def main():
    rclpy.init()
    node = OcrNode()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
