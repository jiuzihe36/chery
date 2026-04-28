#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import json
import os
import base64
import secrets
import time
from datetime import datetime
from urllib.parse import quote
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as crypto_padding

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
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv))
    encryptor = cipher.encryptor()
    padder = crypto_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    encrypted = encryptor.update(padded) + encryptor.finalize()
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
            return data.get("displayName", "?"), int(data.get("pointAccount", {}).get("payableBalance", 0))
        log(f"获取信息失败: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"信息异常: {e}", "ERROR")
    return None, None

def get_points(token):
    try:
        url = f"{BASE_URL}/web/point/consumer/info?encryptParam={enc_token(token)}"
        r = requests.get(url, headers=APP_HEADERS, timeout=15)
        d = r.json()
        if d.get("status") == 200:
            return int(d["data"]["payableBalance"])
    except:
        pass
    return None

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

def get_articles(token):
    try:
        url = f"{BASE_URL}/web/community/recommend/contents?encryptParam={quote(aes_encrypt(f'pageNo=1&pageSize=10&access_token={token}&terminal=3'), safe='')}"
        r = requests.get(url, headers=APP_HEADERS, timeout=30)
        d = r.json()
        if d.get("status") == 200:
            articles = d.get("data", {}).get("data", [])
            if articles:
                return str(articles[0]["content"]["id"])
    except Exception as e:
        log(f"获取文章异常: {e}", "ERROR")
    return None

def do_share(token, aid):
    try:
        url = f"{BASE_URL}/web/community/contents/{aid}/share?encryptParam={enc_token(token)}"
        body = aes_encrypt(json.dumps({"contentId": aid}, separators=(",", ":")))
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
        d = r.json()
        if d.get("status") == 200:
            return True, d.get("message", "成功")
        return False, d.get("message", "失败")
    except Exception as e:
        return False, str(e)

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

    # 获取文章
    aid = get_articles(token)
    if not aid:
        log("无法获取文章ID", "ERROR")
        return

    # 分享 (每天最多2积分)
    share_count = 0
    for i in range(2):
        ok, msg = do_share(token, aid)
        log(f"{'✅' if ok else '❌'} 分享{i+1}: {msg}")
        if ok:
            share_count += 1
        time.sleep(1)

    # 等待积分到账
    log("等待积分到账...")
    time.sleep(25)

    # 检查积分变化
    new_points = get_points(token)
    if new_points is not None:
        gained = new_points - points
        log(f"📊 积分变化: {points} → {new_points} (+{gained})")
    else:
        log("无法获取积分", "ERROR")

def main():
    log("=" * 45)
    log("🚗 奇瑞汽车签到脚本 v3")
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
