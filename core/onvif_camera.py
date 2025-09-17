import os
import time
import cv2
import socket
import requests
from urllib.parse import urlparse, urlunparse

from .camera_base import CameraBase
from config.settings import (
    RTSP_TRANSPORT,
    RECONNECT_MAX_TRIES,
    RECONNECT_BASE_DELAY_SEC,
    RECONNECT_MAX_DELAY_SEC,
    ONVIF_WSDL_DIR,
)
from .logger import get_logger

logger = get_logger()

# onvif-zeep は 'onvif' モジュール名で提供されます
try:
    from onvif import ONVIFCamera as ONVIFClient
    from zeep.exceptions import Fault as ZeepFault
except Exception as e:
    ONVIFClient = None
    ZeepFault = Exception
    logger.error(f"ONVIFクライアントのロードに失敗しました: {e}")


class ONVIFCamera(CameraBase):
    """
    必要なconfigキー（最低限）:
      - ip: str
      - port: int (通常 80)
      - username: str
      - password: str
    任意:
      - rtsp_url: str  # 直接指定したい場合に使用（ONVIF経由の解決をスキップ）
      - profile_token: str  # 使いたいプロファイルを固定
      - resolution: (w, h)
      - fps: int
      - rtsp_transport: "tcp" | "udp"  # デフォルトは settings.RTSP_TRANSPORT
      - wsdl_dir: str  # 個別指定（未指定ならsettingsのONVIF_WSDL_DIR）
    """

    def __init__(self, camera_id, config):
        super().__init__(camera_id, config)
        self.cap = None
        self._dev = None
        self._media = None
        self._profile_token = None
        self._stream_uri = None
        self._rtsp_url = None

        # 連続失敗カウンタ
        self._fail_count = 0

    def connect(self):
        # 1) RTSP URLが明示指定されていればそれを使う
        if self.config.get("rtsp_url"):
            self._rtsp_url = self._inject_credentials(self.config["rtsp_url"])
            logger.info(f"[ONVIF:{self.camera_id}] 使用するRTSP（指定）: {self._rtsp_url}")
        else:
            # 2) ONVIFでストリームURIを解決
            if ONVIFClient is None:
                logger.error("[ONVIF] onvifモジュールが利用できません")
                return False
            if not self._resolve_onvif_rtsp():
                return False

        # 3) OpenCV(FFmpeg)のRTSPオプション設定
        self._apply_ffmpeg_rtsp_options()

        # 4) VideoCapture オープン
        ok = self._open_capture()
        self.is_running = ok
        return ok

    def disconnect(self):
        self.is_running = False
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def capture_frame(self):
        if not self.cap:
            return None

        ret, frame = self.cap.read()
        if ret and frame is not None:
            self._fail_count = 0
            # 任意の解像度/FPS設定（デコーダ側では効かないことも多い）
            return frame

        # 失敗時は再接続試行
        self._fail_count += 1
        if self._fail_count >= 10:
            logger.warning(f"[ONVIF:{self.camera_id}] フレーム取得失敗が連続しました。再接続を試みます。")
            self._reconnect_with_backoff()
        return None

    # ---- 内部メソッド ------------------------------------------------------

    def _resolve_onvif_rtsp(self) -> bool:
        ip = self.config.get("ip")
        port = int(self.config.get("port", 80))
        user = self.config.get("username", "")
        passwd = self.config.get("password", "")
        wsdl_dir = self.config.get("wsdl_dir") or ONVIF_WSDL_DIR or None

        # 接続前にDNS/到達性の軽いチェック
        try:
            socket.gethostbyname(ip)
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] IP解決に失敗: {ip} err={e}")
            return False

        try:
            self._dev = ONVIFClient(ip, port, user, passwd, wsdl_dir)
            self._media = self._dev.create_media_service()
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] ONVIF接続失敗: {e}")
            return False

        # プロファイル取得
        try:
            profiles = self._media.GetProfiles()
        except ZeepFault as e:
            logger.error(f"[ONVIF:{self.camera_id}] プロファイル取得失敗: {e}")
            return False
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] プロファイル取得例外: {e}")
            return False

        if not profiles:
            logger.error(f"[ONVIF:{self.camera_id}] 利用可能なプロファイルがありません")
            return False

        token = self.config.get("profile_token")
        if token:
            found = next((p for p in profiles if p.token == token), None)
            if not found:
                logger.warning(f"[ONVIF:{self.camera_id}] 指定プロファイルが見つからないため先頭を使用: {token}")
                token = profiles[0].token
        else:
            token = profiles[0].token

        self._profile_token = token

        # ストリームURI取得
        stream_setup = {
            "Stream": "RTP-Unicast",
            "Transport": {"Protocol": "RTSP"},
        }
        try:
            uri_resp = self._media.GetStreamUri(
                {"StreamSetup": stream_setup, "ProfileToken": self._profile_token}
            )
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] ストリームURI取得失敗: {e}")
            return False

        # 一部カメラは相対URIや内向きIPを返すことがあるため、必要に応じて補正
        raw_uri = uri_resp.Uri
        if not raw_uri.startswith("rtsp://"):
            raw_uri = f"rtsp://{ip}{raw_uri}"

        # 認証情報を埋め込み
        self._stream_uri = raw_uri
        self._rtsp_url = self._inject_credentials(raw_uri)
        logger.info(f"[ONVIF:{self.camera_id}] 使用するRTSP（解決）: {self._rtsp_url}")
        return True

    def _inject_credentials(self, url: str) -> str:
        """
        rtsp://host:port/path を rtsp://user:pass@host:port/path に変換
        既にuserinfoが含まれている場合は上書きしない
        """
        user = self.config.get("username", "")
        pwd = self.config.get("password", "")
        if not user:
            return url

        parsed = urlparse(url)
        if "@" in parsed.netloc:
            return url  # 既に認証情報あり

        netloc = parsed.netloc
        if not netloc:
            # 形式が崩れている場合はそのまま返す
            return url

        cred = f"{user}:{pwd}@"
        new_netloc = cred + netloc
        new_url = urlunparse(
            (parsed.scheme, new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )
        return new_url

    def _apply_ffmpeg_rtsp_options(self):
        """
        OpenCV(FFmpeg)にRTSPオプションを渡す。
        OpenCVでは環境変数 OPENCV_FFMPEG_CAPTURE_OPTIONS で指定できる。
        例: "rtsp_transport;tcp|stimeout;5000000"
        """
        transport = self.config.get("rtsp_transport", RTSP_TRANSPORT).lower()
        # ネットワークタイムアウト（マイクロ秒）
        stimeout_us = int(5 * 1_000_000)

        opts = [
            f"rtsp_transport;{transport}",
            f"stimeout;{stimeout_us}",
        ]
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(opts)

    def _open_capture(self) -> bool:
        # FFmpegバックエンドを明示（Windowsで安定しやすい）
        cap = cv2.VideoCapture(self._rtsp_url, cv2.CAP_FFMPEG)

        # 解像度は受信側で固定できない場合が多いが、試行しておく
        if "resolution" in self.config:
            w, h = self.config["resolution"]
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if "fps" in self.config:
            cap.set(cv2.CAP_PROP_FPS, int(self.config["fps"]))

        if not cap.isOpened():
            logger.error(f"[ONVIF:{self.camera_id}] RTSP接続に失敗: {self._rtsp_url}")
            return False

        self.cap = cap
        logger.info(f"[ONVIF:{self.camera_id}] RTSP接続に成功")
        return True

    def _reconnect_with_backoff(self):
        self.disconnect()
        delay = RECONNECT_BASE_DELAY_SEC
        for attempt in range(1, RECONNECT_MAX_TRIES + 1):
            logger.info(f"[ONVIF:{self.camera_id}] 再接続試行 {attempt}/{RECONNECT_MAX_TRIES}（待機 {delay:.1f}s）")
            time.sleep(delay)
            if self.connect():
                logger.info(f"[ONVIF:{self.camera_id}] 再接続成功")
                self._fail_count = 0
                return
            delay = min(delay * 2, RECONNECT_MAX_DELAY_SEC)
        logger.error(f"[ONVIF:{self.camera_id}] 再接続に失敗。以降はフレームNoneを返します。")

    def get_snapshot_jpeg(self, timeout=5.0) -> bytes:
        if not self._media:
            return b""
        try:
            snap = self._media.GetSnapshotUri({"ProfileToken": self._profile_token})
            uri = snap.Uri
            # 基本的にHTTP/HTTPS。Basic/Digest認証が必要な場合はrequestsでauth指定
            auth = None
            user = self.config.get("username", "")
            pwd = self.config.get("password", "")
            if user:
                auth = (user, pwd)
            resp = requests.get(uri, auth=auth, timeout=timeout, verify=False)
            if resp.ok:
                return resp.content
        except Exception as e:
            logger.warning(f"[ONVIF:{self.camera_id}] スナップショット取得失敗: {e}")
        return b""

    def list_profiles(self):
        """GUI用: 利用可能なプロファイル一覧を返す [(token, name), ...]"""
        try:
            ip = self.config.get("ip")
            port = int(self.config.get("port", 80))
            user = self.config.get("username", "")
            pwd = self.config.get("password", "")
            wsdl_dir = self.config.get("wsdl_dir") or ONVIF_WSDL_DIR or None
            dev = ONVIFClient(ip, port, user, pwd, wsdl_dir)
            media = dev.create_media_service()
            profiles = media.GetProfiles()
            return [(p.token, getattr(p, "Name", p.token)) for p in profiles]
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] プロファイル一覧取得失敗: {e}")
            return []

    def init_ptz(self):
        """PTZサービス初期化"""
        try:
            self._ptz = self._dev.create_ptz_service()
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] PTZ初期化失敗: {e}")
            self._ptz = None

    def ptz_move(self, pan=0.0, tilt=0.0, zoom=0.0, speed=0.5):
        """相対移動"""
        if not hasattr(self, "_ptz") or self._ptz is None:
            self.init_ptz()
        try:
            self._ptz.ContinuousMove({
                "ProfileToken": self._profile_token,
                "Velocity": {
                    "PanTilt": {"x": pan, "y": tilt, "space": ""},
                    "Zoom": {"x": zoom, "space": ""}
                }
            })
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] PTZ移動失敗: {e}")

    def ptz_stop(self):
        try:
            self._ptz.Stop({"ProfileToken": self._profile_token})
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] PTZ停止失敗: {e}")

    def set_video_encoder_config(self, width=None, height=None, bitrate=None, fps=None):
        """ONVIF経由でエンコーダ設定を変更"""
        try:
            enc_cfg = self._media.GetVideoEncoderConfiguration(self._profile_token)
            if width and height:
                enc_cfg.Resolution.Width = width
                enc_cfg.Resolution.Height = height
            if bitrate:
                enc_cfg.RateControl.BitrateLimit = bitrate
            if fps:
                enc_cfg.RateControl.FrameRateLimit = fps
            self._media.SetVideoEncoderConfiguration(enc_cfg)
            logger.info(f"[ONVIF:{self.camera_id}] エンコーダ設定変更完了")
        except Exception as e:
            logger.error(f"[ONVIF:{self.camera_id}] エンコーダ設定変更失敗: {e}")
