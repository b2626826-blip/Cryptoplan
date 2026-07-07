"""Bitunix 私有 REST 簽名探測工具（唯讀、不下單）。

用途：用真實 API 金鑰呼叫 `get_account`（唯讀），驗證雙層 SHA256 簽名、
Header 與端點路徑是否正確。**本腳本只送唯讀查詢，絕不下任何單。**

金鑰來源（依序嘗試）：
    1. 專案根的 API_KEY.txt（格式：`API_KEY : xxx` / `Secret Key : yyy`）
    2. rapid_frame_bot/config.yaml 的 api.key / api.secret

執行（從 rapid_frame_bot/ 目錄）：
    python scripts/probe_rest.py
    python scripts/probe_rest.py --margin-coin USDT

判讀：
    · 回 {"code":0,...} 且 data 有 available → 簽名/路徑正確。
    · 回認證/簽名錯誤碼 → 依錯誤訊息修 api/rest.py 的簽名串接或 Header。
"""
from __future__ import annotations
import argparse
import asyncio
import re
import sys
from pathlib import Path
from types import SimpleNamespace

# Windows 主控台預設 cp950，輸出 ✓ 與中文會炸；強制 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

# 讓本腳本可從專案根（rapid_frame_bot/）匯入模組
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402
from exchanges.bitunix.rest import BitunixREST  # noqa: E402


def _load_keys() -> tuple[str, str]:
    """從 API_KEY.txt（優先）或 config.yaml 取得金鑰。"""
    key_txt = ROOT.parent / "API_KEY.txt"
    if key_txt.exists():
        text = key_txt.read_text(encoding="utf-8")
        k = re.search(r"API[_ ]?KEY\s*[:=]\s*(\S+)", text, re.I)
        s = re.search(r"Secret\s*Key\s*[:=]\s*(\S+)", text, re.I)
        if k and s:
            return k.group(1), s.group(1)

    cfg_yaml = ROOT / "config.yaml"
    if cfg_yaml.exists():
        import yaml
        d = yaml.safe_load(cfg_yaml.read_text(encoding="utf-8"))
        a = d.get("api", {})
        if a.get("key") and a.get("secret"):
            return a["key"], a["secret"]

    raise SystemExit("找不到金鑰：請確認 API_KEY.txt 或 config.yaml 有填。")


def _show(title: str, resp: dict) -> bool:
    """印出單一端點回應，回傳是否成功（code==0）。"""
    print(f"\n── {title} ──")
    print(resp)
    code = resp.get("code")
    if code == 0:
        print(f"  ✓ code=0（簽名/端點正確）")
        return True
    print(f"  ✗ code={code}, msg={resp.get('msg')} — 依官方文件核對路徑/參數。")
    return False


async def run(margin_coin: str) -> int:
    api_key, api_secret = _load_keys()
    print(f"金鑰已載入：api-key 前4碼={api_key[:4]}… (len={len(api_key)}), "
          f"secret len={len(api_secret)}")
    print("=" * 70)
    print("以下皆為唯讀查詢，絕不下單。")

    cfg = SimpleNamespace(api_key=api_key, api_secret=api_secret)
    ok = True
    async with aiohttp.ClientSession() as session:
        rest = BitunixREST(cfg, session)  # type: ignore[arg-type]

        acc = await rest.get_account(margin_coin=margin_coin)
        if _show(f"get_account (marginCoin={margin_coin})", acc):
            data = acc.get("data")
            if isinstance(data, dict):
                print(f"     available={data.get('available')}")
            elif isinstance(data, list):
                for item in data:
                    print(f"     {item.get('marginCoin')}: "
                          f"available={item.get('available')}")
        else:
            ok = False

        pos = await rest.get_pending_positions()
        if _show("get_pending_positions", pos):
            data = pos.get("data") or []
            print(f"     現有持倉數：{len(data) if isinstance(data, list) else '?'}")
        else:
            ok = False

        orders = await rest.get_pending_orders()
        if _show("get_pending_orders", orders):
            data = orders.get("data")
            # data 可能直接是 list，或包一層 {"orderList":[...]}（待真實回應確認）
            if isinstance(data, dict):
                print(f"     data keys：{list(data.keys())}")
            elif isinstance(data, list):
                print(f"     掛單數：{len(data)}")
        else:
            ok = False

    print("=" * 70)
    print("全部成功 ✓" if ok else "有端點失敗，見上方 ✗。")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Bitunix 私有 REST 簽名探測（唯讀）")
    ap.add_argument("--margin-coin", default="USDT")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.margin_coin)))


if __name__ == "__main__":
    main()
