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
        log(f"签到请求URL: {url[:100]}...")
        log(f"签到请求体长度: {len(body)}")
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
        log(f"签到响应状态码: {r.status_code}")
        d = r.json()
        log(f"签到响应数据: {json.dumps(d, ensure_ascii=False)}")
        if d.get("status") == 200:
            return True, d.get("message", "成功")
        return False, d.get("message", "失败")
    except Exception as e:
        log(f"签到异常: {e}", "ERROR")
        return False, str(e)

def do_share(token):
    try:
        list_url = f"{BASE_URL}/web/community/recommend/contents?encryptParam={quote(aes_encrypt(f'pageNo=1&amp;pageSize=10&amp;access_token={token}&amp;terminal=3'), safe='')}"
        log(f"获取文章列表URL: {list_url[:100]}...")
        r = requests.get(list_url, headers=APP_HEADERS, timeout=30)
        log(f"文章列表响应状态码: {r.status_code}")
        d = r.json()
        log(f"文章列表响应数据: {json.dumps(d, ensure_ascii=False)[:500]}...")
        if d.get("status") != 200:
            return False, d.get("message", "获取文章失败")
        articles = d.get("data", {}).get("data", [])
        if not articles:
            return False, "无推荐文章"
        aid = str(articles[0]["content"]["id"])
        log(f"选中文章ID: {aid}")
        share_url = f"{BASE_URL}/web/community/contents/{aid}/share?encryptParam={enc_token(token)}"
        share_body = aes_encrypt(json.dumps({"contentId": aid}, separators=(",", ":")))
        log(f"分享请求URL: {share_url}")
        log(f"分享请求体长度: {len(share_body)}")
        log(f"分享请求体: {share_body[:100]}...")
        sr = requests.post(share_url, headers=APP_HEADERS, data=share_body.encode("utf-8"), timeout=30)
        log(f"分享响应状态码: {sr.status_code}")
        sd = sr.json()
        log(f"分享响应数据: {json.dumps(sd, ensure_ascii=False)}")
        if sd.get("status") == 200:
            log("分享成功, 尝试领取分享积分...")
            reward_url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
            reward_body = aes_encrypt(json.dumps({"eventCode": "SJ10003"}, separators=(",", ":")))
            rr = requests.post(reward_url, headers=APP_HEADERS, data=reward_body.encode("utf-8"), timeout=30)
            rd = rr.json()
            log(f"分享积分领取响应: {json.dumps(rd, ensure_ascii=False)}")
            if rd.get("status") == 200:
                return True, "分享成功并领取积分"
            return True, f"分享成功, 领取积分: {rd.get('message', '未知')}"
        return False, sd.get("message", "分享失败")
    except Exception as e:
        log(f"分享异常: {e}", "ERROR")
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
    nickname, points_before = get_info(token)
    if nickname is None:
        return
    points_before = int(points_before) if points_before else 0
    log(f"昵称: {nickname}, 积分: {points_before}")
    ok, msg = do_sign(token)
    log(f"{'✅' if ok else '❌'} 签到: {msg}")
    sok, smsg = do_share(token)
    log(f"{'✅' if sok else '⚠️'} 分享: {smsg}")
    _, points_after = get_info(token)
    points_after = int(points_after) if points_after else 0
    if points_after is not None:
        increase = points_after - points_before
        log(f"📈 本次积分变化: {'+' if increase >= 0 else ''}{increase}")
        log(f"💰 当前积分: {points_after}")

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
