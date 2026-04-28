#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os
try:
    import requests, json, base64, secrets
    from datetime import datetime
    from urllib.parse import quote
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    print("✅ 模块导入成功")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

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

def main():
    print("=" * 50)
    print("🔍 调试模式")
    print("=" * 50)

    # 解析环境变量
    val = os.getenv("CHERY_ACCOUNT") or os.getenv("chery", "")
    print(f"环境变量原始长度: {len(val)}")
    print(f"包含&符号: {'&' in val}")
    print(f"包含#符号: {'#' in val}")

    parts = val.split("&")
    print(f"按&拆分后段数: {len(parts)}")
    for idx, p in enumerate(parts):
        print(f"  段{idx}: 长度={len(p)}, 全数字={p.isdigit()}")

    if len(parts) >= 2:
        phone = parts[0].strip()
        password = parts[1].strip()
        print(f"\n手机号: {phone} (长度={len(phone)})")
        print(f"密码长度: {len(password)}")

        # 尝试登录
        print(f"\n正在调用登录接口...")
        try:
            r = requests.post(LOGIN_URL, json={"phone": phone, "password": password}, timeout=30)
            print(f"HTTP状态码: {r.status_code}")
            d = r.json()
            print(f"返回: {json.dumps(d, ensure_ascii=False)}")

            if d.get("status"):
                full = d.get("data", "")
                token = full.split("#")[0] if "#" in full else full
                print(f"\n✅ 登录成功, token前20位: {token[:20]}...")

                # 测试eventCode
                candidates = [
                    "SJ10001", "SJ10003", "SJ10004", "SJ10005", "SJ10006",
                    "SJ10007", "SJ10008", "SJ10009", "SJ10010",
                    "SJ20001", "SJ20002", "SJ20003", "SJ20004", "SJ20005",
                    "SJ30001", "SJ30002", "SJ30003",
                    "FX10001", "FX10002",
                    "SJ10002",
                ]
                print(f"\n{'='*50}")
                print("🔍 eventCode 测试")
                print(f"{'='*50}")
                for code in candidates:
                    url = f"{BASE_URL}/web/event/trigger?encryptParam={enc_token(token)}"
                    body = aes_encrypt(json.dumps({"eventCode": code}, separators=(",", ":")))
                    try:
                        r2 = requests.post(url, headers=APP_HEADERS, data=body.encode("utf-8"), timeout=15)
                        resp = r2.json()
                        status = resp.get("status", "?")
                        msg = resp.get("message", resp.get("msg", str(resp)[:60]))
                        marker = "✅" if status == 200 else "❌"
                        print(f"{marker} {code:12s} | {status} | {msg}")
                    except Exception as e:
                        print(f"❌ {code:12s} | 异常: {e}")
            else:
                print(f"\n❌ 登录失败")
        except Exception as e:
            print(f"❌ 请求异常: {e}")
    else:
        print("❌ 环境变量格式错误，需要手机号&密码")

if __name__ == "__main__":
    main()
