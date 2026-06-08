"""
AMM 仿真系统 — 主入口
用法:
  python main.py                                    # 运行全部 4 个场景
  python main.py --config demo.json                 # 加载指定的配置文件运行
  python main.py --scenario 0                       # 运行指定场景
  python main.py --scenario 1 --verbose             # 详细输出
  python main.py --config my_experiment.json -v     # 自定义场景配置 + 详细输出

配置文件格式 (JSON):
{
    "demo_name": "演示实验",
    "scenarios": [0, 1],
    "output": "results.json"
}
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_scenario(idx, verbose=False):
    """运行单个场景，返回统计摘要"""
    from core.liquidity_pool import LiquidityPool
    from core.swap_engine import SwapEngine
    from core.fee_manager import FeeManager
    from core.position_manager import PositionManager
    from core.oracle_simulator import OracleSimulator
    from core.data_logger import DataLogger
    from core.simulation import SimulationController

    # 加载必要数据
    data_dir = os.path.join(os.path.dirname(__file__), 'data')

    def _load(name):
        with open(os.path.join(data_dir, name), encoding='utf-8') as f:
            return json.load(f)

    pool_cfg = _load('pool_config.json')
    users_data = _load('users.json')
    scenarios_data = _load('scenarios.json')

    pool = LiquidityPool()
    fee_mgr = FeeManager()
    logger = DataLogger()
    swap_engine = SwapEngine(pool, fee_mgr, logger)
    pos_mgr = PositionManager(logger)
    oracle = OracleSimulator()

    init = pool_cfg['initial_liquidity']
    pool.initialize(init['reserve_x'], init['reserve_y'])

    sim = SimulationController(pool, swap_engine, pos_mgr, oracle, logger)
    sim.load_users(users_data)

    scenarios = scenarios_data.get('scenarios', [])
    if idx >= len(scenarios):
        print(f"[错误] 场景 {idx} 不存在 (共 {len(scenarios)} 个)")
        return None

    scenario = scenarios[idx]
    sim.scenario = scenario
    sim.current_step = 0
    sim.results = []

    duration = scenario.get('duration_steps', 0)
    print(f"\n{'='*60}")
    print(f"  场景 {idx}: {scenario['name']}")
    print(f"  描述: {scenario.get('description', '')}")
    print(f"  步数: {duration}")
    print(f"{'='*60}")

    for _ in range(duration):
        result = sim.step()
        if result and verbose:
            events = result.get('events', [])
            state = result.get('pool_state', {})
            price = state.get('price', '--')
            oracle_p = result.get('oracle_price', '--')
            print(f"  [步骤 {result['step']:2d}] 价格: {price:>10}  预言机: {oracle_p:>10}")
            for evt in events:
                if evt.get('error'):
                    print(f"           [错误] {evt['error']}")
                elif evt.get('type') == 'swap':
                    print(f"           SWAP {evt['user_id']}: "
                          f"{evt['amount_in']:.4f} {evt['token_in']} -> "
                          f"{evt['amount_out']:.4f} {evt['token_out']}  "
                          f"(滑点: {evt.get('price_impact', 0):.4%})")
                elif 'liquidity' in evt.get('type', ''):
                    action = '添加' if 'add' in evt['type'] else '移除'
                    print(f"           LP{action} {evt['user_id']}: {evt.get('lp_tokens', 0):.4f} Token")

    stats = logger.get_statistics()
    final = pool.get_state()
    init_price = init['reserve_y'] / init['reserve_x']

    return {
        'scenario': scenario['name'],
        'steps': len(sim.results),
        'total_swaps': stats['total_swaps'],
        'total_volume': stats['total_volume'],
        'total_fees': stats['total_fees'],
        'avg_price_impact': stats['avg_price_impact'],
        'initial_price': init_price,
        'final_price': final['current_price'],
        'price_change_pct': round((final['current_price'] - init_price) / init_price * 100, 2),
    }


def print_summary(results):
    """打印汇总对比表"""
    print(f"\n{'='*80}")
    print("  全部场景汇总")
    print(f"{'='*80}")
    print(f"{'场景':<18} {'步数':>5} {'交易数':>6} {'成交量':>10} {'手续费':>8} "
          f"{'初始价':>10} {'最终价':>10} {'价格变化':>8}")
    print("-" * 80)
    for r in results:
        if r is None:
            continue
        print(f"{r['scenario']:<18} {r['steps']:>5} {r['total_swaps']:>6} "
              f"{r['total_volume']:>10.2f} {r['total_fees']:>8.4f} "
              f"{r['initial_price']:>10.2f} {r['final_price']:>10.2f} "
              f"{r['price_change_pct']:>7.2f}%")
    print("-" * 80)


def run_sensitivity_analysis(verbose=False):
    """参数敏感性分析：固定场景 0，对比三种费率下手续费和价格变化"""
    import copy
    data_dir = os.path.join(os.path.dirname(__file__), 'data')

    def _load(name):
        with open(os.path.join(data_dir, name), encoding='utf-8') as f:
            return json.load(f)

    fee_rates = [0.001, 0.003, 0.01]  # 0.1%、0.3%、1%
    results = []

    for fee in fee_rates:
        from core.liquidity_pool import LiquidityPool
        from core.swap_engine import SwapEngine
        from core.fee_manager import FeeManager
        from core.position_manager import PositionManager
        from core.oracle_simulator import OracleSimulator
        from core.data_logger import DataLogger
        from core.simulation import SimulationController

        pool_cfg = _load('pool_config.json')
        pool_cfg['fee_rate'] = fee
        users_data = _load('users.json')
        scenarios_data = _load('scenarios.json')

        pool = LiquidityPool(fee_rate=fee)
        fee_mgr = FeeManager(fee_rate=fee)
        logger = DataLogger()
        swap_engine = SwapEngine(pool, fee_mgr, logger)
        pos_mgr = PositionManager(logger)
        oracle = OracleSimulator()

        init = pool_cfg['initial_liquidity']
        pool.initialize(init['reserve_x'], init['reserve_y'])

        sim = SimulationController(pool, swap_engine, pos_mgr, oracle, logger)
        sim.load_users(users_data)

        scenario = scenarios_data['scenarios'][0]
        sim.scenario = scenario
        sim.current_step = 0
        sim.results = []

        duration = scenario.get('duration_steps', 50)
        for _ in range(duration):
            sim.step()

        stats = logger.get_statistics()
        final = pool.get_state()
        init_price = init['reserve_y'] / init['reserve_x']

        results.append({
            'fee_pct': f'{fee*100:.1f}%',
            'total_fees': stats['total_fees'],
            'total_volume': stats['total_volume'],
            'avg_price_impact': stats['avg_price_impact'],
            'final_price': final['current_price'],
            'price_change_pct': round((final['current_price'] - init_price) / init_price * 100, 2),
        })

    print(f"\n{'='*75}")
    print("  参数敏感性分析 — 费率对交易结果的影响")
    print(f"  场景: 基础交易 (50 步), 三种费率对比")
    print(f"{'='*75}")
    print(f"{'费率':<8} {'手续费收入':>10} {'成交量':>10} {'平均滑点':>10} "
          f"{'最终价格':>10} {'价格变化':>8}")
    print("-" * 75)
    for r in results:
        print(f"{r['fee_pct']:<8} {r['total_fees']:>10.4f} {r['total_volume']:>10.2f} "
              f"{r['avg_price_impact']:>9.4f}% {r['final_price']:>10.2f} "
              f"{r['price_change_pct']:>7.2f}%")
    print("-" * 75)
    print("  结论: 费率越高 → 手续费收入越多，但 LP 滑点成本也越高")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='AMM 自动做市商仿真系统 — 一键演示',
        epilog='示例: python main.py --config demo.json')
    parser.add_argument('--config', '-c', type=str, default=None,
                        help='配置文件路径 (JSON 格式)')
    parser.add_argument('--scenario', '-s', type=int, default=None,
                        help='场景索引 (0-3), 不指定则运行全部')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='显示每步详细交易记录')
    parser.add_argument('--compare', action='store_true',
                        help='运行费率敏感性分析 (0.1%% vs 0.3%% vs 1.0%%)')
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  AMM 自动做市商仿真系统  v1.0")
    print("  DeFi 核心逻辑仿真 — 恒定乘积 x·y=k")
    print("=" * 60)

    # 参数敏感性分析模式
    if args.compare:
        run_sensitivity_analysis(args.verbose)
        return

    # 加载配置
    scenario_list = []

    if args.config:
        config_path = args.config
        if not os.path.exists(config_path):
            print(f"\n[错误] 配置文件不存在: {config_path}")
            sys.exit(1)

        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)

        demo_name = config.get('demo_name', config_path)
        scenario_list = config.get('scenarios', [])
        print(f"\n  配置: {demo_name}")
        print(f"  场景列表: {scenario_list}")

    elif args.scenario is not None:
        scenario_list = [args.scenario]
    else:
        scenario_list = [0, 1, 2, 3]  # 全部

    # 运行
    results = []
    for idx in scenario_list:
        r = run_scenario(idx, args.verbose)
        results.append(r)

    # 输出
    if len(results) > 1:
        print_summary(results)

    # 保存结果
    if args.config:
        config_dir = os.path.dirname(args.config) or '.'
        output_file = config.get('output')
        if output_file:
            out_path = os.path.join(config_dir, output_file)
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n  [结果已保存] -> {out_path}")

    print(f"\n  [完成] 演示结束。")


if __name__ == '__main__':
    main()
