"""
カメラ制御の共通インターフェース
"""
class CameraBase:
    def __init__(self, camera_id, config):
        self.camera_id = camera_id
        self.config = config
        self.is_running = False

    def connect(self):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def capture_frame(self):
        raise NotImplementedError
