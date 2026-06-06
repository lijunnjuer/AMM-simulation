"""
AMM 交易所仿真系统 - 启动脚本
双击此文件或在终端运行: python run.py
"""

import os
import sys
import webbrowser
import threading
import time

# 确保项目目录在 Python 路径中
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

from app import app

# 获取端口
port = int(os.environ.get('PORT', 5000))

def open_browser():
    """延迟打开浏览器"""
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{port}')

if __name__ == '__main__':
    print("=" * 60)
    print("  AMM 交易所仿真系统 v1.0")
    print("  Automated Market Maker Simulation System")
    print("=" * 60)
    print()
    print(f"  启动服务器: http://127.0.0.1:{port}")
    print(f"  按 Ctrl+C 停止服务器")
    print()

    # 在新线程中打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    # 启动 Flask 服务器
    app.run(debug=False, host='127.0.0.1', port=port)
