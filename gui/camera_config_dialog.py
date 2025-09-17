from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QFormLayout, QMessageBox
)
from core.onvif_camera import ONVIFCamera

class CameraConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("カメラ追加設定")
        self.setMinimumWidth(400)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["usb", "onvif"])
        self.type_combo.currentTextChanged.connect(self.update_fields)

        self.id_input = QLineEdit()
        self.resolution_input = QLineEdit("640x480")
        self.fps_input = QLineEdit("30")

        self.ip_input = QLineEdit()
        self.port_input = QLineEdit("80")
        self.user_input = QLineEdit()
        self.pass_input = QLineEdit()
        self.rtsp_input = QLineEdit()

        self.profile_combo = QComboBox()
        self.profile_combo.setEnabled(False)
        self.profile_btn = QPushButton("プロファイル取得")
        self.profile_btn.setEnabled(False)
        self.profile_btn.clicked.connect(self.fetch_profiles)

        form = QFormLayout()
        form.addRow("カメラ種別", self.type_combo)
        form.addRow("カメラID（USBは整数）", self.id_input)
        form.addRow("解像度 (例: 640x480)", self.resolution_input)
        form.addRow("FPS", self.fps_input)
        form.addRow("IPアドレス", self.ip_input)
        form.addRow("ポート", self.port_input)
        form.addRow("ユーザー名", self.user_input)
        form.addRow("パスワード", self.pass_input)
        form.addRow("RTSP URL", self.rtsp_input)
        form.addRow("ONVIFプロファイル", self.profile_combo)
        form.addRow("", self.profile_btn)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("キャンセル")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.update_fields(self.type_combo.currentText())

    def update_fields(self, cam_type):
        is_onvif = (cam_type == "onvif")
        for w in [self.ip_input, self.port_input, self.user_input, self.pass_input, self.rtsp_input, self.profile_combo, self.profile_btn]:
            w.setEnabled(is_onvif)

    def fetch_profiles(self):
        ip = self.ip_input.text().strip()
        port = int(self.port_input.text() or 80)
        user = self.user_input.text().strip()
        pwd = self.pass_input.text().strip()
        cam = ONVIFCamera("temp", {"ip": ip, "port": port, "username": user, "password": pwd})
        profiles = cam.list_profiles()
        if not profiles:
            QMessageBox.warning(self, "エラー", "プロファイル取得に失敗しました")
            return
        self.profile_combo.clear()
        for token, name in profiles:
            self.profile_combo.addItem(f"{name} ({token})", token)

    def get_camera_info(self):
        cam_type = self.type_combo.currentText()
        cam_id = self.id_input.text().strip()
        if cam_type == "usb":
            try:
                cam_id = int(cam_id)
            except ValueError:
                return None
        res_text = self.resolution_input.text().strip()
        try:
            w, h = map(int, res_text.lower().split("x"))
        except ValueError:
            w, h = (640, 480)

        config = {
            "resolution": (w, h),
            "fps": int(self.fps_input.text() or 30)
        }

        if cam_type == "onvif":
            config.update({
                "ip": self.ip_input.text().strip(),
                "port": int(self.port_input.text() or 80),
                "username": self.user_input.text().strip(),
                "password": self.pass_input.text().strip(),
                "rtsp_url": self.rtsp_input.text().strip(),
                "profile_token": self.profile_combo.currentData()
            })

        return {
            "type": cam_type,
            "id": cam_id,
            "config": config
        }
