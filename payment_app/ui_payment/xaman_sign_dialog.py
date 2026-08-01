"""
Xaman Sign Dialog — reusable sign-request dialog with QR, polling and push support.

Usage:
    dialog = XamanSignDialog(
        xaman_client=client,
        txjson={"TransactionType": "Payment", ...},
        identifier=uetr,
        instruction="Pago de $3,000 MXN a Pedro García",
        expected_account=operator.xrpl_address,
        kind="payment",
        parent=self,
    )
    if dialog.exec() == QDialog.Accepted and dialog.result_data["ok"]:
        txid = dialog.result_data["txid"]
    else:
        reason = dialog.result_data["reason"]

result_data keys: ok (bool), txid (str|None), account (str|None),
                  reason (str), issued_user_token (str|None).
"""

from __future__ import annotations

from datetime import datetime

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QProgressBar, QMessageBox,
    )
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QPixmap, QDesktopServices
except ImportError:
    QDialog = QVBoxLayout = QHBoxLayout = QLabel = QPushButton = QProgressBar = QMessageBox = object
    Qt = QTimer = QUrl = QPixmap = QDesktopServices = object

from core.xaman_client import XamanClient
from shared_ui.workers import FunctionWorker

_POLL_INTERVAL_MS = 2000   # 2 s
_TIMEOUT_SECONDS  = 300    # 5 min


def resolve_status(status: dict, expected_account: str) -> dict:
    """Pure function — maps a raw status dict to a result dict.

    Separated from Qt so it can be unit-tested without a display.
    """
    if not status.get("resolved"):
        return {"ok": False, "reason": "pending"}

    if status.get("signed"):
        account = status.get("account") or ""
        if expected_account and account.lower() != expected_account.lower():
            return {
                "ok": False,
                "reason": "wrong_account",
                "txid": None,
                "account": account,
                "issued_user_token": status.get("issued_user_token"),
            }
        return {
            "ok": True,
            "reason": "signed",
            "txid": status.get("txid"),
            "account": account,
            "issued_user_token": status.get("issued_user_token"),
        }

    if status.get("cancelled"):
        return {"ok": False, "reason": "cancelled", "txid": None}
    if status.get("expired"):
        return {"ok": False, "reason": "expired", "txid": None}
    return {"ok": False, "reason": "unknown", "txid": None}


class XamanSignDialog(QDialog):
    """Modal dialog that shows a Xaman QR and polls until signed/cancelled/expired."""

    def __init__(
        self,
        xaman_client: XamanClient,
        txjson: dict,
        identifier: str,
        instruction: str,
        expected_account: str,
        kind: str,
        parent=None,
    ):
        super().__init__(parent)
        self._client          = xaman_client
        self._txjson          = txjson
        self._identifier      = identifier
        self._instruction     = instruction
        self._expected_account = expected_account
        self._kind            = kind

        self._uuid:       str | None = None
        self._deeplink:   str | None = None
        self._polling     = False
        self._started_at: datetime   = datetime.now()
        self._poll_timer: QTimer | None = None
        self._create_worker: FunctionWorker | None = None
        self._poll_worker:   FunctionWorker | None = None

        self.result_data: dict = {"ok": False, "reason": "cancelled", "txid": None,
                                   "account": None, "issued_user_token": None}

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("Firmar con Xaman")
        self.setFixedSize(420, 520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Instruction text
        inst_label = QLabel(self._instruction)
        inst_label.setAlignment(Qt.AlignCenter)
        inst_label.setWordWrap(True)
        inst_label.setStyleSheet("font-size: 11pt; font-weight: 600;")
        layout.addWidget(inst_label)

        # Status label
        self._status_label = QLabel("Conectando con el backend...")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("color: #605E5C; font-size: 9pt;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # QR image
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setFixedSize(280, 280)
        self._qr_label.setStyleSheet(
            "border: 1px solid #EDEBE9; border-radius: 8px; background: #FAF9F8;"
        )
        self._qr_label.setText("⏳")
        self._qr_label.setStyleSheet(
            "font-size: 40pt; border: 1px solid #EDEBE9; border-radius: 8px;"
            "background: #FAF9F8;"
        )
        layout.addWidget(self._qr_label, alignment=Qt.AlignCenter)

        # Progress bar (indeterminate)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        btn_layout = QHBoxLayout()

        self._open_btn = QPushButton("📱 Abrir en Xaman")
        self._open_btn.setProperty("class", "large")
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_deeplink)
        btn_layout.addWidget(self._open_btn)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setProperty("class", "secondary")
        cancel_btn.clicked.connect(self._on_user_cancel)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # Start creation in background
        self._create_worker = FunctionWorker(self._create_and_fetch_qr)
        self._create_worker.finished_ok.connect(self._on_created)
        self._create_worker.failed.connect(self._on_create_failed)
        self._create_worker.start()

    # ── Background work ───────────────────────────────────────────────────────

    def _create_and_fetch_qr(self) -> dict:
        """Runs in background: create sign request + download QR bytes."""
        result = self._client.create_sign_request(
            self._txjson,
            identifier=self._identifier,
            instruction=self._instruction,
            kind=self._kind,
        )
        # Download QR image bytes while we're already in a worker thread
        qr_bytes = self._client.fetch_qr_bytes(result["qr_png"])
        result["qr_bytes"] = qr_bytes
        return result

    def _on_created(self, data: dict):
        self._uuid     = data["uuid"]
        self._deeplink = data["deeplink"]
        pushed         = data.get("pushed", False)

        # Show QR
        qr_bytes = data.get("qr_bytes", b"")
        if qr_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(qr_bytes)
            self._qr_label.setPixmap(
                pixmap.scaled(280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self._qr_label.setStyleSheet(
                "border: 1px solid #EDEBE9; border-radius: 8px; background: white;"
            )

        self._open_btn.setEnabled(True)
        self._started_at = datetime.now()

        if pushed:
            self._status_label.setText(
                "📲 Revisa tu teléfono — se envió una notificación a Xaman.\n"
                "También puedes escanear el QR."
            )
        else:
            self._status_label.setText(
                "Escanea el código con la app Xaman.\n"
                "Asegúrate de estar en modo TESTNET."
            )

        self._start_polling()

    def _on_create_failed(self, error: str):
        self._progress.setRange(0, 1)
        self._progress.setValue(1)
        self._status_label.setText(f"Error al conectar: {error}")
        QMessageBox.critical(self, "Error de conexión",
                             f"No se pudo crear la solicitud de firma:\n\n{error}\n\n"
                             "Verifique que el backend esté activo y la device key sea válida.")
        self.result_data = {"ok": False, "reason": "backend_error", "txid": None,
                            "account": None, "issued_user_token": None}
        self.reject()

    # ── Polling ───────────────────────────────────────────────────────────────

    def _start_polling(self):
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_tick)
        self._poll_timer.start(_POLL_INTERVAL_MS)

    def _stop_polling(self):
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

    def _poll_tick(self):
        # Timeout check
        elapsed = (datetime.now() - self._started_at).total_seconds()
        if elapsed > _TIMEOUT_SECONDS:
            self._stop_polling()
            self._finish({"ok": False, "reason": "timeout", "txid": None,
                          "account": None, "issued_user_token": None})
            return

        if self._polling or not self._uuid:
            return

        self._polling = True
        self._poll_worker = FunctionWorker(self._client.get_sign_status, self._uuid)
        self._poll_worker.finished_ok.connect(self._on_poll_ok)
        self._poll_worker.failed.connect(self._on_poll_fail)
        self._poll_worker.start()

    def _on_poll_ok(self, status: dict):
        self._polling = False
        if not status.get("resolved"):
            remaining = int(_TIMEOUT_SECONDS -
                            (datetime.now() - self._started_at).total_seconds())
            self._status_label.setText(
                f"Esperando firma en Xaman... ({remaining}s restantes)"
            )
            return

        self._stop_polling()
        result = resolve_status(status, self._expected_account)

        if result["reason"] == "wrong_account":
            QMessageBox.warning(
                self, "Dirección No Coincide",
                f"La wallet que firmó no coincide con la registrada.\n\n"
                f"Esperada: {self._expected_account}\n"
                f"Recibida: {result.get('account', '?')}\n\n"
                "Use la wallet correcta en Xaman."
            )
            result = {"ok": False, "reason": "wrong_account", "txid": None,
                      "account": result.get("account"), "issued_user_token": None}

        self._finish(result)

    def _on_poll_fail(self, error: str):
        self._polling = False
        # Network hiccup — keep polling, just update label
        self._status_label.setText(f"Error de red ({error[:60]}...) — reintentando...")

    # ── Resolution ────────────────────────────────────────────────────────────

    def _finish(self, result: dict):
        self._stop_polling()
        self._progress.setRange(0, 1)
        self._progress.setValue(1)
        self.result_data = result

        if result["ok"]:
            self._status_label.setText("✓ Transacción firmada y enviada.")
            self.accept()
        else:
            reason_map = {
                "cancelled":    "El operador rechazó la transacción en Xaman.",
                "expired":      "La solicitud de firma expiró (5 min).",
                "timeout":      "Tiempo de espera agotado (5 min).",
                "wrong_account": "Wallet incorrecta.",
                "backend_error": "Error de conexión con el backend.",
            }
            msg = reason_map.get(result.get("reason", ""), "No se completó la firma.")
            self._status_label.setText(msg)
            self.reject()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_deeplink(self):
        if self._deeplink:
            QDesktopServices.openUrl(QUrl(self._deeplink))

    def _on_user_cancel(self):
        self._stop_polling()
        self.result_data = {"ok": False, "reason": "cancelled", "txid": None,
                            "account": None, "issued_user_token": None}
        self.reject()

    def closeEvent(self, event):
        self._stop_polling()
        event.accept()
