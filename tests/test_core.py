"""
AMM 交易所仿真系统 — 核心业务逻辑单元测试
覆盖: LiquidityPool / SwapEngine / FeeManager / PositionManager / OracleSimulator / DataLogger
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from core.liquidity_pool import LiquidityPool, InsufficientLiquidityError, InvalidLiquidityRatioError
from core.swap_engine import SwapEngine
from core.fee_manager import FeeManager
from core.position_manager import PositionManager
from core.oracle_simulator import OracleSimulator
from core.data_logger import DataLogger


def f(val):
    """将 Decimal 或数值统一转为 float，方便断言比较"""
    return float(val)


# ============================================================
# LiquidityPool 测试
# ============================================================
class TestLiquidityPool(unittest.TestCase):

    def setUp(self):
        self.pool = LiquidityPool()

    # ---- 初始化 ----
    def test_initialize_pool(self):
        self.pool.initialize(100, 200000)
        self.assertEqual(f(self.pool.reserve_x), 100.0)
        self.assertEqual(f(self.pool.reserve_y), 200000.0)
        self.assertEqual(f(self.pool.k), 100.0 * 200000.0)
        self.assertAlmostEqual(f(self.pool.get_price()), 2000.0, delta=0.1)
        expected_lp = (100 * 200000) ** 0.5
        self.assertAlmostEqual(f(self.pool.total_lp_tokens), expected_lp, delta=0.01)

    def test_initialize_zero_liquidity_raises(self):
        with self.assertRaises(ValueError):
            self.pool.initialize(0, 100)

    # ---- Swap 报价 ----
    def test_get_swap_quote_eth_to_usdc(self):
        self.pool.initialize(100, 200000)
        quote = self.pool.get_swap_quote(1.0, True)
        self.assertIn('output_amount', quote)
        self.assertIn('price_impact', quote)
        self.assertIn('fee_amount', quote)
        self.assertGreater(f(quote['output_amount']), 0)
        self.assertGreater(f(quote['fee_amount']), 0)
        # 1 ETH → ~1974 USDC (扣除 0.3% 手续费)
        self.assertAlmostEqual(f(quote['output_amount']), 1974.32, delta=10)

    def test_get_swap_quote_usdc_to_eth(self):
        self.pool.initialize(100, 200000)
        quote = self.pool.get_swap_quote(2000.0, False)
        self.assertGreater(f(quote['output_amount']), 0)
        self.assertAlmostEqual(f(quote['output_amount']), 0.99, delta=0.1)

    def test_get_swap_quote_invalid_amount_raises(self):
        self.pool.initialize(100, 200000)
        with self.assertRaises(ValueError):
            self.pool.get_swap_quote(-1, True)
        with self.assertRaises(ValueError):
            self.pool.get_swap_quote(0, True)

    def test_get_swap_quote_exceeds_liquidity(self):
        self.pool.initialize(100, 200000)
        with self.assertRaises(InsufficientLiquidityError):
            self.pool.get_swap_quote(1e12, True)

    # ---- Swap 执行 ----
    def test_execute_swap_updates_reserves(self):
        self.pool.initialize(100, 200000)
        self.pool.execute_swap(1.0, True)
        # 池子储备应更新: ETH 增加, USDC 减少
        self.assertAlmostEqual(f(self.pool.reserve_x), 100.0 + 1.0 * 0.997, delta=0.1)
        self.assertLess(f(self.pool.reserve_y), 200000.0)

    def test_price_impact_increases_with_size(self):
        self.pool.initialize(100, 200000)
        small = f(self.pool.get_swap_quote(1.0, True)['price_impact'])
        large = f(self.pool.get_swap_quote(20.0, True)['price_impact'])
        self.assertGreater(large, small)

    def test_constant_product_maintained(self):
        """交易后 x*y=k 值保持不变"""
        self.pool.initialize(100, 200000)
        k_before = f(self.pool.k)
        self.pool.execute_swap(1.0, True)
        k_after = f(self.pool.k)
        self.assertAlmostEqual(k_before, k_after, delta=0.1)

    # ---- 流动性 ----
    def test_add_liquidity_proportional(self):
        self.pool.initialize(100, 200000)
        old_total = f(self.pool.total_lp_tokens)
        lp = self.pool.add_liquidity(2.0, 4000.0)
        self.assertGreater(lp, 0)
        self.assertAlmostEqual(f(self.pool.total_lp_tokens), old_total + lp, delta=0.01)

    def test_add_liquidity_wrong_ratio_raises(self):
        self.pool.initialize(100, 200000)
        with self.assertRaises(InvalidLiquidityRatioError):
            self.pool.add_liquidity(2.0, 3000.0)

    def test_remove_liquidity(self):
        self.pool.initialize(100, 200000)
        lp = self.pool.add_liquidity(2.0, 4000.0)
        x_return, y_return = self.pool.remove_liquidity(lp)
        self.assertAlmostEqual(x_return, 2.0, delta=0.02)
        self.assertAlmostEqual(y_return, 4000.0, delta=2)

    def test_remove_all_liquidity_raises(self):
        self.pool.initialize(100, 200000)
        total = f(self.pool.total_lp_tokens)
        with self.assertRaises(ValueError):
            self.pool.remove_liquidity(total)


# ============================================================
# SwapEngine 测试
# ============================================================
class TestSwapEngine(unittest.TestCase):

    def setUp(self):
        self.pool = LiquidityPool()
        self.fee_mgr = FeeManager()
        self.logger = DataLogger()
        self.engine = SwapEngine(self.pool, self.fee_mgr, self.logger)

    def test_execute_swap_full_flow(self):
        self.pool.initialize(100, 200000)
        result = self.engine.execute_swap('user_001', 'ETH', 1.0)
        self.assertIn('amount_out', result)
        self.assertIn('fee', result)
        self.assertIn('price_impact', result)
        self.assertGreater(f(result['fee']), 0)

    def test_get_quote(self):
        self.pool.initialize(100, 200000)
        quote = self.engine.get_quote('ETH', 1.0)
        self.assertGreater(f(quote['output_amount']), 0)


# ============================================================
# FeeManager 测试
# ============================================================
class TestFeeManager(unittest.TestCase):

    def setUp(self):
        self.pool = LiquidityPool()
        self.fee_mgr = FeeManager()

    def test_calculate_fee(self):
        fee = self.fee_mgr.calculate_fee(100.0)
        self.assertAlmostEqual(f(fee), 0.3, delta=0.001)

    def test_distribute_fees_accumulates_in_pool(self):
        self.pool.initialize(100, 200000)
        # distribute_fees 的 asset_type 参数是 'x' 或 'y'
        self.fee_mgr.distribute_fees(self.pool, 0.3, 'x')
        self.assertAlmostEqual(f(self.pool.accumulated_fees_x), 0.3, delta=0.001)

    def test_get_total_fees_after_distribution(self):
        self.pool.initialize(100, 200000)
        self.fee_mgr.distribute_fees(self.pool, 0.3, 'x')
        self.fee_mgr.distribute_fees(self.pool, 600.0, 'y')
        totals = self.fee_mgr.get_total_fees()
        self.assertAlmostEqual(totals['total_fees_x'], 0.3, delta=0.001)
        self.assertAlmostEqual(totals['total_fees_y'], 600.0, delta=0.01)

    def test_reset_clears_fees(self):
        self.pool.initialize(100, 200000)
        self.fee_mgr.distribute_fees(self.pool, 10.0, 'x')
        self.fee_mgr.reset()
        totals = self.fee_mgr.get_total_fees()
        self.assertEqual(totals['total_fees_x'], 0.0)
        self.assertEqual(totals['total_fees_y'], 0.0)


# ============================================================
# PositionManager 测试
# ============================================================
class TestPositionManager(unittest.TestCase):

    def setUp(self):
        self.logger = DataLogger()
        self.pm = PositionManager(self.logger)

    def test_calculate_impermanent_loss_no_change(self):
        il = self.pm.calculate_impermanent_loss(1.0)
        self.assertAlmostEqual(il, 0.0, delta=0.0001)

    def test_calculate_impermanent_loss_2x(self):
        il = self.pm.calculate_impermanent_loss(2.0)
        self.assertAlmostEqual(il, -0.05719, delta=0.001)

    def test_calculate_impermanent_loss_5x(self):
        il = self.pm.calculate_impermanent_loss(5.0)
        self.assertAlmostEqual(il, -0.25464, delta=0.001)

    def test_calculate_impermanent_loss_0_5x(self):
        """价格减半与翻倍的 IL 对称"""
        il = self.pm.calculate_impermanent_loss(0.5)
        self.assertAlmostEqual(il, -0.05719, delta=0.001)

    def test_il_curve_data(self):
        curve = self.pm.get_impermanent_loss_curve()
        self.assertGreater(len(curve), 0)
        for point in curve:
            self.assertIn('price_ratio', point)
            self.assertIn('il_pct', point)

    def test_open_and_close_position(self):
        self.pm.open_position('user_001', 'pool_1', 100.0, 2.0, 4000.0, 2000.0)
        pos = self.pm.positions['user_001']['pool_1']
        self.assertEqual(f(pos['lp_tokens']), 100.0)
        self.assertEqual(f(pos['deposit_x']), 2.0)

        self.pm.close_position('user_001', 'pool_1', 100.0, 1.8, 4200.0)
        self.assertNotIn('pool_1', self.pm.positions.get('user_001', {}))


# ============================================================
# OracleSimulator 测试
# ============================================================
class TestOracleSimulator(unittest.TestCase):

    def test_load_from_data_file(self):
        oracle = OracleSimulator()
        self.assertGreater(len(oracle.price_data), 0)
        self.assertGreater(oracle.get_price(), 0)

    def test_get_price_at_step(self):
        oracle = OracleSimulator()
        if len(oracle.price_data) > 5:
            self.assertGreater(oracle.get_price_at(0), 0)
            self.assertGreater(oracle.get_price_at(5), 0)

    def test_generate_price_series(self):
        oracle = OracleSimulator(data_file=None)
        oracle.seed = 42
        oracle._rng = __import__('random').Random(42)
        oracle.base_price = 2000.0
        prices = oracle.generate_price_series(20, start_price=2000.0)
        self.assertEqual(len(prices), 21)
        for p in prices:
            self.assertGreater(p, 0)

    def test_reproducibility(self):
        """seed=42 产生相同序列"""
        def make_series():
            o = OracleSimulator(data_file=None)
            o.seed = 42
            o._rng = __import__('random').Random(42)
            o.base_price = 2000.0
            return o.generate_price_series(10, start_price=2000.0)

        p1 = make_series()
        p2 = make_series()
        for a, b in zip(p1, p2):
            self.assertAlmostEqual(a, b, delta=0.0001)

    def test_reset(self):
        oracle = OracleSimulator(data_file=None)
        oracle.base_price = 2000.0
        oracle.seed = 42
        oracle._rng = __import__('random').Random(42)
        oracle.generate_price_series(5, start_price=2000.0)
        oracle.reset()
        self.assertEqual(oracle.current_step, 0)
        self.assertEqual(len(oracle.price_data), 0)


# ============================================================
# DataLogger 测试
# ============================================================
class TestDataLogger(unittest.TestCase):

    def setUp(self):
        self.logger = DataLogger()

    def test_log_swap(self):
        self.logger.log_swap('user_001', 'ETH', 'USDC',
                             1.0, 1974.0, 0.003, 0.005, 2000.0, 1980.0)
        txns = self.logger.get_recent_transactions(10)
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0]['type'], 'SWAP')

    def test_log_liquidity_event(self):
        self.logger.log_liquidity_event('user_002', 'ADD', 2.0, 4000.0, 88.56)
        events = self.logger.get_liquidity_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'LIQUIDITY_ADD')

    def test_get_statistics_empty(self):
        stats = self.logger.get_statistics()
        self.assertEqual(stats['total_swaps'], 0)
        self.assertEqual(stats['total_liquidity_events'], 0)

    def test_clear(self):
        self.logger.log_swap('user_001', 'ETH', 'USDC',
                             1.0, 1974.0, 0.003, 0.005, 2000.0, 1980.0)
        self.logger.clear()
        self.assertEqual(len(self.logger.get_recent_transactions(10)), 0)

    def test_multiple_events(self):
        self.logger.log_swap('user_001', 'ETH', 'USDC',
                             1.0, 1974.0, 0.003, 0.005, 2000.0, 1980.0)
        self.logger.log_swap('user_003', 'USDC', 'ETH',
                             2000.0, 0.99, 0.006, 0.01, 2000.0, 2020.0)
        stats = self.logger.get_statistics()
        self.assertEqual(stats['total_swaps'], 2)
        self.assertGreater(stats['total_volume'], 0)
        self.assertGreater(stats['total_fees'], 0)


# ============================================================
# 运行
# ============================================================
if __name__ == '__main__':
    unittest.main(verbosity=2)
