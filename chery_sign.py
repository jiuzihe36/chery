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

LOGIN_URL = "https://logintools.smallfawn.top/chery/loginByPassword"
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

def parse_accounts():
    val = os.getenv("CHERY_ACCOUNT") or os.getenv("chery", "")
    if not val:
        return []
    parts = [p.strip() for p in val.replace("\n", "&").split("&") if p.strip()]
    accounts = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if "#" in p:
            segs = p.split("#", 1)
            accounts.append({"token": segs[0], "remark": segs[1]})
            i += 1
        elif len(p) == 11 and p.isdigit() and i + 1 < len(parts):
            accounts.append({"phone": p, "password": parts[i + 1]})
            i += 2
        else:
            accounts.append({"token": p})
            i += 1
    return accounts

def login(phone, password):
    try:
        r = requests.post(LOGIN_URL, json={"phone": phone, "password": password}, timeout=30)
        d = r.json()
        if d.get("status"):
            full = d.get("data", "")
            return full.split("#")[0] if "#" in full else full
    except Exception as e:
        print(f"登录异常: {e}")
    return ""

def get_token():
    accs = parse_accounts()
    if not accs:
        print("❌ 未配置 CHERY_ACCOUNT 环境变量")
        return ""
    acc = accs[0]
    token = acc.get("token", "")
    if not token and acc.get("phone"):
        token = login(acc["phone"], acc["password"])
    return token

def test_event(token, event_code):
    url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
    body = aes_encrypt(json.dumps({"eventCode": event_code}, separators=(",", ":")))
    try:
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def main():
    token = get_token()
    if not token:
        return
    print(f"✅ token 获取成功\n")

    candidates = [
        "SJ10001", "SJ10003", "SJ10004", "SJ10005", "SJ10006",
        "SJ10007", "SJ10008", "SJ10009", "SJ10010",
        "SJ20001", "SJ20002", "SJ20003", "SJ20004", "SJ20005",
        "SJ30001", "SJ30002", "SJ30003",
        "FX10001", "FX10002",
        "SHARE001", "SHARE002",
        "SJ10002",
    ]

    print("=" * 50)
    print("🔍 eventCode 暴力测试")
    print("=" * 50)

    for code in candidates:
        resp = test_event(token, code)
        status = resp.get("status", "?")
        msg = resp.get("message", resp.get("msg", str(resp)[:80]))
        marker = "✅" if status == 200 else "❌"
        print(f"{marker} {code:12s} | status={status} | {msg}")

if __name__ == "__main__":
    main()
