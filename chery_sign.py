#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import json
import os
import base64
import secrets
import random
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


def aes_encrypt(plaintext):
    iv = secrets.token_bytes(16)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size, style="pkcs7"))
    b64 = base64.b64encode(iv + encrypted).decode("utf-8")
    return b64.replace("+", "-")


def enc_token(token):
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
        log(f"login failed: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"login error: {e}", "ERROR")
    return ""


def get_info(token):
    try:
        url = f"{BASE_URL}/web/user/current/details?encryptParam={enc_token(token)}"
        r = requests.get(url, headers=APP_HEADERS, timeout=30)
        d = r.json()
        if d.get("status") == 200:
            data = d["data"]
            return data.get("displayName", "?"), data.get("pointAccount", {}).get("payableBalance", 0)
        log(f"get info failed: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"get info error: {e}", "ERROR")
    return None, None


def do_sign(token):
    try:
        url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
        body = aes_encrypt(json.dumps({"eventCode": "SJ10002"}, separators=(",", ":")))
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
        d = r.json()
        if d.get("status") == 200:
            return True, d.get("message", "ok")
        return False, d.get("message", "fail")
    except Exception as e:
        return False, str(e)


def get_articles(token):
    try:
        enc = quote(aes_encrypt(f"pageNo=1&pageSize=10&access_token={token}&terminal=3"), safe='')
        url = f"{BASE_URL}/web/community/recommend/contents?encryptParam={enc}"
        r = requests.get(url, headers=APP_HEADERS, timeout=30)
        d = r.json()
        if d.get("status") == 200:
            return d.get("data", {}).get("data", [])
    except Exception as e:
        log(f"get articles error: {e}", "ERROR")
    return []


def do_share(token):
    articles = get_articles(token)
    if not articles:
        return False, "no articles"

    article = random.choice(articles)
    aid = str(article["content"]["id"])
    log(f"article: [{aid}] {article['content'].get('title', '?')[:30]}")

    strategies = []

    strategies.append(("user-action(share)", lambda: requests.post(
        f"{BASE_URL}/web/op/user-action?encryptParam={enc_token(token)}",
        headers=APP_HEADERS,
        data=aes_encrypt(json.dumps({"action": "share", "bizId": aid, "bizType": "content", "channel": "wechat"}, separators=(",", ":"))).encode("utf-8"),
        timeout=30
    )))

    strategies.append(("user-action(shareContent)", lambda: requests.post(
        f"{BASE_URL}/web/op/user-action?encryptParam={enc_token(token)}",
        headers=APP_HEADERS,
        data=aes_encrypt(json.dumps({"action": "shareContent", "contentId": aid, "platform": "wechat", "shareType": "1"}, separators=(",", ":"))).encode("utf-8"),
        timeout=30
    )))

    for code in ["SJ10003", "SJ10004", "SJ10005", "SJ10006"]:
        strategies.append((f"event({code})", lambda c=code: requests.post(
            f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}",
            headers=APP_HEADERS,
            data=aes_encrypt(json.dumps({"eventCode": c, "bizId": aid, "bizType": "content"}, separators=(",", ":"))).encode("utf-8"),
            timeout=30
        )))

    strategies.append(("original", lambda: requests.post(
        f"{BASE_URL}/web/community/contents/{aid}/share?encryptParams={enc_token(token)}",
        headers=APP_HEADERS,
        data=aes_encrypt(json.dumps({"contentId": aid}, separators=(",", ":"))).encode("utf-8"),
        timeout=30
    )))

    for name, req_fn in strategies:
        try:
            sr = req_fn()
            sd = sr.json()
            status = sd.get("status")
            msg = sd.get("message", "")
            log(f"  [{name}] status={status}, msg={msg}", "DEBUG")
            if status == 200:
                return True, f"{name}: {msg}"
        except Exception as e:
            log(f"  [{name}] error: {e}", "DEBUG")

    return False, "all strategies failed"


def process_account(acc, idx):
    name = acc.get("remark") or acc.get("phone") or "account"
    log(f"--- account {idx}: {name} ---")
    token = acc.get("token", "")
    if not token and acc.get("phone"):
        log("logging in...")
        token = login(acc["phone"], acc["password"])
        if not token:
            log("no valid token, skip", "ERROR")
            return

    nickname, points = get_info(token)
    if nickname is None:
        return
    log(f"user: {nickname}, points: {points}")

    ok, msg = do_sign(token)
    log(f"{'pass' if ok else 'fail'} sign: {msg}")

    sok, smsg = do_share(token)
    log(f"{'pass' if sok else 'warn'} share: {smsg}")

    if sok:
        _, points2 = get_info(token)
        if points2 and points2 > points:
            log(f"points: {points} -> {points2} (+{points2 - points})")
        elif points2 is not None:
            log(f"points unchanged: {points2}", "WARN")


def main():
    log("=" * 45)
    log("chery sign script v4")
    log("=" * 45)
    accounts = parse_accounts()
    if not accounts:
        log("no CHERY_ACCOUNT env", "ERROR")
        return
    log(f"total {len(accounts)} accounts")
    for i, acc in enumerate(accounts, 1):
        process_account(acc, i)
    log("=" * 45)
    log("done")
    log("=" * 45)


if __name__ == "__main__":
    main()
