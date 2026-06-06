"""
手续费管理模块 (FeeManager)
管理手续费的计算、累计和分配
"""

from decimal import Decimal


class FeeManager:
    """手续费管理器"""

    def __init__(self, fee_rate=0.003):
        self.fee_rate = Decimal(str(fee_rate))
        self.total_fees_collected_x = Decimal('0')
        self.total_fees_collected_y = Decimal('0')
        self.fee_distribution_log = []

    def calculate_fee(self, trade_amount):
        """计算单笔交易手续费，返回 Decimal"""
        trade_amount = Decimal(str(trade_amount))
        return trade_amount * self.fee_rate

    def distribute_fees(self, pool, fee_amount, asset_type):
        """
        将手续费累积到池子（作为 LP 未来收益）
        asset_type: 'x' 或 'y'
        """
        fee_amount = Decimal(str(fee_amount))
        if asset_type == 'x':
            self.total_fees_collected_x += fee_amount
            pool.accumulated_fees_x += fee_amount
        else:
            self.total_fees_collected_y += fee_amount
            pool.accumulated_fees_y += fee_amount

        # 记录分配日志
        self.fee_distribution_log.append({
            'fee_amount': float(fee_amount),
            'asset_type': asset_type,
            'total_fees_x': float(self.total_fees_collected_x),
            'total_fees_y': float(self.total_fees_collected_y),
        })

    def get_lp_fee_share(self, pool, user_lp_tokens):
        """计算某个 LP 应分得的手续费"""
        user_lp_tokens = Decimal(str(user_lp_tokens))
        if pool.total_lp_tokens == 0:
            return 0, 0

        share = user_lp_tokens / pool.total_lp_tokens
        fee_x = float(share * pool.accumulated_fees_x)
        fee_y = float(share * pool.accumulated_fees_y)
        return fee_x, fee_y

    def get_total_fees(self):
        """获取总手续费"""
        return {
            'total_fees_x': float(self.total_fees_collected_x),
            'total_fees_y': float(self.total_fees_collected_y),
        }

    def reset(self):
        """重置手续费统计"""
        self.total_fees_collected_x = Decimal('0')
        self.total_fees_collected_y = Decimal('0')
        self.fee_distribution_log = []
