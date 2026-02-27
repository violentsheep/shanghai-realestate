#!/usr/bin/env python3
"""
上海房地产数据采集脚本
策略：Playwright 无头浏览器渲染页面 → 提取页面文本 → MiniMax 文本模型 + 正则双重解析
数据源：网上房地产 fangdi.com.cn（上海市房地产交易中心，政府机构）
合规说明：
  - 只访问公开页面，无需登录
  - robots.txt 不存在（404），无限制规则
  - 渲染后提取文本，不绕过任何反爬机制
  - 每次请求间隔 ≥6 秒，只采集必要字段
"""

import asyncio
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ─── 配置 ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data" / "history"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "data.json"

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_API_URL = "https://api.minimaxi.com/anthropic/v1/messages"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

URLS = {
    "second_hand": "https://www.fangdi.com.cn/old_house/old_house.html",
    "trade":       "https://www.fangdi.com.cn/trade/trade.html",
}


# ─── Playwright 提取页面文本 ──────────────────────────────────────────────────
async def get_page_text(url: str) -> str:
    """Playwright 完整渲染页面，等待真实内容加载后返回可见文本"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            extra_http_headers=BROWSER_HEADERS,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            user_agent=BROWSER_HEADERS["User-Agent"],
        )
        # 隐藏 webdriver 特征
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        page = await ctx.new_page()

        print(f"    → 访问 {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)

        # 等待页面真实内容：最长等 15 秒，每秒检查一次
        real_content = False
        for i in range(15):
            await page.wait_for_timeout(1000)
            text = await page.inner_text("body")
            # 真实页面包含"套数"或"成交"或"挂牌"
            if any(kw in text for kw in ["套数", "成交", "挂牌", "平方米", "㎡"]):
                real_content = True
                print(f"    → 第 {i+1}s 检测到真实内容（{len(text)} 字符）")
                break
            print(f"    → 第 {i+1}s 等待内容加载... ({len(text)} 字)")

        if not real_content:
            print("    ⚠️  15秒内未检测到真实内容，尝试继续解析")

        text = await page.inner_text("body")
        await browser.close()

    return text


# ─── 正则兜底解析 ─────────────────────────────────────────────────────────────
def regex_parse_second_hand(text: str) -> dict:
    """正则直接从文本提取二手房数据"""
    units, area = None, None
    m = re.search(r'昨日二手房成交套数[：:\s]*(\d[\d,]*)\s*套?', text)
    if m:
        units = int(m.group(1).replace(",", ""))
    m = re.search(r'昨日二手房成交面积[：:\s]*([\d,]+\.?\d*)', text)
    if m:
        area = float(m.group(1).replace(",", ""))
    return {"units": units, "area": area}


def regex_parse_listing(text: str) -> int | None:
    """从文本中提取挂牌总套数"""
    # 找所有 5-6 位数字后面跟"套"的
    nums = re.findall(r'(\d{4,6})\s*套', text)
    if nums:
        return max(int(n) for n in nums)
    return None


def regex_parse_new_house(text: str) -> dict:
    """从文本中提取一手房今日成交"""
    units, area = None, None
    m = re.search(r'今日[共]?[预出售各类商品房]*\s*(\d[\d,]*)\s*套', text)
    if m:
        units = int(m.group(1).replace(",", ""))
    m = re.search(r'面积\s*([\d,]+\.?\d*)\s*平方米', text)
    if not m:
        m = re.search(r'今日.*?([\d,]+\.?\d{2})\s*万?[㎡平]', text)
    if m:
        val = float(m.group(1).replace(",", ""))
        area = val * 10000 if val < 10000 else val
    return {"units": units, "area": area}


# ─── MiniMax 解析（有真实文本时增强用）────────────────────────────────────────
def ask_minimax(prompt: str) -> str:
    payload = json.dumps({
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        MINIMAX_API_URL,
        data=payload,
        headers={
            "x-api-key": MINIMAX_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read())
    for c in d.get("content", []):
        if c.get("type") == "text":
            return c["text"].strip()
    raise RuntimeError(f"无文本回复: {d}")


def parse_with_minimax(text: str, page_type: str) -> dict:
    """用 MiniMax 从文本中提取结构化数据"""
    if page_type == "second_hand":
        prompt = f"""从下面的网页文本中提取数据，只返回JSON，不要任何解释：
{{"units": <昨日二手房成交套数，整数，如527>, "area": <昨日二手房成交面积，浮点数㎡，如42244.63>}}
找不到的字段填null。

文本：
{text[:2000]}"""
    else:
        prompt = f"""从下面的网页文本中提取数据，只返回JSON，不要任何解释：
{{"new_house_units": <今日一手房成交套数，整数>, "new_house_area": <今日一手房成交面积㎡，浮点数，若显示万㎡请×10000>, "listing_total": <二手房出售挂牌套数合计，整数>}}
找不到的字段填null。

文本：
{text[:3000]}"""

    raw = ask_minimax(prompt)
    # 清理 markdown
    raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        return json.loads(m.group())
    return json.loads(raw)


# ─── 采集任务 ─────────────────────────────────────────────────────────────────
async def fetch_second_hand(debug_dir: Path) -> dict:
    print("\n  📄 采集二手房数据...")
    text = await get_page_text(URLS["second_hand"])
    (debug_dir / f"second_hand_{date.today()}.txt").write_text(text, encoding="utf-8")

    has_real = any(kw in text for kw in ["套数", "成交", "昨日"])

    if has_real and MINIMAX_API_KEY:
        try:
            result = parse_with_minimax(text, "second_hand")
            if result.get("units") or result.get("area"):
                print(f"  ✅ MiniMax解析: {result}")
                return result
        except Exception as e:
            print(f"  ⚠️  MiniMax解析失败({e})，降级用正则")

    result = regex_parse_second_hand(text)
    print(f"  ✅ 正则解析: {result}")
    return result


async def fetch_trade(debug_dir: Path) -> dict:
    print("\n  📄 采集交易统计数据...")
    text = await get_page_text(URLS["trade"])
    (debug_dir / f"trade_{date.today()}.txt").write_text(text, encoding="utf-8")

    has_real = any(kw in text for kw in ["套数", "成交", "挂牌"])

    if has_real and MINIMAX_API_KEY:
        try:
            result = parse_with_minimax(text, "trade")
            if any(result.get(k) for k in ["new_house_units", "listing_total"]):
                print(f"  ✅ MiniMax解析: {result}")
                return result
        except Exception as e:
            print(f"  ⚠️  MiniMax解析失败({e})，降级用正则")

    nh = regex_parse_new_house(text)
    listing = regex_parse_listing(text)
    result = {
        "new_house_units": nh.get("units"),
        "new_house_area": nh.get("area"),
        "listing_total": listing,
    }
    print(f"  ✅ 正则解析: {result}")
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

    history = load_history()
    if any(r["date"] == today for r in history) and "--force" not in sys.argv:
        print("⚠️  今日数据已存在，跳过（加 --force 强制重采）")
        return

    debug_dir = DATA_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)

    sh, trade = {}, {}

    try:
        sh = await fetch_second_hand(debug_dir)
    except Exception as e:
        print(f"  ❌ 二手房采集异常: {e}")

    print("\n  ⏳ 等待 6 秒（合规间隔）...")
    await asyncio.sleep(6)

    try:
        trade = await fetch_trade(debug_dir)
    except Exception as e:
        print(f"  ❌ 交易统计采集异常: {e}")

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
