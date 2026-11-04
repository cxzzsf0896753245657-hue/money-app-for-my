# 記帳本（打包成 Android APK）

這個專案把「記帳本」網頁 App 用 Capacitor 包成 Android APK，並由 GitHub Actions 自動打包，你不需要在電腦上安裝 Android Studio。

## 檔案說明

| 路徑 | 用途 |
|---|---|
| `www/index.html` | App 本體（單一檔案，所有功能都在裡面） |
| `www/manifest.webmanifest`、`www/sw.js`、`www/icon-*.png` | 網頁版「加到主畫面」與離線快取用 |
| `assets/` | APK 的 App 圖示來源（1024 像素） |
| `capacitor.config.json`、`package.json` | 打包設定（App 名稱、套件版本） |
| `.github/workflows/build-apk.yml` | 打包 APK 的自動流程 |
| `.github/workflows/update-prices.yml`、`scripts/update_prices.py`、`symbols.txt` | 每天自動抓股價（可選） |

## 一、打包 APK

1. 在 GitHub 建一個新的 repo（Private 或 Public 都可以）。
2. 把這個資料夾裡的**所有檔案與資料夾**上傳（包含開頭是點的 `.github`、`.gitignore`）。用網頁上傳時，請把整個資料夾拖進去；`.github` 若沒有一起上傳，Actions 不會出現。
3. 到 repo 的 **Settings → Actions → General → Workflow permissions**，選 **Read and write permissions**，按 Save。
4. 到 **Actions** 頁面 → 左邊選 **build-apk** → 右邊 **Run workflow**。
5. 約 5～10 分鐘後完成。點進那次執行，最下面 **Artifacts** 有 `money-app-apk`，下載解壓縮就是 `app-debug.apk`。
6. 把 APK 傳到手機安裝（手機要允許「安裝未知來源的應用程式」）。

之後想發佈固定版本：推送標籤（例如 `v1.0.0`），APK 會自動附在 Releases 頁面。

## 二、每日更新股價（可選）

1. 編輯 `symbols.txt`，換成你的持股代號（App 裡「帳戶詳情 → 持股 → 代號清單」可以複製）。
2. 到 Actions → **update-prices** → Run workflow 手動跑一次，之後平日台灣時間 16:30 會自動更新，結果存在 repo 根目錄的 `prices.json`。
3. 在 App 的「帳戶詳情 → 持股 → 代號清單」最下面，貼上股價檔網址：
   `https://raw.githubusercontent.com/你的帳號/你的倉庫/main/prices.json`
   （Private repo 讀不到，需要改成 Public）。
4. 基金、債券請在 App 裡手動輸入淨值。

APK 版另外會直接連證交所與 Yahoo 抓價，不一定要設定網址。

## 三、App 識別碼與更新

Android 用三樣東西判斷「這是不是同一個 App、能不能直接更新」：

| 項目 | 設定位置 | 目前值 |
|---|---|---|
| App 識別碼（appId） | `capacitor.config.json` | `com.example.moneyapp` |
| 簽章金鑰 | `signing/money-app.keystore` | 已建立，打包時固定使用 |
| 版本號（versionCode） | 打包時自動設為第幾次執行 | 每次打包自動加一 |

- **第一次安裝前，請先決定 appId**（例如改成 `com.你的名字.money`）。改了就會被當成另一個 App，無法覆蓋舊的、資料也不會帶過去。
- **簽章金鑰請保留好**。換了金鑰，手機會拒絕覆蓋安裝，只能先解除安裝（資料會消失）。這個金鑰和密碼都放在專案裡，方便你不用另外設定；因此 repo 請設成 **Private**，也不要把它拿去上架。
- 更新時直接安裝新的 APK 即可覆蓋，資料會保留。
- 如果你安裝過更早之前、還沒有固定簽章的 APK，第一次換成這一版需要先解除安裝（先備份）。

## 四、注意事項

- **資料只存在手機裡**。APK 版和瀏覽器版的資料是分開的：從網頁版搬過去，請先在網頁版「更多 → 備份與還原」複製備份，再到 APK 裡貼上還原。換手機、解除安裝前也請先備份。
- 這個 APK 可以自己安裝使用，但不能上架 Google Play。要上架需要另外建立私有的簽章金鑰（不要放進 repo）並改用 release 打包。
- 更新 App 內容：把新的 `index.html` 覆蓋到 `www/index.html`，再執行一次 build-apk。
- 如果 build-apk 失敗，點進失敗的步驟看紅字訊息，把訊息貼給我即可。
