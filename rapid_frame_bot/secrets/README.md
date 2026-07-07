# 金鑰設定

機器人依下列順序載入每家交易所金鑰（**環境變數優先於檔案**）：

## 方式一：環境變數（推薦，容器化友善）

    export BITUNIX_API_KEY=xxx
    export BITUNIX_API_SECRET=yyy
    export BINGX_API_KEY=xxx
    export BINGX_API_SECRET=yyy

## 方式二：檔案

在本目錄放 `<交易所名>.txt`，例如 `secrets/bitunix.txt`：

    API_KEY : xxx
    Secret Key : yyy

⚠️ 本目錄（除本 README）已被 .gitignore 忽略，金鑰不會進 git。
