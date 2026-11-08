# ShotDrag

**English** | [繁體中文](#繁體中文)

A lightweight Windows utility that turns clipboard images into draggable PNG files. Capture with **Win + Shift + S**, then drag the floating thumbnail into apps that accept file drops, such as ChatGPT, Claude, Discord, or LINE.

> **Status:** Personal project / work in progress. Python syntax has been checked, and the user has tested basic screenshot capture on Windows; cross-machine testing and automated Windows GUI tests have not been completed.

## Features

- Watches the Windows clipboard for images (not limited to the screenshot shortcut).
- Uses a restartable, single-shot 150 ms timer to debounce rapid clipboard notifications.
- Saves each captured image as a PNG with a collision-resistant filename without overwriting files.
- Shows a draggable floating thumbnail. Double-click to open; right-click to dismiss.
- Runs in the Windows system tray with pause/resume, open-folder, exit, and optional auto-start.
- Uses a single-instance mutex to prevent accidentally running multiple copies.
- Writes unexpected Python errors to `%LOCALAPPDATA%\ShotDrag\error.log`.
- Includes a minimalist system tray icon.

## Requirements

- Windows 10 or Windows 11
- Python 3.12 (the version used for development; other versions are not verified)
- [PySide6](https://pypi.org/project/PySide6/)

## Installation

Clone or download this repository. Open PowerShell in the folder containing `shotdrag.py`, then run:

~~~powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 shotdrag.py
~~~

Once you have verified it launches, you can start it with `pythonw.exe` from the **same Python environment** to hide the console window. When troubleshooting, use `python.exe` so startup errors are visible.

## Usage

1. Run ShotDrag and look for its icon in the system tray (including hidden icons).
2. Press **Win + Shift + S** and take a screenshot, or copy an image to the clipboard.
3. Drag the thumbnail that appears in the upper-right corner into a compatible app.
4. Right-click the tray icon to pause/resume, open the screenshot folder, enable auto-start, or quit.

**Where files go:** ShotDrag creates a `screenshot/` folder next to `shotdrag.py` and saves images there as `截圖_*.png`. This folder is excluded by `.gitignore`.

## Known limitations

- Debouncing is **not a queue**: if multiple different images arrive within the 150 ms window, only the most recent clipboard image may be processed.
- An image identical to the previously saved one may not produce another thumbnail because of duplicate suppression.
- This project is Windows-only and is distributed as Python source code, **not** a pre-built Windows executable.
- Auto-start settings refer to the location of the script. If you move or rename it, update the auto-start setting.

## Privacy

ShotDrag saves images locally. It does not upload screenshots to GitHub or to any server on its own. Do not commit your personal screenshots, error logs, API keys, or other private files to the repository.

## License

Licensed under the [MIT License](LICENSE). You may use, modify, and redistribute this code under the terms of that license.

---

## 繁體中文

**ShotDrag** 是 Windows 截圖拖曳小工具。按 **Win + Shift + S** 截圖後，畫面右上角會出現浮動縮圖，可直接拖進支援檔案拖放的 ChatGPT、Claude、LINE、Discord 等程式。

### 主要功能

- 監聽剪貼簿圖片，不限於 Windows 截圖快捷鍵。
- 使用 150 毫秒單次計時器合併密集的剪貼簿通知。
- 將圖片另存為 PNG，不覆蓋既有檔案。
- 浮動縮圖可拖曳；雙擊開啟；右鍵關閉。
- 系統匣提供暫停／恢復、開啟資料夾、開機啟動與結束功能。
- 具備簡約系統匣圖示、單一執行個體保護與錯誤日誌。

### 安裝與執行

需要 Windows 10／11、Python 3.12 和 PySide6。先下載本倉庫並在程式所在資料夾開啟 PowerShell：

~~~powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 shotdrag.py
~~~

測試成功後，可使用與安裝 PySide6 相同 Python 環境的 `pythonw.exe` 背景啟動，避免跳出主控台。若程式無法啟動，先以 `python.exe` 查看錯誤。

### 截圖儲存與操作

程式會在 `shotdrag.py` 旁自動建立 `screenshot/` 資料夾，並將圖片以 `截圖_*.png` 命名。系統匣選單可以暫停監聽、開啟儲存資料夾、設定開機啟動及結束程式。

### 已知限制與隱私

- 在 150 毫秒內快速連續複製多張圖片，可能只處理最後一張。
- 若新複製的圖片與上一張完全相同，可能不會重新顯示縮圖。
- 本工具只支援 Windows，尚未全面完成 Windows GUI 自動化測試。
- 截圖只存放在本機，不會由本程式自動上傳至 GitHub。請勿提交 `screenshot/`、日誌或私人憑證。

### 授權

本專案採用 [MIT License](LICENSE)，允許依授權條款使用、修改及再散布。
