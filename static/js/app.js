/**
 * AMM 交易所仿真系统 - 前端应用逻辑
 */

// ============================================================
// 全局状态
// ============================================================
const STATE = {
    currentPage: 'dashboard',
    pool: null,
    users: {},
    updateInterval: null,
    charts: {},
};

// ============================================================
// 工具函数
// ============================================================
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function fmt(n, decimals = 4) {
    if (n == null || isNaN(n)) return '--';
    return Number(n).toLocaleString('zh-CN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

function fmtPrice(n) { return fmt(n, 2); }
function fmtShort(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(2) + 'K';
    return fmt(n, 2);
}

function showToast(msg, type = 'info') {
    const container = $('#toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 3500);
}

function getTimestamp() {
    const now = new Date();
    return now.toLocaleTimeString('zh-CN', { hour12: false });
}

// ============================================================
// API 请求封装
// ============================================================
async function apiGet(url) {
    const resp = await fetch(url);
    if (resp.status === 401) { window.location.href = '/login'; return; }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

async function apiPost(url, data = {}) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (resp.status === 401) { window.location.href = '/login'; return; }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

// 退出登录
async function logout() {
    await apiPost('/api/logout');
    window.location.href = '/login';
}

// 加载登录用户信息
async function loadSession() {
    try {
        const resp = await fetch('/api/session');
        const data = await resp.json();
        if (!data.logged_in) {
            window.location.href = '/login';
            return;
        }
        const el = document.getElementById('loginUsername');
        if (el) el.textContent = data.username;
    } catch (e) {
        console.error('Session check failed:', e);
    }
}

// ============================================================
// 导航
// ============================================================
function initNavigation() {
    $$('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    STATE.currentPage = page;
    $$('.nav-item').forEach(i => i.classList.remove('active'));
    $$('.page').forEach(p => p.classList.remove('active'));
    document.querySelector(`.nav-item[data-page="${page}"]`).classList.add('active');
    const pageEl = $(`#page-${page}`);
    if (pageEl) pageEl.classList.add('active');

    // 页面切换时的初始化
    if (page === 'dashboard') refreshDashboard();
    if (page === 'swap') refreshSwapPage();
    if (page === 'liquidity') refreshLiquidityPage();
    if (page === 'analysis') refreshAnalysisPage();
    if (page === 'simulation') refreshSimulationPage();
    if (page === 'data') refreshDataPage();

    // 延迟resize图表
    setTimeout(resizeAllCharts, 200);
}

// ============================================================
// 图表初始化
// ============================================================
function getChartTheme() {
    return {
        textStyle: { color: '#5f6b7a' },
        backgroundColor: 'transparent',
    };
}

function initCharts() {
    // 价格图表
    const priceChart = echarts.init($('#chartPrice'));
    priceChart.setOption({
        ...getChartTheme(),
        tooltip: { trigger: 'axis', formatter: p => `步骤 ${p[0].axisValue}<br/>价格: ${Number(p[0].value).toFixed(2)} USDC` },
        grid: { left: 50, right: 20, top: 10, bottom: 30 },
        xAxis: { type: 'category', data: [], axisLine: { lineStyle: { color: '#e5e7eb' } }, axisTick: { show: false } },
        yAxis: { type: 'value', name: 'USDC', axisLine: { show: false }, splitLine: { lineStyle: { color: '#eef0f2' } }, axisLabel: { formatter: v => fmtPrice(v) } },
        series: [{
            type: 'line', data: [], smooth: true,
            lineStyle: { color: '#2563eb', width: 2.5 },
            areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(37,99,235,0.12)' }, { offset: 1, color: 'rgba(37,99,235,0.01)' }]) },
            symbol: 'none',
        }],
    });
    STATE.charts.price = priceChart;

    // 深度图表
    const depthChart = echarts.init($('#chartDepth'));
    depthChart.setOption({
        ...getChartTheme(),
        tooltip: { trigger: 'axis' },
        grid: { left: 60, right: 20, top: 10, bottom: 30 },
        xAxis: { type: 'value', name: 'ETH', axisLine: { lineStyle: { color: '#e5e7eb' } }, splitLine: { lineStyle: { color: '#eef0f2' } } },
        yAxis: { type: 'value', name: 'USDC', axisLine: { show: false }, splitLine: { lineStyle: { color: '#eef0f2' } }, axisLabel: { formatter: v => fmtShort(v) } },
        series: [{
            type: 'line', data: [], smooth: true,
            lineStyle: { color: '#2563eb', width: 2 },
            areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(37,99,235,0.1)' }, { offset: 1, color: 'rgba(37,99,235,0.01)' }]) },
            symbol: 'none',
        }],
    });
    STATE.charts.depth = depthChart;

    // 无常损失图表
    const ilChart = echarts.init($('#chartIL'));
    ilChart.setOption({
        ...getChartTheme(),
        tooltip: { trigger: 'axis', formatter: p => `价格倍数: ${p[0].axisValue}x<br/>无常损失: ${p[0].value}%` },
        grid: { left: 55, right: 20, top: 10, bottom: 30 },
        xAxis: { type: 'category', data: [], name: '价格倍数', axisLine: { lineStyle: { color: '#e5e7eb' } }, axisTick: { show: false } },
        yAxis: { type: 'value', name: 'IL (%)', axisLine: { show: false }, splitLine: { lineStyle: { color: '#eef0f2' } }, axisLabel: { formatter: v => v.toFixed(1) + '%' } },
        series: [{
            type: 'line', data: [], smooth: true,
            lineStyle: { color: '#d97706', width: 2.5 },
            areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(217,119,6,0.1)' }, { offset: 1, color: 'rgba(217,119,6,0.01)' }]) },
            symbol: 'none',
            markLine: { data: [{ yAxis: 0, label: { formatter: '盈亏平衡' }, lineStyle: { color: '#8b95a1', type: 'dashed' } }], silent: true },
        }],
    });
    STATE.charts.il = ilChart;

    // 储备图表
    const reservesChart = echarts.init($('#chartReserves'));
    reservesChart.setOption({
        ...getChartTheme(),
        tooltip: { trigger: 'axis' },
        grid: { left: 50, right: 20, top: 10, bottom: 30 },
        xAxis: { type: 'category', data: [], axisLine: { lineStyle: { color: '#e5e7eb' } }, axisTick: { show: false } },
        yAxis: [
            { type: 'value', name: 'ETH', axisLine: { show: false }, splitLine: { lineStyle: { color: '#eef0f2' } } },
            { type: 'value', name: 'USDC', axisLine: { show: false }, splitLine: { show: false } },
        ],
        series: [
            { name: 'ETH', type: 'bar', data: [], itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] }, barGap: '30%' },
            { name: 'USDC', type: 'bar', data: [], yAxisIndex: 1, itemStyle: { color: '#16a34a', borderRadius: [4, 4, 0, 0] } },
        ],
    });
    STATE.charts.reserves = reservesChart;

    // 仿真价格图表
    const simPriceChart = echarts.init($('#chartSimPrice'));
    simPriceChart.setOption({
        ...getChartTheme(),
        tooltip: { trigger: 'axis' },
        grid: { left: 50, right: 50, top: 10, bottom: 30 },
        xAxis: { type: 'category', data: [], name: '步骤', axisLine: { lineStyle: { color: '#e5e7eb' } }, axisTick: { show: false } },
        yAxis: { type: 'value', name: '价格', axisLine: { show: false }, splitLine: { lineStyle: { color: '#eef0f2' } } },
        series: [
            { name: 'AMM价格', type: 'line', data: [], smooth: true, lineStyle: { color: '#2563eb', width: 2 }, symbol: 'none' },
            { name: '预言机价格', type: 'line', data: [], smooth: true, lineStyle: { color: '#d97706', width: 2, type: 'dashed' }, symbol: 'none' },
        ],
    });
    STATE.charts.simPrice = simPriceChart;

    // 仓位分析图表
    const posChart = echarts.init($('#chartPosition'));
    posChart.setOption({
        ...getChartTheme(),
        tooltip: { trigger: 'axis' },
        legend: { data: ['HODL价值', 'LP价值'], textStyle: { color: '#5f6b7a' }, top: 0 },
        grid: { left: 60, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: [], axisLine: { lineStyle: { color: '#e5e7eb' } }, axisTick: { show: false } },
        yAxis: { type: 'value', name: 'USDC', axisLine: { show: false }, splitLine: { lineStyle: { color: '#eef0f2' } }, axisLabel: { formatter: v => fmtShort(v) } },
        series: [
            { name: 'HODL价值', type: 'bar', data: [], itemStyle: { color: '#2563eb' } },
            { name: 'LP价值', type: 'bar', data: [], itemStyle: { color: '#16a34a' } },
        ],
    });
    STATE.charts.position = posChart;

    // 响应式
    window.addEventListener('resize', resizeAllCharts);
}

function resizeAllCharts() {
    Object.values(STATE.charts).forEach(chart => {
        try { chart.resize(); } catch (e) { /* ignore */ }
    });
}

// ============================================================
// 仪表盘刷新
// ============================================================
async function refreshDashboard() {
    try {
        const [poolState, stats, txData] = await Promise.all([
            apiGet('/api/pool/state'),
            apiGet('/api/statistics'),
            apiGet('/api/transactions?limit=20'),
        ]);
        STATE.pool = poolState;

        // 更新顶部状态栏
        $('#topPair').textContent = `${poolState.token_x}/${poolState.token_y}`;
        $('#topPrice').textContent = fmtPrice(poolState.current_price);
        $('#topVolume').textContent = fmt(stats.total_volume, 2);
        $('#topLiquidity').textContent = '$' + fmtShort(poolState.reserve_y * 2);

        // 更新仪表盘卡片
        $('#dashPrice').textContent = fmtPrice(poolState.current_price);
        $('#dashPriceUSDC').textContent = fmtPrice(poolState.current_price);
        $('#dashTVL').textContent = '$' + fmtShort(poolState.reserve_x * poolState.current_price + poolState.reserve_y);
        $('#dashVolume').textContent = fmt(stats.total_volume, 2);
        $('#dashFees').textContent = fmt(stats.total_fees, 4);
        $('#dashTxCount').textContent = stats.total_swaps;

        // 更新价格图表
        const history = poolState.price_history || [];
        const steps = history.map((_, i) => i);
        const prices = history.map(h => h.price);
        STATE.charts.price.setOption({
            xAxis: { data: steps },
            series: [{ data: prices }],
        });

        // 更新深度图表（恒定乘积曲线）
        const x = parseFloat(poolState.reserve_x);
        const y = parseFloat(poolState.reserve_y);
        const k = x * y;
        const depthData = [];
        for (let rx = x * 0.1; rx <= x * 3; rx += x * 0.05) {
            depthData.push([rx, k / rx]);
        }
        STATE.charts.depth.setOption({
            series: [{ data: depthData }],
        });

        // 更新储备图表
        const reserveSteps = history.map((_, i) => i);
        STATE.charts.reserves.setOption({
            xAxis: { data: reserveSteps },
            series: [
                { data: history.map(h => h.reserve_x) },
                { data: history.map(h => h.reserve_y) },
            ],
        });

        // 更新最近交易
        renderTransactionTable('recentTxTable', txData.transactions || []);

        // 更新价格变化
        if (history.length > 1) {
            const change = ((prices[prices.length - 1] - prices[0]) / prices[0] * 100);
            const changeEl = $('#dashPriceChange');
            changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
            changeEl.className = 'stat-change ' + (change >= 0 ? 'positive' : 'negative');
        }
    } catch (e) {
        console.error('Dashboard refresh error:', e);
    }
}

function renderTransactionTable(tbodyId, transactions) {
    const tbody = $(`#${tbodyId}`);
    if (!transactions.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">暂无交易记录</td></tr>';
        return;
    }
    tbody.innerHTML = transactions.slice().reverse().map(tx => `
        <tr>
            <td><code style="font-size:11px;color:var(--text-muted)">${tx.tx_id}</code></td>
            <td>${tx.user_id}</td>
            <td><span class="tx-type swap">SWAP</span></td>
            <td>${fmt(tx.amount_in)} ${tx.token_in}</td>
            <td>${fmt(tx.amount_out)} ${tx.token_out}</td>
            <td>${fmt(tx.fee, 6)}</td>
            <td>${(tx.price_impact * 100).toFixed(3)}%</td>
            <td style="font-size:11px;">${tx.timestamp}</td>
        </tr>
    `).join('');
}

// ============================================================
// Swap 页面
// ============================================================
let swapTimeout = null;

async function refreshSwapPage() {
    try {
        const [poolState, usersData] = await Promise.all([
            apiGet('/api/pool/state'),
            apiGet('/api/users'),
        ]);
        STATE.pool = poolState;
        STATE.users = usersData.users || {};

        // 填充用户选择
        const userSelects = ['#swapUser', '#liqAddUser', '#liqRemoveUser'];
        userSelects.forEach(sel => {
            const el = $(sel);
            if (el) {
                el.innerHTML = Object.entries(STATE.users).map(([id, u]) =>
                    `<option value="${id}">${u.name} (${u.type})</option>`
                ).join('');
            }
        });

        updateSwapBalance();
        updateSwapQuote();
    } catch (e) {
        console.error('Swap refresh error:', e);
    }
}

function updateSwapBalance() {
    const inputToken = $('#swapInputToken').value;
    const outputToken = $('#swapOutputToken').value;
    const user = $('#swapUser').value;

    if (STATE.users[user]) {
        $('#swapInputBalance').textContent = `余额: ${fmt(STATE.users[user][inputToken] || 0, 6)} ${inputToken}`;
        $('#swapOutputBalance').textContent = `余额: ${fmt(STATE.users[user][outputToken] || 0, 6)} ${outputToken}`;
    }
}

async function updateSwapQuote() {
    const amount = parseFloat($('#swapInputAmount').value);
    const tokenIn = $('#swapInputToken').value;

    if (!amount || amount <= 0) {
        $('#swapOutputAmount').value = '';
        $('#swapInfoBox').style.display = 'none';
        return;
    }

    try {
        const resp = await apiPost('/api/swap/quote', { token_in: tokenIn, amount });
        if (resp.success) {
            const q = resp.quote;
            $('#swapOutputAmount').value = fmt(q.output_amount, 6);
            $('#swapRate').textContent = `1 ${tokenIn} = ${fmt(q.effective_price, 4)} ${$('#swapOutputToken').value}`;
            $('#swapSlippage').textContent = (q.price_impact * 100).toFixed(4) + '%';
            $('#swapFee').textContent = fmt(q.fee_amount, 6) + ' ' + tokenIn;
            $('#swapMinOut').textContent = fmt(q.output_amount * 0.995, 6);
            $('#swapInfoBox').style.display = 'block';
            $('#swapError').style.display = 'none';
        } else {
            $('#swapError').textContent = resp.error;
            $('#swapError').style.display = 'block';
            $('#swapInfoBox').style.display = 'none';
        }
    } catch (e) {
        console.error('Quote error:', e);
    }
}

async function executeSwap() {
    const amount = parseFloat($('#swapInputAmount').value);
    const tokenIn = $('#swapInputToken').value;
    const user = $('#swapUser').value;

    if (!amount || amount <= 0) {
        showToast('请输入有效的交易数量', 'error');
        return;
    }

    try {
        const resp = await apiPost('/api/swap/execute', { token_in: tokenIn, amount, user_id: user });
        if (resp.success) {
            const r = resp.result;
            showToast(`交易成功! 用 ${fmt(r.amount_in)} ${r.token_in} 兑换了 ${fmt(r.amount_out)} ${r.token_out}`, 'success');
            $('#swapInputAmount').value = '';
            $('#swapOutputAmount').value = '';
            $('#swapInfoBox').style.display = 'none';
            await refreshSwapPage();
            refreshDashboard();
        } else {
            $('#swapError').textContent = resp.error;
            $('#swapError').style.display = 'block';
        }
    } catch (e) {
        showToast('交易执行失败: ' + e.message, 'error');
    }
}

// Swap 事件绑定
function initSwapEvents() {
    $('#swapInputAmount').addEventListener('input', () => {
        clearTimeout(swapTimeout);
        swapTimeout = setTimeout(updateSwapQuote, 400);
    });
    $('#swapInputToken').addEventListener('change', () => {
        $('#swapOutputToken').value = $('#swapInputToken').value === 'ETH' ? 'USDC' : 'ETH';
        updateSwapBalance();
        updateSwapQuote();
    });
    $('#swapOutputToken').addEventListener('change', () => {
        $('#swapInputToken').value = $('#swapOutputToken').value === 'ETH' ? 'USDC' : 'ETH';
        updateSwapBalance();
        updateSwapQuote();
    });
    $('#swapUser').addEventListener('change', updateSwapBalance);
    $('#swapArrow').addEventListener('click', () => {
        const tmp = $('#swapInputToken').value;
        $('#swapInputToken').value = $('#swapOutputToken').value;
        $('#swapOutputToken').value = tmp;
        updateSwapBalance();
        updateSwapQuote();
    });
    $('#btnSwap').addEventListener('click', executeSwap);
}

// ============================================================
// 流动性页面
// ============================================================
async function refreshLiquidityPage() {
    try {
        const poolState = await apiGet('/api/pool/state');
        STATE.pool = poolState;

        $('#liqTokenXLabel').textContent = poolState.token_x;
        $('#liqTokenXTag').textContent = poolState.token_x;
        $('#liqTokenYLabel').textContent = poolState.token_y;
        $('#liqTokenYTag').textContent = poolState.token_y;
        $('#liqRemoveTokenX').textContent = poolState.token_x;
        $('#liqRemoveTokenY').textContent = poolState.token_y;

        const ratio = poolState.reserve_y / poolState.reserve_x;
        $('#liqRatio').textContent = `1 ${poolState.token_x} = ${fmt(ratio, 2)} ${poolState.token_y}`;
        $('#liqTotalLP').textContent = fmt(poolState.total_lp_tokens, 6);

        updateLiquidityEstimate();
    } catch (e) {
        console.error('Liquidity refresh error:', e);
    }
}

function updateLiquidityEstimate() {
    const x = parseFloat($('#liqInputX').value) || 0;
    const y = parseFloat($('#liqInputY').value) || 0;

    if (STATE.pool && x > 0) {
        const lpTokens = x / STATE.pool.reserve_x * STATE.pool.total_lp_tokens;
        $('#liqExpectedLP').textContent = fmt(lpTokens, 6);
    } else {
        $('#liqExpectedLP').textContent = '--';
    }

    // 移除流动性预估
    const lpRemove = parseFloat($('#liqRemoveLP').value) || 0;
    if (STATE.pool && lpRemove > 0 && STATE.pool.total_lp_tokens > 0) {
        const share = lpRemove / STATE.pool.total_lp_tokens;
        $('#liqReturnX').textContent = fmt(share * STATE.pool.reserve_x, 6);
        $('#liqReturnY').textContent = fmt(share * STATE.pool.reserve_y, 2);
        $('#liqShare').textContent = (share * 100).toFixed(4) + '%';
    } else {
        $('#liqReturnX').textContent = '--';
        $('#liqReturnY').textContent = '--';
        $('#liqShare').textContent = '--';
    }
}

async function addLiquidity() {
    const x = parseFloat($('#liqInputX').value);
    const y = parseFloat($('#liqInputY').value);
    const user = $('#liqAddUser').value;

    if (!x || !y || x <= 0 || y <= 0) {
        showToast('请输入有效的存入数量', 'error');
        return;
    }

    try {
        const resp = await apiPost('/api/liquidity/add', { x_amount: x, y_amount: y, user_id: user });
        if (resp.success) {
            showToast(`流动性添加成功! 获得 ${fmt(resp.lp_tokens, 6)} LP Token`, 'success');
            $('#liqInputX').value = '';
            $('#liqInputY').value = '';
            refreshLiquidityPage();
            refreshDashboard();
        } else {
            $('#liqAddError').textContent = resp.error;
            $('#liqAddError').style.display = 'block';
        }
    } catch (e) {
        showToast('添加失败: ' + e.message, 'error');
    }
}

async function removeLiquidity() {
    const lpTokens = parseFloat($('#liqRemoveLP').value);
    const user = $('#liqRemoveUser').value;

    if (!lpTokens || lpTokens <= 0) {
        showToast('请输入有效的 LP Token 数量', 'error');
        return;
    }

    try {
        const resp = await apiPost('/api/liquidity/remove', { lp_tokens: lpTokens, user_id: user });
        if (resp.success) {
            showToast(`移除成功! 返还 ${fmt(resp.returned_x, 6)} ${STATE.pool.token_x} 和 ${fmt(resp.returned_y, 2)} ${STATE.pool.token_y}`, 'success');
            $('#liqRemoveLP').value = '';
            refreshLiquidityPage();
            refreshDashboard();
        } else {
            $('#liqRemoveError').textContent = resp.error;
            $('#liqRemoveError').style.display = 'block';
        }
    } catch (e) {
        showToast('移除失败: ' + e.message, 'error');
    }
}

function initLiquidityEvents() {
    // Tab切换
    $$('.liq-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            $$('.liq-tab').forEach(t => t.classList.remove('active'));
            $$('.liq-panel').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            $(`#panel-${tab.dataset.tab}`).classList.add('active');
        });
    });

    $('#liqInputX').addEventListener('input', updateLiquidityEstimate);
    $('#liqInputY').addEventListener('input', updateLiquidityEstimate);
    $('#liqRemoveLP').addEventListener('input', updateLiquidityEstimate);
    $('#btnAddLiquidity').addEventListener('click', addLiquidity);
    $('#btnRemoveLiquidity').addEventListener('click', removeLiquidity);
}

// ============================================================
// 分析页面
// ============================================================
async function refreshAnalysisPage() {
    try {
        // 无常损失曲线
        const ilCurve = await apiGet('/api/impermanent_loss_curve');
        STATE.charts.il.setOption({
            xAxis: { data: ilCurve.map(d => d.price_ratio.toFixed(1) + 'x') },
            series: [{ data: ilCurve.map(d => d.il_pct) }],
        });

        // LP仓位数据
        const positions = await apiGet('/api/positions');
        const posData = [];
        const posNames = [];
        const hodlValues = [];
        const lpValues = [];

        const tbody = $('#positionTable');
        let rows = '';

        for (const [uid, userData] of Object.entries(positions)) {
            for (const [pid, pos] of Object.entries(userData.positions)) {
                if (pos.analysis) {
                    const a = pos.analysis;
                    rows += `
                        <tr>
                            <td>${userData.name}</td>
                            <td>${fmt(pos.deposit_x, 4)}</td>
                            <td>${fmt(pos.deposit_y, 2)}</td>
                            <td>${fmtPrice(a.initial_price)}</td>
                            <td>${fmtPrice(a.current_price)}</td>
                            <td style="color:${a.impermanent_loss_pct < 0 ? '#ef4444' : '#22c55e'}">${a.impermanent_loss_pct.toFixed(4)}%</td>
                            <td>${fmt(a.hodl_value, 2)}</td>
                            <td>${fmt(a.lp_value, 2)}</td>
                            <td style="color:${a.pnl_vs_hodl >= 0 ? '#22c55e' : '#ef4444'}">${fmt(a.pnl_vs_hodl, 2)} (${a.pnl_vs_hodl_pct.toFixed(2)}%)</td>
                        </tr>
                    `;
                    posNames.push(userData.name);
                    hodlValues.push(a.hodl_value);
                    lpValues.push(a.lp_value);
                }
            }
        }

        tbody.innerHTML = rows || '<tr><td colspan="9" class="empty-msg">暂无 LP 仓位数据</td></tr>';

        STATE.charts.position.setOption({
            xAxis: { data: posNames },
            series: [
                { name: 'HODL价值', data: hodlValues },
                { name: 'LP价值', data: lpValues },
            ],
        });
    } catch (e) {
        console.error('Analysis refresh error:', e);
    }
}

// ============================================================
// 仿真页面
// ============================================================
async function refreshSimulationPage() {
    try {
        const scenarios = await apiGet('/api/simulation/scenarios');
        const sel = $('#simScenario');
        const currentIdx = sel.value;  // 记录当前选中项
        sel.innerHTML = scenarios.map((s, i) =>
            `<option value="${i}">${s.name}</option>`
        ).join('');

        // 恢复选中项（如果仍然有效）
        if (currentIdx && currentIdx < scenarios.length) {
            sel.value = currentIdx;
            $('#simScenarioDesc').textContent = scenarios[currentIdx].description || '';
        } else if (scenarios.length > 0) {
            $('#simScenarioDesc').textContent = scenarios[0].description || '';
        }

        // 更新用户余额显示
        const simState = await apiGet('/api/simulation/state');
        renderSimBalances(simState.user_balances || {});

        // 更新进度
        if (simState.scenario_name) {
            $('#simProgressText').textContent = `${simState.current_step} / ${simState.total_steps || '--'}`;
        }
    } catch (e) {
        console.error('Simulation refresh error:', e);
    }
}

function renderSimBalances(balances) {
    const container = $('#simBalances');
    container.innerHTML = Object.entries(balances).map(([id, u]) => `
        <div class="sim-balance-user">
            <span class="user-name">${u.name || id}</span>
            <span class="user-balance">ETH: ${fmt(u.ETH || 0, 2)} | USDC: ${fmt(u.USDC || 0, 0)} | LP: ${fmt(u.lp_tokens || 0, 2)}</span>
        </div>
    `).join('');
}

async function runSimulation() {
    const index = parseInt($('#simScenario').value);
    const btn = $('#btnSimRun');
    btn.disabled = true;
    btn.textContent = '运行中...';

    try {
        const resp = await apiPost('/api/simulation/run', { scenario_index: index });
        if (resp.success) {
            showToast(`仿真完成! 共执行 ${resp.total_steps} 步`, 'success');
            await refreshSimulationPage();
            await refreshDashboard();
            await renderSimResults(resp.results);
        }
    } catch (e) {
        showToast('仿真运行失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '运行完整仿真';
    }
}

async function stepSimulation() {
    try {
        const idx = parseInt($('#simScenario').value);
        const resp = await apiPost('/api/simulation/step', { scenario_index: idx });
        if (resp.success) {
            const r = resp.result;
            showToast(`步骤 ${r.step} 执行完成`, 'info');
            await refreshSimulationPage();
            await refreshDashboard();
            appendSimLog(r);

            // 更新进度
            const simState = await apiGet('/api/simulation/state');
            const totalSteps = simState.total_steps || 0;
            if (totalSteps > 0) {
                const pct = (r.step / totalSteps * 100);
                $('#simProgressBar').style.width = pct + '%';
                $('#simProgressText').textContent = `${r.step} / ${totalSteps}`;
            }
            updateSimPriceChart();
        } else {
            showToast(resp.error, 'error');
        }
    } catch (e) {
        showToast('步骤执行失败: ' + e.message, 'error');
    }
}

async function resetSimulation() {
    try {
        await apiPost('/api/reset');
        showToast('系统已重置', 'info');
        $('#simProgressBar').style.width = '0%';
        $('#simProgressText').textContent = '0 / 0';
        $('#simLog').innerHTML = '<div class="empty-msg">等待仿真开始...</div>';
        await refreshSimulationPage();
        await refreshDashboard();
    } catch (e) {
        showToast('重置失败: ' + e.message, 'error');
    }
}

function appendSimLog(stepResult) {
    const log = $('#simLog');
    if (log.querySelector('.empty-msg')) log.innerHTML = '';

    const entry = document.createElement('div');
    entry.className = 'sim-log-entry';
    let html = `<span class="step-num">[步骤 ${stepResult.step}]</span> `;
    if (stepResult.pool_state) {
        html += `价格: ${fmtPrice(stepResult.pool_state.price)} `;
    }
    if (stepResult.events) {
        stepResult.events.forEach(evt => {
            if (evt.error) {
                html += `<span class="error">⚠ ${evt.error}</span> `;
            } else if (evt.type === 'swap') {
                html += `<span class="event-type">SWAP</span> ${evt.user_id}: ${fmt(evt.amount_in)} ${evt.token_in}→${fmt(evt.amount_out)} ${evt.token_out} `;
            } else if (evt.type === 'add_liquidity') {
                html += `<span class="event-type">ADD LP</span> ${evt.user_id}: +${fmt(evt.lp_tokens)} LP `;
            } else if (evt.type === 'remove_liquidity') {
                html += `<span class="event-type">REMOVE LP</span> ${evt.user_id}: -${fmt(evt.lp_tokens)} LP `;
            }
        });
    }
    entry.innerHTML = html;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

async function renderSimResults(results) {
    const log = $('#simLog');
    log.innerHTML = '';
    results.forEach(r => appendSimLog(r));

    // 更新进度条
    if (results.length > 0) {
        const simState = await apiGet('/api/simulation/state');
        const totalSteps = simState.total_steps || results.length;
        const lastStep = results[results.length - 1].step;
        $('#simProgressBar').style.width = '100%';
        $('#simProgressText').textContent = `${lastStep + 1} / ${totalSteps}`;
    }

    updateSimPriceChart();
}

async function updateSimPriceChart() {
    try {
        const poolState = await apiGet('/api/pool/state');
        const oracleData = await apiGet('/api/oracle/prices');

        const history = poolState.price_history || [];
        STATE.charts.simPrice.setOption({
            xAxis: { data: history.map((_, i) => i) },
            series: [
                { data: history.map(h => h.price) },
                { data: oracleData.slice(0, history.length).map(d => d.price) },
            ],
        });
    } catch (e) {
        console.error('Update sim chart error:', e);
    }
}

function initSimulationEvents() {
    $('#simScenario').addEventListener('change', async () => {
        const idx = parseInt($('#simScenario').value);
        const scenarios = await apiGet('/api/simulation/scenarios');
        if (scenarios[idx]) {
            $('#simScenarioDesc').textContent = scenarios[idx].description || '';
        }
        // 自动加载选中的场景
        try {
            await apiPost('/api/simulation/load', { scenario_index: idx });
            $('#simProgressBar').style.width = '0%';
            $('#simProgressText').textContent = '0 / ' + (scenarios[idx].duration_steps || 0);
            $('#simLog').innerHTML = '<div class="empty-msg">场景已加载，点击"单步执行"开始...</div>';
            await refreshSimulationPage();
        } catch (e) {
            showToast('场景加载失败: ' + e.message, 'error');
        }
    });
    $('#btnSimRun').addEventListener('click', runSimulation);
    $('#btnSimStep').addEventListener('click', stepSimulation);
    $('#btnSimReset').addEventListener('click', resetSimulation);
}

// ============================================================
// 数据页面
// ============================================================
async function refreshDataPage() {
    try {
        const [txData, stats] = await Promise.all([
            apiGet('/api/transactions?limit=500'),
            apiGet('/api/statistics'),
        ]);

        $('#dataTotalTx').textContent = stats.total_swaps;
        $('#dataTotalLiq').textContent = stats.total_liquidity_events;
        $('#dataTotalVolume').textContent = fmt(stats.total_volume, 2);
        $('#dataAvgSlippage').textContent = (stats.avg_price_impact * 100).toFixed(4) + '%';

        // 全部交易记录
        const allTxs = [...(txData.transactions || []), ...(txData.liquidity_events || [])];
        allTxs.sort((a, b) => (b.tx_id || b.event_id || '').localeCompare(a.tx_id || a.event_id || ''));

        const tbody = $('#fullTxTable');
        tbody.innerHTML = allTxs.map(tx => {
            const isSwap = tx.type === 'SWAP';
            const typeClass = isSwap ? 'swap' : (tx.type.includes('ADD') ? 'add' : 'remove');
            return `
                <tr>
                    <td><code style="font-size:11px;color:var(--text-muted)">${tx.tx_id || tx.event_id}</code></td>
                    <td><span class="tx-type ${typeClass}">${tx.type}</span></td>
                    <td>${tx.user_id}</td>
                    <td>${fmt(tx.amount_in || tx.token_x_amount, 4)} ${tx.token_in || ''}</td>
                    <td>${fmt(tx.amount_out || tx.token_y_amount, 4)} ${tx.token_out || ''}</td>
                    <td>${fmt(tx.fee || 0, 6)}</td>
                    <td>${tx.price_impact ? (tx.price_impact * 100).toFixed(3) + '%' : '--'}</td>
                    <td style="font-size:11px;">${tx.timestamp}</td>
                </tr>
            `;
        }).join('') || '<tr><td colspan="8" class="empty-msg">暂无交易记录</td></tr>';
    } catch (e) {
        console.error('Data page refresh error:', e);
    }
}

// ============================================================
// 初始化
// ============================================================
async function init() {
    // 检查登录状态
    await loadSession();

    initNavigation();
    initCharts();
    initSwapEvents();
    initLiquidityEvents();
    initSimulationEvents();

    // 退出登录按钮
    const btnLogout = document.getElementById('btnLogout');
    if (btnLogout) {
        btnLogout.addEventListener('click', logout);
    }

    // 重置按钮
    $('#btnReset').addEventListener('click', async () => {
        if (confirm('确定要重置系统吗？所有交易记录和仓位将被清除。')) {
            try {
                await apiPost('/api/reset');
                showToast('系统已重置', 'info');
                refreshDashboard();
            } catch (e) {
                showToast('重置失败', 'error');
            }
        }
    });

    // 初始加载
    await refreshDashboard();

    // 定时刷新
    STATE.updateInterval = setInterval(refreshDashboard, 15000);
}

// 启动
document.addEventListener('DOMContentLoaded', init);
