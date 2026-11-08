# ShotDrag

Windows 截圖拖曳小工具（PySide6）。使用 `Win + Shift + S` 截圖後，程式會在螢幕右上角顯示可拖曳縮圖，方便將 PNG 拖放到支援檔案拖曳的應用程式。

> 此程式由使用者自行在 Windows 執行；GitHub 倉庫僅保存原始碼，不會自動執行程式。原始碼已通過 Python 語法檢查，但尚未在此環境執行 Windows GUI 自動化測試。

## 功能

- 監聽剪貼簿中的圖片（不限於 Windows 截圖快捷鍵）
- 使用可重啟的 150ms 單次計時器，合併密集的剪貼簿變動通知
- 將圖片儲存為 PNG，避免覆寫現有檔案
- 提供可拖曳縮圖，雙擊可開啟圖片，右鍵關閉
- Windows 系統匣常駐、暫停監聽、開機啟動選項
- 簡約設計的系統匣圖示
- 透過 Mutex 防止程式重複啟動
- 發生未預期錯誤時，可查看 `%LOCALAPPDATA%\ShotDrag\error.log`

## 使用環境

- Windows 10 / 11
- Python 3.12（目前使用的版本）
- [PySide6](https://pypi.org/project/PySide6/)

## 安裝與啟動

在 PowerShell 中進入放置程式的資料夾後：

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 shotdrag.py
```

確認可正常使用後，若希望不顯示 PowerShell 主控台，可以使用對應 Python 安裝位置的 `pythonw.exe` 啟動 `shotdrag.py`。請注意：使用 `pythonw.exe` 時，啟動錯誤不會出現在終端機內；必要時先用 `python.exe` 除錯。

## 檔案儲存位置

程式會在 `shotdrag.py` 所在目錄旁自動建立 `screenshot/`，截圖以 `截圖_*.png` 命名；此資料夾已在 `.gitignore` 中排除，不應提交至 GitHub。

## 系統匣操作

在 ShotDrag 圖示上按右鍵，可暫停或恢復監聽、設定登入 Windows 後自動執行、開啟截圖資料夾，或結束程式。

## 已知限制

- 若在 150ms 的合併時間內連續複製多張不同圖片，可能只會保留最後一張剪貼簿圖片；此功能不保證每次快速截圖都會保存。
- 連續複製與上一張內容完全相同的圖片時，程式可能不會再次顯示縮圖。
- 程式目前只支援 Windows，且必須在本機安裝 PySide6。

## 隱私

截圖保存在本機，不會由 ShotDrag 自動上傳到 GitHub；請勿將 `screenshot/`、`error.log`、任何個人截圖或含有憑證的設定檔提交至公開倉庫。建議先以 **Private** 倉庫保存。