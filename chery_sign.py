#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import json
import os
import base64
import secrets
from datetime import datetime
from urllib.parse import quote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

BASE_URL = "https://mobile-consumer-sapp.chery.cn"
AES_KEY = base64.b64decode("vVfnp9ozfDQyonMKuqgZUWjtdV+7PtBqtMCwJqz2HKQ=")

APP_HEADERS = {
    "user-agent": "Dart/2.19 (dart:io)",
    "appversioncode": "26030901",
    "accept": "application/json, text/plain, */*",
    "appversion": "3.6.9",
    "accept-language": "zh-CN,zh;q=0.9",
    "accept-encoding": "gzip, deflate",
    "content-type": "application/json; charset=UTF-8",
    "agent": "android",
    "encryptflag": "true",
    "request-channel": "app",
    "host": "mobile-consumer-sapp.chery.cn",
}

def aes_encrypt(plaintext: str) -> str:
    iv = secrets.token_bytes(16)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size, style="pkcs7"))
    b64 = base64.b64encode(iv + encrypted).decode("utf-8")
    return b64.replace("+", "-")

def enc_token(token: str) -> str:
    return quote(aes_encrypt(f"access_token={token}&terminal=3"), safe='')

def test_event(token, event_code, extra_params=None):
    url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
    payload = {"eventCode": event_code}
    if extra_params:
        payload.update(extra_params)
    body = aes_encrypt(json.dumps(payload, separators=(",", ":")))
    try:
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=15)
        d = r.json()
        return d
    except Exception as e:
        return {"error": str(e)}

def main():
    token = os.getenv("CHERY_TOKEN", "").strip()
    if not token:
        print("❌ 请设置环境变量 CHERY_TOKEN（你的 access_token）")
        print("   export CHERY_TOKEN=你的token")
        return

    # 已知: SJ10002 = 签到
    # 猜测: 分享相关的事件码
    candidates = [
        "SJ10001", "SJ10003", "SJ10004", "SJ10005", "SJ10006",
        "SJ10007", "SJ10008", "SJ10009", "SJ10010",
        "SJ20001", "SJ20002", "SJ20003", "SJ20004", "SJ20005",
        "SJ30001", "SJ30002", "SJ30003",
        "FX10001", "FX10002",
        "SHARE001", "SHARE002",
        "SJ10002",  # 已知签到，作为对照
    ]

    print("=" * 50)
    print("🔍 奇瑞汽车 eventCode 暴力测试")
    print("=" * 50)

    results = []
    for code in candidates:
        resp = test_event(token, code)
        status = resp.get("status", "?")
        msg = resp.get("message", resp.get("msg", str(resp)[:80]))
        marker = "✅" if status == 200 else "❌"
        print(f"{marker} {code:12s} | status={status} | {msg}")
        results.append((code, status, msg))

    print("\n" + "=" * 50)
    print("📊 汇总:")
    ok_list = [r for r in results if r[1] == 200]
    if ok_list:
        print(f"成功 ({len(ok_list)}):")
        for code, status, msg in ok_list:
            print(f"  ✅ {code} → {msg}")
    else:
        print("没有找到新的有效事件码")

if __name__ == "__main__":
    main()
