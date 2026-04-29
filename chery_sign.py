#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import json
import os
import base64
import secrets
import time
import random
from datetime import datetime
from urllib.parse import quote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ==================== 配置 ====================
LOGIN_URL = "https://logintools.smallfawn.top/chery/loginByPassword"
BASE_URL = "https://mobile-consumer-sapp.chery.cn"
AES_KEY = base64.b64decode("vVfnp9ozfDQyonMKuqgZUWjtdV+7PtBqtMCwJqz2HKQ=")

# 指定抽奖活动ID（留空=自动查找所有抽奖活动）
LOTTERY_ACTIVITY_ID = os.getenv("LOTTERY_ACTIVITY_ID", "")

# 配置参数
RETRY_TIMES = int(os.getenv("RETRY_TIMES", "3"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.5"))
SHARE_COUNT = int(os.getenv("SHARE_COUNT", "2"))

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


# ==================== 颜色输出 ====================
class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


# ==================== 基础工具 ====================
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    level_color = {
        "INFO": Color.BLUE,
        "ERROR": Color.RED,
        "SUCCESS": Color.GREEN,
        "WARNING": Color.YELLOW,
        "DEBUG": Color.MAGENTA
    }
    color = level_color.get(level, Color.RESET)
    print(f"{Color.RESET}[{ts}] {color}[{level}] {msg}{Color.RESET}")


def aes_encrypt(plaintext: str) -> str:
    iv = secrets.token_bytes(16)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size, style="pkcs7"))
    b64 = base64.b64encode(iv + encrypted).decode("utf-8")
    return b64.replace("+", "-")


def enc_token(token: str) -> str:
    return quote(aes_encrypt(f"access_token={token}&terminal=3"), safe='')


def enc_params(token, **kwargs):
    params = f"access_token={token}&terminal=3"
    for k, v in kwargs.items():
        params += f"&{k}={v}"
    return quote(aes_encrypt(params), safe='')


def safe_json(resp):
    try:
        return resp.json()
    except Exception as e:
        log(f"JSON解析失败: {e}, 响应内容: {resp.text[:200]}", "ERROR")
        return {"status": 0, "message": f"JSON解析失败: {str(e)}"}


def random_delay(base=1.0, jitter=0.5):
    time.sleep(base + random.uniform(-jitter, jitter))


def test_network():
    log("📡 正在测试网络连接...")
    try:
        r = requests.get("https://www.baidu.com", timeout=10)
        if r.status_code == 200:
            log("✅ 网络连接正常", "SUCCESS")
            return True
        else:
            log(f"❌ 网络连接异常: {r.status_code}", "ERROR")
            return False
    except Exception as e:
        log(f"❌ 网络连接失败: {e}", "ERROR")
        return False


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


# ==================== 登录 & 信息 ====================
def login(phone, password):
    for attempt in range(RETRY_TIMES):
        try:
            log(f"🔐 登录尝试 {attempt + 1}/{RETRY_TIMES}")
            r = requests.post(LOGIN_URL, json={"phone": phone, "password": password}, timeout=30)
            d = r.json()
            if d.get("status"):
                full = d.get("data", "")
                token = full.split("#")[0] if "#" in full else full
                log("✅ 登录成功", "SUCCESS")
                return token
            log(f"登录失败: {d.get('message')}", "ERROR")
        except Exception as e:
            log(f"登录异常: {e}", "ERROR")
        if attempt < RETRY_TIMES - 1:
            time.sleep(2)
    return ""


def get_info(token):
    for attempt in range(RETRY_TIMES):
        try:
            url = f"{BASE_URL}/web/user/current/details?encryptParam={enc_token(token)}"
            r = requests.get(url, headers=APP_HEADERS, timeout=30)
            d = r.json()
            if d.get("status") == 200:
                data = d["data"]
                nickname = data.get("displayName", "?")
                points = data.get("pointAccount", {}).get("payableBalance", 0)
                return nickname, int(points) if points else 0
            log(f"获取信息失败: {d.get('message')}", "ERROR")
        except Exception as e:
            log(f"信息获取异常: {e}", "ERROR")
        if attempt < RETRY_TIMES - 1:
            time.sleep(2)
    return None, 0


# ==================== 签到 ====================
def do_sign(token):
    for attempt in range(RETRY_TIMES):
        try:
            url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
            body = aes_encrypt(json.dumps({"eventCode": "SJ10002"}, separators=(",", ":")))
            r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
            d = safe_json(r)
            if d.get("status") == 200:
                return True, d.get("message", "签到成功")
            msg = d.get("message", "签到失败")
            # 已签到的情况也视为成功
            if "已签" in msg or "已完成" in msg:
                return True, msg
            log(f"签到失败: {msg}", "WARNING")
            return False, msg
        except Exception as e:
            log(f"签到异常: {e}", "ERROR")
        if attempt < RETRY_TIMES - 1:
            time.sleep(2)
    return False, f"签到失败（重试{RETRY_TIMES}次）"


# ==================== 分享 ====================
def get_articles(token):
    for attempt in range(RETRY_TIMES):
        try:
            list_url = f"{BASE_URL}/web/community/recommend/contents?encryptParam={quote(aes_encrypt(f'pageNo=1&pageSize=10&access_token={token}&terminal=3'), safe='')}"
            r = requests.get(list_url, headers=APP_HEADERS, timeout=30)
            d = safe_json(r)
            if d.get("status") != 200:
                log(f"获取文章列表失败: {d.get('message')}", "ERROR")
                continue
            
            articles_data = d.get("data", {})
            if not articles_data:
                log("文章列表数据为空", "WARNING")
                return []
            
            articles = articles_data.get("data", [])
            article_ids = []
            for article in articles:
                content = article.get("content")
                if content and content.get("id"):
                    article_ids.append(str(content["id"]))
            
            log(f"📚 获取到 {len(article_ids)} 篇文章")
            return article_ids
        except Exception as e:
            log(f"获取文章列表异常: {e}", "ERROR")
        if attempt < RETRY_TIMES - 1:
            time.sleep(2)
    return []


def do_single_share(token, article_id, share_index=1):
    try:
        share_url = f"{BASE_URL}/web/community/contents/{article_id}/share?encryptParam={enc_token(token)}"
        share_body = aes_encrypt(json.dumps({"contentId": article_id}, separators=(",", ":")))
        sr = requests.post(share_url, headers=APP_HEADERS, data=share_body.encode("utf-8"), timeout=30)
        sd = safe_json(sr)
        
        if sd.get("status") != 200:
            msg = sd.get("message", "分享失败")
            # 已分享的情况也视为成功
            if "已分享" in msg or "已完成" in msg:
                return True, f"第{share_index}次分享: {msg}"
            return False, f"第{share_index}次分享失败: {msg}"
        
        # 领取分享奖励
        reward_url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
        reward_body = aes_encrypt(json.dumps({"eventCode": "SJ10003"}, separators=(",", ":")))
        rr = requests.post(reward_url, headers=APP_HEADERS, data=reward_body.encode("utf-8"), timeout=30)
        rd = safe_json(rr)
        
        if rd.get("status") == 200:
            return True, f"第{share_index}次分享成功并领取积分"
        
        msg = rd.get("message", "未知")
        # 已领取的情况也视为成功
        if "已领取" in msg or "已完成" in msg:
            return True, f"第{share_index}次分享成功: {msg}"
        return True, f"第{share_index}次分享成功, 领取积分: {msg}"
        
    except Exception as e:
        log(f"第{share_index}次分享异常: {e}", "ERROR")
        return False, f"第{share_index}次分享异常: {str(e)}"


def do_share(token, share_count=SHARE_COUNT):
    articles = get_articles(token)
    if not articles:
        return False, "获取文章列表失败"
    
    results = []
    success_count = 0
    
    for i in range(min(share_count, len(articles))):
        ok, msg = do_single_share(token, articles[i], i + 1)
        results.append((ok, msg))
        if ok:
            success_count += 1
        random_delay(REQUEST_DELAY)
    
    if success_count == share_count:
        return True, f"✅ 全部{share_count}次分享完成"
    elif success_count > 0:
        return True, f"⚠️ 部分分享完成 ({success_count}/{share_count})"
    else:
        return False, "❌ 全部分享失败"


# ==================== 🎰 抽奖功能 ====================
def is_wednesday():
    """判断是否是周三"""
    today = datetime.now()
    return today.weekday() == 2  # Monday=0, Sunday=6


def get_activity_list(token):
    for attempt in range(RETRY_TIMES):
        try:
            url = f"{BASE_URL}/web/activity/app/common/getActivityListToC?encryptParam={enc_token(token)}"
            body = aes_encrypt(json.dumps({
                "pageNo": 1,
                "pageSize": 50,
                "terminal": 4
            }, separators=(",", ":")))
            log("正在获取活动列表...")
            r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
            d = safe_json(r)
            log(f"活动列表响应状态: {d.get('status')}")
            return d
        except Exception as e:
            log(f"获取活动列表异常: {e}", "ERROR")
        if attempt < RETRY_TIMES - 1:
            time.sleep(2)
    return {}


def get_lottery_page_info(token, activity_id):
    try:
        url = f"{BASE_URL}/web/activity/app/lottery/pageInfo?encryptParam={enc_params(token, activityId=activity_id)}"
        r = requests.get(url, headers=APP_HEADERS, timeout=30)
        d = safe_json(r)
        return d
    except Exception as e:
        log(f"获取页面信息异常: {e}", "ERROR")
        return {}


def query_draw_times(token, activity_id):
    for attempt in range(RETRY_TIMES):
        try:
            url = f"{BASE_URL}/web/activity/app/lottery/queryDrawTimes?encryptParam={enc_params(token, activityId=activity_id)}"
            r = requests.get(url, headers=APP_HEADERS, timeout=30)
            d = safe_json(r)
            
            if d.get("status") == 200:
                data = d.get("data", {})
                if isinstance(data, dict):
                    return int(data.get("drawTimes", data.get("remainTimes", data.get("times", 0))))
                return int(data) if data else 0
            return 0
        except Exception as e:
            log(f"查询抽奖次数异常: {e}", "ERROR")
        if attempt < RETRY_TIMES - 1:
            time.sleep(2)
    return 0


def do_lottery_draw(token, activity_id):
    try:
        url = f"{BASE_URL}/web/activity/app/lottery/lotteryDraw?encryptParam={enc_token(token)}"
        body = aes_encrypt(json.dumps({
            "activityId": str(activity_id),
            "terminal": 4
        }, separators=(",", ":")))
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
        d = safe_json(r)
        return d
    except Exception as e:
        log(f"抽奖异常: {e}", "ERROR")
        return {"status": 0, "message": str(e)}


def get_my_prizes(token):
    try:
        url = f"{BASE_URL}/web/activity/app/prize/listMyPrizeV2?encryptParam={enc_token(token)}"
        body = aes_encrypt(json.dumps({
            "pageNo": 1,
            "pageSize": 20
        }, separators=(",", ":")))
        r = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=30)
        d = safe_json(r)

        if d.get("status") == 200:
            data = d.get("data", {})
            prizes = []
            if isinstance(data, dict):
                prizes = data.get("records", data.get("list", data.get("data", [])))
            elif isinstance(data, list):
                prizes = data

            if prizes:
                log(f"🎁 共有 {len(prizes)} 个奖品:", "SUCCESS")
                for i, p in enumerate(prizes, 1):
                    if isinstance(p, dict):
                        name = p.get("prizeName", p.get("name", "未知"))
                        status = p.get("status", p.get("prizeStatus", ""))
                        log(f"  {i}. {name} (状态: {status})")
            else:
                log("  暂无奖品记录")
        return d
    except Exception as e:
        log(f"获取奖品异常: {e}", "ERROR")
        return {}


def do_lottery(token, force=False):
    """自动抽奖主流程"""
    
    if not force and not is_wednesday():
        today = datetime.now().strftime("%Y-%m-%d")
        day_of_week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        log(f"📅 {today} ({day_of_week[datetime.now().weekday()]})")
        log("⏭️ 抽奖活动仅在周三进行，跳过抽奖", "INFO")
        return
    
    log("-" * 40)
    log("🎰 开始自动抽奖流程")
    log("-" * 40)

    lottery_ids = []

    if LOTTERY_ACTIVITY_ID:
        lottery_ids = [LOTTERY_ACTIVITY_ID.strip()]
        log(f"使用指定活动ID: {LOTTERY_ACTIVITY_ID}")
    else:
        result = get_activity_list(token)
        data = result.get("data", {})

        if isinstance(data, dict):
            records = data.get("records", data.get("list", data.get("data", [])))
        elif isinstance(data, list):
            records = data
        else:
            records = []

        if not isinstance(records, list):
            log(f"活动列表格式异常: {type(records)}", "ERROR")
            records = []

        log(f"共获取到 {len(records)} 个活动")

        for act in records:
            if not isinstance(act, dict):
                continue
            act_name = act.get("activityName", "")
            act_id = act.get("id", "")
            act_type = str(act.get("activityType", ""))
            act_status = act.get("status", "")

            log(f"  📌 活动: {act_name} | ID: {act_id} | 类型: {act_type} | 状态: {act_status}")

            act_str = json.dumps(act, ensure_ascii=False).lower()
            is_lottery = any(k in act_str for k in [
                "lottery", "抽奖", "转盘", "大转盘", "luckydraw", "luckdraw"
            ])
            is_lottery = is_lottery or act_type in ["lottery", "4", "5", "6", "7"]

            if is_lottery and act_id:
                lottery_ids.append(act_id)
                log(f"    ✅ 识别为抽奖活动")

    if not lottery_ids:
        log("⚠️ 未找到抽奖活动，跳过抽奖", "WARNING")
        return

    log(f"共找到 {len(lottery_ids)} 个抽奖活动: {lottery_ids}")

    total_drawn = 0
    total_prizes = 0

    for act_id in lottery_ids:
        log(f"\n{'='*30}")
        log(f"🎯 处理抽奖活动: {act_id}")
        log(f"{'='*30}")

        page_info = get_lottery_page_info(token, act_id)
        random_delay(REQUEST_DELAY)

        draw_times = query_draw_times(token, act_id)
        draw_times = int(draw_times) if draw_times else 0

        if draw_times <= 0:
            log(f"  ❌ 剩余抽奖次数: 0, 跳过此活动")
            continue

        log(f"  � 剩余抽奖次数: {draw_times}")

        for i in range(draw_times):
            log(f"\n  --- 第 {i+1}/{draw_times} 次抽奖 ---")
            result = do_lottery_draw(token, act_id)

            if isinstance(result, dict):
                status = result.get("status")
                msg = result.get("message", "")
                data = result.get("data", {})

                if status == 200:
                    total_drawn += 1
                    if isinstance(data, dict):
                        prize_name = data.get("prizeName", data.get("name", ""))
                        prize_type = data.get("prizeType", "")
                        if prize_name:
                            total_prizes += 1
                            log(f"  🎁🎉 恭喜获得: {prize_name} (类型: {prize_type})", "SUCCESS")
                        else:
                            log(f"  ✅ 抽奖成功: {msg or '完成'}", "SUCCESS")
                    elif isinstance(data, str) and data:
                        log(f"  ✅ 抽奖结果: {data}", "SUCCESS")
                    else:
                        log(f"  ✅ 抽奖成功: {msg or '完成'}", "SUCCESS")
                elif "次数" in str(msg) or "不足" in str(msg) or "用完" in str(msg):
                    log(f"  ⛔ 抽奖次数已用完: {msg}", "WARNING")
                    break
                elif "未开始" in str(msg) or "已结束" in str(msg):
                    log(f"  ⛔ 活动状态异常: {msg}", "ERROR")
                    break
                else:
                    log(f"  ❌ 抽奖失败: {msg}", "ERROR")
                    total_drawn += 1
            else:
                log(f"  ❌ 响应异常: {result}", "ERROR")

            random_delay(REQUEST_DELAY)

    if total_drawn > 0:
        log(f"\n📋 查看我的全部奖品...")
        get_my_prizes(token)

    log(f"\n🎰 抽奖汇总: 共抽奖 {total_drawn} 次, 获奖 {total_prizes} 次")


# ==================== 主流程 ====================
def process_account(acc, idx):
    name = acc.get("remark") or acc.get("phone") or "账号"
    log(f"\n{'='*45}")
    log(f"🚗 账号{idx}: {name}")
    log(f"{'='*45}")

    token = acc.get("token", "")
    if not token and acc.get("phone"):
        log("🔐 正在登录...")
        token = login(acc["phone"], acc["password"])
    
    if not token:
        log("❌ 无有效token, 跳过此账号", "ERROR")
        return

    nickname, points_before = get_info(token)
    if nickname is None:
        log("❌ 获取用户信息失败, 跳过此账号", "ERROR")
        return
    
    log(f"👤 昵称: {nickname}")
    log(f"💰 当前积分: {points_before}")

    # 签到
    ok, msg = do_sign(token)
    log(f"{'✅' if ok else '❌'} 签到: {msg}")
    random_delay(REQUEST_DELAY)

    # 分享
    sok, smsg = do_share(token)
    log(f"{'✅' if sok else '⚠️'} 分享: {smsg}")
    random_delay(REQUEST_DELAY)

    # 抽奖 🎰
    do_lottery(token)

    # 积分变化
    _, points_after = get_info(token)
    increase = points_after - points_before
    log(f"\n📈 本次积分变化: {Color.GREEN if increase > 0 else Color.RED}{'+' if increase >= 0 else ''}{increase}{Color.RESET}")
    log(f"💰 最终积分: {points_after}")


def main():
    log("=" * 45)
    log("🚗 奇瑞汽车 自动签到+分享+抽奖 脚本")
    log("=" * 45)
    log(f"📅 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 网络测试
    if not test_network():
        log("❌ 网络连接失败, 退出脚本", "ERROR")
        return

    accounts = parse_accounts()
    if not accounts:
        log("❌ 未配置环境变量 CHERY_ACCOUNT", "ERROR")
        log("配置格式示例:")
        log("  export CHERY_ACCOUNT='token#备注'")
        log("  export CHERY_ACCOUNT='手机号&密码'")
        return
    
    log(f"� 共 {len(accounts)} 个账号待处理")

    for i, acc in enumerate(accounts, 1):
        process_account(acc, i)
        if i < len(accounts):
            log(f"\n⏳ 等待 {REQUEST_DELAY} 秒后处理下一个账号...")
            time.sleep(REQUEST_DELAY)

    log("\n" + "=" * 45)
    log("✅ 全部任务完成", "SUCCESS")
    log("=" * 45)


if __name__ == "__main__":
    main()
