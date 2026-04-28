#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
r = requests.get("https://www.baidu.com", timeout=10)
print(f"网络测试: {r.status_code}")
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

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")

def aes_encrypt(plaintext: str) -> str:
    iv = secrets.token_bytes(16)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size, style="pkcs7"))
    b64 = base64.b64encode(iv + encrypted).decode("utf-8")
    return b64.replace("+", "-")

def enc_token(token: str) -> str:
    return quote(aes_encrypt(f"access_token={token}&amp;terminal=3"), safe='')

def parse_accounts():
    val = os.getenv("CHERY_ACCOUNT") or os.getenv("chery", "")
    if not val:
        return []
    parts = [p.strip() for p in val.replace("\n", "&amp;").split("&amp;") if p.strip()]
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
            token = full.split("#")[0] if "#" in full else full
            return token
        log(f"登录失败: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"登录异常: {e}", "ERROR")
    return ""

def get_info(token):
    try:
        url = f"{BASE_URL}/web/user/current/details?encryptParam={enc_token(token)}"
        r = requests.get(url, headers=APP_HEADERS, timeout=30)
        d = r.json()
        if d.get("status") == 200:
            data = d["data"]
            return data.get("displayName", "?"), data.get("pointAccount", {}).get("payableBalance", 0)
        log(f"获取信息失败: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"信息异常: {e}", "ERROR")
    return None, None

def do_sign(token):
    try:
        url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
        body = aes_encrypt(json.dumps({"eventCode": "SJ10002"}, separators=(",", ":")))
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
        d = r.json()
        if d.get("status") == 200:
            return True, d.get("message", "成功")
        return False, d.get("message", "失败")
    except Exception as e:
        return False, str(e)

def do_share(token):
    try:
        list_url = f"{BASE_URL}/web/community/recommend/contents?encryptParam={quote(aes_encrypt(f'pageNo=1&amp;pageSize=10&amp;access_token={token}&amp;terminal=3'), safe='')}"
        r = requests.get(list_url, headers=APP_HEADERS, timeout=30)
        d = r.json()
        if d.get("status") != 200:
            return False, d.get("message", "获取文章失败")
        articles = d.get("data", {}).get("data", [])
        if not articles:
            return False, "无推荐文章"
        aid = str(articles[0]["content"]["id"])
        share_url = f"{BASE_URL}/web/community/contents/{aid}/share?encryptParams={enc_token(token)}"
        share_body = aes_encrypt(json.dumps({"contentId": aid}, separators=(",", ":")))
        sr = requests.post(share_url, headers=APP_HEADERS, data=share_body.encode("utf-8"), timeout=30)
        sd = sr.json()
        if sd.get("status") == 200:
            return True, sd.get("message", "分享成功")
        return False, sd.get("message", "分享失败")
    except Exception as e:
        return False, str(e)

def test_event_codes(token):
    """暴力测试所有可能的分享事件码"""
    candidates = [
        "SJ10001", "SJ10003", "SJ10004", "SJ10005", "SJ10006",
        "SJ10007", "SJ10008", "SJ10009", "SJ10010",
        "SJ20001", "SJ20002", "SJ20003", "SJ20004", "SJ20005",
        "SJ30001", "SJ30002", "SJ30003",
        "FX10001", "FX10002",
        "SHARE001", "SHARE002",
        "SJ10002",
    ]
    log("=" * 50)
    log("🔍 eventCode 暴力测试")
    log("=" * 50)
    for code in candidates:
        try:
            url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
            body = aes_encrypt(json.dumps({"eventCode": code}, separators=(",", ":")))
            r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=15)
            resp = r.json()
            status = resp.get("status", "?")
            msg = resp.get("message", resp.get("msg", str(resp)[:60]))
            marker = "✅" if status == 200 else "❌"
            log(f"{marker} {code:12s} | status={status} | {msg}")
        except Exception as e:
            log(f"❌ {code:12s} | 异常: {e}")

def process_account(acc, idx):
    name = acc.get("remark") or acc.get("phone") or "账号"
    log(f"--- 账号{idx}: {name} ---")
    token = acc.get("token", "")
    if not token and acc.get("phone"):
        log("正在登录...")
        token = login(acc["phone"], acc["password"])
    if not token:
        log("无有效token,跳过", "ERROR")
        return
    nickname, points = get_info(token)
    if nickname is None:
        return
    log(f"昵称: {nickname}, 积分: {points}")

    # 签到
    ok, msg = do_sign(token)
    log(f"{'✅' if ok else '❌'} 签到: {msg}")

    # 分享
    sok, smsg = do_share(token)
    log(f"{'✅' if sok else '⚠️'} 分享: {smsg}")

    # 暴力测试事件码
    test_event_codes(token)

def main():
    log("=" * 45)
    log("🚗 奇瑞汽车签到脚本启动")
    log("=" * 45)
    accounts = parse_accounts()
    if not accounts:
        log("❌ 未配置环境变量 CHERY_ACCOUNT", "ERROR")
        return
    log(f"共 {len(accounts)} 个账号")
    for i, acc in enumerate(accounts, 1):
        process_account(acc, i)
    log("=" * 45)
    log("✅ 全部完成")
    log("=" * 45)

if __name__ == "__main__":
    main()
