# ============================================================
# 主遊戲迴圈（SERVER_FPS TICK/秒）
# ============================================================
from game import state as gs
from game.constants import *
import math
import random
_socketio = None


def _obs_size(obs):
    """Return (w,h) for an obstacle from its dict or OBSTACLE_SIZES mapping."""
    _default = OBSTACLE_SIZES.get(OBSTACLE_DEFAULT_TYPE, (64, 64))
    if not obs:
        return _default
    if 'w' in obs and 'h' in obs:
        return obs['w'], obs['h']
    t = obs.get('type') if isinstance(obs, dict) else None
    if not t:
        t = OBSTACLE_DEFAULT_TYPE
    return OBSTACLE_SIZES.get(t, _default)


def init(socketio_instance) -> None:
    """由 app.py 在啟動時注入 socketio 實例。"""
    global _socketio
    _socketio = socketio_instance


# ============================================================
# 通用物理
# ============================================================

def _apply_gravity(entity, vel_key='vel'):
    """對任何有 vel/y 的物件施加重力並更新位置（玩家用 vel_key='vel'；障礙物用 vel_key='vy'）。"""
    entity[vel_key] += GRAVITY
    entity['y']     += entity[vel_key]


# ============================================================
# 障礙物物理
# ============================================================

def _obs_move_horizontal(obs):
    """水平移動：火球向右（vx 有符號），石塊向左（vx 為速度大小）。"""
    if obs.get('is_fireball'):
        obs['x'] += obs.get('vx', P2_UPSKILL_FIREBALL_VX)
    else:
        obs['x'] -= obs.get('vx', OBSTACLE_SPEED)


def _fireball_land(obs):
    """火球觸地：停止彈跳，轉為向左以普通障礙速度滾動。"""
    obs['vy']      = 0.0
    obs['jumping'] = False
    obs.pop('current_bounce_vy', None)
    obs.pop('bounce_cooldown', None)
    obs['vx'] = -OBSTACLE_SPEED


def _stone_bounce(obs):
    """石塊觸地：計算下一段反彈初速（遞減），設置等待冷卻。"""
    obs['vy'] = 0.0
    nv = obs.get('current_bounce_vy', OBS_BOUNCE_VY_START) + OBS_BOUNCE_VY_DECREMENT
    obs['current_bounce_vy'] = min(nv, OBS_BOUNCE_VY_MIN)
    obs['bounce_cooldown']   = OBS_BOUNCE_COOLDOWN_TICKS


def _obs_vertical_physics(obs):
    """障礙物垂直物理：冷卻倒數 → _apply_gravity → 觸地分派（_fireball_land / _stone_bounce）。"""
    if not obs.get('jumping'):
        return
    if obs.get('bounce_cooldown', 0) > 0:
        obs['bounce_cooldown'] -= 1
        if obs['bounce_cooldown'] <= 0:
            obs['vy'] = obs.get('current_bounce_vy', P2_UPSKILL_FIREBALL_VY_START)
        return
    _apply_gravity(obs, 'vy')
    if obs['y'] >= GROUND_Y:
        obs['y'] = GROUND_Y
        if obs.get('is_fireball'):
            _fireball_land(obs)
        else:
            _stone_bounce(obs)


def _obs_update_angle(obs):
    """依速度向量更新障礙物朝向角度（用於渲染旋轉）。
    龍類不進行角度旋轉，保留為 0。"""
    if obs.get('is_dragon'):
        obs['angle'] = 0.0
        return
    try:
        obs_vy = obs.get('vy', 0.0)
        obs_vx = obs.get('vx', P2_UPSKILL_FIREBALL_VX) if obs.get('is_fireball') \
                 else -obs.get('vx', OBSTACLE_SPEED)
        obs['angle'] = math.atan2(obs_vy, obs_vx)
    except Exception:
        obs['angle'] = obs.get('angle', 0.0)


def _obs_tick_fading(obs):
    """推進淡出倒數，回傳 True 表示已完全淡出（應從列表中移除）。"""
    if not obs.get('fading'):
        return False
    obs['fade_ticks_remaining'] = max(0, obs.get('fade_ticks_remaining', 0) - 1)
    return obs['fade_ticks_remaining'] <= 0


def _tick_obstacle_sprite_schedule(obs):
    """推進障礙物的 sprite_schedule；支援循環（obs['sprite_schedule_loop']=True）或一次性排程。
    會依序更新 obs['sprite'] 為當前圖檔名稱。"""
    sched = obs.get('sprite_schedule')
    if not sched:
        return
    loop = obs.get('sprite_schedule_loop', False)
    obs['schedule_tick'] = obs.get('schedule_tick', 0) + 1
    # 若尚未達到當前 frame 的停留 ticks，繼續等待
    if obs['schedule_tick'] < sched[0]['ticks']:
        return
    # 到達時間，推進下一張
    obs['schedule_tick'] = 0
    if loop:
        # 旋轉第一張至尾端，並更新當前 sprite
        first = sched.pop(0)
        sched.append(first)
        obs['sprite'] = sched[0]['sprite']
    else:
        # 非循環：消耗第一張，若還有剩下設定下一張，否則清除排程
        sched.pop(0)
        if sched:
            obs['sprite'] = sched[0]['sprite']
        else:
            obs.pop('sprite_schedule', None)
            obs.pop('schedule_tick', None)
            obs.pop('sprite_schedule_loop', None)


# ============================================================
# P2 技能對障礙物的影響
# ============================================================

def _downskill_apply_to_obs(obs):
    """P2 downskill 落地時對單個地面障礙物施加向上衝量。
    - 火球：清狀態、停止水平、觸發淡出
    - 石塊：初始化反彈速度
    """
    obs['vy']              = P2_DOWNSKILL_LAND_IMPULSE
    obs['jumping']         = True
    obs['bounce_cooldown'] = 0
    if obs.get('is_fireball'):
        obs.pop('current_bounce_vy', None)
        obs.pop('bounce_cooldown', None)
        obs['vx'] = 0
        fade_ticks = int(SERVER_FPS * 0.2)
        obs['fading']               = True
        obs['fade_ticks_remaining'] = fade_ticks
        obs['fade_ticks_total']     = fade_ticks
    else:
        obs.setdefault('current_bounce_vy', OBS_BOUNCE_VY_START)


def _downskill_apply_to_player(player):
    """P2 downskill 落地時對地面上的玩家施加向上衝量。"""
    player['vel']       = P2_DOWNSKILL_PLAYER_IMPULSE
    player['isJumping'] = True
    player['canDouble'] = True


def _downskill_land(sio):
    """P2 downskill 落地：推起地面障礙物 + 玩家（P2 自身除外），觸發地面動畫。"""
    for obs in gs.game_state['obstacles']:
        if obs.get('y', 0) >= GROUND_Y - 1:
            _downskill_apply_to_obs(obs)
    gt_p1 = gs.ground_top(1)
    for role, player in gs.game_state['players'].items():
        if role == 2:
            continue   # P2 是施術者，不受影響
        if not player.get('active'):
            continue
        if player['y'] >= gt_p1 - 1 and player.get('vel', 0) == 0.0:
            _downskill_apply_to_player(player)
    gs.game_state['ground_animation']['vy'] = GROUND_ANIM_VY_START
    sio.emit('skill_event', {'skill': 'downskill', 'event': 'land'})
    print(f"[downskill] land impulse + ground anim tick={gs.tick_count}")


# ============================================================
# P2 upskill 火球生成
# ============================================================

def _spawn_upskill_fireball(player, role):
    """P2 upskill 跳躍後計時觸發：在玩家當前位置生成火球。"""
    fw, fh = OBSTACLE_SIZES['fire']
    obs_x  = player['x'] + PLAYER_WIDTH[role] * 4 // 5 - fw // 2
    obs_y  = int(player['y'] + PLAYER_HEIGHT[role] * 4 // 5 + fh // 2)
    obs_y  = max(fh, min(obs_y, CANVAS_HEIGHT))
    obs = {
        'x':                 obs_x,
        'y':                 obs_y,
        'scored':            False,
        'jumping':           True,
        'vy':                P2_UPSKILL_FIREBALL_VY_START,
        'vx':                P2_UPSKILL_FIREBALL_VX,
        'bounce_cooldown':   0,
        'current_bounce_vy': P2_UPSKILL_FIREBALL_VY_START,
        'is_fireball':       True,
        'type':              'fire',
        'w':                 fw,
        'h':                 fh,
        'angle':             math.atan2(0, P2_UPSKILL_FIREBALL_VX),
    }
    gs.game_state['obstacles'].append(obs)
    # 若常數有定義 appearance set，套用並讓其循環
    try:
        ap = OBSTACLE_APPEARANCE_SETS.get('fire')
        if ap:
            gs.apply_sprite_schedule(obs, ap)
            if ap.get('loop'):
                obs['sprite_schedule_loop'] = True
    except Exception:
        pass
    print(f"[upskill] fireball spawned tick={gs.tick_count}")


# ============================================================
# 玩家物理
# ============================================================

def _apply_player_horizontal(role, player):
    """Horizontal movement using acceleration model.

    Behavior:
    - If airborne (jumping and above ground), keep using `jump_h_vel` as horizontal velocity.
    - On ground, applying `move_dir` adds acceleration to `vel_x` each tick.
    - When no input, apply friction to `vel_x`.
    - After updating velocity, apply the movement (final position update).
    """
    gt = gs.ground_top(role)

    # Airborne: stick to jump horizontal velocity (no ground accel)
    if player.get('isJumping', False) and player['y'] < gt:
        player['vel_x'] = player.get('jump_h_vel', player.get('vel_x', 0.0))
    else:
        move_dir = int(player.get('move_dir', 0) or 0)
        # ensure vel_x exists
        vx = player.get('vel_x', 0.0)
        if move_dir != 0:
            # apply acceleration toward direction
            vx += move_dir * PLAYER_H_ACCEL
        else:
            # apply friction when no input
            vx = vx * PLAYER_H_FRICTION
            # snap very small velocities to zero
            if abs(vx) < 0.01:
                vx = 0.0

        # clamp to max horizontal speed
        vx = max(-PLAYER_H_MAX_VX, min(PLAYER_H_MAX_VX, vx))
        player['vel_x'] = vx

    # Final: move by the computed horizontal velocity
    player['x'] += player.get('vel_x', 0.0)

    # Clamp to bounds
    min_x = 0
    max_x = CANVAS_WIDTH - PLAYER_WIDTH[role]
    if player['x'] < min_x:
        player['x'] = min_x
        player['vel_x'] = 0.0
    elif player['x'] > max_x:
        player['x'] = max_x
        player['vel_x'] = 0.0


def _tick_player_physics(role, player, sio):
    """單一玩家每 tick：水平移動 → 重力 → 垂直移動 → 觸地結算 → upskill 火球計時。"""
    gt = gs.ground_top(role)
    # 小優化：若在地上且垂直速度為 0，僅套用水平（地面）移動
    if player['y'] >= gt and player['vel'] == 0.0:
        _apply_player_horizontal(role, player)
        return

    # 記錄前一 tick 是否處於跳躍中
    was_jumping = player.get('isJumping', False)

    # 先套用重力（更新 player['y'] 與 player['vel']）
    _apply_gravity(player)

    # 如果上一 tick 在空中且本 tick 已落地，先清除舊水平慣性，再套用本 tick 的加速度，最後結算移動
    if was_jumping and player['y'] >= gt:
        # 落地：先修正垂直位置與狀態
        player['y'] = gt
        player['vel'] = 0.0
        player['jump_h_vel'] = 0.0
        player['isJumping'] = False
        player['canDouble'] = True

        # 清除空中的舊水平慣性
        player['vel_x'] = 0.0

        # 根據當前輸入計算本 tick 的水平速度（從 0 開始累加加速度），並立即移動
        move_dir = int(player.get('move_dir', 0) or 0)
        vx = player.get('vel_x', 0.0)
        if move_dir != 0:
            vx += move_dir * PLAYER_H_ACCEL
        else:
            vx = vx * PLAYER_H_FRICTION
            if abs(vx) < 0.01:
                vx = 0.0
        vx = max(-PLAYER_H_MAX_VX, min(PLAYER_H_MAX_VX, vx))
        player['vel_x'] = vx
        player['x'] += player['vel_x']

        # 若是 P2，處理落地相關旗標與效果
        if role == 2:
            player['skillLocked'] = False
            if player.get('downskill_pending_land'):
                player['downskill_pending_land'] = False
                _downskill_land(sio)

    else:
        # 正常情況：尚未落地或非從空中落地，使用既有水平物理處理（加速度/摩擦/移動）
        _apply_player_horizontal(role, player)

    # P2 upskill 火球生成計時（在本 tick 推進，無論落地與否）
    if role == 2 and player.get('upskill_spawn_tick', -1) >= 0:
        player['upskill_spawn_tick'] += 1
        if player['upskill_spawn_tick'] == P2_UPSKILL_SPAWN_TICK:
            player['upskill_spawn_tick'] = -1
            _spawn_upskill_fireball(player, role)


# ============================================================
# 玩家外觀排程
# ============================================================

def _tick_sprite_schedule(role, player, sio):
    """推進單一玩家的 sprite animation queue，觸發 roar 音效事件。"""
    sched = player.get('sprite_schedule', [])
    if not sched:
        return
    player['schedule_tick'] += 1
    if player['schedule_tick'] < sched[0]['ticks']:
        return
    sched.pop(0)
    player['schedule_tick'] = 0
    if sched:
        new_sprite = sched[0]['sprite']
        player['sprite'] = new_sprite
        if role == 2 and new_sprite == P2_SPRITE_ROAR:
            sio.emit('skill_event', {'skill': 'upskill', 'event': 'roar'})
    else:
        player['sprite'] = P2_SPRITE_NORMAL if role == 2 else P1_SPRITE


# ============================================================
# P1 與障礙物互動
# ============================================================

def _p1_process_obs_interaction(p1, obs, ow, oh):
    """P1 與單個障礙物的完整互動：頂部落地 → 維持支撐 → 側面碰撞觸發死亡。"""
    obs_top            = obs['y'] - oh
    player_bottom      = p1['y'] + PLAYER_HEIGHT[1]
    prev_player_bottom = player_bottom - p1.get('vel', 0)
    next_player_bottom = player_bottom + p1.get('vel', 0)
    p_left    = p1['x'];   p_right   = p1['x'] + PLAYER_WIDTH[1]
    obs_left  = obs['x'];  obs_right = obs['x'] + ow
    overlap   = min(p_right, obs_right) - max(p_left, obs_left)
    horiz_ok  = overlap > max(2, PLAYER_WIDTH[1] * 0.2)
    vel       = p1.get('vel', 0)
    crossed    = vel > 0 and prev_player_bottom <= obs_top and player_bottom >= obs_top
    will_cross = vel > 0 and player_bottom <= obs_top and next_player_bottom >= obs_top

    if horiz_ok and (crossed or will_cross) and not obs.get('is_fireball', False):
        # ── 頂部落地 ──
        p1['y']           = obs_top - PLAYER_HEIGHT[1]
        p1['vel']         = obs.get('vy', 0)
        p1['isJumping']   = False
        p1['canDouble']   = True
        p1['standing_on'] = obs
        print(f"[land] on obs id={id(obs)} overlap={overlap:.1f} vel={vel:.2f} tick={gs.tick_count}")

    elif p1.get('standing_on') is obs:
        # ── 維持已站立支撐 ──
        p1['y']   = obs_top - PLAYER_HEIGHT[1]
        p1['vel'] = obs.get('vy', 0)
        print(f"[support] on obs id={id(obs)} overlap={overlap:.1f} tick={gs.tick_count}")

    else:
        # ── 側面碰撞 → 依障礙物類型觸發死亡動畫 ──
        if gs.check_collision(p1, obs):
            print(f"[hit] obs id={id(obs)} is_fireball={obs.get('is_fireball', False)} tick={gs.tick_count}")
            if obs.get('is_fireball'):
                _trigger_dying_fireball(p1, obs)
            else:
                _trigger_dying_obstacle(p1, obs)


def _tick_standing_support():
    """確保站在障礙物上的玩家跟隨垂直移動；水平脫離或障礙物消失則清除標記。"""
    for role, player in gs.game_state['players'].items():
        standing = player.get('standing_on')
        if not standing:
            continue
        if standing not in gs.game_state['obstacles']:
            player.pop('standing_on', None)
            continue
        obs = standing
        ow, oh  = _obs_size(obs)
        obs_top = obs['y'] - oh
        player_cx = player['x'] + PLAYER_WIDTH[role] / 2
        obs_cx    = obs['x'] + ow / 2
        if abs(player_cx - obs_cx) > (ow + PLAYER_WIDTH[role]) / 2:
            player.pop('standing_on', None)
            continue
        player['y'] = obs_top - PLAYER_HEIGHT[role]
        if obs.get('vy'):
            player['vel']       = obs['vy']
            player['isJumping'] = True


# ============================================================
# 死亡動畫
# ============================================================

def _get_jump_params(start_pos, target_pos, g, vx):
    """由已知水平速度與重力，反算所需初始垂直速度。返回 (vx, vy) 或 None（無解）。"""
    x1, y1 = start_pos; x2, y2 = target_pos
    dx = x2 - x1; dy = y2 - y1
    if vx == 0 or dx / vx <= 0:
        return None
    t = dx / vx
    return vx, (dy - 0.5 * g * (t ** 2)) / t


def _trigger_dying_obstacle(p1, obs):
    """【障礙物死亡】P1 以拋物線飛向 P2（P2 eat 動畫）。dying_type='obstacle'"""
    gs.game_state['dying']          = True
    gs.game_state['dying_type']     = 'obstacle'
    gs.game_state['gameOverReason'] = 'P1 hit obstacle'
    p1['dying_from_obs']            = obs
    start_x = p1['x'] + PLAYER_WIDTH[1] / 2
    start_y = p1['y'] + PLAYER_HEIGHT[1] / 2
    p2 = gs.game_state['players'].get(2)
    if p2 and p2.get('active'):
        target_x = p2['x'] + PLAYER_WIDTH[2] / 2
        target_y = p2['y'] + PLAYER_HEIGHT[2] / 2
    else:
        target_x = CANVAS_WIDTH / 2
        target_y = gs.ground_top(1)
    raw_vx   = obs.get('vx', 0)
    world_vx = raw_vx if obs.get('is_fireball') else -raw_vx
    params   = _get_jump_params((start_x, start_y), (target_x, target_y), GRAVITY, world_vx)
    if params is None:
        p1['vel'] = -10.0
        p1['vx']  = obs.get('vx', 0) / 5
    else:
        vx_used, vy_used = params
        p1['vx']  = -vx_used  # engine 以 p1['x'] -= p1['vx'] 位移
        p1['vel'] = vy_used
    p1['standing_on'] = None


def _trigger_dying_fireball(p1, obs):
    """【火球死亡】P1 繼承火球水平動能 /5，自由落體出畫面。dying_type='fireball'"""
    gs.game_state['dying']          = True
    gs.game_state['dying_type']     = 'fireball'
    gs.game_state['gameOverReason'] = 'P1 hit fireball'
    p1['dying_from_obs']  = obs
    raw_vx   = obs.get('vx', 0)
    world_vx = raw_vx if obs.get('is_fireball') else -raw_vx
    p1['vx']  = -world_vx / 5
    p1['vel'] = -8.0
    p1['standing_on'] = None


def _handle_dying_obstacle_tick(p1, sio):
    """每 tick【障礙物死亡】：P1 飛向 P2，觸碰後 P2 eat → 定時 gameOver。"""
    p2 = gs.game_state['players'].get(2)
    if p2 and p2.get('active') and not p1.get('hidden'):
        horiz = (p1['x'] + PLAYER_WIDTH[1]  > p2['x']) and (p1['x'] < p2['x'] + PLAYER_WIDTH[2])
        vert  = (p1['y'] + PLAYER_HEIGHT[1] > p2['y']) and (p1['y'] < p2['y'] + PLAYER_HEIGHT[2])
        if horiz and vert:
            gs.apply_sprite_schedule(p2, P2_SKILL_SETS['eat'])
            p1['hidden'] = True
            p1['vel']    = 0.0
            p1['vx']     = 0.0
            gs.game_state['dying_end_tick'] = gs.tick_count + int(SERVER_FPS * 0.5)
    if gs.game_state.get('dying_end_tick') is not None:
        if gs.tick_count >= gs.game_state['dying_end_tick']:
            gs.game_state['gameOver'] = True
    else:
        if p1['y'] > CANVAS_HEIGHT:
            gs.game_state['gameOver'] = True


def _handle_dying_fireball_tick(p1):
    """每 tick【火球死亡】：P1 離開畫面即 gameOver，不與 P2 互動。"""
    if p1['y'] > CANVAS_HEIGHT:
        gs.game_state['gameOver'] = True


def _tick_dying_p1(sio):
    """dying 模式每 tick：_apply_gravity + 水平位移 → 依 dying_type 分派動畫邏輯。"""
    p1 = gs.game_state['players'].get(1)
    if not (p1 and p1['active']):
        return
    _apply_gravity(p1)
    p1['x'] -= p1.get('vx', 0)
    if gs.game_state.get('dying_type', 'obstacle') == 'fireball':
        _handle_dying_fireball_tick(p1)
    else:
        _handle_dying_obstacle_tick(p1, sio)


# ============================================================
# 障礙物生成
# ============================================================

def _spawn_stone_obstacle():
    """生成一個普通石塊障礙物於右側畫面外。"""
    sw, sh = OBSTACLE_SIZES['stone']
    gs.game_state['obstacles'].append({
        'x':                 OBSTACLE_SPAWN_X,
        'y':                 GROUND_Y,
        'scored':            False,
        'jumping':           False,
        'vy':                0.0,
        'vx':                OBSTACLE_SPEED,
        'bounce_cooldown':   0,
        'current_bounce_vy': OBS_BOUNCE_VY_START,
        'is_fireball':       False,
        'type':              'stone',
        'w':                 sw,
        'h':                 sh,
        'angle':             0.0,
    })


def _spawn_dragon_obstacle():
    """生成一個空中龍類障礙物，於右側畫面外生成並以固定水平速度向左飛行，垂直以簡諧運動擺動。
    obs['y'] 表示底邊位置；實際垂直位置在每個 tick 以簡諧函數覆寫（忽略重力）。"""
    t = random.choice(DRAGON_TYPES)
    sw, sh = OBSTACLE_SIZES.get(t, (128, 64))
    center = (DRAGON_Y_MIN + DRAGON_Y_MAX) / 2.0
    amp = max(0.0, (DRAGON_Y_MAX - DRAGON_Y_MIN) / 2.0)
    period_ticks = max(1, int(SERVER_FPS * DRAGON_OSC_PERIOD))
    obs = {
        'x':                 OBSTACLE_SPAWN_X,
        'y':                 center,
        'scored':            False,
        'is_dragon':         True,
        'type':              t,
        'w':                 sw,
        'h':                 sh,
        'vx':                OBSTACLE_SPEED,
        'phase':             random.random() * 2 * math.pi,
        'osc_center':        center,
        'osc_amp':           amp,
        'osc_period_ticks':  period_ticks,
        'angle':             0.0,
    }
    gs.game_state['obstacles'].append(obs)
    # 套用 appearance schedule（若定義）且通常龍要循環動畫
    try:
        ap = OBSTACLE_APPEARANCE_SETS.get('dragon')
        if ap:
            gs.apply_sprite_schedule(obs, ap)
            if ap.get('loop'):
                obs['sprite_schedule_loop'] = True
    except Exception:
        pass
    print(f"[spawn] dragon {t} tick={gs.tick_count}")


# ============================================================
# 地面動畫
# ============================================================

def _tick_ground_animation():
    """地面外觀動畫：_apply_gravity 下拉偏移，回到 0 後靜止。"""
    ga = gs.game_state.get('ground_animation')
    if not ga or (ga.get('vy', 0.0) == 0.0 and ga.get('offset', 0.0) == 0.0):
        return
    ga['vy']     += GRAVITY
    ga['offset'] += ga['vy']
    if ga['offset'] > 0:
        ga['offset'] = 0.0
        ga['vy']     = 0.0


# ============================================================
# 主遊戲迴圈
# ============================================================

def game_loop() -> None:
    """每 TICK 依序執行：
       dying → 玩家物理 → 外觀排程 → 障礙物物理+P1互動 → 站立支撐 → 生成 → 地面動畫 → 廣播
    """
    sio     = _socketio
    dt      = 1.0 / SERVER_FPS
    spawn_t = 0
    gs.reset_game()

    while True:
        sio.sleep(dt)
        gs.tick_count += 1

        # 遊戲結束：暫停一切，僅廣播
        if gs.game_state['gameOver']:
            sio.emit('state', gs.game_state)
            continue

        # ── dying 動畫 ──────────────────────────────────────
        if gs.game_state['dying']:
            _tick_dying_p1(sio)
            # dying 期間障礙物繼續運動，但後面的 P1 互動會被跳過

        # ── 1. 玩家物理 ─────────────────────────────────────
        for role, player in gs.game_state['players'].items():
            if not player['active']:
                continue
            if gs.game_state['dying'] and role == 1:
                continue  # P1 已由 _tick_dying_p1 處理
            _tick_player_physics(role, player, sio)

        # ── 2. 外觀排程推進 ─────────────────────────────────
        for role, player in gs.game_state['players'].items():
            if player['active']:
                _tick_sprite_schedule(role, player, sio)

        # ── 3. 障礙物物理  4. P1 互動 ───────────────────────
        new_obstacles = []
        p1 = gs.game_state['players'].get(1)
        for obs in gs.game_state['obstacles']:
            ow, oh = _obs_size(obs)
            _obs_move_horizontal(obs)
            # 龍類使用簡諧運動覆寫垂直位置，並忽略重力
            if obs.get('is_dragon'):
                period_ticks = obs.get('osc_period_ticks', max(1, int(SERVER_FPS * DRAGON_OSC_PERIOD)))
                phase = obs.get('phase', 0.0)
                amp = obs.get('osc_amp', 0.0)
                center = obs.get('osc_center', obs.get('y', 0.0))
                omega = (2 * math.pi / period_ticks) if period_ticks else 0.0
                y = center + amp * math.sin(omega * gs.tick_count + phase)
                vy = amp * omega * math.cos(omega * gs.tick_count + phase)
                obs['y'] = y
                obs['vy'] = vy
            else:
                _obs_vertical_physics(obs)
            _obs_update_angle(obs)
            # 進行障礙物的 sprite schedule（若有）
            _tick_obstacle_sprite_schedule(obs)

            if not gs.game_state['dying'] and p1 and p1['active']:
                _p1_process_obs_interaction(p1, obs, ow, oh)

            if not gs.game_state['dying'] and not obs.get('scored') \
                    and obs['x'] + ow < (p1['x'] if p1 else 0):
                gs.game_state['score'] += 1
                obs['scored'] = True

            if _obs_tick_fading(obs):
                continue  # 淡出完畢，丟棄

            if obs['x'] + ow > OBSTACLE_DESPAWN_X:
                new_obstacles.append(obs)

        gs.game_state['obstacles'] = new_obstacles

        # ── 5. 維持站立支撐 ─────────────────────────────────
        if not gs.game_state['dying']:
            _tick_standing_support()

        # ── 6. 生成新石塊 ───────────────────────────────────
        spawn_t += 1
        if spawn_t >= SPAWN_INTERVAL_TICKS:
            spawn_t = 0
            # 以機率產生龍或石塊（龍忽略重力，做簡諧擺動）
            if random.random() < DRAGON_SPAWN_CHANCE:
                _spawn_dragon_obstacle()
            else:
                _spawn_stone_obstacle()

        # ── 7. 地面動畫 ─────────────────────────────────────
        _tick_ground_animation()

        # ── 8. 廣播 ─────────────────────────────────────────
        sio.emit('state', gs.game_state)
