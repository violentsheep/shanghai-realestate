#!/usr/bin/env python3
"""
上海房地产数据采集脚本
策略：Playwright 无头浏览器截图 → 百度OCR 文字识别 → 正则提取数字
数据源：网上房地产 fangdi.com.cn（上海市房地产交易中心，政府机构）
合规说明：
  - 只访问公开页面，无需登录
  - robots.txt 不存在（404），无限制规则
  - 截图方式，非结构化爬虫，不绕过任何反爬机制
  - 每次请求间隔 ≥5 秒
  - 只采集必要字段
"""

import asyncio
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ─── 配置 ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data" / "history"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "data.json"

BAIDU_API_KEY    = os.environ.get("BAIDU_OCR_API_KEY", "")
BAIDU_SECRET_KEY = os.environ.get("BAIDU_OCR_SECRET_KEY", "")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

URLS = {
    "second_hand": "https://www.fangdi.com.cn/old_house/old_house.html",
    "trade":       "https://www.fangdi.com.cn/trade/trade.html",
}

# ─── 百度 OCR ─────────────────────────────────────────────────────────────────
def get_baidu_token() -> str:
    """用 API Key + Secret Key 换取 access_token（有效期30天）"""
    url = (
        f"https://aip.baidubce.com/oauth/2.0/token"
        f"?grant_type=client_credentials"
        f"&client_id={BAIDU_API_KEY}"
        f"&client_secret={BAIDU_SECRET_KEY}"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    return data["access_token"]


def baidu_ocr(img_bytes: bytes, token: str) -> str:
    """调用百度通用文字识别，返回所有识别行拼接成的纯文本"""
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={token}"
    b64 = base64.b64encode(img_bytes).decode()
    body = urllib.parse.urlencode({"image": b64}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    if "error_code" in result:
        raise RuntimeError(f"百度OCR错误: {result}")

    lines = [item["words"] for item in result.get("words_result", [])]
    return "\n".join(lines)


# ─── Playwright 截图 ──────────────────────────────────────────────────────────
async def screenshot_page(url: str, wait_ms: int = 4000) -> bytes:
    """Playwright 渲染页面并全页截图"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = await browser.new_context(
            extra_http_headers=BROWSER_HEADERS,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(wait_ms)
        img = await page.screenshot(full_page=True)
        await browser.close()
    return img


# ─── 数字解析 ─────────────────────────────────────────────────────────────────
def parse_second_hand(text: str) -> dict:
    """从OCR文本中提取二手房昨日成交套数和面积"""
    units, area = None, None

    # 套数：匹配 "昨日二手房成交套数: 527套" 或 "成交套数527"
    m = re.search(r'昨日二手房成交套数[：:\s]*(\d[\d,]*)\s*套?', text)
    if not m:
        # 宽松匹配：找"套数"后面跟的数字
        m = re.search(r'套数[：:\s]*(\d[\d,]*)', text)
    if m:
        units = int(m.group(1).replace(",", ""))

    # 面积：匹配 "昨日二手房成交面积: 42244.63㎡"
    m = re.search(r'昨日二手房成交面积[：:\s]*([\d,]+\.?\d*)\s*[㎡平方]?', text)
    if not m:
        m = re.search(r'成交面积[：:\s]*([\d,]+\.?\d*)', text)
    if m:
        area = float(m.group(1).replace(",", ""))

    return {"units": units, "area": area}


def parse_trade(text: str) -> dict:
    """从OCR文本中提取一手房今日成交 + 二手房挂牌数量"""
    nh_units, nh_area, listing = None, None, None

    # 一手房今日成交套数
    # 页面文本类似："今日成交 230套 面积12345㎡"
    m = re.search(r'今日[共预出售]*各类商品房\s*(\d[\d,]*)\s*套', text)
    if not m:
        m = re.search(r'今日成交.*?(\d[\d,]+)\s*套', text)
    if m:
        nh_units = int(m.group(1).replace(",", ""))

    # 一手房今日成交面积（㎡）
    m = re.search(r'面积\s*([\d,]+\.?\d*)\s*平方米', text)
    if not m:
        m = re.search(r'今日.*?面积.*?([\d,]+\.?\d*)', text)
    if m:
        val = float(m.group(1).replace(",", ""))
        # 如果是万㎡单位转换
        nh_area = val * 10000 if val < 1000 else val

    # 二手房挂牌总套数：找最大的挂牌数字
    # 页面列各区套数，我们找合计或所有数字加总
    listing_nums = re.findall(r'(\d{4,6})\s*套', text)
    if listing_nums:
        nums = [int(n) for n in listing_nums]
        # 挂牌数一般是最大的那个，或者取最后出现的合计
        listing = max(nums)

    return {"new_house_units": nh_units, "new_house_area": nh_area, "listing_total": listing}


# ─── 采集任务 ─────────────────────────────────────────────────────────────────
async def fetch_second_hand(token: str, debug_dir: Path) -> dict:
    print("  📸 截图：二手房页面...")
    img = await screenshot_page(URLS["second_hand"])
    (debug_dir / f"second_hand_{date.today()}.png").write_bytes(img)

    print("  🔍 OCR 识别...")
    text = baidu_ocr(img, token)
    (debug_dir / f"second_hand_{date.today()}.txt").write_text(text, encoding="utf-8")
    print(f"     OCR文本片段: {text[:200]!r}")

    result = parse_second_hand(text)
    print(f"  ✅ 二手房: {result}")
    return result


async def fetch_trade(token: str, debug_dir: Path) -> dict:
    print("  📸 截图：交易统计页面...")
    img = await screenshot_page(URLS["trade"])
    (debug_dir / f"trade_{date.today()}.png").write_bytes(img)

    print("  🔍 OCR 识别...")
    text = baidu_ocr(img, token)
    (debug_dir / f"trade_{date.today()}.txt").write_text(text, encoding="utf-8")
    print(f"     OCR文本片段: {text[:200]!r}")

    result = parse_trade(text)
    print(f"  ✅ 交易统计: {result}")
    return result


# ─── 数据存储 ─────────────────────────────────────────────────────────────────
def load_history() -> list:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def save_history(records: list):
    HISTORY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def avg_area(units, area):
    try:
        if units and area and float(units) > 0:
            return round(float(area) / float(units), 2)
    except Exception:
        pass
    return None


# ─── 主流程 ───────────────────────────────────────────────────────────────────
async def main():
    today = date.today().isoformat()
    print(f"\n🏠 上海房地产数据采集 [{today}]")
    print("─" * 45)

    if not BAIDU_API_KEY or not BAIDU_SECRET_KEY:
        print("❌ 请设置环境变量 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY")
        sys.exit(1)

    history = load_history()

    if any(r["date"] == today for r in history) and "--force" not in sys.argv:
        print(f"⚠️  今日数据已存在，跳过（加 --force 强制重采）")
        return

    debug_dir = DATA_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)

    # 获取百度 token（缓存到文件，30天有效）
    token_cache = DATA_DIR / ".baidu_token"
    if token_cache.exists():
        token = token_cache.read_text().strip()
        print("  🔑 使用缓存 Token")
    else:
        print("  🔑 获取百度 OCR Token...")
        token = get_baidu_token()
        token_cache.write_text(token)

    sh, trade = {}, {}

    try:
        sh = await fetch_second_hand(token, debug_dir)
    except Exception as e:
        print(f"  ❌ 二手房采集失败: {e}")
        # token 可能过期，重新获取
        if "111" in str(e) or "token" in str(e).lower():
            token = get_baidu_token()
            token_cache.write_text(token)

    print("  ⏳ 等待 6 秒（合规间隔）...")
    await asyncio.sleep(6)

    try:
        trade = await fetch_trade(token, debug_dir)
    except Exception as e:
        print(f"  ❌ 交易统计采集失败: {e}")

    sh_u = sh.get("units")
    sh_a = sh.get("area")
    nh_u = trade.get("new_house_units")
    nh_a = trade.get("new_house_area")
    li_t = trade.get("listing_total")

    record = {
        "date": today,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "second_hand": {
            "units":    sh_u,
            "area":     sh_a,
            "avg_area": avg_area(sh_u, sh_a),
            "note":     "昨日网签成交（T+1）",
        },
        "new_house": {
            "units":    nh_u,
            "area":     nh_a,
            "avg_area": avg_area(nh_u, nh_a),
            "note":     "今日成交（当日累计）",
        },
        "listing": {
            "total": li_t,
            "note":  "二手房出售挂牌套数",
        },
    }

    history = [r for r in history if r["date"] != today]
    history.append(record)
    history.sort(key=lambda x: x["date"])
    save_history(history)

    print(f"\n✅ 已保存 → {HISTORY_FILE}")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
