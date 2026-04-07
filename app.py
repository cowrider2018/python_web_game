from flask import Flask, render_template, jsonify, request, session
from uuid import uuid4
import os
import random
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret')
socketio = SocketIO(app, cors_allowed_origins='*')

# ============================================================
# 伺服器常數（集中管理，可在此調整所有數值）
# ============================================================

# ---- 伺服器 ----
PORT       = 8515
SERVER_FPS = 120.0          # 每秒 TICK 數

# ---- 畫布 / 場景 ----
CANVAS_WIDTH  = 800
CANVAS_HEIGHT = 600
GROUND_Y      = CANVAS_HEIGHT - 40   # 地面底邊 Y（地面頂邊 = GROUND_Y - PLAYER_HEIGHT）

# ---- 玩家 ----
PLAYER_WIDTH  = 40
PLAYER_HEIGHT = 40
GRAVITY       = 0.6

# P1 跳躍
P1_JUMP_VY        = -15.0   # 一段跳初速（向上為負）
P1_DOUBLE_JUMP_VY = -12.0   # 二段跳初速

# P2 技能
P2_UPSKILL_JUMP_VY        = -12.0  # upskill 起跳速度
P2_DOWNSKILL_JUMP_VY      = -15.0  # downskill 起跳速度
P2_UPSKILL_SPAWN_TICK     = 30     # upskill 起跳後第幾 TICK 召喚障礙物
P2_DOWNSKILL_LAND_IMPULSE = -9.0   # downskill 落地時給地面障礙物的向上速度
# 地面（僅外觀）震動/抖動參數
GROUND_ANIM_VY_START      = -5.0   # 地面外觀的初始向上速度（負值）

# ---- 障礙物 ----
OBSTACLE_WIDTH  = 40
OBSTACLE_HEIGHT = 40
OBSTACLE_SPEED  = 5                 # 每 TICK 水平移動像素
SPAWN_INTERVAL_TICKS = 300          # 每隔幾 TICK 生成一個障礙物（120=1秒）

# 障礙物反彈（jumping=True 的障礙物落地後自動重跳）
OBS_BOUNCE_VY_START       = -7.0   # 初始反彈速度（向上）
OBS_BOUNCE_VY_DECREMENT   =  1.0   # 每次反彈速度衰減量（絕對值減少）
OBS_BOUNCE_VY_MIN         = -3.0   # 反彈速度下限
OBS_BOUNCE_COOLDOWN_TICKS =  1     # 落地後冷卻 TICK 數（0=立即再跳）

# ---- Sprite 名稱 ----
P1_SPRITE        = 'player_1.png'
P2_SPRITE_NORMAL = 'player_2_normal.png'
P2_SPRITE_ROAR   = 'player_2_roar.png'
P2_SPRITE_SQUAT  = 'player_2_squat.png'

# ---- P2 技能外觀排程 ----
# sequence: sprite 清單；frames: 每個 sprite 持續 TICK 數
P2_SKILL_SETS = {
    'upskill': {
        'sequence': [P2_SPRITE_SQUAT, P2_SPRITE_ROAR, P2_SPRITE_SQUAT],
        'frames':   [15,              20,               15]
    },
    'downskill': {
        'sequence': [P2_SPRITE_SQUAT],
        'frames':   [80]
    }
}
DEFAULT_P2_SKILL = 'upskill'

# ============================================================
# 槽位 / 連線管理
# ============================================================
SLOT_NAMES       = {1: 'P1', 2: 'P2'}
slot_owners      = {1: None, 2: None}   # slot -> client_id
sid_to_slot      = {}                   # sid  -> slot
role_map         = {}                   # sid  -> slot (0=觀眾)
spawn_task_running = False

# ============================================================
# 遊戲狀態
# ============================================================
game_state = {
    'players':        {},
    'obstacles':      [],
    'score':          0,
    'gameOver':       False,
    'gameOverReason': ''
}
tick_count = 0


# ============================================================
# 輔助函式
# ============================================================

def ground_top():
    return GROUND_Y - PLAYER_HEIGHT


def rebuild_players():
    """根據 slot_owners 初始化 players。"""
    new_players = {}
    for slot in (1, 2):
        owner  = slot_owners.get(slot)
        active = owner is not None
        x = 50 if slot == 1 else (CANVAS_WIDTH - 50 - PLAYER_WIDTH)
        new_players[slot] = {
            'x':      x,
            'y':      ground_top(),
            'vel':    0.0,
            'active': active,
            'name':   SLOT_NAMES.get(slot, f'P{slot}'),
            'sprite': P2_SPRITE_NORMAL if slot == 2 else P1_SPRITE,
            'isJumping':   False,
            'canDouble':   True,       # P1 本次空中是否還可二段跳
            'skillLocked': False,      # P2 技能執行中時禁止再次觸發
            'sprite_schedule': [],     # [{'sprite': str, 'ticks': int}, ...]
            'schedule_tick':   0,      # 當前排程項目已消耗 TICK 數
            'upskill_spawn_tick':      -1,    # upskill 計時（-1=未啟用）
            'downskill_pending_land':  False,
        }
    game_state['players'] = new_players


def apply_sprite_schedule(player, schedule):
    """將技能外觀排程套用到玩家（覆蓋先前排程）。"""
    player['sprite_schedule'] = [{'sprite': s, 'ticks': t}
                                  for s, t in zip(schedule['sequence'], schedule['frames'])]
    player['schedule_tick'] = 0
    if player['sprite_schedule']:
        player['sprite'] = player['sprite_schedule'][0]['sprite']


def check_collision(player, obs):
    """AABB 碰撞：player.y 為左上角，obs.y 為底邊。"""
    obs_top = obs['y'] - OBSTACLE_HEIGHT
    return (player['x'] + PLAYER_WIDTH  > obs['x'] and
            player['x']                 < obs['x'] + OBSTACLE_WIDTH and
            player['y'] + PLAYER_HEIGHT > obs_top  and
            player['y']                 < obs['y'])


def reset_game():
    rebuild_players()
    game_state['obstacles']      = []
    game_state['score']          = 0
    game_state['gameOver']       = False
    game_state['gameOverReason'] = ''
    # cosmetic ground animation state (offset in pixels, vy in px/tick)
    game_state['ground_animation'] = {'offset': 0.0, 'vy': 0.0}



# ============================================================
# Flask 路由
# ============================================================

@app.route('/')
def index():
    if 'client_id' not in session:
        session['client_id'] = uuid4().hex
    return render_template('index.html')


@app.route('/game_config')
def game_config():
    return jsonify({
        'canvas_width':    CANVAS_WIDTH,
        'canvas_height':   CANVAS_HEIGHT,
        'ground_y':        GROUND_Y,
        'player_width':    PLAYER_WIDTH,
        'player_height':   PLAYER_HEIGHT,
        'obstacle_width':  OBSTACLE_WIDTH,
        'obstacle_height': OBSTACLE_HEIGHT,
        'server_fps':      SERVER_FPS,
        'p2_skill_sets':   P2_SKILL_SETS,
        'p2_default_skill': DEFAULT_P2_SKILL,
    })


# ============================================================
# Socket.IO 事件
# ============================================================

@socketio.on('connect')
def on_connect():
    print(f"[socket] connect: {request.sid}")


@socketio.on('disconnect')
def on_disconnect():
    sid  = request.sid
    slot = sid_to_slot.pop(sid, None)
    role_map.pop(sid, None)
    occupied = sum(1 for v in slot_owners.values() if v is not None)
    socketio.emit('state', game_state)
    socketio.emit('player_count', {'count': occupied})
    print(f"[socket] disconnect: sid={sid} slot={slot}")


@socketio.on('join')
def handle_join():
    sid       = request.sid
    client_id = session.get('client_id')
    existing  = next((s for s, o in slot_owners.items() if o == client_id), None)
    if existing:
        assigned = existing
    else:
        empty = next((s for s, o in slot_owners.items() if o is None), None)
        if empty is not None:
            slot_owners[empty] = client_id
            assigned = empty
        else:
            assigned = 0

    role_map[sid] = assigned
    if assigned:
        sid_to_slot[sid] = assigned

    rebuild_players()
    occupied = sum(1 for v in slot_owners.values() if v is not None)
    emit('assign', {'assigned': assigned, 'count': occupied})
    socketio.emit('state', game_state)
    socketio.emit('player_count', {'count': occupied})

    global spawn_task_running
    if not spawn_task_running and occupied > 0:
        spawn_task_running = True
        socketio.start_background_task(target=game_loop)

    print(f"[socket] join: sid={sid} assigned={assigned} occupied={occupied}")


@socketio.on('leave')
def handle_leave():
    sid       = request.sid
    client_id = session.get('client_id')
    slot = next((s for s, o in slot_owners.items() if o == client_id), None)
    if slot:
        slot_owners[slot] = None
        for s, sl in list(sid_to_slot.items()):
            if sl == slot:
                sid_to_slot.pop(s, None)
                role_map.pop(s, None)
    role_map[sid] = 0
    rebuild_players()
    occupied = sum(1 for v in slot_owners.values() if v is not None)
    emit('assign', {'assigned': 0, 'count': occupied})
    socketio.emit('state', game_state)
    socketio.emit('player_count', {'count': occupied})
    print(f"[socket] leave: sid={sid} slot_cleared={slot}")


@socketio.on('request_reset')
def handle_reset():
    reset_game()
    socketio.emit('state', game_state)
    print(f"[socket] reset by sid={request.sid}")


# ---- P1 輸入 ----

@socketio.on('jump')
def handle_jump(data):
    """P1 地面點擊 → 一段跳；空中點擊 → 二段跳（最多一次）。"""
    role      = _parse_role(data)
    client_id = session.get('client_id')
    if not _owns(role, client_id):
        return
    player = game_state['players'].get(role)
    if not player or not player['active'] or game_state['gameOver']:
        return

    gt        = ground_top()
    on_ground = player['y'] >= gt - 1

    if on_ground:
        player['vel']       = P1_JUMP_VY
        player['isJumping'] = True
        player['canDouble'] = True
        print(f"[jump] role={role} 一段跳")
    elif role == 1 and player.get('canDouble', False):
        player['vel']       = P1_DOUBLE_JUMP_VY
        player['canDouble'] = False
        print(f"[jump] role={role} 二段跳")


# ---- P2 輸入 ----

@socketio.on('swipe_up')
def handle_swipe_up(data):
    """P2 上滑 → upskill：起跳 + 外觀排程 + P2_UPSKILL_SPAWN_TICK 後召喚反彈障礙物。"""
    client_id = session.get('client_id')
    if not _owns(2, client_id):
        return
    player = game_state['players'].get(2)
    if not player or not player['active'] or game_state['gameOver']:
        return

    gt = ground_top()
    if player['y'] < gt - 1 or player.get('skillLocked'):
        return

    player['vel']                = P2_UPSKILL_JUMP_VY
    player['isJumping']          = True
    player['skillLocked']        = True
    player['upskill_spawn_tick'] = 0
    apply_sprite_schedule(player, P2_SKILL_SETS['upskill'])
    print(f"[swipe_up] P2 upskill triggered")


@socketio.on('swipe_down')
def handle_swipe_down(data):
    """P2 下滑 → downskill：起跳 + 外觀排程 + 落地時給地面障礙物向上衝量。"""
    client_id = session.get('client_id')
    if not _owns(2, client_id):
        return
    player = game_state['players'].get(2)
    if not player or not player['active'] or game_state['gameOver']:
        return

    gt = ground_top()
    if player['y'] < gt - 1 or player.get('skillLocked'):
        return

    player['vel']                    = P2_DOWNSKILL_JUMP_VY
    player['isJumping']              = True
    player['skillLocked']            = True
    player['downskill_pending_land'] = True
    apply_sprite_schedule(player, P2_SKILL_SETS['downskill'])
    print(f"[swipe_down] P2 downskill triggered")


# ---- 輔助 ----

def _parse_role(data):
    role = data.get('role') if isinstance(data, dict) else None
    try:
        return int(role) if role is not None else None
    except Exception:
        return None


def _owns(role, client_id):
    return slot_owners.get(role) == client_id


# ============================================================
# 主遊戲迴圈（SERVER_FPS TICK/秒）
# ============================================================

def game_loop():
    """每 TICK：
       1. 玩家物理（重力 → 位置 → 落地）
       2. 外觀排程推進
       3. 障礙物物理（水平移動 + 反彈）
       4. P1 碰撞障礙物 → 遊戲結束
       5. 生成新障礙物
       6. 廣播狀態
    """
    global tick_count
    dt      = 1.0 / SERVER_FPS
    spawn_t = 0
    reset_game()

    while True:
        socketio.sleep(dt)
        tick_count += 1

        if game_state['gameOver']:
            socketio.emit('state', game_state)
            continue

        gt = ground_top()

        # ── 1. 玩家物理 ──────────────────────────────────────
        for role, player in game_state['players'].items():
            if not player['active']:
                continue

            if player['y'] < gt or player['vel'] != 0.0:
                player['vel'] += GRAVITY
                player['y']   += player['vel']

                # P2 upskill 障礙物召喚計時
                if role == 2 and player.get('upskill_spawn_tick', -1) >= 0:
                    player['upskill_spawn_tick'] += 1
                    if player['upskill_spawn_tick'] == P2_UPSKILL_SPAWN_TICK:
                        player['upskill_spawn_tick'] = -1
                        obs_x = player['x'] + PLAYER_WIDTH // 2 - OBSTACLE_WIDTH // 2
                        obs_y = max(0, player['y'] - OBSTACLE_HEIGHT - 5)
                        game_state['obstacles'].append({
                            'x':               obs_x,
                            'y':               obs_y,
                            'scored':          False,
                            'jumping':         True,
                            'vy':              OBS_BOUNCE_VY_START,
                            'bounce_cooldown': 0,
                            'current_bounce_vy': OBS_BOUNCE_VY_START,
                        })
                        print(f"[upskill] obstacle spawned tick={tick_count}")

                # 落地
                if player['y'] >= gt:
                    player['y']   = gt
                    player['vel'] = 0.0
                    was_jumping   = player.get('isJumping', False)
                    player['isJumping'] = False
                    player['canDouble'] = True

                    if role == 2:
                        player['skillLocked'] = False

                        # downskill 落地衝量
                        if player.get('downskill_pending_land') and was_jumping:
                            player['downskill_pending_land'] = False
                            for obs in game_state['obstacles']:
                                if obs.get('y', 0) >= GROUND_Y - 1:
                                    obs['vy']              = P2_DOWNSKILL_LAND_IMPULSE
                                    obs['jumping']         = True
                                    obs['bounce_cooldown'] = 0
                                    if 'current_bounce_vy' not in obs:
                                        obs['current_bounce_vy'] = OBS_BOUNCE_VY_START
                            # 觸發下砸技能的地面外觀動畫（僅外觀，不影響碰撞）
                            game_state.setdefault('ground_animation', {'offset': 0.0, 'vy': 0.0})
                            game_state['ground_animation']['vy'] = GROUND_ANIM_VY_START
                            socketio.emit('skill_event', {'skill': 'downskill', 'event': 'land'})
                            print(f"[downskill] land impulse + ground anim tick={tick_count}")

        # ── 2. 外觀排程推進 ──────────────────────────────────
        for role, player in game_state['players'].items():
            if not player['active']:
                continue
            sched = player.get('sprite_schedule', [])
            if not sched:
                continue
            player['schedule_tick'] += 1
            if player['schedule_tick'] >= sched[0]['ticks']:
                sched.pop(0)
                player['schedule_tick'] = 0
                if sched:
                    new_sprite = sched[0]['sprite']
                    player['sprite'] = new_sprite
                    # 進入 roar 幀 → 通知前端播放音效
                    if role == 2 and new_sprite == P2_SPRITE_ROAR:
                        socketio.emit('skill_event', {'skill': 'upskill', 'event': 'roar'})
                else:
                    # 排程結束，回到預設外觀
                    player['sprite'] = P2_SPRITE_NORMAL if role == 2 else P1_SPRITE

        # ── 3. 障礙物物理 ─────────────────────────────────────
        new_obstacles = []
        for obs in game_state['obstacles']:
            obs['x'] -= OBSTACLE_SPEED

            # 反彈物理
            if obs.get('jumping'):
                if obs.get('bounce_cooldown', 0) > 0:
                    obs['bounce_cooldown'] -= 1
                    if obs['bounce_cooldown'] <= 0:
                        # 冷卻結束，重新施加向上速度
                        obs['vy'] = obs.get('current_bounce_vy', OBS_BOUNCE_VY_START)
                else:
                    obs['vy'] += GRAVITY
                    obs['y']  += obs['vy']
                    if obs['y'] >= GROUND_Y:
                        obs['y']  = GROUND_Y
                        obs['vy'] = 0.0
                        # 衰減下次反彈速度（僅在落地時一次性調整）
                        nv = obs.get('current_bounce_vy', OBS_BOUNCE_VY_START) + OBS_BOUNCE_VY_DECREMENT
                        # 由於速度為負值，使用 min() 以確保不會超過（數值上變大）允許的最小負速度
                        obs['current_bounce_vy'] = min(nv, OBS_BOUNCE_VY_MIN)
                        obs['bounce_cooldown']   = OBS_BOUNCE_COOLDOWN_TICKS

            # ── 4. P1 碰撞 → 遊戲結束 ─────────────────────────
            p1 = game_state['players'].get(1)
            if p1 and p1['active'] and check_collision(p1, obs):
                game_state['gameOver']       = True
                game_state['gameOverReason'] = 'P1 hit obstacle'

            # 計分
            if not obs.get('scored') and obs['x'] + OBSTACLE_WIDTH < (p1['x'] if p1 else 0):
                game_state['score'] += 1
                obs['scored'] = True

            if obs['x'] + OBSTACLE_WIDTH > 0:
                new_obstacles.append(obs)

        game_state['obstacles'] = new_obstacles

        # ── 5. 生成新障礙物 ───────────────────────────────────
        spawn_t += 1
        if spawn_t >= SPAWN_INTERVAL_TICKS:
            spawn_t = 0
            game_state['obstacles'].append({
                'x':               CANVAS_WIDTH,
                'y':               GROUND_Y,
                'scored':          False,
                'jumping':         False,
                'vy':              0.0,
                'bounce_cooldown': 0,
                'current_bounce_vy': OBS_BOUNCE_VY_START,
            })

        # ── 6. 地面（外觀）動畫推進（僅視覺）────────────────────────
        ga = game_state.get('ground_animation')
        if ga:
            # 使用與物理相同的重力感覺拉回地面（這裡僅為外觀）
            if ga.get('vy', 0.0) != 0.0 or ga.get('offset', 0.0) != 0.0:
                ga['vy'] += GRAVITY
                ga['offset'] += ga['vy']
                # 不允許地面往下穿過原位（offset>0 表示往下）
                if ga['offset'] > 0:
                    ga['offset'] = 0.0
                    ga['vy'] = 0.0

        # ── 7. 廣播 ───────────────────────────────────────────
        socketio.emit('state', game_state)


if __name__ == '__main__':
    print(f"遊戲伺服器已啟動：http://localhost:{PORT}")
    socketio.run(app, port=PORT, debug=True, use_reloader=False)

