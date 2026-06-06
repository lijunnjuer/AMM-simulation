"""
交易引擎模块 (SwapEngine)
执行具体的代币交换逻辑，协调池子操作、手续费计算和数据记录

按概要设计文档 3.1 节序列图实现:
  User -> SE: 请求交换
  SE -> LP: getSwapQuote (计算报价与滑点)
  SE -> FM: calculateFee (计算手续费)
  SE -> LP: 更新储备金
  SE -> FM: distributeFees (累积手续费)
  SE -> DL: 记录交易详情
  SE -> User: 返回输出数量
"""


class SwapEngine:
    """AMM 代币交换引擎"""

    def __init__(self, pool, fee_manager=None, data_logger=None):
        self.pool = pool
        self.fee_manager = fee_manager
        self.data_logger = data_logger

    def execute_swap(self, user_id, input_asset, input_amount):
        """
        执行代币交换（按设计文档序列图流程）
        """
        is_x_input = (input_asset.upper() == self.pool.token_x.upper())
        input_token = self.pool.token_x if is_x_input else self.pool.token_y
        output_token = self.pool.token_y if is_x_input else self.pool.token_x

        # Step 1: 获取报价（内部已计算手续费）
        quote = self.pool.get_swap_quote(input_amount, is_x_input)

        # Step 2: 通过 FeeManager 计算手续费（按设计文档要求）
        if self.fee_manager:
            fee_amount = self.fee_manager.calculate_fee(input_amount)
        else:
            fee_amount = quote['fee_amount']

        # Step 3: 执行交换，更新池子储备金
        result = self.pool.execute_swap(input_amount, is_x_input)

        # Step 4: 通过 FeeManager 分配手续费到池子（按设计文档要求）
        if self.fee_manager:
            asset_type = 'x' if is_x_input else 'y'
            self.fee_manager.distribute_fees(self.pool, fee_amount, asset_type)

        # Step 5: 记录交易到 DataLogger
        if self.data_logger:
            self.data_logger.log_swap(
                user_id=user_id,
                token_in=input_token,
                token_out=output_token,
                amount_in=float(input_amount),
                amount_out=float(result['output_amount']),
                fee=float(fee_amount),
                price_impact=float(result['price_impact']),
                price_before=float(result['spot_price_before']),
                price_after=float(result['spot_price_after']),
            )

        # Step 6: 返回结果
        return {
            'user_id': user_id,
            'token_in': input_token,
            'token_out': output_token,
            'amount_in': float(input_amount),
            'amount_out': float(result['output_amount']),
            'fee': float(fee_amount),
            'price_impact': float(result['price_impact']),
            'effective_price': float(result['effective_price']),
            'spot_price_before': float(result['spot_price_before']),
            'spot_price_after': float(result['spot_price_after']),
        }

    def get_quote(self, input_asset, input_amount):
        """获取报价（不执行交易，用于 UI 预览）"""
        is_x_input = (input_asset.upper() == self.pool.token_x.upper())
        quote = self.pool.get_swap_quote(input_amount, is_x_input)
        # 转换为 float 供 JSON 序列化
        return {
            'output_amount': float(quote['output_amount']),
            'fee_amount': float(quote['fee_amount']),
            'price_impact': float(quote['price_impact']),
            'spot_price_before': float(quote['spot_price_before']),
            'spot_price_after': float(quote['spot_price_after']),
            'effective_price': float(quote['effective_price']),
        }
