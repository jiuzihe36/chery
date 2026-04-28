#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奇瑞汽车自动签到+分享脚本 (优化版)
- 自动检测今日签到/分享状态
- 跳过已完成的操作
- 明确显示积分变化
"""
import requests
import json
import os
import base64
import secrets
import sys
from datetime import datetime
from urllib.parse import quote
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

# ======================== 配置 ========================
LOGIN_URL = "https://logintools.smallfawn.top/chery/loginByPassword"
BASE_URL = "https://mobile-consumer-sapp.chery.cn"
AES_KEY = base64.b64decode("vVfnp9ozfDQyonMKuqgZUWjtdV+7PtBqtMCwJqz2HKQ=")

APP_HEADERS = {
    "user-agent": "Dart/2.19 (dart:io)",
    "appversioncode": "26030901",
    "accept": "application/json, text/plain, */*",
    "appversion": "3.6.9",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json; charset=UTF-8",
    "agent": "android",
    "encryptflag": "true",
    "request-channel": "app",
    "host": "mobile-consumer-sapp.chery.cn",
}

# 每日分享积分上限（根据观察约为2次）
SHARE_DAILY_LIMIT = 2

# ======================== 工具函数 ========================

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")

def aes_encrypt(plaintext: str) -> str:
    iv = secrets.token_bytes(16)
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv))
    encryptor = cipher.encryptor()
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(iv + encrypted).decode("utf-8").replace("+", "-")

def enc_token(token: str) -> str:
    return quote(aes_encrypt(f"access_token={token}&terminal=3"), safe='')

def enc_params(params: dict, token: str) -> str:
    parts = [f"access_token={token}", "terminal=3"]
    for k, v in params.items():
        parts.append(f"{k}={v}")
    return quote(aes_encrypt("&".join(parts)), safe='')

def api_get(path, token, extra_params=None):
    if extra_params:
        url = f"{BASE_URL}{path}?encryptParam={enc_params(extra_params, token)}"
    else:
        url = f"{BASE_URL}{path}?encryptParam={enc_token(token)}"
    r = requests.get(url, headers=APP_HEADERS, timeout=30)
    return r.json()

def api_post(path, token, body_dict=None):
    url = f"{BASE_URL}{path}?encryptParam={enc_token(token)}"
    if body_dict:
        body = aes_encrypt(json.dumps(body_dict, separators=(",", ":")))
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
    else:
        r = requests.post(url, headers=APP_HEADERS, timeout=30)
    return r.json()

# ======================== 核心功能 ========================

def login(phone, password):
    """登录获取token"""
    try:
        r = requests.post(LOGIN_URL, json={"phone": phone, "password": password}, timeout=30)
        d = r.json()
        if d.get("status"):
            full = d.get("data", "")
            return full.split("#")[0] if "#" in full else full
        log(f"登录失败: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"登录异常: {e}", "ERROR")
    return ""

def get_user_info(token):
    """获取用户信息和积分"""
    d = api_get("/web/user/current/details", token)
    if d.get("status") == 200:
        data = d["data"]
        nickname = data.get("displayName", "?")
        points = int(data.get("pointAccount", {}).get("payableBalance", 0))
        return nickname, points
    log(f"获取用户信息失败: {d.get('message')}", "ERROR")
    return None, None

def get_today_flow(token):
    """获取今日积分流水"""
    d = api_get("/web/point/consumer/flow", token, {"pageNo": "1", "pageSize": "50"})
    if d.get("status") != 200:
        return []
    today = datetime.now().strftime("%Y-%m-%d")
    flows = d.get("data", {}).get("data", [])
    return [f for f in flows if f.get("createTime", "").startswith(today)]

def check_today_status(token):
    """检查今日签到和分享状态"""
    flows = get_today_flow(token)
    signed = False
    share_count = 0
    for f in flows:
        name = f.get("businessName", "")
        if "签到" in name:
            signed = True
        if "分享" in name:
            share_count += 1
    return signed, share_count

def do_sign(token):
    """执行签到"""
    d = api_post("/web/event/trigger", token, {"eventCode": "SJ10002"})
    if d.get("status") == 200:
        return True, d.get("message", "成功")
    return False, d.get("message", "失败")

def do_share(token, article_id):
    """执行分享"""
    url = f"{BASE_URL}/web/community/contents/{article_id}/share?encryptParams={enc_token(token)}"
    body = aes_encrypt(json.dumps({"contentId": article_id}, separators=(",", ":")))
    r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
    d = r.json()
    if d.get("status") == 200:
        return True, d.get("message", "成功")
    return False, d.get("message", "失败")

def get_articles(token, count=5):
    """获取推荐文章列表"""
    d = api_get("/web/community/recommend/contents", token, {"pageNo": "1", "pageSize": str(count)})
    if d.get("status") == 200:
        return d.get("data", {}).get("data", [])
    return []

# ======================== 主流程 ========================

def process_account(phone, password, remark=""):
    """处理单个账号"""
    name = remark or phone or "未知"
    log(f"{'='*45}")
    log(f"🚗 账号: {name}")
    log(f"{'='*45}")

    # 1. 登录
    log("正在登录...")
    token = login(phone, password)
    if not token:
        log("❌ 登录失败,跳过", "ERROR")
        return
    log("✅ 登录成功")

    # 2. 获取用户信息
    nickname, points = get_user_info(token)
    if nickname is None:
        return
    log(f"👤 昵称: {nickname}")
    log(f"💰 当前积分: {points}")

    # 3. 检查今日状态
    already_signed, share_count = check_today_status(token)
    log(f"📋 今日状态: 签到={'✅已完成' if already_signed else '❌未完成'}, 分享={share_count}次")

    results = {"sign": None, "share": 0, "points_before": points}

    # 4. 签到
    if already_signed:
        log("⏭️  签到: 今日已完成,跳过")
        results["sign"] = "skip"
    else:
        log("📝 执行签到...")
        ok, msg = do_sign(token)
        if ok:
            log(f"✅ 签到成功: {msg}")
            results["sign"] = "ok"
        else:
            log(f"❌ 签到失败: {msg}")
            results["sign"] = "fail"

    # 5. 分享
    remaining = SHARE_DAILY_LIMIT - share_count
    if remaining <= 0:
        log(f"⏭️  分享: 今日已分享{share_count}次(上限{SHARE_DAILY_LIMIT}),跳过")
        results["share"] = 0
    else:
        log(f"📤 还可分享 {remaining} 次,开始执行...")
        articles = get_articles(token, count=remaining + 2)
        if not articles:
            log("❌ 无法获取文章", "ERROR")
        else:
            earned = 0
            for art in articles:
                if earned >= remaining:
                    break
                aid = str(art["content"]["id"])
                title = art["content"].get("title", "?")[:25]

                pts_before = get_user_info(token)[1]
                ok, msg = do_share(token, aid)
                if ok:
                    log(f"  📤 分享: [{title}] → {msg}")
                    # 等一下再查积分变化
                    import time
                    time.sleep(2)
                    pts_after = get_user_info(token)[1]
                    diff = pts_after - pts_before if pts_before and pts_after else 0
                    if diff > 0:
                        log(f"     💰 +{diff} 积分!")
                        earned += 1
                    else:
                        log(f"     ⚠️  无积分变化(可能已达上限)")
                        break  # 没加分说明到上限了,不用继续
                else:
                    log(f"  ❌ 分享失败: [{title}] {msg}")
            results["share"] = earned

    # 6. 最终积分
    import time
    time.sleep(1)
    _, final_points = get_user_info(token)
    diff = final_points - points if final_points else 0

    log(f"")
    log(f"📊 汇总:")
    log(f"   签到: {results['sign']}")
    log(f"   分享: +{results['share']}次")
    log(f"   积分: {points} → {final_points} ({diff:+d})")

    return results

def parse_accounts():
    """解析环境变量中的账号"""
    val = os.getenv("CHERY_ACCOUNT") or os.getenv("chery", "")
    if not val:
        return []
    parts = [p.strip() for p in val.replace("\n", "&").split("&") if p.strip()]
    accounts = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if "#" in p and len(p.split("#")[0]) == 11:
            segs = p.split("#", 1)
            accounts.append({"phone": segs[0], "password": segs[1], "remark": ""})
            i += 1
        elif len(p) == 11 and p.isdigit() and i + 1 < len(parts):
            accounts.append({"phone": p, "password": parts[i + 1], "remark": ""})
            i += 2
        else:
            # token格式,跳过
            i += 1
    return accounts

def main():
    log("=" * 45)
    log("🚗 奇瑞汽车自动签到+分享")
    log("=" * 45)

    accounts = parse_accounts()
    if not accounts:
        log("❌ 未配置环境变量 CHERY_ACCOUNT", "ERROR")
        log("   格式: CHERY_ACCOUNT='手机号#密码' 或 '手机号#密码&手机号#密码'", "ERROR")
        return

    log(f"共 {len(accounts)} 个账号")

    total_ok = 0
    for i, acc in enumerate(accounts, 1):
        try:
            r = process_account(acc["phone"], acc["password"], acc.get("remark", ""))
            if r:
                total_ok += 1
        except Exception as e:
            log(f"❌ 账号{i}异常: {e}", "ERROR")

    log(f"")
    log("=" * 45)
    log(f"✅ 完成: {total_ok}/{len(accounts)} 个账号处理成功")
    log("=" * 45)

if __name__ == "__main__":
    main()
