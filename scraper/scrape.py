#!/usr/bin/env python3
"""
上海房地产数据采集脚本
策略：Playwright 截图 → Gemini Vision OCR 解析数字
数据源：网上房地产 fangdi.com.cn（上海市房地产交易中心）
robots.txt：不存在（404），无限制规则
采集频率：每次请求间隔 5 秒，合规操作
"""

import asyncio
import base64
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

# ─── 配置 ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data" / "history"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "data.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

URLS = {
    "second_hand": "https://www.fangdi.com.cn/old_house/old_house.html",
    "new_house":   "https://www.fangdi.com.cn/trade/trade.html",
    "listing":     "https://www.fangdi.com.cn/trade/trade.html",
}

# ─── 截图函数 ─────────────────────────────────────────────────────────────────
async def screenshot_page(url: str, selector: str = None, wait_ms: int = 3000) -> bytes:
    """用 Playwright 截图，返回 PNG bytes"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(
            extra_http_headers=HEADERS,
            viewport={"width": 1280, "height": 900}
        )
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(wait_ms)

        if selector:
            element = await page.query_selector(selector)
            if element:
                img_bytes = await element.screenshot()
            else:
                img_bytes = await page.screenshot(full_page=True)
        else:
            img_bytes = await page.screenshot(full_page=True)

        await browser.close()
        return img_bytes


# ─── Gemini Vision OCR ────────────────────────────────────────────────────────
async def ocr_with_gemini(img_bytes: bytes, prompt: str) -> dict:
    """将截图发给 Gemini Vision，返回解析后的 JSON"""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 环境变量未设置")

    b64 = base64.b64encode(img_bytes).decode()
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": b64}}
            ]
        }],
        "generationConfig": {
            "temperature": 0,
            "response_mime_type": "application/json"
        }
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()
        result = resp.json()

    text = result["candidates"][0]["content"]["parts"][0]["text"]
    # 清理可能的 markdown code fence
    text = re.sub(r"```json\s*|\s*```", "", text).strip()
    return json.loads(text)


# ─── 各数据采集任务 ───────────────────────────────────────────────────────────
async def fetch_second_hand() -> dict:
    """采集二手房昨日成交数据"""
    print("📸 截图：二手房成交页面...")
    img = await screenshot_page(
        URLS["second_hand"],
        wait_ms=3000
    )

    # 保存截图供调试
    debug_path = DATA_DIR / f"debug_second_hand_{date.today()}.png"
    debug_path.write_bytes(img)

    prompt = """
请仔细阅读这张上海网上房地产（fangdi.com.cn）二手房页面截图。
找到页面中"昨日成交量"区域的数字，提取以下信息并以JSON格式返回：

{
  "units": <昨日二手房成交套数，整数>,
  "area": <昨日二手房成交面积，浮点数，单位平方米>
}

注意：
- 套数是整数（例如527）
- 面积单位是平方米（㎡），是一个带小数的数字（例如42244.63）
- 如果数据无法读取，对应字段填 null
"""
    result = await ocr_with_gemini(img, prompt)
    print(f"  ✅ 二手房成交：{result}")
    return result


async def fetch_new_house() -> dict:
    """采集一手房今日成交数据（住宅汇总）"""
    print("📸 截图：一手房/交易统计页面...")
    img = await screenshot_page(
        URLS["new_house"],
        wait_ms=3000
    )

    debug_path = DATA_DIR / f"debug_new_house_{date.today()}.png"
    debug_path.write_bytes(img)

    prompt = """
请仔细阅读这张上海网上房地产（fangdi.com.cn）交易统计页面截图。
找到"一手房各区成交统计"或"今日成交"区域，提取住宅类（普通住宅）的全市合计今日成交数据：

{
  "units": <今日一手房住宅成交总套数，整数，全市所有区域汇总>,
  "area": <今日一手房住宅成交总面积，浮点数，单位平方米>
}

注意：
- 需要汇总所有区域（内环、中环、外环、郊环）的今日成交数字
- 面积可能显示为万平方米，请换算为平方米（× 10000）
- 如果数据无法读取或页面显示为0，照实返回
- 如果无法确定，填 null
"""
    result = await ocr_with_gemini(img, prompt)
    print(f"  ✅ 一手房成交：{result}")
    return result


async def fetch_listing() -> dict:
    """采集二手房挂牌数量"""
    print("📸 截图：二手房挂牌页面...")
    img = await screenshot_page(
        URLS["listing"],
        wait_ms=3000
    )
    # 复用 new_house 截图（同一个页面）
    debug_path = DATA_DIR / f"debug_listing_{date.today()}.png"
    debug_path.write_bytes(img)

    prompt = """
请仔细阅读这张上海网上房地产（fangdi.com.cn）交易统计页面截图。
找到"各区二手房出售挂牌排行"区域，提取全市出售挂牌总套数：

{
  "total_listing": <全市二手房出售挂牌总套数，整数，各区套数之和>
}

注意：
- 需要将所有区域（黄浦、徐汇、长宁、静安、普陀、虹口、杨浦、浦东、宝山、闵行、嘉定、松江、青浦、奉贤、崇明等）的挂牌套数加总
- 如果有"合计"行，直接取合计数字
- 如果数据无法读取，填 null
"""
    result = await ocr_with_gemini(img, prompt)
    print(f"  ✅ 二手房挂牌：{result}")
    return result


# ─── 数据持久化 ───────────────────────────────────────────────────────────────
def load_history() -> list:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(records: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def compute_avg_area(units, area):
    """计算套均面积"""
    if units and area and units > 0:
        return round(area / units, 2)
    return None


# ─── 主流程 ───────────────────────────────────────────────────────────────────
async def main():
    today = date.today().isoformat()
    print(f"\n🏠 上海房地产数据采集 — {today}\n{'─'*40}")

    history = load_history()

    # 检查今日数据是否已采集
    existing = next((r for r in history if r["date"] == today), None)
    if existing and "--force" not in sys.argv:
        print(f"⚠️  今日({today})数据已存在，跳过。使用 --force 强制重采集。")
        return

    # 注意：fangdi.com.cn 二手房数据显示的是"昨日"成交
    # 所以我们记录 date = today，但标注数据对应的是 yesterday
    data_date = today  # 记录采集日期

    # 采集各数据（间隔5秒，合规）
    second_hand = {}
    new_house = {}
    listing = {}

    try:
        second_hand = await fetch_second_hand()
    except Exception as e:
        print(f"  ❌ 二手房采集失败: {e}")

    await asyncio.sleep(5)  # 合规间隔

    try:
        new_house = await fetch_new_house()
    except Exception as e:
        print(f"  ❌ 一手房采集失败: {e}")

    await asyncio.sleep(5)  # 复用同一截图，跳过再次请求

    try:
        listing = await fetch_listing()
    except Exception as e:
        print(f"  ❌ 挂牌数据采集失败: {e}")

    # 组装记录
    sh_units = second_hand.get("units")
    sh_area = second_hand.get("area")
    nh_units = new_house.get("units")
    nh_area = new_house.get("area")

    record = {
        "date": data_date,
        "scraped_at": datetime.now().isoformat(),
        "second_hand": {
            "units": sh_units,
            "area": sh_area,
            "avg_area": compute_avg_area(sh_units, sh_area),
            "note": "昨日网签成交（T+1）"
        },
        "new_house": {
            "units": nh_units,
            "area": nh_area,
            "avg_area": compute_avg_area(nh_units, nh_area),
            "note": "今日成交（当日累计）"
        },
        "listing": {
            "total": listing.get("total_listing"),
            "note": "二手房出售挂牌套数"
        }
    }

    # 更新历史（如已存在则替换）
    history = [r for r in history if r["date"] != data_date]
    history.append(record)
    history.sort(key=lambda x: x["date"])

    save_history(history)
    print(f"\n✅ 数据已保存至 {HISTORY_FILE}")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
