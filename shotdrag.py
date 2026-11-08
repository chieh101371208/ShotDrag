"""
ShotDrag — 讓 Windows 截圖也能「拖進對話框」

使用方式：
    1. 安裝：py -m pip install PySide6
    2. 執行：pythonw shotdrag.py
    3. 使用 Win + Shift + S 截圖，右上角會顯示可拖曳縮圖。
    4. 將縮圖拖到 LINE、Discord、Claude、ChatGPT 等支援檔案拖放的視窗。

縮圖操作：
    左鍵拖曳：以 PNG 檔案形式拖出
    雙擊：使用預設圖片程式開啟
    右鍵：關閉縮圖

系統匣選單：
    暫停／恢復監聽、開機自動啟動、開啟截圖資料夾、結束程式。

注意：
    - 本程式會處理剪貼簿中的所有圖片，不限於 Win + Shift + S。
    - 截圖存放位置由 SAVE_DIR 決定；KEEP_DAYS = 0 代表不自動刪除舊截圖。
    - 重複執行時，第二份會提示後自動離開，不會出現兩個縮圖。
    - 發生未預期的錯誤時，詳細內容會寫入 %LOCALAPPDATA%\\ShotDrag\\error.log。
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import time
import traceback
import winreg
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QMimeData,
    QPoint,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDrag,
    QGuiApplication,
    QIcon,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# ---------- 可調整設定 ----------
SAVE_DIR = Path(__file__).resolve().parent / "screenshot"  # 與程式同層，自動建立
FILE_PREFIX = "截圖_"           # 檔名開頭；自動清理只會動這個開頭的檔案
KEEP_DAYS = 0                   # 自動刪除幾天前的舊截圖；0 = 永不刪除
SHOW_SECONDS = 10               # 縮圖初次顯示時間；滑鼠移入時會暫停倒數
HIDE_AFTER_DRAG_MS = 1500       # 拖曳結束後多久收起
HIDE_AFTER_LEAVE_MS = 2500      # 滑鼠移開後多久收起
CLIPBOARD_SETTLE_MS = 150       # 偵測到剪貼簿變動後，等截圖工具寫完再讀取
THUMB_SIZE = QSize(240, 170)
DRAG_PREVIEW_WIDTH = 140
MARGIN = 20                     # 與螢幕邊緣的距離（像素）

# ---------- 內部常數 ----------
APP_NAME = "ShotDrag"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MUTEX_NAME = "Local\\ShotDrag_SingleInstance"
ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183
MB_INFO = 0x40
MB_WARN = 0x30
MB_TOPMOST = 0x40000
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
LOG_FILE = LOG_DIR / "error.log"


# ====================================================================
# 一般工具
# ====================================================================
def notify_windows(message: str, title: str = APP_NAME, icon: int = MB_INFO) -> None:
    """顯示 Windows 訊息框（會阻塞到使用者按下確定）。"""
    ctypes.windll.user32.MessageBoxW(0, message, title, icon | MB_TOPMOST)


_error_reported = False


def log_exception(exc_type, exc, tb) -> None:
    """全域例外處理：pythonw 沒有主控台，錯誤會無聲消失，所以寫進記錄檔。"""
    global _error_reported
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}\n")
    except OSError:
        pass
    if not _error_reported:  # 一次執行只彈一次，避免連環跳窗
        _error_reported = True
        notify_windows(
            f"發生未預期的錯誤，詳細內容已寫入：\n{LOG_FILE}\n\n{exc}",
            icon=MB_WARN,
        )


def open_path(path: Path) -> None:
    """使用 Windows 預設程式開啟檔案或資料夾。"""
    try:
        os.startfile(str(path))
    except OSError as exc:
        notify_windows(f"無法開啟路徑：\n{path}\n\n{exc}", icon=MB_WARN)


def cleanup_old_files() -> None:
    """只清理本程式命名格式的 PNG，不碰其他檔案。"""
    if KEEP_DAYS <= 0:
        return
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in SAVE_DIR.glob(f"{FILE_PREFIX}*.png"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def save_unique(raw: bytes) -> Path:
    """把 PNG 存成不會覆蓋任何現有檔案的唯一檔名。

    檔名精確到毫秒；萬一仍撞名，改用獨佔模式 ("xb") 建立並自動加上 _1、_2…
    """
    SAVE_DIR.mkdir(parents=True, exist_ok=True)  # 資料夾執行中被刪掉也能自動補建
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 例：20261017_225602_481
    n = 0
    while True:
        name = f"{FILE_PREFIX}{stamp}.png" if n == 0 else f"{FILE_PREFIX}{stamp}_{n}.png"
        path = SAVE_DIR / name
        try:
            with open(path, "xb") as f:  # 檔案已存在會丟 FileExistsError，絕不覆蓋
                f.write(raw)
            return path
        except FileExistsError:
            n += 1


def encode_png(image: QImage) -> bytes | None:
    """把 QImage 編碼成 PNG 位元組；失敗回傳 None。"""
    data = QByteArray()
    buf = QBuffer(data)
    if not buf.open(QIODevice.WriteOnly):
        return None
    ok = image.save(buf, "PNG")
    buf.close()
    return bytes(data.data()) if ok else None


# ====================================================================
# 防止重複開啟
# ====================================================================
def _exit_already_running() -> None:
    notify_windows("ShotDrag 已經在執行中了。\n請到右下角系統匣（隱藏圖示）找藍色方塊圖示。")
    sys.exit(0)


def ensure_single_instance():
    """用 Windows 具名 Mutex 確保只有一份在執行。

    - 同名 Mutex 已存在          → 已有一份在跑，提示後離開
    - 建立失敗且為「存取被拒」    → 同名 Mutex 屬於別的權限，同樣視為已在執行
    - 其他原因建立失敗           → 警告使用者，但仍繼續執行（只是少了防重複保護）
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    err = ctypes.get_last_error()

    if not handle:  # 回傳 NULL = 建立失敗
        if err == ERROR_ACCESS_DENIED:
            _exit_already_running()
        notify_windows(
            f"無法建立單一執行保護（錯誤碼 {err}）。\n程式仍會繼續執行，但請避免重複開啟。",
            icon=MB_WARN,
        )
        return None
    if err == ERROR_ALREADY_EXISTS:
        _exit_already_running()
    return handle  # 必須一直持有，程式結束時系統才會自動釋放


# ====================================================================
# 開機自動啟動（寫入目前使用者的 Run 登錄項，不需系統管理員權限）
# ====================================================================
def autostart_command() -> str:
    if getattr(sys, "frozen", False):  # 已用 PyInstaller 包成 exe
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")  # 開機時不要跳出黑色視窗
    if pyw.exists():
        exe = pyw
    return f'"{exe}" "{Path(__file__).resolve()}"'


def is_autostart_enabled() -> bool:
    """只有登錄項存在、且指向目前這份程式時才算「已啟用」。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
        return value == autostart_command()
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ====================================================================
# 浮動縮圖
# ====================================================================
class Toast(QWidget):
    """右上角浮動縮圖，可拖曳出去當檔案用。"""

    def __init__(self, path: Path, image: QImage, on_closed: Callable[[Toast], None]) -> None:
        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,  # 不搶走聊天輸入框的焦點
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.path = path
        self.on_closed = on_closed
        self.pix = QPixmap.fromImage(image)
        self._press_pos: QPoint | None = None
        self._dragging = False

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)

        self.adjustSize()
        self._place()
        self.show()
        self.timer.start(SHOW_SECONDS * 1000)

    def _build_ui(self) -> None:
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            "#card { background: rgba(30,30,34,240);"
            " border: 1px solid rgba(255,255,255,50); border-radius: 12px; }"
            "QLabel { color: #d8d8d8; font-size: 11px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setPixmap(self.pix.scaled(THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        hint = QLabel("拖曳到對話框 · 雙擊開啟 · 右鍵關閉")
        hint.setAlignment(Qt.AlignCenter)
        for label in (thumb, hint):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)  # 讓滑鼠事件交給整張卡片
            layout.addWidget(label)

    def _place(self) -> None:
        """放在游標所在螢幕的右上角（避開工作列）。"""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = area.x() + area.width() - self.width() - MARGIN
        y = area.y() + MARGIN
        self.move(x, y)

    # ---- 事件 ----
    def enterEvent(self, event: QEvent) -> None:
        self.timer.stop()

    def leaveEvent(self, event: QEvent) -> None:
        if not self._dragging:
            self.timer.start(HIDE_AFTER_LEAVE_MS)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
        elif event.button() == Qt.RightButton:
            self.close()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            open_path(self.path)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_pos is None or not (event.buttons() & Qt.LeftButton):
            return
        moved = (event.position().toPoint() - self._press_pos).manhattanLength()
        if moved < QApplication.startDragDistance():
            return
        self._press_pos = None
        self._start_drag()

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.on_closed(self)
        super().closeEvent(event)

    # ---- 拖曳 ----
    def _start_drag(self) -> None:
        self._dragging = True
        self.timer.stop()

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.path))])  # 以檔案形式拖出

        preview = self.pix.scaledToWidth(DRAG_PREVIEW_WIDTH, Qt.SmoothTransformation)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(preview)
        drag.setHotSpot(QPoint(preview.width() // 2, preview.height() // 2))
        drag.exec(Qt.CopyAction)

        self._dragging = False
        self.timer.start(HIDE_AFTER_DRAG_MS)  # 拖完稍等一下自動收起


# ====================================================================
# 主程式（剪貼簿監聽 + 系統匣）
# ====================================================================
class ShotDrag:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.clipboard = app.clipboard()
        self.paused = False
        self.last_hash: str | None = None
        self.toast: Toast | None = None

        # 合併短時間內重複的剪貼簿通知，避免多次編碼同一張圖片。
        self.clipboard_timer = QTimer()
        self.clipboard_timer.setSingleShot(True)
        self.clipboard_timer.setInterval(CLIPBOARD_SETTLE_MS)
        self.clipboard_timer.timeout.connect(self.grab_image)

        self._prepare_save_dir()
        self._setup_tray()
        self.clipboard.dataChanged.connect(self.on_clipboard_changed)

    def _prepare_save_dir(self) -> None:
        try:
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            notify_windows(
                f"無法建立截圖資料夾：\n{SAVE_DIR}\n\n{exc}\n\n"
                "程式仍會執行，但截圖可能無法存檔。請檢查 SAVE_DIR 設定。",
                icon=MB_WARN,
            )
            return
        cleanup_old_files()

    @staticmethod
    def _create_tray_icon() -> QIcon:
        """簡約截圖取景框圖示；在高解析度畫布繪製，縮小後依然清楚。"""
        size = 128
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#182436"))
            painter.drawRoundedRect(7, 7, 114, 114, 29, 29)

            # 四個取景角：形狀比細節更重要，縮成系統匣小圖示也能辨識。
            pen = QPen(QColor("#F5FAFF"), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            for start, corner, end in (
                ((35, 55), (35, 35), (55, 35)),
                ((73, 35), (93, 35), (93, 55)),
                ((35, 73), (35, 93), (55, 93)),
                ((73, 93), (93, 93), (93, 73)),
            ):
                painter.drawLine(*start, *corner)
                painter.drawLine(*corner, *end)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#47D7C4"))
            painter.drawEllipse(55, 55, 18, 18)
        finally:
            painter.end()
        return QIcon(pix)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._create_tray_icon(), self.app)
        self.tray.setToolTip("ShotDrag：截圖後會浮出可拖曳的縮圖")

        self.menu = QMenu()  # 需保留參照，否則會被回收

        pause_act = self.menu.addAction("暫停監聽")
        pause_act.setCheckable(True)
        pause_act.toggled.connect(self.on_pause_toggled)

        self.autostart_act = self.menu.addAction("開機自動啟動")
        self.autostart_act.setCheckable(True)
        self.autostart_act.setChecked(is_autostart_enabled())
        self.autostart_act.toggled.connect(self.on_autostart_toggled)

        self.menu.addAction("開啟截圖資料夾", lambda: open_path(SAVE_DIR))
        self.menu.addSeparator()
        self.menu.addAction("結束", self.app.quit)

        self.tray.setContextMenu(self.menu)
        self.tray.show()
        self.app.aboutToQuit.connect(self.tray.hide)  # 避免結束後殘留幽靈圖示

    def _warn(self, message: str) -> None:
        """從系統匣跳出帶警告圖示的通知。"""
        self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Warning)

    # ---- 選單動作 ----
    def on_pause_toggled(self, paused: bool) -> None:
        self.paused = paused
        if paused:
            self.clipboard_timer.stop()  # 取消暫停前已排程的讀取
        self.tray.setToolTip("ShotDrag（已暫停）" if paused else "ShotDrag：截圖後會浮出可拖曳的縮圖")

    def on_autostart_toggled(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError as exc:
            self._warn(f"無法變更開機啟動設定：{exc}")
            self.autostart_act.blockSignals(True)  # 還原勾選狀態，避免畫面與實際不符
            self.autostart_act.setChecked(not enabled)
            self.autostart_act.blockSignals(False)

    # ---- 剪貼簿 ----
    def on_clipboard_changed(self) -> None:
        if self.paused:
            return
        self.clipboard_timer.start()  # 重啟倒數；只讀取最後一次穩定的剪貼簿內容

    def grab_image(self) -> None:
        if self.paused:
            return
        mime = self.clipboard.mimeData()
        if mime is None or not mime.hasImage():
            return
        image = self.clipboard.image()
        if image.isNull():
            return

        raw = encode_png(image)
        if raw is None:
            self._warn("無法將剪貼簿中的圖片編碼為 PNG。")
            return

        digest = hashlib.sha256(raw).hexdigest()
        if digest == self.last_hash:  # dataChanged 可能連發，避免重複
            return

        try:
            path = save_unique(raw)
        except OSError as exc:  # 資料夾無法寫入、磁碟已滿等
            self._warn(f"截圖存檔失敗：{exc}")
            return
        self.last_hash = digest  # 存檔成功才記錄，失敗時重新複製還能再試

        self.show_toast(path, image)

    def show_toast(self, path: Path, image: QImage) -> None:
        if self.toast is not None:
            self.toast.close()
        self.toast = Toast(path, image, self._toast_closed)

    def _toast_closed(self, toast: Toast) -> None:
        if self.toast is toast:
            self.toast = None


def main() -> int:
    sys.excepthook = log_exception
    _mutex = ensure_single_instance()  # 已有一份在跑就直接離開；變數需持有到程式結束

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # 縮圖關閉後程式仍留在系統匣

    _shotdrag = ShotDrag(app)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())