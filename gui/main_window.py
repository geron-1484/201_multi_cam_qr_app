from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QHBoxLayout,
    QLineEdit, QComboBox, QGroupBox, QFormLayout, QSpinBox
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt
import cv2
import numpy as np
import time

from core.process_manager import ProcessManager
from core.logger import get_logger
from core.history_store import HistoryStore, now_iso
from gui.camera_config_dialog import CameraConfigDialog
from gui.history_window import HistoryWindow

logger = get_logger()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Cam QR Reader")
        self.setGeometry(60, 60, 1200, 900)

        self.pm = ProcessManager()
        self.video_labels = {}
        self.history = HistoryStore()

        # 上部操作バー
        self.add_btn = QPushButton("カメラ追加")
        self.stop_btn = QPushButton("全カメラ停止")
        self.history_btn = QPushButton("履歴を開く")

        # 読み取り対象選択UI
        self.decode_mode_combo = QComboBox()
        self.decode_mode_combo.addItems(["DataMatrix全般", "QRコード全般", "Barcode全般", "全て"])
        self.decode_mode_combo.currentIndexChanged.connect(self._on_decode_mode_changed)
        self.current_decode_mode = "all"

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.add_btn)
        top_layout.addWidget(self.stop_btn)
        top_layout.addWidget(self.history_btn)
        top_layout.addWidget(self.decode_mode_combo)
        top_bar = QWidget()
        top_bar.setLayout(top_layout)

        # 映像エリア
        self.video_area = QVBoxLayout()
        self.video_area.addStretch()
        video_wrap = QWidget()
        video_wrap.setLayout(self.video_area)

        # PTZパネル
        ptz_group = QGroupBox("PTZ操作（ONVIF）")
        self.ptz_cam_select = QComboBox()
        self.ptz_speed = QSpinBox()
        self.ptz_speed.setRange(1, 100)
        self.ptz_speed.setValue(30)

        btn_up = QPushButton("↑")
        btn_down = QPushButton("↓")
        btn_left = QPushButton("←")
        btn_right = QPushButton("→")
        btn_zoomin = QPushButton("Zoom +")
        btn_zoomout = QPushButton("Zoom -")
        btn_stop = QPushButton("Stop")

        grid = QFormLayout()
        grid.addRow("対象カメラ", self.ptz_cam_select)
        grid.addRow("スピード(%)", self.ptz_speed)

        btn_row1 = QHBoxLayout()
        btn_row1.addWidget(btn_left); btn_row1.addWidget(btn_up); btn_row1.addWidget(btn_right)

        btn_row2 = QHBoxLayout()
        btn_row2.addWidget(btn_down); btn_row2.addWidget(btn_zoomin); btn_row2.addWidget(btn_zoomout); btn_row2.addWidget(btn_stop)

        v_ptz = QVBoxLayout()
        v_ptz.addLayout(grid)
        v_ptz.addLayout(btn_row1)
        v_ptz.addLayout(btn_row2)
        ptz_group.setLayout(v_ptz)

        # ログ
        self.result_log = QTextEdit()
        self.result_log.setReadOnly(True)

        # レイアウト
        root = QVBoxLayout()
        root.addWidget(top_bar)
        root.addWidget(video_wrap)
        root.addWidget(ptz_group)
        root.addWidget(self.result_log)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        # タイマー
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frames)
        self.timer.start(30)

        # シグナル
        self.add_btn.clicked.connect(self.add_camera)
        self.stop_btn.clicked.connect(self.stop_all_cameras)
        self.history_btn.clicked.connect(self.open_history)

        btn_up.clicked.connect(lambda: self._ptz_move(0, +1, 0))
        btn_down.clicked.connect(lambda: self._ptz_move(0, -1, 0))
        btn_left.clicked.connect(lambda: self._ptz_move(-1, 0, 0))
        btn_right.clicked.connect(lambda: self._ptz_move(+1, 0, 0))
        btn_zoomin.clicked.connect(lambda: self._ptz_move(0, 0, +1))
        btn_zoomout.clicked.connect(lambda: self._ptz_move(0, 0, -1))
        btn_stop.clicked.connect(self._ptz_stop)

        self.seen_codes = {}  # {コード文字列: 最終読み取り時刻}
        self.code_expire_sec = 15

    def add_camera(self):
        dialog = CameraConfigDialog(self)
        if dialog.exec_():
            camera_info = dialog.get_camera_info()
            if not camera_info:
                self.result_log.append("[ERROR] カメラ設定が不正です")
                return

            # 修正: 実際に動いているか確認
            if self.pm.is_camera_running(camera_info["id"]):
                self.result_log.append(f"[WARN] カメラ {camera_info['id']} はすでに起動中です")
                return

            camera_info["decode_mode"] = self.current_decode_mode
            if self.pm.start_camera(camera_info):
                label = QLabel(f"{camera_info['type'].upper()} Cam {camera_info['id']}")
                label.setFixedHeight(300)
                label.setMinimumWidth(480)
                self.video_labels[camera_info['id']] = label
                self.video_area.insertWidget(self.video_area.count() - 1, label)
                self.result_log.append(f"[INFO] {camera_info['type']} カメラ {camera_info['id']} を追加しました")
                self._refresh_ptz_cam_list()
            else:
                self.result_log.append(f"[ERROR] カメラ {camera_info['id']} の起動に失敗しました")

    def stop_all_cameras(self):
        self.pm.stop_all()
        for i in reversed(range(self.video_area.count() - 1)):
            w = self.video_area.itemAt(i).widget()
            if w:
                w.deleteLater()
        self.video_labels.clear()
        # 修正: list_onvif_cameras() が存在しない場合でも落ちない
        try:
            self._refresh_ptz_cam_list()
        except AttributeError:
            self.ptz_cam_select.clear()
        self.result_log.append("[INFO] 全カメラを停止しました")

    def update_frames(self):
        frames = self.pm.get_frames()
        for data in frames:
            if isinstance(data, tuple) and data[0] == "ERROR":
                self.result_log.append(f"[ERROR] {data[1]}")
                continue

            cam_id, cam_type, frame_bgr, results = data
            if frame_bgr is None:
                continue

            display = frame_bgr.copy()
            now_t = time.time()
            ts = now_iso()

            for res in results:
                code = res["data"] or ""
                # === 描画は毎回行う（15秒ルールに関わらず） ===
                # 枠
                if res.get("polygon"):
                    pts = np.array(res["polygon"], dtype=np.int32)
                    cv2.polylines(display, [pts], True, (0, 255, 0), 2)
                    anchor = (pts[0][0], max(0, pts[0][1] - 10))
                elif res.get("rect"):
                    x, y, w, h = res["rect"]
                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    anchor = (x, max(0, y - 10))
                else:
                    anchor = (10, 30)

                # ラベル
                label = f"{res.get('type','')}: {code}" if code else f"{res.get('type','')}"
                cv2.putText(display, label, anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # === 履歴/ログは15秒ルールを順守 ===
                last = self.seen_codes.get(code, 0)
                if code and (now_t - last >= self.code_expire_sec):
                    self.seen_codes[code] = now_t
                    self.history.add_record(ts, str(cam_id), cam_type, code)
                    self.result_log.append(f"[{res.get('type','')}][{ts}][{cam_type}:{cam_id}] {code}")

            # 表示（アスペクト比維持）
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            if cam_id in self.video_labels:
                label = self.video_labels[cam_id]
                pixmap = QPixmap.fromImage(qimg).scaled(
                    label.width(), label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                label.setPixmap(pixmap)

    def _on_decode_mode_changed(self, idx):
        text = self.decode_mode_combo.currentText()
        if text.startswith("DataMatrix"):
            mode = "datamatrix"
        elif text.startswith("QRコード"):
            mode = "qrcode"
        elif text.startswith("Barcode"):
            mode = "barcode"
        else:
            mode = "all"

        self.current_decode_mode = mode
        self.result_log.append(f"[INFO] 読み取りモードを {mode} に変更しました")

        # 修正: 全カメラに即時反映
        for cam_id in list(self.pm.processes.keys()):
            self.pm.send_command(cam_id, ("SET_DECODE_MODE", mode))

    def _refresh_ptz_cam_list(self):
        self.ptz_cam_select.clear()
        for cid in self.pm.list_onvif_cameras():
            self.ptz_cam_select.addItem(str(cid), cid)

    def _ptz_move(self, x, y, z):
        cam_id = self.ptz_cam_select.currentData()
        if cam_id is None:
            self.result_log.append("[WARN] ONVIFカメラが選択されていません")
            return
        speed = max(1, min(100, self.ptz_speed.value())) / 100.0
        pan = x * speed
        tilt = y * speed
        zoom = z * speed
        ok = self.pm.send_command(cam_id, {"cmd": "ptz_move", "pan": pan, "tilt": tilt, "zoom": zoom})
        if not ok:
            self.result_log.append("[ERROR] PTZコマンド送信に失敗しました")

    def _ptz_stop(self):
        cam_id = self.ptz_cam_select.currentData()
        if cam_id is None:
            return
        self.pm.send_command(cam_id, {"cmd": "ptz_stop"})

    def open_history(self):
        dlg = HistoryWindow(self.history, self)
        dlg.exec_()

    def closeEvent(self, event):
        """ウィンドウが閉じられるときの終了処理"""
        self.result_log.append("[INFO] アプリ終了処理中...")
        try:
            self.pm.stop_all()
        except Exception as e:
            logger.error(f"終了処理中にエラー: {e}")

        # 念のため残っている子プロセスを強制終了
        import multiprocessing as mp
        for p in mp.active_children():
            try:
                logger.warning(f"残存プロセス {p.pid} を強制終了します")
                p.terminate()
                p.join(timeout=1)
                if p.is_alive():
                    p.kill()
            except Exception as e:
                logger.error(f"強制終了失敗: {e}")

        event.accept()
