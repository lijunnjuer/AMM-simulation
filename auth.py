"""
认证模块
提供用户登录验证和会话管理
使用 SQLite 存储用户凭证，werkzeug 进行密码哈希
"""

import sqlite3
import os
from functools import wraps
from flask import session, jsonify, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'auth.db')


def init_db():
    """初始化数据库，创建用户表并插入默认账号"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def create_default_users():
    """预置默认账号（仅当用户表为空时）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        default_users = [
            ('admin', 'admin123'),
            ('demo', 'demo123'),
        ]
        for username, password in default_users:
            password_hash = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (username, password_hash)
            )
        conn.commit()
    conn.close()


def verify_user(username, password):
    """验证用户名和密码，成功返回 True，失败返回 False"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT password_hash FROM users WHERE username = ?',
        (username,)
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return False
    return check_password_hash(row[0], password)


def login_required(f):
    """
    登录鉴权装饰器
    - 未登录访问 API 返回 401 JSON
    - 未登录访问页面返回 302 重定向到 /login
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            # 判断是否为 API 路由
            if request_path().startswith('/api/'):
                return jsonify({'success': False, 'error': '请先登录'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def request_path():
    """获取当前请求路径（用于装饰器内部判断）"""
    from flask import request
    return request.path
