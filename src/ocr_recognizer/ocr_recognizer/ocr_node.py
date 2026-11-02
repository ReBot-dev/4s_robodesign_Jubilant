import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

class OcrNode(Node):
    def __init__(self):
        super().__init__('ocr_node')
        self.bridge = CvBridge()
        self.create_subscription(Image, '/camera/camera/color/image_raw', self.on_image, 10)
        self.get_logger().info('画像を待っています')

    def on_image(self, msg):
        img = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        h, w = img.shape[:2]
        self.get_logger().info(f'受け取った: {w}x{h}')

def main():
    rclpy.init()
    node = OcrNode()
    rclpy.spin(node)
    rclpy.shutdown()
