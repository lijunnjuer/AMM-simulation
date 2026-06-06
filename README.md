# AMM 交易所仿真系统

基于恒定乘积 $x \cdot y = k$ 的自动做市商离线仿真平台，支持代币交换、流动性管理、无常损失分析和多场景交易模拟。

## 环境

- Python 3.10+
- 依赖见 `requirements.txt`

## 启动

```bash
pip install -r requirements.txt

# Web 界面
python run.py

# 命令行演示
python main.py --config demo.json
```

浏览器打开 `http://127.0.0.1:5000`，默认账号 `admin` / `admin123`。

## 测试

```bash
python -m pytest tests/ -v
```

## 项目结构

```
AMM-simulation/
├── run.py
├── main.py
├── app.py
├── auth.py
├── demo.json
├── requirements.txt
├── core/
│   ├── liquidity_pool.py      # x·y=k 池子
│   ├── swap_engine.py         # 交易引擎
│   ├── fee_manager.py         # 手续费
│   ├── position_manager.py    # LP 仓位 & 无常损失
│   ├── oracle_simulator.py    # 价格预言机
│   ├── data_logger.py         # 事件日志
│   └── simulation.py          # 仿真控制器
├── tests/
│   └── test_core.py           # 35 个单元测试
├── data/
│   ├── pool_config.json
│   ├── users.json
│   ├── scenarios.json
│   └── oracle_prices.json
├── scripts/
│   └── fetch_prices.py        # 爬取 Uniswap 真实数据
├── templates/
│   ├── index.html
│   └── login.html
└── static/
    ├── css/style.css
    ├── js/
    │   ├── app.js
    │   └── echarts.min.js
    └── img/
        ├── logo.svg
        └── favicon.svg
```

## 仿真场景

| # | 场景 | 步数 | 说明 |
|---|------|------|------|
| 0 | 基础交易 | 50 | swap 和 LP 操作混合 |
| 1 | 大额冲击 | 20 | 鲸鱼卖出 30%-50% 池深 |
| 2 | LP 提供者 | 30 | 添加 → 持有 → 移除 |
| 3 | 套利 | 40 | 高频小额套利 |

## CLI 演示

```bash
python main.py                        # 全部场景
python main.py --scenario 1           # 只看大额冲击
python main.py --scenario 1 -v        # 逐笔交易明细
python main.py --config demo.json     # 配置文件运行
```

## 使用真实行情

```bash
python scripts/fetch_prices.py        # 需挂 VPN
```

数据来源：DEX Screener（Uniswap V2 链上）→ Binance → CoinGecko 逐级回退。

## 核心公式

**Swap 输出**（手续费 $f$）：

$$y_{out} = y - \frac{k}{x + (1-f) \cdot x_{in}}$$

**无常损失**（价格变 $r$ 倍）：

$$IL = \frac{2\sqrt{r}}{1+r} - 1$$
