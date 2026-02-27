#!/usr/bin/env python3
"""
上海房地产数据采集脚本
策略：Playwright 无头浏览器截图 → MiniMax Vision API 解析数字
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
from datetime import date, datetime
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

# ─── 配置 ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data" / "history"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "data.json"

MINIMAX_API_KEY    = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID   = os.environ.get("MINIMAX_GROUP_ID", "")
MINIMAX_URL        = f"https://api.minimax.chat/v1/text/chatcompletion_v2"

HEADERS = {
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

# ─── 截图 ────────────────────────────────────────────────────────────────────
async def screenshot_page(url: str, wait_ms: int = 4000) -> bytes:
    """Playwright 渲染页面并截图，返回 PNG bytes"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        ctx = await browser.new_context(
            extra_http_headers=HEADERS,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(wait_ms)
        img_bytes = await page.screenshot(full_page=True)
        await browser.close()
    return img_bytes


# ─── MiniMax Vision OCR ───────────────────────────────────────────────────────
async def ask_minimax_vision(img_bytes: bytes, prompt: str) -> str:
    """把截图发给 MiniMax VL 模型，返回原始文本"""
    if not MINIMAX_API_KEY:
        raise ValueError("MINIMAX_API_KEY 未设置")

    b64 = base64.b64encode(img_bytes).decode()
    payload = {
        "model": "MiniMax-VL-01",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "temperature": 0.01,
        "max_tokens": 512,
    }

    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    if MINIMAX_GROUP_ID:
        params = {"GroupId": MINIMAX_GROUP_ID}
    else:
        params = {}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            MINIMAX_URL,
            json=payload,
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        result = resp.json()

    return result["choices"][0]["message"]["content"]


async def parse_json_from_vision(img_bytes: bytes, prompt: str) -> dict:
    """Vision 结果解析为 JSON dict"""
    raw = await ask_minimax_vision(img_bytes, prompt)
    # 清理 markdown 代码块
    text = re.sub(r"```json\s*|\s*```", "", raw).strip()
    # 提取第一个 {...}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group())
    return json.loads(text)


# ─── 采集任务 ─────────────────────────────────────────────────────────────────
async def fetch_second_hand(debug_dir: Path) -> dict:
    """二手房：昨日成交套数、面积"""
    print("  📸 截图二手房页面...")
    img = await screenshot_page(URLS["second_hand"])
    (debug_dir / f"second_hand_{date.today()}.png").write_bytes(img)

    prompt = (
        "这是上海网上房地产（fangdi.com.cn）二手房页面的截图。"
        "请找到页面中'昨日成交量'区域，提取以下数字，以JSON返回：\n"
        '{"units": <昨日二手房成交套数，整数>, '
        '"area": <昨日二手房成交面积，浮点数，单位㎡>}\n'
        "注意：套数是纯整数（如527），面积是带小数的㎡数值（如42244.63）。"
        "若无法读取填null。只返回JSON，不要其他内容。"
    )
    result = await parse_json_from_vision(img, prompt)
    print(f"    ✅ 二手房成交: {result}")
    return result


async def fetch_trade(debug_dir: Path) -> dict:
    """交易统计页：一手房今日成交 + 二手房挂牌数量"""
    print("  📸 截图交易统计页面...")
    img = await screenshot_page(URLS["trade"])
    (debug_dir / f"trade_{date.today()}.png").write_bytes(img)

    prompt = (
        "这是上海网上房地产（fangdi.com.cn）交易统计页面的截图。\n"
        "请提取以下两组数据，以JSON返回：\n"
        "1. 一手房今日成交住宅（普通住宅）：全市合计今日成交套数和面积\n"
        "2. 各区二手房出售挂牌总套数（所有区加总，或直接读合计行）\n"
        "返回格式：\n"
        '{"new_house_units": <今日一手房住宅成交套数，整数>, '
        '"new_house_area": <今日一手房住宅成交面积，平方米，浮点数>, '
        '"listing_total": <二手房出售挂牌总套数，整数>}\n'
        "面积若显示为万㎡请乘以10000转换为㎡。若无法读取填null。只返回JSON。"
    )
    result = await parse_json_from_vision(img, prompt)
    print(f"    ✅ 交易统计: {result}")
    return result


# ─── 数据存储 ─────────────────────────────────────────────────────────────────
def load_history() -> list:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(records: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


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

    history = load_history()

    if any(r["date"] == today for r in history) and "--force" not in sys.argv:
        print(f"⚠️  今日数据已存在，跳过（--force 可强制重采）")
        return

    debug_dir = DATA_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)

    sh, trade = {}, {}

    try:
        sh = await fetch_second_hand(debug_dir)
    except Exception as e:
        print(f"  ❌ 二手房采集失败: {e}")

    print("  ⏳ 等待 6 秒...")
    await asyncio.sleep(6)

    try:
        trade = await fetch_trade(debug_dir)
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
            "note":     "昨日网签成交（T+1）"
        },
        "new_house": {
            "units":    nh_u,
            "area":     nh_a,
            "avg_area": avg_area(nh_u, nh_a),
            "note":     "今日成交（当日累计）"
        },
        "listing": {
            "total": li_t,
            "note":  "二手房出售挂牌套数"
        }
    }

    history = [r for r in history if r["date"] != today]
    history.append(record)
    history.sort(key=lambda x: x["date"])
    save_history(history)

    print(f"\n✅ 已保存 → {HISTORY_FILE}")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
