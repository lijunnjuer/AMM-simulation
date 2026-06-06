"""
数据记录器模块 (DataLogger)
记录所有关键事件（交易、流动性变更）到结构化日志
"""

import json
import os
import time
from datetime import datetime


class DataLogger:
    """仿真数据记录器"""

    def __init__(self, log_file=None):
        self.transactions = []
        self.liquidity_events = []
        self.simulation_steps = []

        if log_file is None:
            log_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'data', 'transaction_log.json'
            )
        self.log_file = log_file
        self._event_counter = 0

    def _generate_tx_id(self):
        """生成交易ID"""
        self._event_counter += 1
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"TX-{timestamp}-{self._event_counter:06d}"

    def _timestamp(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def log_swap(self, user_id, token_in, token_out, amount_in, amount_out,
                  fee, price_impact, price_before, price_after):
        """记录代币交换交易"""
        tx = {
            'tx_id': self._generate_tx_id(),
            'type': 'SWAP',
            'user_id': user_id,
            'timestamp': self._timestamp(),
            'token_in': token_in,
            'token_out': token_out,
            'amount_in': round(amount_in, 8),
            'amount_out': round(amount_out, 8),
            'fee': round(fee, 8),
            'price_impact': round(price_impact, 6),
            'price_before': round(price_before, 6),
            'price_after': round(price_after, 6),
        }
        self.transactions.append(tx)
        return tx

    def log_liquidity_event(self, user_id, action, token_x, token_y, lp_tokens):
        """记录流动性变更事件"""
        event = {
            'event_id': self._generate_tx_id(),
            'type': f'LIQUIDITY_{action}',
            'user_id': user_id,
            'timestamp': self._timestamp(),
            'token_x_amount': round(token_x, 8),
            'token_y_amount': round(token_y, 8),
            'lp_tokens': round(lp_tokens, 8),
        }
        self.liquidity_events.append(event)
        return event

    def log_simulation_step(self, step, pool_state, oracle_price=None):
        """记录每个仿真步骤的系统状态"""
        step_record = {
            'step': step,
            'timestamp': self._timestamp(),
            'pool_state': pool_state,
            'oracle_price': oracle_price,
        }
        self.simulation_steps.append(step_record)
        return step_record

    def get_all_transactions(self):
        """获取所有交易记录"""
        return self.transactions

    def get_transactions_by_user(self, user_id):
        """获取指定用户的交易记录"""
        return [tx for tx in self.transactions if tx['user_id'] == user_id]

    def get_recent_transactions(self, limit=20):
        """获取最近的交易记录"""
        return self.transactions[-limit:]

    def get_liquidity_events(self):
        """获取所有流动性事件"""
        return self.liquidity_events

    def save_to_file(self, filepath=None):
        """保存日志到文件"""
        if filepath is None:
            filepath = self.log_file

        data = {
            'transactions': self.transactions,
            'liquidity_events': self.liquidity_events,
            'simulation_steps': self.simulation_steps,
            'total_events': len(self.transactions) + len(self.liquidity_events),
            'exported_at': self._timestamp(),
        }

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return filepath

    def clear(self):
        """清空所有记录"""
        self.transactions = []
        self.liquidity_events = []
        self.simulation_steps = []
        self._event_counter = 0

    def get_statistics(self):
        """获取统计信息"""
        total_swaps = len(self.transactions)
        total_liquidity = len(self.liquidity_events)

        if total_swaps > 0:
            total_volume_in = sum(tx['amount_in'] for tx in self.transactions)
            total_fees = sum(tx['fee'] for tx in self.transactions)
            avg_price_impact = sum(tx['price_impact'] for tx in self.transactions) / total_swaps
        else:
            total_volume_in = 0
            total_fees = 0
            avg_price_impact = 0

        return {
            'total_swaps': total_swaps,
            'total_liquidity_events': total_liquidity,
            'total_volume': round(total_volume_in, 4),
            'total_fees': round(total_fees, 4),
            'avg_price_impact': round(avg_price_impact, 6),
        }
