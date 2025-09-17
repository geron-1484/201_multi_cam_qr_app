# core/process_manager.py
import multiprocessing as mp
import queue
import logging
import cv2
from core.qr_reader import QRReader
from core.usb_camera import USBCamera
from core.onvif_camera import ONVIFCamera

logger = logging.getLogger(__name__)

def _create_camera_from_info(camera_info):
    cam_type = camera_info["type"]
    cam_id = camera_info["id"]
    config = camera_info.get("config", {})

    if cam_type == "usb":
        return USBCamera(cam_id, config)
    elif cam_type == "onvif":
        return ONVIFCamera(cam_id, config)
    else:
        raise ValueError(f"Unsupported camera type: {cam_type}")

def camera_worker(camera_info, frame_queue, cmd_queue):
    """
    子プロセスとして動作し、カメラからフレームを取得してデコード結果を送信する。
    """
    cam_id = camera_info["id"]
    cam_type = camera_info["type"]
    decode_mode = camera_info.get("decode_mode", "all")

    reader = QRReader(mode=decode_mode)
    cam = _create_camera_from_info(camera_info)

    try:
        if not cam.connect():
            frame_queue.put(("ERROR", f"Camera {cam_id} connection failed"))
            return

        while True:
            # コマンド処理（モード変更など）
            try:
                while True:
                    cmd = cmd_queue.get_nowait()
                    if cmd and cmd[0] == "SET_DECODE_MODE":
                        reader.set_mode(cmd[1])
                        logger.info(f"Camera {cam_id} decode mode set to {cmd[1]}")
            except queue.Empty:
                pass

            # フレーム取得
            frame_bgr = cam.capture_frame()
            if frame_bgr is None:
                continue

            # グレースケール化（高速化）
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

            # デコード（1回だけ）
            results = reader.decode(gray)

            # GUIへ送信（カラー画像＋結果）
            frame_queue.put((cam_id, cam_type, frame_bgr, results))

    except KeyboardInterrupt:
        pass
    finally:
        try:
            cam.disconnect()
        except Exception:
            pass

class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.queues = {}
        self.cmd_queues = {}
        self.camera_infos = {}

    def start_camera(self, camera_info):
        cam_id = camera_info["id"]

        if cam_id in self.processes:
            proc = self.processes[cam_id]
            if proc.is_alive():
                logger.warning(f"Camera {cam_id} already running")
                return False
            else:
                logger.info(f"Cleaning up stale process entry for camera {cam_id}")
                self.stop_camera(cam_id)

        frame_queue = mp.Queue()
        cmd_queue = mp.Queue()

        proc = mp.Process(
            target=camera_worker,
            args=(camera_info, frame_queue, cmd_queue),
            daemon=True
        )
        proc.start()

        self.processes[cam_id] = proc
        self.queues[cam_id] = frame_queue
        self.cmd_queues[cam_id] = cmd_queue
        self.camera_infos[cam_id] = camera_info

        logger.info(f"Camera {cam_id} ({camera_info['type']}) started")
        return True

    def stop_camera(self, cam_id):
        if cam_id in self.processes:
            proc = self.processes.pop(cam_id)
            try:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=2)
                    if proc.is_alive():
                        logger.warning(f"Camera {cam_id} process did not exit, killing")
                        proc.kill()
            except Exception as e:
                logger.error(f"Error stopping camera {cam_id}: {e}")

            self.queues.pop(cam_id, None)
            self.cmd_queues.pop(cam_id, None)
            self.camera_infos.pop(cam_id, None)
            logger.info(f"Camera {cam_id} stopped")

    def stop_all(self):
        for cam_id in list(self.processes.keys()):
            self.stop_camera(cam_id)

    def get_frames(self):
        frames = []
        for cam_id, q in self.queues.items():
            try:
                while True:
                    frames.append(q.get_nowait())
            except queue.Empty:
                pass
        return frames

    def send_command(self, cam_id, cmd):
        if cam_id in self.cmd_queues:
            self.cmd_queues[cam_id].put(cmd)

    def list_onvif_cameras(self):
        """
        現在登録されているONVIFカメラのID一覧を返す
        """
        return [
            cam_id
            for cam_id, info in self.camera_infos.items()
            if info.get("type") == "onvif"
        ]

    def is_camera_running(self, cam_id):
        proc = self.processes.get(cam_id)
        return proc.is_alive() if proc else False
