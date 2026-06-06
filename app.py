"""
AMM 交易所仿真系统 - Flask 后端 API
提供 RESTful API 接口供前端调用

架构遵循分层设计:
  UI 层 (templates/static) → API 层 (app.py)
  → 仿真控制层 (simulation.py) → 业务逻辑层 (core/)
  → 数据访问层 (data_logger.py, data/*.json)
"""

import json
import os
import sys
import secrets
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.liquidity_pool import LiquidityPool, InsufficientLiquidityError, InvalidLiquidityRatioError
from core.swap_engine import SwapEngine
from core.fee_manager import FeeManager
from core.position_manager import PositionManager
from core.oracle_simulator import OracleSimulator
from core.data_logger import DataLogger
from core.simulation import SimulationController
from auth import init_db, login_required, create_default_users

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.secret_key = secrets.token_hex(32)

# ============================================================
# 数据文件路径
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

VALID_TOKENS = {'ETH', 'USDC'}


def load_json(filename):
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# ============================================================
# 初始化系统模块
# ============================================================
pool_config = load_json('pool_config.json')
users_data = load_json('users.json')
scenarios_data = load_json('scenarios.json')

pool = LiquidityPool(
    token_x_name=pool_config.get('token_x', {}).get('name', 'ETH'),
    token_y_name=pool_config.get('token_y', {}).get('name', 'USDC'),
    fee_rate=pool_config.get('fee_rate', 0.003),
)

fee_manager = FeeManager(fee_rate=pool_config.get('fee_rate', 0.003))
data_logger = DataLogger()
swap_engine = SwapEngine(pool, fee_manager, data_logger)
position_manager = PositionManager(data_logger)
oracle = OracleSimulator()
simulation = SimulationController(pool, swap_engine, position_manager, oracle, data_logger)

# 初始流动性
init_liq = pool_config.get('initial_liquidity', {})
INIT_X = init_liq.get('reserve_x', 100)
INIT_Y = init_liq.get('reserve_y', 200000)


def _full_reset():
    """集中重置所有模块到初始状态"""
    pool.initialize(INIT_X, INIT_Y)
    simulation.reset()
    simulation.load_users(users_data)
    oracle.reset()
    data_logger.clear()
    fee_manager.reset()
    position_manager.positions.clear()


# 启动时初始化
init_db()
create_default_users()
_full_reset()


# ============================================================
# 页面路由
# ============================================================
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html')


@app.route('/login')
def login_page():
    return render_template('login.html')


# ============================================================
# 认证 API
# ============================================================
@app.route('/api/login', methods=['POST'])
def api_login():
    from auth import verify_user
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'error': '请输入用户名和密码'})

    if verify_user(username, password):
        session['username'] = username
        return jsonify({'success': True, 'username': username})

    return jsonify({'success': False, 'error': '用户名或密码错误'})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/session')
def api_session():
    if 'username' in session:
        return jsonify({'logged_in': True, 'username': session['username']})
    return jsonify({'logged_in': False})


# ============================================================
# 流动性池 API
# ============================================================
@app.route('/api/pool/state')
@login_required
def api_pool_state():
    return jsonify(pool.get_state())


@app.route('/api/pool/price_history')
@login_required
def api_pool_price_history():
    return jsonify(pool.get_state()['price_history'])


# ============================================================
# 交易 API
# ============================================================
@app.route('/api/swap/quote', methods=['POST'])
@login_required
def api_swap_quote():
    data = request.get_json()
    token_in = data.get('token_in', '')
    if token_in.upper() not in VALID_TOKENS:
        return jsonify({'success': False, 'error': f'无效代币: {token_in}'})

    try:
        amount = float(data.get('amount', 0))
        if amount <= 0:
            return jsonify({'success': False, 'error': '交易数量必须大于零'})
        quote = swap_engine.get_quote(token_in, amount)
        return jsonify({'success': True, 'quote': quote})
    except InsufficientLiquidityError as e:
        return jsonify({'success': False, 'error': str(e), 'type': 'liquidity'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/swap/execute', methods=['POST'])
@login_required
def api_swap_execute():
    data = request.get_json()
    token_in = data.get('token_in', '')
    user_id = data.get('user_id', 'anonymous')
    if token_in.upper() not in VALID_TOKENS:
        return jsonify({'success': False, 'error': f'无效代币: {token_in}'})

    try:
        amount = float(data.get('amount', 0))
        if amount <= 0:
            return jsonify({'success': False, 'error': '交易数量必须大于零'})

        # 检查用户余额
        balances = simulation.user_balances
        if user_id in balances:
            if balances[user_id].get(token_in, 0) < amount:
                return jsonify({
                    'success': False,
                    'error': f'余额不足：需要 {amount} {token_in}，'
                             f'仅有 {balances[user_id].get(token_in, 0):.4f} {token_in}'
                })

        result = swap_engine.execute_swap(user_id, token_in, amount)

        # 更新余额
        if user_id in balances:
            balances[user_id][token_in] -= amount
            balances[user_id][result['token_out']] = (
                balances[user_id].get(result['token_out'], 0) + result['amount_out']
            )

        return jsonify({'success': True, 'result': result})
    except InsufficientLiquidityError as e:
        return jsonify({'success': False, 'error': str(e), 'type': 'liquidity'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# 流动性 API
# ============================================================
@app.route('/api/liquidity/add', methods=['POST'])
@login_required
def api_liquidity_add():
    data = request.get_json()
    user_id = data.get('user_id', 'anonymous')

    try:
        x_amount = float(data.get('x_amount', 0))
        y_amount = float(data.get('y_amount', 0))
        if x_amount <= 0 or y_amount <= 0:
            return jsonify({'success': False, 'error': '存入数量必须大于零'})

        # 检查余额
        balances = simulation.user_balances
        if user_id in balances:
            if balances[user_id].get(pool.token_x, 0) < x_amount:
                return jsonify({'success': False,
                                'error': f'{pool.token_x} 余额不足'})
            if balances[user_id].get(pool.token_y, 0) < y_amount:
                return jsonify({'success': False,
                                'error': f'{pool.token_y} 余额不足'})

        lp_tokens = pool.add_liquidity(x_amount, y_amount)

        # 记录仓位
        position_manager.open_position(
            user_id=user_id, pool_id='default',
            lp_tokens=lp_tokens, deposit_x=x_amount, deposit_y=y_amount,
            initial_price=float(pool.get_price()),
        )

        # 更新余额
        if user_id in balances:
            balances[user_id][pool.token_x] -= x_amount
            balances[user_id][pool.token_y] -= y_amount
            balances[user_id]['lp_tokens'] = balances[user_id].get('lp_tokens', 0) + lp_tokens

        return jsonify({
            'success': True, 'lp_tokens': lp_tokens,
            'new_total_lp': float(pool.total_lp_tokens),
        })
    except InvalidLiquidityRatioError as e:
        return jsonify({'success': False, 'error': str(e), 'type': 'ratio'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/liquidity/remove', methods=['POST'])
@login_required
def api_liquidity_remove():
    data = request.get_json()
    user_id = data.get('user_id', 'anonymous')

    try:
        lp_tokens = float(data.get('lp_tokens', 0))
        if lp_tokens <= 0:
            return jsonify({'success': False, 'error': 'LP Token 数量必须大于零'})

        # 检查 LP Token 余额
        balances = simulation.user_balances
        if user_id in balances:
            if balances[user_id].get('lp_tokens', 0) < lp_tokens:
                return jsonify({
                    'success': False,
                    'error': f'LP Token 余额不足：需要 {lp_tokens}，'
                             f'仅有 {balances[user_id].get("lp_tokens", 0):.4f}'
                })

        x_return, y_return = pool.remove_liquidity(lp_tokens)

        # 更新余额
        if user_id in balances:
            balances[user_id][pool.token_x] = balances[user_id].get(pool.token_x, 0) + x_return
            balances[user_id][pool.token_y] = balances[user_id].get(pool.token_y, 0) + y_return
            balances[user_id]['lp_tokens'] = balances[user_id].get('lp_tokens', 0) - lp_tokens

        # 关闭仓位
        position_manager.close_position(
            user_id=user_id, pool_id='default',
            lp_tokens_burned=lp_tokens, returned_x=x_return, returned_y=y_return,
        )

        return jsonify({'success': True, 'returned_x': x_return, 'returned_y': y_return})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/liquidity/expected_ratio')
@login_required
def api_liquidity_expected_ratio():
    x = float(pool.reserve_x)
    y = float(pool.reserve_y)
    return jsonify({
        'ratio_y_per_x': y / x if x > 0 else 0,
        'ratio_x_per_y': x / y if y > 0 else 0,
        'price': float(pool.get_price()),
    })


# ============================================================
# 仓位分析 API
# ============================================================
@app.route('/api/positions')
@login_required
def api_positions():
    result = {}
    for user_id, user_positions in position_manager.positions.items():
        user_name = simulation.user_balances.get(user_id, {}).get('name', user_id)
        result[user_id] = {'name': user_name, 'positions': {}}
        for pool_id, pos in user_positions.items():
            analysis = position_manager.analyze_position(user_id, pool_id, pool)
            result[user_id]['positions'][pool_id] = {
                'lp_tokens': float(pos['lp_tokens']),
                'deposit_x': float(pos['deposit_x']),
                'deposit_y': float(pos['deposit_y']),
                'initial_price': pos['initial_price'],
                'analysis': analysis,
            }
    return jsonify(result)


@app.route('/api/impermanent_loss', methods=['POST'])
@login_required
def api_impermanent_loss():
    data = request.get_json()
    price_ratio = float(data.get('price_ratio', 1.0))
    if price_ratio <= 0:
        return jsonify({'success': False, 'error': '价格比率必须大于零'})
    il = position_manager.calculate_impermanent_loss(price_ratio)
    return jsonify({
        'price_ratio': price_ratio,
        'impermanent_loss_ratio': il,
        'impermanent_loss_pct': round(il * 100, 4),
    })


@app.route('/api/impermanent_loss_curve')
@login_required
def api_impermanent_loss_curve():
    return jsonify(position_manager.get_impermanent_loss_curve())


# ============================================================
# 预言机 API
# ============================================================
@app.route('/api/oracle/price')
@login_required
def api_oracle_price():
    return jsonify({'price': oracle.get_price(), 'step': oracle.current_step})


@app.route('/api/oracle/prices')
@login_required
def api_oracle_prices():
    return jsonify(oracle.get_all_prices())


@app.route('/api/oracle/generate', methods=['POST'])
@login_required
def api_oracle_generate():
    """逐步生成新的预言机价格（追加到已有数据）"""
    data = request.get_json()
    steps = int(data.get('steps', 1))
    new_prices = []
    for _ in range(steps):
        p = oracle.generate_next_price()
        new_prices.append({'step': oracle.current_step, 'price': p})
    return jsonify({'prices': new_prices})


# ============================================================
# 仿真 API
# ============================================================
@app.route('/api/simulation/scenarios')
@login_required
def api_simulation_scenarios():
    return jsonify(scenarios_data.get('scenarios', []))


@app.route('/api/simulation/load', methods=['POST'])
@login_required
def api_simulation_load():
    data = request.get_json()
    scenario_index = int(data.get('scenario_index', 0))

    _full_reset()

    scenario = simulation.load_scenario_from_file(
        os.path.join(DATA_DIR, 'scenarios.json'), scenario_index)
    return jsonify({'success': True, 'scenario': scenario})


@app.route('/api/simulation/step', methods=['POST'])
@login_required
def api_simulation_step():
    data = request.get_json() or {}
    scenario_index = data.get('scenario_index')

    if scenario_index is not None:
        scenario_index = int(scenario_index)
        # 如果场景未加载或索引不同，自动加载
        current_id = simulation.scenario.get('id') if simulation.scenario else None
        scenarios_data = load_json('scenarios.json')
        if scenario_index < len(scenarios_data.get('scenarios', [])):
            target = scenarios_data['scenarios'][scenario_index]
            if current_id != target.get('id'):
                _full_reset()
                simulation.load_scenario_from_file(
                    os.path.join(DATA_DIR, 'scenarios.json'), scenario_index)

    result = simulation.step()
    if result is None:
        return jsonify({'success': False, 'error': '未加载场景，请先加载场景'})
    return jsonify({'success': True, 'result': result})


@app.route('/api/simulation/run', methods=['POST'])
@login_required
def api_simulation_run():
    data = request.get_json()
    scenario_index = int(data.get('scenario_index', 0))

    _full_reset()
    simulation.load_scenario_from_file(
        os.path.join(DATA_DIR, 'scenarios.json'), scenario_index)
    results = simulation.run_full()
    data_logger.save_to_file()

    return jsonify({
        'success': True,
        'total_steps': len(results),
        'results': results,
    })


@app.route('/api/simulation/state')
@login_required
def api_simulation_state():
    return jsonify({
        'current_step': simulation.current_step,
        'is_running': simulation.is_running,
        'scenario_name': simulation.scenario.get('name', '') if simulation.scenario else '',
        'total_steps': simulation.get_total_steps(),
        'user_balances': simulation.user_balances,
        'pool_state': pool.get_state(),
    })


# ============================================================
# 数据/统计 API
# ============================================================
@app.route('/api/transactions')
@login_required
def api_transactions():
    limit = request.args.get('limit', 50, type=int)
    return jsonify({
        'transactions': data_logger.get_recent_transactions(limit),
        'liquidity_events': data_logger.get_liquidity_events(),
    })


@app.route('/api/statistics')
@login_required
def api_statistics():
    stats = data_logger.get_statistics()
    stats['pool'] = pool.get_state()
    stats['fees'] = fee_manager.get_total_fees()
    return jsonify(stats)


@app.route('/api/users')
@login_required
def api_users():
    return jsonify({
        'users': simulation.user_balances,
        'pool_tokens': {
            pool.token_x: float(pool.reserve_x),
            pool.token_y: float(pool.reserve_y),
        },
    })


@app.route('/api/reset', methods=['POST'])
@login_required
def api_reset():
    _full_reset()
    return jsonify({'success': True, 'message': '系统已重置'})


# ============================================================
# 启动
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("  AMM 交易所仿真系统 v1.0")
    print("  Automated Market Maker Simulation System")
    print("=" * 60)
    print(f"  交易对: {pool.token_x}/{pool.token_y}")
    print(f"  初始价格: 1 {pool.token_x} = {float(pool.get_price()):.2f} {pool.token_y}")
    print(f"  手续费率: {float(pool.fee_rate) * 100:.1f}%")
    print(f"  初始储备: {float(pool.reserve_x):.2f} {pool.token_x} / {float(pool.reserve_y):.2f} {pool.token_y}")
    print(f"  初始 k: {float(pool.k):.2f}")
    print("=" * 60)
    print(f"  访问地址: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host='127.0.0.1', port=5000)
