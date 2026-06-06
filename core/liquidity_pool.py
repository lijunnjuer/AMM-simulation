"""
流动性池模块 (LiquidityPool)
管理单个交易对的流动性池状态，实现 AMM 恒定乘积公式 x * y = k
使用 Decimal 高精度计算，消除浮点误差
"""

from decimal import Decimal, getcontext, ROUND_DOWN

getcontext().prec = 50


class InsufficientLiquidityError(Exception):
    """流动性不足异常"""
    pass


class InvalidLiquidityRatioError(Exception):
    """流动性比例不匹配异常"""
    pass


class LiquidityPool:
    """AMM 恒定乘积做市商流动性池"""

    def __init__(self, token_x_name="ETH", token_y_name="USDC", fee_rate=0.003):
        self.token_x = token_x_name
        self.token_y = token_y_name
        self.reserve_x = Decimal('0')
        self.reserve_y = Decimal('0')
        self.k = Decimal('0')
        self.fee_rate = Decimal(str(fee_rate))
        self.total_lp_tokens = Decimal('0')
        self.accumulated_fees_x = Decimal('0')
        self.accumulated_fees_y = Decimal('0')
        self.price_history = []
        self._initial_price = None

    def initialize(self, x, y):
        """初始化流动性池"""
        x = Decimal(str(x))
        y = Decimal(str(y))
        if x <= 0 or y <= 0:
            raise ValueError("初始流动性必须大于零")

        self.reserve_x = x
        self.reserve_y = y
        self.k = x * y
        # LP Token = sqrt(x * y)，使用 Decimal 高精度开方
        self.total_lp_tokens = (x * y).sqrt()
        self._initial_price = y / x
        self._record_price()

    def _record_price(self):
        """记录当前价格快照（内部保持 Decimal 精度）"""
        if self.reserve_x > 0:
            self.price_history.append({
                'price': self.reserve_y / self.reserve_x,
                'reserve_x': self.reserve_x,
                'reserve_y': self.reserve_y,
                'k': self.k,
                'total_lp': self.total_lp_tokens,
            })

    def get_price(self):
        """获取当前现货价格 (TokenY / TokenX)"""
        if self.reserve_x == 0:
            return Decimal('0')
        return self.reserve_y / self.reserve_x

    def get_swap_quote(self, input_amount, is_x_input):
        """
        计算交易报价与滑点
        is_x_input=True: 用 TokenX 购买 TokenY
        is_x_input=False: 用 TokenY 购买 TokenX
        返回 Dict 中所有数值为 Decimal
        """
        input_amount = Decimal(str(input_amount))
        if input_amount <= 0:
            raise ValueError("输入数量必须为正数")

        fee_amount = input_amount * self.fee_rate
        effective_input = input_amount - fee_amount

        # 统一价格表示为 TokenY/TokenX
        if is_x_input:
            if effective_input >= self.reserve_x:
                raise InsufficientLiquidityError(
                    f"流动性不足：需要 {effective_input:.4f} {self.token_x}，"
                    f"池中仅有 {self.reserve_x:.4f} {self.token_x}"
                )
            new_reserve_x = self.reserve_x + effective_input
            new_reserve_y = self.k / new_reserve_x
            output_amount = self.reserve_y - new_reserve_y
            # 价格始终以 TokenY/TokenX 表示
            spot_price_before = self.reserve_y / self.reserve_x
            spot_price_after = new_reserve_y / new_reserve_x
            effective_price = output_amount / effective_input
        else:
            if effective_input >= self.reserve_y:
                raise InsufficientLiquidityError(
                    f"流动性不足：需要 {effective_input:.4f} {self.token_y}，"
                    f"池中仅有 {self.reserve_y:.4f} {self.token_y}"
                )
            new_reserve_y = self.reserve_y + effective_input
            new_reserve_x = self.k / new_reserve_y
            output_amount = self.reserve_x - new_reserve_x
            # 价格始终以 TokenY/TokenX 表示
            spot_price_before = self.reserve_y / self.reserve_x
            spot_price_after = new_reserve_y / new_reserve_x
            effective_price = effective_input / output_amount

        # 滑点 = (before - after) / before
        price_impact = (spot_price_before - spot_price_after) / spot_price_before

        return {
            'output_amount': output_amount,
            'fee_amount': fee_amount,
            'price_impact': price_impact,
            'spot_price_before': spot_price_before,
            'spot_price_after': spot_price_after,
            'effective_price': effective_price,
        }

    def execute_swap(self, input_amount, is_x_input):
        """执行代币交换，更新池子状态"""
        quote = self.get_swap_quote(input_amount, is_x_input)

        input_amount = Decimal(str(input_amount))
        fee_amount = input_amount * self.fee_rate
        effective_input = input_amount - fee_amount

        if is_x_input:
            self.reserve_x += effective_input
            self.reserve_y -= quote['output_amount']
            self.accumulated_fees_x += fee_amount
        else:
            self.reserve_y += effective_input
            self.reserve_x -= quote['output_amount']
            self.accumulated_fees_y += fee_amount

        # 验证恒定乘积守恒
        self.k = self.reserve_x * self.reserve_y
        self._record_price()
        return quote

    def add_liquidity(self, x_amount, y_amount):
        """
        添加流动性并铸造 LP Token
        返回: 铸造的 LP Token 数量 (float)
        """
        x_amount = Decimal(str(x_amount))
        y_amount = Decimal(str(y_amount))

        if x_amount <= 0 or y_amount <= 0:
            raise ValueError("添加的流动性必须大于零")

        if self.total_lp_tokens == 0:
            lp_tokens = (x_amount * y_amount).sqrt()
        else:
            expected_y = x_amount * self.reserve_y / self.reserve_x
            ratio_diff = abs(y_amount - expected_y) / expected_y
            if ratio_diff > Decimal('0.001'):
                raise InvalidLiquidityRatioError(
                    f"流动性比例不匹配：按当前池比例需要 {expected_y:.2f} {self.token_y}，"
                    f"提供了 {y_amount:.2f} {self.token_y}（偏差 {ratio_diff * 100:.2f}%）"
                )
            lp_tokens = x_amount * self.total_lp_tokens / self.reserve_x

        self.reserve_x += x_amount
        self.reserve_y += y_amount
        self.k = self.reserve_x * self.reserve_y
        self.total_lp_tokens += lp_tokens
        self._record_price()

        return float(lp_tokens)

    def remove_liquidity(self, lp_tokens):
        """
        移除流动性并返还资产
        返回: (返还的 TokenX 数量, 返还的 TokenY 数量) 均为 float
        """
        lp_tokens = Decimal(str(lp_tokens))

        if lp_tokens <= 0:
            raise ValueError("移除的 LP Token 必须大于零")
        if lp_tokens > self.total_lp_tokens:
            raise ValueError(
                f"LP Token 不足：需要 {lp_tokens:.4f}，仅有 {self.total_lp_tokens:.4f}"
            )

        share = lp_tokens / self.total_lp_tokens
        x_return = share * self.reserve_x
        y_return = share * self.reserve_y

        self.reserve_x -= x_return
        self.reserve_y -= y_return
        self.k = self.reserve_x * self.reserve_y
        self.total_lp_tokens -= lp_tokens
        self._record_price()

        return float(x_return), float(y_return)

    def get_reserve_ratio(self):
        """获取当前储备比例 (TokenX/TokenY)"""
        if self.reserve_y == 0:
            return Decimal('0')
        return self.reserve_x / self.reserve_y

    def get_state(self):
        """获取池子完整状态（API 边界，转换为 float 供 JSON 序列化）"""
        return {
            'token_x': self.token_x,
            'token_y': self.token_y,
            'reserve_x': float(self.reserve_x),
            'reserve_y': float(self.reserve_y),
            'k': float(self.k),
            'fee_rate': float(self.fee_rate),
            'total_lp_tokens': float(self.total_lp_tokens),
            'accumulated_fees_x': float(self.accumulated_fees_x),
            'accumulated_fees_y': float(self.accumulated_fees_y),
            'current_price': float(self.get_price()),
            'initial_price': float(self._initial_price) if self._initial_price else None,
            'price_history': [
                {k: float(v) if isinstance(v, Decimal) else v for k, v in entry.items()}
                for entry in self.price_history
            ],
        }
