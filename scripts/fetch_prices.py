"""
Uniswap 真实数据爬取脚本
========================
数据源:
  1. DEX Screener — 获取 Uniswap 池子实时状态 (免费, 无需密钥)
  2. Binance 公开 API — 100 天日线历史价格 (免费, 无需密钥)
  3. CoinGecko 免费 API — 最终兜底

输出:
  - data/oracle_prices.json   (100天历史价格, 与现有格式完全兼容)
  - data/pool_config.json     (可选, --pool 参数更新池子配置)

用法:
  python scripts/fetch_prices.py          # 只更新价格
  python scripts/fetch_prices.py --pool   # 同时更新池子配置为 Uniswap 真实数据
"""

import json
import urllib.request
import os
import sys
import argparse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_PATH = os.path.join(ROOT, "data", "oracle_prices.json")
POOL_PATH = os.path.join(ROOT, "data", "pool_config.json")

# Uniswap V2 ETH/USDC 真实合约地址 (以太坊主网)
# 这是 Uniswap V2 上真实存在的 ETH/USDC 交易对
UNISWAP_V2_ETH_USDC = "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"


def simple_get(url: str, timeout: int = 30) -> dict | list | None:
    """HTTP GET, 返回解析后的 JSON, 失败返回 None"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [FAIL] {e}")
        return None


# ---------------------------------------------------------------------------
# 数据源 1: DEX Screener — Uniswap 池子实时数据
# ---------------------------------------------------------------------------

def fetch_pool_from_dexscreener(pair_address: str) -> dict | None:
    """
    从 DEX Screener 获取 Uniswap 池子当前状态。
    免费, 无需 API Key, 数据来自 Uniswap 链上。
    """
    url = f"https://api.dexscreener.com/latest/dex/pairs/ethereum/{pair_address}"
    data = simple_get(url)

    if not data:
        return None

    pairs = data.get("pairs", [])
    if not pairs:
        print("  [WARN] DEX Screener 未找到该池子")
        return None

    pair = pairs[0]
    base = pair.get("baseToken", {})
    quote = pair.get("quoteToken", {})
    price = float(pair.get("priceUsd", 0))

    print(f"  [OK] DEX Screener 池子数据")
    print(f"       交易对: {base.get('symbol', '?')}/{quote.get('symbol', '?')}")
    print(f"       价格:   1 {base.get('symbol', 'ETH')} = ${price:,.2f}")
    print(f"       DEX:    {pair.get('dexId', 'unknown')}")
    print(f"       TVL:    ${float(pair.get('liquidity', {}).get('usd', 0)):,.0f}")

    return {
        "source": "dexscreener+uniswap",
        "price": round(price, 2),
    }


# ---------------------------------------------------------------------------
# 数据源 2: Binance 公开 API — 日线 K 线 (无需密钥)
# ---------------------------------------------------------------------------

def fetch_daily_prices_binance(symbol: str, limit: int = 100) -> list[float] | None:
    """从 Binance 获取日线收盘价。symbol: ETHUSDC 或 ETHUSDT"""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}"
    data = simple_get(url)

    if not data or not isinstance(data, list) or len(data) == 0:
        print(f"  [WARN] Binance {symbol} 无数据")
        return None

    prices = [float(k[4]) for k in data]
    print(f"  [OK] Binance {symbol}: {len(prices)} 条日线")
    return prices


# ---------------------------------------------------------------------------
# 数据源 3: CoinGecko 免费 API — ETH/USD 历史价格
# ---------------------------------------------------------------------------

def fetch_daily_prices_coingecko(days: int = 100) -> list[float] | None:
    """从 CoinGecko 获取 ETH 日线价格 (USD)"""
    url = (
        "https://api.coingecko.com/api/v3/coins/ethereum/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily"
    )
    data = simple_get(url)

    if not data:
        return None

    prices_list = data.get("prices", [])
    if not prices_list:
        print("  [WARN] CoinGecko 返回数据为空")
        return None

    prices = [round(p[1], 2) for p in prices_list]
    print(f"  [OK] CoinGecko: {len(prices)} 条日线")
    return prices


# ---------------------------------------------------------------------------
# 文件操作
# ---------------------------------------------------------------------------

def backup_file(path: str):
    """创建备份"""
    if os.path.exists(path):
        bak = path + ".bak"
        os.replace(path, bak)
        print(f"  [BAK] {os.path.basename(path)} -> {os.path.basename(bak)}")


def save_json(path: str, data: dict):
    """写入 JSON"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  [SAVE] -> {path}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="从 Uniswap/DEX 爬取真实数据")
    parser.add_argument("--pool", action="store_true", help="同时更新 pool_config.json")
    args = parser.parse_args()

    print("=" * 55)
    print("  Uniswap 真实数据爬取 - AMM 仿真")
    print("=" * 55)
    print()
    print(f"  目标池子: Uniswap V2 ETH/USDC")
    print(f"  合约地址: {UNISWAP_V2_ETH_USDC}")
    print()

    # ---- 1. 获取 Uniswap 池子信息 ----
    print("--- 1. 获取 Uniswap 池子状态 (DEX Screener) ---")
    pool_info = fetch_pool_from_dexscreener(UNISWAP_V2_ETH_USDC)

    # ---- 2. 获取 100 天历史价格 ----
    print()
    print("--- 2. 获取 100 天历史价格 ---")

    prices_raw = None

    # 2a. Binance ETHUSDC
    print("  尝试 Binance ETHUSDC...")
    prices_raw = fetch_daily_prices_binance("ETHUSDC", 100)

    # 2b. Binance ETHUSDT (回退)
    if not prices_raw:
        print("  回退 Binance ETHUSDT...")
        prices_raw = fetch_daily_prices_binance("ETHUSDT", 100)

    # 2c. CoinGecko (最终兜底)
    if not prices_raw:
        print("  回退 CoinGecko...")
        prices_raw = fetch_daily_prices_coingecko(100)

    if not prices_raw:
        print()
        print("[FATAL] 所有数据源均失败，请检查网络连接后重试。")
        print("        如果在中国大陆，可能需要科学上网。")
        sys.exit(1)

    # ---- 3. 写入 oracle_prices.json ----
    print()
    print("--- 3. 写入 oracle_prices.json ---")

    first_price = prices_raw[0]
    last_price = prices_raw[-1]
    price_history = [{"step": i, "price": p} for i, p in enumerate(prices_raw)]

    oracle_data = {
        "description": (
            f"Uniswap ETH/USDC 真实价格数据"
            f" (爬取: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')})"
        ),
        "price_model": "historical",
        "base_price": first_price,
        "volatility": 0.02,
        "seed": 42,
        "price_history": price_history,
    }

    backup_file(ORACLE_PATH)
    save_json(ORACLE_PATH, oracle_data)
    print(f"  价格范围: ${first_price:,.2f} -> ${last_price:,.2f}")
    print(f"  数据条数: {len(price_history)}")

    # ---- 4. 可选: 更新 pool_config.json ----
    if args.pool and pool_info:
        print()
        print("--- 4. 更新 pool_config.json ---")

        # 保持 token 元信息不变，只更新数值
        if os.path.exists(POOL_PATH):
            with open(POOL_PATH, "r", encoding="utf-8") as f:
                pool_cfg = json.load(f)
        else:
            pool_cfg = {}

        # 用第一天的价格反推合理储备量 (保持总流动性规模可配置)
        # 沿用现有 100 ETH + 200000 USDC 的比例精神，但以真实价格修正
        current_price = pool_info["price"]
        # reserve_x: 保持 100 ETH, reserve_y: 按真实价格
        pool_cfg["initial_liquidity"] = {
            "reserve_x": 100.0,
            "reserve_y": round(100.0 * current_price, 2),
        }
        pool_cfg["fee_rate"] = 0.003
        pool_cfg["description"] = (
            f"ETH/USDC 交易对 - 数据来源: Uniswap V2 主网"
            f" (更新于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')})"
        )

        backup_file(POOL_PATH)
        save_json(POOL_PATH, pool_cfg)
        print(f"  reserve_x (ETH) : 100.0")
        print(f"  reserve_y (USDC): {pool_cfg['initial_liquidity']['reserve_y']:,.2f}")
        print(f"  初始价格: 1 ETH = ${current_price:,.2f}")
        print(f"  fee_rate: 0.3%")

    # ---- 完成 ----
    print()
    print("=" * 55)
    print("  [DONE] 数据爬取完成!")
    print()
    print("  启动仿真:")
    print("    cd TeamProject && python run.py")
    print("=" * 55)


if __name__ == "__main__":
    main()
