"""Bitunix 私有 WebSocket 探測工具（登入 + 訂閱訂單頻道，唯讀不下單）。

用途：用真實 API 金鑰對私有 WS 登入，驗證 login 簽名公式與訂單頻道訂閱格式，
並印出所有原始訊息（登入確認、訂單推送）。**只送 login / subscribe / ping，
絕不下任何單。**

金鑰來源：專案根 API_KEY.txt（同 probe_rest.py）。

執行（從 rapid_frame_bot/ 目錄）：
    python scripts/probe_private_ws.py
    python scripts/probe_private_ws.py --timeout 30

判讀：
    · 登入成功 → 之後可收到 order 頻道推送（若當下有掛單/成交變動）。
    · 登入失敗（回認證錯誤）→ 依錯誤訊息修 api/ws.py 的 sign_login 公式或 login 格式。
"""
from __future__ import annotations
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import websockets  # noqa: E402
from exchanges.bitunix.ws import BitunixWS, parse_order_message  # noqa: E402

PRIVATE_URL = "wss://fapi.bitunix.com/private/"


def _load_keys() -> tuple[str, str]:
    key_txt = ROOT.parent / "API_KEY.txt"
    if key_txt.exists():
        text = key_txt.read_text(encoding="utf-8")
        k = re.search(r"API[_ ]?KEY\s*[:=]\s*(\S+)", text, re.I)
        s = re.search(r"Secret\s*Key\s*[:=]\s*(\S+)", text, re.I)
        if k and s:
            return k.group(1), s.group(1)
    raise SystemExit("找不到金鑰：請確認 API_KEY.txt。")


async def run(timeout: float, bad_sign: bool = False) -> int:
    api_key, api_secret = _load_keys()
    login = BitunixWS.build_login(api_key, api_secret)
    if bad_sign:
        login["args"][0]["sign"] = "0" * 64  # 故意錯簽名，用於對照實驗
        print("⚠ 對照模式：故意送錯誤簽名，觀察伺服器是否有別於正常的反應。")
    print(f"金鑰已載入：api-key 前4碼={api_key[:4]}… ")
    print(f"連線中：{PRIVATE_URL}")
    sub = {"op": "subscribe", "args": ["order"]}
    # 策略：等 connect 問候 → 送 login → 2 秒後主動送訂閱（因伺服器可能不回 login 回執）
    # → 監聽是否有 login 回應 / 訂閱回應 / 被踢線。
    logged_in = False
    sent_login = False
    subscribed = False
    sub_after = None  # 預定送訂閱的時間
    try:
        async with websockets.connect(PRIVATE_URL, open_timeout=15) as ws:
            print("✓ 連線成功")
            print("=" * 70)
            deadline = time.monotonic() + timeout
            n = 0
            while time.monotonic() < deadline:
                # 到時間且尚未訂閱 → 主動送訂閱（不等 login 回執）
                if sub_after is not None and not subscribed and \
                        time.monotonic() >= sub_after:
                    await ws.send(json.dumps(sub))
                    subscribed = True
                    print(f"        → （主動）送訂閱：{json.dumps(sub)}")

                try:
                    wait = max(0.2, min(deadline, (sub_after or deadline))
                               - time.monotonic())
                    raw = await asyncio.wait_for(ws.recv(), timeout=wait)
                except asyncio.TimeoutError:
                    continue
                n += 1
                text = raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")
                print(f"[原始 #{n}] {text[:400]}")
                try:
                    msg = json.loads(text)
                except Exception:  # noqa: BLE001
                    print("        （非 JSON，可能是心跳）")
                    continue
                op = msg.get("op")

                if op == "ping":
                    await ws.send(json.dumps({"op": "pong", "pong": msg.get("ping")}))
                    print("        → 回 pong")
                    continue

                if op == "connect" and not sent_login:
                    await ws.send(json.dumps(login))
                    sent_login = True
                    sub_after = time.monotonic() + 2.0
                    print(f"        → 連線確認，已送 login "
                          f"(nonce={login['args'][0]['nonce'][:8]}…)；2s 後送訂閱")
                    continue

                if op == "login":
                    ok = (msg.get("data", {}) or {}).get("result", None)
                    logged_in = bool(ok) or msg.get("code") in (0, "0")
                    print(f"        {'✓ 登入成功' if logged_in else '✗ 登入失敗'}：{msg}")
                    continue

                parsed = parse_order_message(msg)
                if parsed:
                    print(f"        ✓ 訂單事件：orderId={parsed[0]} status={parsed[1]}")

            print("=" * 70)
            print(f"共收到 {n} 則訊息；login {'已送' if sent_login else '未送'}，"
                  f"訂閱 {'已送' if subscribed else '未送'}，"
                  f"連線結束時仍存活（未被踢線）。")
            return 0
    except websockets.ConnectionClosed as exc:
        print("=" * 70)
        print(f"✗ 連線被伺服器關閉：code={exc.code} reason={exc.reason!r}")
        print("  （若僅在錯誤簽名時被關閉 → 代表正常簽名其實有通過）")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"✗ 失敗：{type(exc).__name__}: {exc}")
        return 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Bitunix 私有 WS 探測（唯讀）")
    ap.add_argument("--timeout", type=float, default=25.0,
                    help="總監聽秒數")
    ap.add_argument("--bad-sign", action="store_true",
                    help="對照實驗：故意送錯誤簽名")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.timeout, args.bad_sign)))


if __name__ == "__main__":
    main()
