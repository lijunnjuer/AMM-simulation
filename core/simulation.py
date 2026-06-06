"""
仿真控制模块 (SimulationController)
加载模拟场景，驱动业务逻辑层按时间步长运行，并收集结果数据
"""

import json
import os


class SimulationController:
    """仿真控制器 - 协调所有模块执行模拟场景"""

    def __init__(self, pool, swap_engine, position_manager, oracle, data_logger):
        self.pool = pool
        self.swap_engine = swap_engine
        self.position_manager = position_manager
        self.oracle = oracle
        self.data_logger = data_logger

        self.current_step = 0
        self.is_running = False
        self.scenario = None
        self.user_balances = {}
        self.results = []

    def load_users(self, users_data):
        """加载用户数据并初始化余额"""
        self.user_balances = {}
        for user in users_data.get('users', []):
            self.user_balances[user['id']] = {
                'name': user['name'],
                'type': user['type'],
                'ETH': user['initial_balance'].get('ETH', 0),
                'USDC': user['initial_balance'].get('USDC', 0),
                'lp_tokens': 0.0,
            }

    def load_scenario(self, scenario):
        """加载仿真场景"""
        self.scenario = scenario
        self.current_step = 0
        self.results = []

    def load_scenario_from_file(self, filepath, scenario_index=0):
        """从文件加载场景"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        scenarios = data.get('scenarios', [])
        if scenario_index >= len(scenarios):
            raise ValueError(
                f"场景索引 {scenario_index} 超出范围 (共 {len(scenarios)} 个场景)"
            )

        self.scenario = scenarios[scenario_index]
        self.current_step = 0
        self.results = []
        return self.scenario

    def step(self):
        """执行一个仿真步骤"""
        if not self.scenario:
            return None

        events = self.scenario.get('events', [])
        step_events = [e for e in events if e.get('step') == self.current_step]

        step_results = []
        for event in step_events:
            try:
                result = self._execute_event(event)
                step_results.append(result)
            except Exception as e:
                step_results.append({
                    'error': str(e),
                    'event': event,
                })

        # 记录步骤状态
        oracle_price = self.oracle.get_price_at(self.current_step) if self.oracle else None
        pool_state = self.pool.get_state()

        self.data_logger.log_simulation_step(
            step=self.current_step,
            pool_state={
                'reserve_x': pool_state['reserve_x'],
                'reserve_y': pool_state['reserve_y'],
                'price': pool_state['current_price'],
                'k': pool_state['k'],
                'total_lp': pool_state['total_lp_tokens'],
            },
            oracle_price=oracle_price,
        )

        step_record = {
            'step': self.current_step,
            'events': step_results,
            'pool_state': {
                'price': pool_state['current_price'],
                'reserve_x': pool_state['reserve_x'],
                'reserve_y': pool_state['reserve_y'],
            },
            'oracle_price': oracle_price,
        }
        self.results.append(step_record)
        self.current_step += 1
        return step_record

    def _execute_event(self, event):
        """执行单个事件"""
        user_id = event['user_id']
        action = event['action']
        user_balance = self.user_balances.get(user_id, {})

        if action == 'swap':
            token_in = event['token_in']
            amount = event['amount']

            # 检查余额
            balance = user_balance.get(token_in, 0)
            if balance < amount:
                return {
                    'error': f'用户 {user_id} 余额不足：需要 {amount} {token_in}，'
                             f'仅有 {balance:.4f} {token_in}',
                    'event': event,
                }

            result = self.swap_engine.execute_swap(user_id, token_in, amount)

            # 更新余额
            token_out = result['token_out']
            user_balance[token_in] -= amount
            user_balance[token_out] = user_balance.get(token_out, 0) + result['amount_out']

            return {'type': 'swap', 'success': True, **result}

        elif action == 'add_liquidity':
            x_amount = event['token_x_amount']
            y_amount = event['token_y_amount']

            # 检查余额
            if user_balance.get(self.pool.token_x, 0) < x_amount:
                return {'error': f'用户 {user_id} 余额不足', 'event': event}
            if user_balance.get(self.pool.token_y, 0) < y_amount:
                return {'error': f'用户 {user_id} 余额不足', 'event': event}

            lp_tokens = self.pool.add_liquidity(x_amount, y_amount)

            # 更新余额
            user_balance[self.pool.token_x] -= x_amount
            user_balance[self.pool.token_y] -= y_amount
            user_balance['lp_tokens'] = user_balance.get('lp_tokens', 0) + lp_tokens

            # 记录 LP 仓位
            self.position_manager.open_position(
                user_id=user_id,
                pool_id='default',
                lp_tokens=lp_tokens,
                deposit_x=x_amount,
                deposit_y=y_amount,
                initial_price=float(self.pool.get_price()),
            )

            return {
                'type': 'add_liquidity',
                'success': True,
                'user_id': user_id,
                'lp_tokens': lp_tokens,
                'x_amount': x_amount,
                'y_amount': y_amount,
            }

        elif action == 'remove_liquidity':
            lp_to_remove = event.get('lp_tokens', 0)

            # 检查用户是否持有足够 LP Token
            user_lp = user_balance.get('lp_tokens', 0)
            if user_lp < lp_to_remove:
                return {
                    'error': f'用户 {user_id} LP Token 不足：需要 {lp_to_remove}，'
                             f'仅有 {user_lp:.4f}',
                    'event': event,
                }

            returned_x, returned_y = self.pool.remove_liquidity(lp_to_remove)

            # 更新余额
            user_balance[self.pool.token_x] = user_balance.get(self.pool.token_x, 0) + returned_x
            user_balance[self.pool.token_y] = user_balance.get(self.pool.token_y, 0) + returned_y
            user_balance['lp_tokens'] = user_balance.get('lp_tokens', 0) - lp_to_remove

            # 关闭 LP 仓位（按设计文档要求）
            self.position_manager.close_position(
                user_id=user_id,
                pool_id='default',
                lp_tokens_burned=lp_to_remove,
                returned_x=returned_x,
                returned_y=returned_y,
            )

            return {
                'type': 'remove_liquidity',
                'success': True,
                'user_id': user_id,
                'lp_tokens': lp_to_remove,
                'returned_x': returned_x,
                'returned_y': returned_y,
            }

        return {'error': f'未知操作: {action}', 'event': event}

    def run_full(self):
        """运行完整仿真"""
        if not self.scenario:
            return []

        duration = self.scenario.get('duration_steps', 50)
        all_results = []

        for step in range(duration):
            result = self.step()
            if result:
                all_results.append(result)

        return all_results

    def run_until(self, target_step):
        """运行到指定步骤"""
        while self.current_step < target_step:
            self.step()

    def get_results(self):
        """获取仿真结果"""
        return self.results

    def get_user_balances(self):
        """获取所有用户余额"""
        return self.user_balances

    def get_step_result(self, step):
        """获取指定步骤的结果"""
        for r in self.results:
            if r['step'] == step:
                return r
        return None

    def get_total_steps(self):
        """获取当前场景的总步数"""
        if self.scenario:
            return self.scenario.get('duration_steps', 0)
        return 0

    def reset(self):
        """重置仿真状态"""
        self.current_step = 0
        self.is_running = False
        self.scenario = None
        self.results = []
        self.user_balances = {}
