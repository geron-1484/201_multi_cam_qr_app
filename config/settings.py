# アプリ全体の設定値
DEFAULT_RESOLUTION = (640, 480)
DEFAULT_FPS = 30
QR_SCAN_INTERVAL_MS = 30

# ログ
LOG_DIR = "data/logs"
LOG_FILE_BASENAME = "app.log"
LOG_MAX_BYTES = 2 * 1024 * 1024  # 2MB
LOG_BACKUP_COUNT = 3

# ONVIF/RTSP受信まわり
RTSP_TRANSPORT = "tcp"  # "tcp" or "udp"
RECONNECT_MAX_TRIES = 5
RECONNECT_BASE_DELAY_SEC = 1.0  # バックオフ開始
RECONNECT_MAX_DELAY_SEC = 10.0

# ONVIF WSDLディレクトリ（空ならonvif-zeepデフォルトを使用）
ONVIF_WSDL_DIR = ""  # 例: "wsdl"
