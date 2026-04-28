#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奇瑞汽车 APP 自动签到 + 分享脚本 v3
基于 APK 反编译分析修正：
  - 原 /web/community/contents/{id}/share 端点在 APP 中不存在
  - 分享通过 web/op/user-action 记录用户行为
  - 或通过 web/event/trigger 触发分享事件
"""
import requests
import json
import os
import base64
import secrets
import time
import sys
import random
from datetime import datetime
from urllib.parse import quote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ==================== 配置 ====================
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

REQUEST_DELAY = 1.5


# ==================== 工具函数 ====================
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def aes_encrypt(plaintext: str) -> str:
    iv = secrets.token_bytes(16)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(
        pad(plaintext.encode("utf-8"), AES.block_size, style="pkcs7")
    )
    b64 = base64.b64encode(iv + encrypted).decode("utf-8")
    return b64.replace("+", "-")


def enc_token(token: str) -> str:
    return quote(aes_encrypt(f"access_token={token}&terminal=3"), safe="")


def enc_params_str(params_str: str) -> str:
    return quote(aes_encrypt(params_str), safe="")


def safe_request(method, url, retries=2, **kwargs):
    kwargs.setdefault("timeout", 30)
    for attempt in range(retries + 1):
        try:
            r = getattr(requests, method.lower())(url, **kwargs)
            return r
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                log(f"请求失败，重试 {attempt + 1}: {e}", "WARN")
                time.sleep(1)
            else:
                raise


def api_call(token, method, path, body_dict=None, raw_body=None):
    """统一 API 调用"""
    url = f"{BASE_URL}{path}?encryptParam={enc_token(token)}"
    data = None
    if body_dict:
        data = aes_encrypt(json.dumps(body_dict, separators=(",", ":"))).encode("utf-8")
    elif raw_body:
        data = aes_encrypt(raw_body).encode("utf-8")
    r = safe_request(method, url, headers=APP_HEADERS, data=data)
    try:
        d = r.json()
        log(f"  API {method} {path} → status={d.get('status')}, msg={d.get('message', '')[:50]}", "DEBUG")
        return d
    except:
        log(f"  API 响应非JSON: {r.text[:100]}", "WARN")
        return {"status": r.status_code, "message": r.text[:100]}


# ==================== 账号解析 ====================
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


# ==================== 核心功能 ====================
def login(phone, password):
    try:
        r = safe_request("POST", LOGIN_URL, json={"phone": phone, "password": password})
        d = r.json()
        if d.get("status"):
            full = d.get("data", "")
            return full.split("#")[0] if "#" in full else full
        log(f"登录失败: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"登录异常: {e}", "ERROR")
    return ""


def get_info(token):
    try:
        d = api_call(token, "GET", "/web/user/current/details")
        if d.get("status") == 200:
            data = d["data"]
            return data.get("displayName", "?"), data.get("pointAccount", {}).get("payableBalance", 0)
        log(f"获取信息失败: {d.get('message')}", "ERROR")
    except Exception as e:
        log(f"信息异常: {e}", "ERROR")
    return None, None


def get_point_info(token):
    """查询积分详情"""
    try:
        d = api_call(token, "GET", "/web/point/consumer/info")
        if d.get("status") == 200:
            return d.get("data", {})
    except Exception as e:
        log(f"积分查询异常: {e}", "ERROR")
    return None


def get_task_list(token):
    """查询积分任务列表"""
    try:
        d = api_call(token, "GET", "/web/task/list/equity-point")
        if d.get("status") == 200:
            return d.get("data", [])
    except Exception as e:
        log(f"任务列表异常: {e}", "ERROR")
    return []


def get_event_instances(token):
    """查询事件实例（获取可用的事件码）"""
    try:
        d = api_call(token, "GET", "/web/event/event-instances")
        if d.get("status") == 200:
            return d.get("data", [])
        log(f"事件实例查询: status={d.get('status')}, msg={d.get('message')}", "DEBUG")
    except Exception as e:
        log(f"事件实例异常: {e}", "ERROR")
    return []


def do_sign(token):
    """每日签到"""
    try:
        d = api_call(token, "POST", "/web/event/trigger", {"eventCode": "SJ10002"})
        if d.get("status") == 200:
            return True, d.get("message", "签到成功")
        if "已" in str(d.get("message", "")):
            return True, d.get("message", "今日已签到")
        return False, d.get("message", "签到失败")
    except Exception as e:
        return False, str(e)


def get_articles(token):
    """获取推荐文章"""
    try:
        url = f"{BASE_URL}/web/community/recommend/contents?encryptParam={enc_params_str(f'pageNo=1&pageSize=10&access_token={token}&terminal=3')}"
        r = safe_request("GET", url, headers=APP_HEADERS)
        d = r.json()
        if d.get("status") == 200:
            return d.get("data", {}).get("data", [])
    except Exception as e:
        log(f"获取文章异常: {e}", "ERROR")
    return []


def do_share(token):
    """
    分享策略（基于 APK 分析）：
    APP 分享流程：
    1. 获取文章列表
    2. 调用原生微信 SDK 分享
    3. 微信回调后调用 web/op/user-action 记录行为
    4. 后端发放积分

    策略：
    1. web/op/user-action 记录分享行为
    2. web/event/trigger 触发分享事件
    3. web/community/contents/{id}/incr-pv 增加浏览量（可能触发积分）
    """
    articles = get_articles(token)
    if not articles:
        return False, "无可用文章"

    article = random.choice(articles)
    content_id = str(article["content"]["id"])
    title = article["content"].get("title", "未知")[:30]
    log(f"📄 选中文章: [{content_id}] {title}")

    strategies = []

    # --- 策略1: web/op/user-action 记录分享行为 ---
    strategies.append(("user-action(share)", lambda t: api_call(
        t, "POST", "/web/op/user-action",
        {"action": "share", "bizId": content_id, "bizType": "content", "channel": "wechat"}
    )))
    strategies.append(("user-action(shareContent)", lambda t: api_call(
        t, "POST", "/web/op/user-action",
        {"action": "shareContent", "contentId": content_id, "platform": "wechat", "shareType": "1"}
    )))
    strategies.append(("user-action(share_article)", lambda t: api_call(
        t, "POST", "/web/op/user-action",
        {"action": "share_article", "bizId": content_id, "bizType": "community_content"}
    )))

    # --- 策略2: web/event/trigger 触发分享事件 ---
    for code in ["SJ10003", "SJ10004", "SJ10005", "SJ10006", "SJ10007", "SJ10008"]:
        strategies.append((f"event/trigger({code})", lambda t, c=code: api_call(
            t, "POST", "/web/event/trigger",
            {"eventCode": c, "bizId": content_id, "bizType": "content"}
        )))

    # --- 策略3: 增加文章浏览量（incr-pv） ---
    strategies.append(("incr-pv", lambda t: api_call(
        t, "POST", f"/web/community/contents/incr-pv/{content_id}", {}
    )))

    # --- 策略4: 社区内容收藏/互动 ---
    strategies.append(("content-collections(collect)", lambda t: api_call(
        t, "POST", "/web/community/content-collections",
        {"contentId": content_id, "type": "share"}
    )))

    # --- 策略5: PGC 统计 ---
    strategies.append(("pgc/stats/collect", lambda t: api_call(
        t, "POST", f"/web/pgc/stats/collect/{content_id}", {}
    )))

    # ==================== 依次尝试 ====================
    for name, strategy in strategies:
        try:
            d = strategy(token)
            status = d.get("status")
            msg = d.get("message", "")

            is_success = status == 200
            is_already = "已" in str(msg)

            if is_success or is_already:
                log(f"  ✅ [{name}] status={status}, msg={msg}")
                return True, msg
            else:
                log(f"  ❌ [{name}] status={status}, msg={msg}", "DEBUG")
        except Exception as e:
            log(f"  ❌ [{name}] 异常: {e}", "DEBUG")

        time.sleep(REQUEST_DELAY)

    return False, "所有策略均未获得积分"


# ==================== 主流程 ====================
def process_account(acc, idx):
    name = acc.get("remark") or acc.get("phone") or f"账号{idx}"
    log(f"{'=' * 45}")
    log(f"📱 账号 {idx}: {name}")
    log(f"{'=' * 45}")

    token = acc.get("token", "")
    if not token and acc.get("phone"):
        log("正在登录...")
        token = login(acc["phone"], acc["password"])
        if not token:
            log("❌ 登录失败，跳过", "ERROR")
            return False

    nickname, points = get_info(token)
    if nickname is None:
        log("❌ token 可能已失效", "ERROR")
        return False
    log(f"👤 昵称: {nickname}")
    log(f"💰 当前积分: {points}")

    # 查询任务列表（调试用）
    log("--- 积分任务列表 ---")
    tasks = get_task_list(token)
    if tasks:
        for task in tasks[:5]:
            task_name = task.get("name", task.get("taskName", "未知"))
            task_status = task.get("status", task.get("completed", "?"))
            log(f"  📋 {task_name}: {task_status}")
    else:
        log("  (无法获取任务列表)")

    # 查询事件实例（调试用，获取可用事件码）
    log("--- 事件实例 ---")
    events = get_event_instances(token)
    if events:
        for ev in events[:10]:
            ev_code = ev.get("eventCode", ev.get("code", "?"))
            ev_name = ev.get("name", ev.get("eventName", "?"))
            log(f"  🎯 {ev_code}: {ev_name}")
    else:
        log("  (无法获取事件实例)")

    points_before = points

    # 签到
    time.sleep(REQUEST_DELAY)
    ok, msg = do_sign(token)
    log(f"{'✅' if ok else '❌'} 签到: {msg}")

    if ok:
        time.sleep(REQUEST_DELAY)
        _, points_mid = get_info(token)
        if points_mid and points_mid > points_before:
            log(f"  签到积分: {points_before} → {points_mid} (+{points_mid - points_before})")
            points_before = points_mid

    # 分享
    time.sleep(REQUEST_DELAY)
    log("--- 分享任务 ---")
    sok, smsg = do_share(token)
    log(f"{'✅' if sok else '⚠️'} 分享: {smsg}")

    if sok:
        time.sleep(REQUEST_DELAY)
        _, points_after = get_info(token)
        if points_after and points_after > points_before:
            log(f"🎉 积分变化: {points_before} → {points_after} (+{points_after - points_before})")
        else:
            log(f"⚠️ 积分未变化: {points_after}（可能今日已分享过）", "WARN")

    return True


def main():
    log("=" * 45)
    log("🚗 奇瑞汽车签到脚本 v3（APK分析修正版）")
    log("=" * 45)

    accounts = parse_accounts()
    if not accounts:
        log("❌ 未配置环境变量 CHERY_ACCOUNT", "ERROR")
        log("格式: export CHERY_ACCOUNT='token1#备注1' 或 '手机号&密码'")
        sys.exit(1)

    log(f"共 {len(accounts)} 个账号")

    success = 0
    for i, acc in enumerate(accounts, 1):
        try:
            if process_account(acc, i):
                success += 1
        except Exception as e:
            log(f"❌ 账号{i}异常: {e}", "ERROR")
        if i < len(accounts):
            time.sleep(REQUEST_DELAY * 2)

    log("=" * 45)
    log(f"✅ 完成 ({success}/{len(accounts)})")
    log("=" * 45)


if __name__ == "__main__":
    main()
