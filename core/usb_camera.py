"""
カメラ種別ごとの接続・フレーム取得処理
"""
import cv2
from .camera_base import CameraBase

class USBCamera(CameraBase):
    def connect(self):
        self.cap = cv2.VideoCapture(self.camera_id)
        # 解像度設定（可能なら）
        if "resolution" in self.config:
            w, h = self.config["resolution"]
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if "fps" in self.config:
            self.cap.set(cv2.CAP_PROP_FPS, self.config["fps"])
        ok = self.cap.isOpened()
        self.is_running = ok
        return ok

    def disconnect(self):
        self.is_running = False
        if hasattr(self, "cap") and self.cap:
            self.cap.release()
            self.cap = None

    def capture_frame(self):
        if not getattr(self, "cap", None):
            return None
        ret, frame = self.cap.read()
        return frame if ret else None
