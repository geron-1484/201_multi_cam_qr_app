# core/qr_reader.py
import zxingcpp
from pyzbar import pyzbar
from pyzbar.pyzbar import ZBarSymbol

class QRReader:
    def __init__(self, mode="all"):
        """
        mode: "datamatrix", "qrcode", "barcode", "all"
        """
        self.mode = mode

    def set_mode(self, mode: str):
        self.mode = mode

    def decode(self, gray_frame):
        """
        gray_frame: OpenCVの単一チャンネル画像（uint8）
        戻り値: [{data, rect, polygon, type}]
        """
        results = []

        # --- DataMatrix: zxing-cpp ---
        if self.mode in ("datamatrix", "all"):
            try:
                # DataMatrix専用にフォーマットを絞る
                dm_results = zxingcpp.read_barcodes(
                    gray_frame,
                    formats={zxingcpp.BarcodeFormat.DataMatrix}
                )
                for r in dm_results:
                    if r.format == zxingcpp.BarcodeFormat.DataMatrix and r.text:
                        poly = [(p.x, p.y) for p in r.position] if r.position else None
                        rect = None
                        if poly and len(poly) >= 2:
                            xs = [p[0] for p in poly]
                            ys = [p[1] for p in poly]
                            x, y = min(xs), min(ys)
                            w, h = max(xs) - x, max(ys) - y
                            rect = (x, y, w, h)
                        results.append({
                            "data": r.text,
                            "rect": rect,
                            "polygon": poly,
                            "type": "DataMatrix"
                        })
            except Exception:
                pass

        # --- QRコード & バーコード: pyzbar ---
        if self.mode in ("qrcode", "barcode", "all"):
            if self.mode == "qrcode":
                symbols = [ZBarSymbol.QRCODE]
            elif self.mode == "barcode":
                symbols = [
                    ZBarSymbol.CODE128, ZBarSymbol.CODE39, ZBarSymbol.CODE93,
                    ZBarSymbol.EAN8, ZBarSymbol.EAN13, ZBarSymbol.UPCA, ZBarSymbol.UPCE,
                    ZBarSymbol.ITF, ZBarSymbol.CODABAR
                ]
            else:
                symbols = None  # all
            decoded_objs = pyzbar.decode(gray_frame, symbols=symbols)

            try:
                decoded_objs = pyzbar.decode(gray_frame, symbols=symbols)
                for obj in decoded_objs:
                    poly = [(p.x, p.y) for p in obj.polygon] if obj.polygon else None
                    results.append({
                        "data": obj.data.decode("utf-8", errors="ignore"),
                        "rect": obj.rect,  # (x, y, w, h)
                        "polygon": poly,
                        "type": obj.type
                    })
            except Exception:
                pass

        return results
