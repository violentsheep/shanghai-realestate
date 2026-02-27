#!/usr/bin/env python3
"""
上海房地产数据采集脚本
策略：Playwright 无头浏览器渲染页面 → 提取页面文本 → MiniMax 文本模型解析数字
数据源：网上房地产 fangdi.com.cn（上海市房地产交易中心，政府机构）
合规说明：
  - 只访问公开页面，无需登录
  - robots.txt 不存在（404），无限制规则
  - 渲染后提取文本，不绕过任何反爬机制
  - 每次请求间隔 ≥6 秒
  - 只采集必要字段
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
    "Accept-Language": "zh-CN,zh;q=0.9",
}

URLS = {
    "second_hand": "https://www.fangdi.com.cn/old_house/old_house.html",
    "trade":       "https://www.fangdi.com.cn/trade/trade.html",
}


# ─── Playwright 提取页面文本 ──────────────────────────────────────────────────
async def get_page_text(url: str, wait_ms: int = 5000) -> str:
    """Playwright 完整渲染页面，返回可见文本内容"""
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
        # 提取页面全部可见文本
        text = await page.inner_text("body")
        await browser.close()
    return text


# ─── MiniMax 文本解析 ─────────────────────────────────────────────────────────
def ask_minimax(prompt: str) -> str:
    """调用 MiniMax（Anthropic 兼容接口）解析文本，返回回复内容"""
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
    raise RuntimeError(f"MiniMax 无文本回复: {d}")


def parse_json_reply(raw: str) -> dict:
    """从模型回复中提取 JSON"""
    text = re.sub(r"```json\s*|\s*```", "", raw).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group())
    return json.loads(text)


# ─── 采集任务 ─────────────────────────────────────────────────────────────────
async def fetch_second_hand(debug_dir: Path) -> dict:
    print("  🌐 渲染二手房页面...")
    text = await get_page_text(URLS["second_hand"])
    (debug_dir / f"second_hand_{date.today()}.txt").write_text(text, encoding="utf-8")
    print(f"     页面文本长度: {len(text)} 字符")

    prompt = f"""下面是上海网上房地产（fangdi.com.cn）二手房页面的文本内容。
请从中找到"昨日成交量"相关的数字，提取：
1. 昨日二手房成交套数（整数）
2. 昨日二手房成交面积（浮点数，单位㎡）

只返回JSON，格式：
{{"units": <套数整数>, "area": <面积浮点数>}}

若某项找不到填null。不要任何解释。

页面文本：
{text[:3000]}"""

    raw = ask_minimax(prompt)
    result = parse_json_reply(raw)
    print(f"  ✅ 二手房成交: {result}")
    return result


async def fetch_trade(debug_dir: Path) -> dict:
    print("  🌐 渲染交易统计页面...")
    text = await get_page_text(URLS["trade"])
    (debug_dir / f"trade_{date.today()}.txt").write_text(text, encoding="utf-8")
    print(f"     页面文本长度: {len(text)} 字符")

    prompt = f"""下面是上海网上房地产（fangdi.com.cn）交易统计页面的文本内容。
请提取以下两项数据：
1. 一手房今日成交住宅套数（全市合计，整数）
2. 一手房今日成交住宅面积（全市合计，浮点数，单位㎡，若是万㎡请乘以10000）
3. 二手房出售挂牌总套数（各区加总，整数）

只返回JSON，格式：
{{"new_house_units": <套数>, "new_house_area": <面积㎡>, "listing_total": <挂牌套数>}}

若某项找不到填null。不要任何解释。

页面文本：
{text[:4000]}"""

    raw = ask_minimax(prompt)
    result = parse_json_reply(raw)
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

    if not MINIMAX_API_KEY:
        print("❌ 请设置环境变量 MINIMAX_API_KEY")
        sys.exit(1)

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
        print(f"  ❌ 二手房采集失败: {e}")

    print("  ⏳ 等待 6 秒（合规间隔）...")
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
