"""
认证模块
提供用户登录验证和会话管理
使用 SQLite 存储用户凭证，werkzeug 进行密码哈希
每个登录账号绑定一个仿真用户 ID，用于 Swap/流动性的角色绑定
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
            sim_user_id TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 兼容旧表：如果缺少 sim_user_id 列则添加
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'sim_user_id' not in columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN sim_user_id TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 列已存在或无法修改

    conn.commit()
    conn.close()


def create_default_users():
    """预置默认账号（仅当用户表为空时）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        # (username, password, sim_user_id)
        default_users = [
            ('Alice', 'alice123', 'user_001'),
            ('Bob',   'bob123',   'user_002'),
        ]
        for username, password, sim_user_id in default_users:
            password_hash = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO users (username, password_hash, sim_user_id) VALUES (?, ?, ?)',
                (username, password_hash, sim_user_id)
            )
        conn.commit()
    conn.close()


def verify_user(username, password):
    """验证用户名和密码，成功返回 {'username': ..., 'sim_user_id': ...}，失败返回 None"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT password_hash, sim_user_id FROM users WHERE username = ?',
        (username,)
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None
    if check_password_hash(row[0], password):
        return {'username': username, 'sim_user_id': row[1]}
    return None


def get_user_info(username):
    """根据用户名获取用户信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT sim_user_id FROM users WHERE username = ?',
        (username,)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'username': username, 'sim_user_id': row[0]}
    return None


def login_required(f):
    """
    登录鉴权装饰器
    - 未登录访问 API 返回 401 JSON
    - 未登录访问页面返回 302 重定向到 /login
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            if request_path().startswith('/api/'):
                return jsonify({'success': False, 'error': '请先登录'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def request_path():
    """获取当前请求路径"""
    from flask import request
    return request.path
