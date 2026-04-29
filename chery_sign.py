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
import time
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
        log(f"签到异常: {e}", "ERROR")
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
        share_url = f"{BASE_URL}/web/community/contents/{aid}/share?encryptParam={enc_token(token)}"
        share_body = aes_encrypt(json.dumps({"contentId": aid}, separators=(",", ":")))
        sr = requests.post(share_url, headers=APP_HEADERS, data=share_body.encode("utf-8"), timeout=30)
        sd = sr.json()
        if sd.get("status") == 200:
            reward_url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
            reward_body = aes_encrypt(json.dumps({"eventCode": "SJ10003"}, separators=(",", ":")))
            rr = requests.post(reward_url, headers=APP_HEADERS, data=reward_body.encode("utf-8"), timeout=30)
            rd = rr.json()
            if rd.get("status") == 200:
                return True, "分享成功并领取积分"
            return True, f"分享成功, 领取积分: {rd.get('message', '未知')}"
        return False, sd.get("message", "分享失败")
    except Exception as e:
        log(f"分享异常: {e}", "ERROR")
        return False, str(e)

def do_lottery(token):
    try:
        activities_url = f"{BASE_URL}/api/v1/activity/app/common/getActivityListToC?encryptParam={enc_token(token)}"
        r = requests.get(activities_url, headers=APP_HEADERS, timeout=30)
        d = r.json()
        if d.get("status") != 200:
            return False, "获取活动列表失败"
        activities = d.get("data", [])
        if not activities:
            return False, "暂无活动"
        lottery_activities = [a for a in activities if a.get("activityType") == "lottery"]
        if not lottery_activities:
            return False, "暂无抽奖活动"
        activity = lottery_activities[0]
        activity_id = activity.get("id")
        if not activity_id:
            return False, "活动ID为空"
        
        times_url = f"{BASE_URL}/api/v1/activity/app/lottery/queryDrawTimes?encryptParam={enc_token(token)}&activityId={activity_id}"
        tr = requests.get(times_url, headers=APP_HEADERS, timeout=30)
        td = tr.json()
        if td.get("status") != 200:
            return False, f"查询抽奖次数失败: {td.get('message')}"
        remaining_times = td.get("data", {}).get("remainingTimes", 0)
        if remaining_times <= 0:
            return False, "今日抽奖次数已用完"
        
        lottery_url = f"{BASE_URL}/api/v1/activity/app/lottery/draw?encryptParam={enc_token(token)}"
        body = aes_encrypt(json.dumps({"activityId": activity_id}, separators=(",", ":")))
        lr = requests.post(lottery_url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
        ld = lr.json()
        if ld.get("status") == 200:
            prize = ld.get("data", {}).get("prizeName", "未知奖品")
            return True, f"抽奖成功! 获得: {prize}"
        return False, ld.get("message", "抽奖失败")
    except Exception as e:
        log(f"抽奖异常: {e}", "ERROR")
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
    
    if datetime.now().weekday() == 2:
        log("今天是周三, 执行抽奖...")
        lok, lmsg = do_lottery(token)
        log(f"{'🎰' if lok else '❌'} 抽奖: {lmsg}")
    
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
        if i < len(accounts):
            time.sleep(2)
    log("=" * 45)
    log("✅ 全部完成")
    log("=" * 45)

if __name__ == "__main__":
    main()
