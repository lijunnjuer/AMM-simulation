"""
预言机模拟器模块 (OracleSimulator)
模拟外部市场价格数据流，为无常损失计算和交易策略提供基准价格
"""

import random
import json
import os
import math


class OracleSimulator:
    """外部价格预言机模拟器"""

    def __init__(self, data_file=None):
        self.base_price = 2000.0
        self.volatility = 0.02
        self.current_step = 0
        self.price_data = []
        self.seed = 42
        self._rng = random.Random(self.seed)

        if data_file and os.path.exists(data_file):
            self._load_data(data_file)
        else:
            default_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'data', 'oracle_prices.json'
            )
            if os.path.exists(default_path):
                self._load_data(default_path)

    def _load_data(self, filepath):
        """从文件加载价格数据"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.base_price = data.get('base_price', 2000.0)
        self.volatility = data.get('volatility', 0.02)
        self.seed = data.get('seed', 42)
        self._rng = random.Random(self.seed)

        history = data.get('price_history', [])
        if history:
            self.price_data = [item['price'] for item in history]
            self.current_step = len(self.price_data) - 1

    def get_price(self, step=None):
        """获取指定步骤的市场价格"""
        if step is not None and 0 <= step < len(self.price_data):
            return self.price_data[step]

        if self.price_data:
            return self.price_data[-1]
        return self.base_price

    def generate_next_price(self):
        """
        使用对数正态随机漫步模型生成下一个价格
        """
        if self.price_data:
            last_price = self.price_data[-1]
        else:
            last_price = self.base_price

        log_return = self._rng.gauss(0, self.volatility)
        new_price = last_price * math.exp(log_return)

        # 防止价格过低（相对于当前价格，而非初始价格）
        new_price = max(new_price, last_price * 0.01)

        self.price_data.append(new_price)
        self.current_step = len(self.price_data) - 1
        return new_price

    def generate_price_series(self, steps, start_price=None):
        """生成一系列价格数据"""
        if start_price is None:
            start_price = self.base_price

        prices = [start_price]
        for _ in range(steps):
            log_return = self._rng.gauss(0, self.volatility)
            new_price = prices[-1] * math.exp(log_return)
            # 底限相对于上一步价格
            new_price = max(new_price, prices[-1] * 0.01)
            prices.append(new_price)

        self.price_data = prices
        self.current_step = len(prices) - 1
        return prices

    def get_price_at(self, step):
        """获取指定步骤的价格，如果不存在则生成"""
        if 0 <= step < len(self.price_data):
            return self.price_data[step]

        while len(self.price_data) <= step:
            self.generate_next_price()
        return self.price_data[step]

    def get_all_prices(self):
        """获取所有价格数据"""
        return [
            {'step': i, 'price': p}
            for i, p in enumerate(self.price_data)
        ]

    def reset(self):
        """重置到初始状态（保持种子可复现）"""
        self.current_step = 0
        self.price_data = []
        self._rng = random.Random(self.seed)
