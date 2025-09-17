from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QFileDialog, QFormLayout, QSpinBox
)

class HistoryWindow(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR読み取り履歴")
        self.setMinimumSize(800, 500)
        self.store = store

        # フィルタ
        self.ts_from = QLineEdit()
        self.ts_to = QLineEdit()
        self.cam_id = QLineEdit()
        self.keyword = QLineEdit()
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(500)

        form = QFormLayout()
        form.addRow("開始時刻 (YYYY-MM-DD HH:MM:SS)", self.ts_from)
        form.addRow("終了時刻 (YYYY-MM-DD HH:MM:SS)", self.ts_to)
        form.addRow("カメラID", self.cam_id)
        form.addRow("キーワード", self.keyword)
        form.addRow("件数上限", self.limit)

        self.search_btn = QPushButton("検索")
        self.export_btn = QPushButton("CSVエクスポート")

        btns = QHBoxLayout()
        btns.addWidget(self.search_btn)
        btns.addWidget(self.export_btn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["時刻", "カメラID", "種別", "内容"])
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(btns)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.search_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self.export_csv)

        self.refresh()

    def refresh(self):
        rows = self.store.query(
            ts_from=self.ts_from.text().strip() or None,
            ts_to=self.ts_to.text().strip() or None,
            camera_id=self.cam_id.text().strip() or None,
            keyword=self.keyword.text().strip() or None,
            limit=self.limit.value()
        )
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, val in enumerate(r):
                self.table.setItem(row, col, QTableWidgetItem(str(val)))

    def export_csv(self):
        rows = []
        for row in range(self.table.rowCount()):
            rows.append([
                self.table.item(row, 0).text(),
                self.table.item(row, 1).text(),
                self.table.item(row, 2).text(),
                self.table.item(row, 3).text(),
            ])
        path, _ = QFileDialog.getSaveFileName(self, "CSVとして保存", "data/exports/qr_history.csv", "CSV (*.csv)")
        if path:
            self.store.export_csv(path, rows)
