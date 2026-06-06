"""
仓位/损益分析模块 (PositionManager)
跟踪 LP 头寸并计算损益，包括无常损失分析
"""

from decimal import Decimal
import math


class PositionManager:
    """LP 仓位管理器"""

    def __init__(self, data_logger=None):
        self.positions = {}  # user_id -> {pool_id: position_data}
        self.data_logger = data_logger

    def open_position(self, user_id, pool_id, lp_tokens, deposit_x, deposit_y, initial_price):
        """开立 LP 仓位"""
        if user_id not in self.positions:
            self.positions[user_id] = {}

        # 如果已有仓位，累加
        if pool_id in self.positions[user_id]:
            existing = self.positions[user_id][pool_id]
            existing['lp_tokens'] += Decimal(str(lp_tokens))
            existing['deposit_x'] += Decimal(str(deposit_x))
            existing['deposit_y'] += Decimal(str(deposit_y))
        else:
            self.positions[user_id][pool_id] = {
                'lp_tokens': Decimal(str(lp_tokens)),
                'deposit_x': Decimal(str(deposit_x)),
                'deposit_y': Decimal(str(deposit_y)),
                'initial_price': float(initial_price),
            }

        if self.data_logger:
            self.data_logger.log_liquidity_event(
                user_id=user_id,
                action='ADD',
                token_x=float(deposit_x),
                token_y=float(deposit_y),
                lp_tokens=float(lp_tokens),
            )

    def close_position(self, user_id, pool_id, lp_tokens_burned, returned_x, returned_y):
        """
        关闭（部分）LP 仓位
        lp_tokens_burned: 被销毁的 LP Token 数量
        returned_x, returned_y: 返还给用户的资产数量
        """
        if user_id not in self.positions or pool_id not in self.positions[user_id]:
            raise ValueError(f"仓位不存在: user={user_id}, pool={pool_id}")

        pos = self.positions[user_id][pool_id]
        burn = Decimal(str(lp_tokens_burned))

        # 按比例减少存入记录
        if pos['lp_tokens'] > 0:
            share = burn / pos['lp_tokens']
            pos['deposit_x'] -= share * pos['deposit_x']
            pos['deposit_y'] -= share * pos['deposit_y']

        pos['lp_tokens'] -= burn

        # 如果 LP Token 清零，删除仓位
        if pos['lp_tokens'] <= 0:
            del self.positions[user_id][pool_id]
            if not self.positions[user_id]:
                del self.positions[user_id]

        if self.data_logger:
            self.data_logger.log_liquidity_event(
                user_id=user_id,
                action='REMOVE',
                token_x=float(returned_x),
                token_y=float(returned_y),
                lp_tokens=float(lp_tokens_burned),
            )

    def calculate_impermanent_loss(self, price_ratio):
        """
        计算无常损失
        IL = 2 * sqrt(price_ratio) / (1 + price_ratio) - 1
        """
        if price_ratio <= 0:
            raise ValueError("价格比率必须为正数")

        sqrt_pr = math.sqrt(price_ratio)
        il = 2 * sqrt_pr / (1 + price_ratio) - 1
        return il

    def analyze_position(self, user_id, pool_id, pool):
        """分析 LP 仓位的盈亏状况"""
        if user_id not in self.positions or pool_id not in self.positions[user_id]:
            return None

        pos = self.positions[user_id][pool_id]
        current_price = pool.get_price()
        current_price_f = float(current_price)
        initial_price = pos['initial_price']

        # 当前持有价值（按 LP Token 份额）
        lp_share = float(pos['lp_tokens'] / pool.total_lp_tokens) if pool.total_lp_tokens > 0 else 0
        current_value_x = lp_share * float(pool.reserve_x)
        current_value_y = lp_share * float(pool.reserve_y)

        # HODL 价值 = 初始存入资产按当前价格计算的价值
        hodl_value = float(pos['deposit_x']) * current_price_f + float(pos['deposit_y'])

        # 当前 LP 价值 = 份额对应的两种资产按当前价格计价
        lp_value = current_value_x * current_price_f + current_value_y

        # 无常损失
        price_ratio = current_price_f / initial_price if initial_price > 0 else 1
        il_ratio = self.calculate_impermanent_loss(price_ratio)

        # PnL vs HODL
        pnl_vs_hodl = lp_value - hodl_value
        pnl_vs_hodl_pct = (pnl_vs_hodl / hodl_value * 100) if hodl_value > 0 else 0

        return {
            'user_id': user_id,
            'pool_id': pool_id,
            'initial_price': initial_price,
            'current_price': current_price_f,
            'price_ratio': price_ratio,
            'impermanent_loss_ratio': il_ratio,
            'impermanent_loss_pct': il_ratio * 100,
            'hodl_value': hodl_value,
            'lp_value': lp_value,
            'pnl_vs_hodl': pnl_vs_hodl,
            'pnl_vs_hodl_pct': pnl_vs_hodl_pct,
            'current_lp_share': lp_share,
        }

    def get_impermanent_loss_curve(self, price_ratios=None):
        """生成无常损失曲线数据"""
        if price_ratios is None:
            ratios = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
                      1.2, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]
        else:
            ratios = price_ratios

        curve = []
        for r in ratios:
            il = self.calculate_impermanent_loss(r)
            curve.append({
                'price_ratio': r,
                'il_pct': round(il * 100, 4),
            })
        return curve
