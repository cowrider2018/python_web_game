# ============================================================
# app.py - 輕量啟動器（路由 + socketio 初始化）
# 遊戲邏輯請見 game/ 套件
# ============================================================
from flask import Flask, render_template, jsonify, session
from uuid import uuid4
import os
from flask_socketio import SocketIO

import config
from game.constants import (
    CANVAS_WIDTH, CANVAS_HEIGHT, GROUND_Y,
    PLAYER_WIDTH, PLAYER_HEIGHT,
    OBSTACLE_WIDTH, OBSTACLE_HEIGHT,
    SERVER_FPS, PORT,
    P2_SKILL_SETS, DEFAULT_P2_SKILL,
)
from game import engine, socket_handlers

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret')
app.jinja_env.globals['DEBUG'] = getattr(config, 'DEBUG', False)
socketio = SocketIO(app, cors_allowed_origins='*')

# 注入 socketio 到 engine，並掛載所有 socket handlers
engine.init(socketio)
socket_handlers.register(socketio)


# ============================================================
# 路由
# ============================================================

@app.route('/')
def index():
    if 'client_id' not in session:
        session['client_id'] = uuid4().hex
    return render_template('index.html')


@app.route('/game_config')
def game_config():
    return jsonify({
        'canvas_width':     CANVAS_WIDTH,
        'canvas_height':    CANVAS_HEIGHT,
        'ground_y':         GROUND_Y,
        'player_width':     PLAYER_WIDTH,
        'player_height':    PLAYER_HEIGHT,
        'obstacle_width':   OBSTACLE_WIDTH,
        'obstacle_height':  OBSTACLE_HEIGHT,
        'server_fps':       SERVER_FPS,
        'p2_skill_sets':    P2_SKILL_SETS,
        'p2_default_skill': DEFAULT_P2_SKILL,
    })


if __name__ == '__main__':
    print(f"遊戲伺服器已啟動：http://localhost:{PORT}")
    socketio.run(app, port=PORT, debug=getattr(config, 'DEBUG', False), use_reloader=False)
