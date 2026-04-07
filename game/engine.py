# ============================================================
# 主遊戲迴圈（SERVER_FPS TICK/秒）
# ============================================================
from game import state as gs
from game.constants import *
_socketio = None


def init(socketio_instance) -> None:
    """由 app.py 在啟動時注入 socketio 實例。"""
    global _socketio
    _socketio = socketio_instance


def game_loop() -> None:
    """每 TICK：
       1. 玩家物理（重力 → 位置 → 落地）
       2. 外觀排程推進
       3. 障礙物物理（水平移動 + 反彈）
       4. P1 碰撞障礙物 → 遊戲結束
       5. 生成新障礙物
       6. 地面外觀動畫推進
       7. 廣播狀態
    """
    sio     = _socketio
    dt      = 1.0 / SERVER_FPS
    spawn_t = 0
    gs.reset_game()

    while True:
        sio.sleep(dt)
        gs.tick_count += 1

        if gs.game_state['gameOver']:
            sio.emit('state', gs.game_state)
            continue

        gt = gs.ground_top()

        # ── 1. 玩家物理 ─────────────────────────────────────
        for role, player in gs.game_state['players'].items():
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
                        gs.game_state['obstacles'].append({
                            'x':                 obs_x,
                            'y':                 obs_y,
                            'scored':            False,
                            'jumping':           True,
                            'vy':                OBS_BOUNCE_VY_START,
                            'bounce_cooldown':   0,
                            'current_bounce_vy': OBS_BOUNCE_VY_START,
                        })
                        print(f"[upskill] obstacle spawned tick={gs.tick_count}")

                # 落地
                if player['y'] >= gt:
                    player['y']         = gt
                    player['vel']       = 0.0
                    was_jumping         = player.get('isJumping', False)
                    player['isJumping'] = False
                    player['canDouble'] = True

                    if role == 2:
                        player['skillLocked'] = False

                        if player.get('downskill_pending_land') and was_jumping:
                            player['downskill_pending_land'] = False
                            for obs in gs.game_state['obstacles']:
                                if obs.get('y', 0) >= GROUND_Y - 1:
                                    obs['vy']            = P2_DOWNSKILL_LAND_IMPULSE
                                    obs['jumping']       = True
                                    obs['bounce_cooldown'] = 0
                                    obs.setdefault('current_bounce_vy', OBS_BOUNCE_VY_START)
                            gs.game_state['ground_animation']['vy'] = GROUND_ANIM_VY_START
                            sio.emit('skill_event', {'skill': 'downskill', 'event': 'land'})
                            print(f"[downskill] land impulse + ground anim tick={gs.tick_count}")

        # ── 2. 外觀排程推進 ─────────────────────────────────
        for role, player in gs.game_state['players'].items():
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
                    if role == 2 and new_sprite == P2_SPRITE_ROAR:
                        sio.emit('skill_event', {'skill': 'upskill', 'event': 'roar'})
                else:
                    player['sprite'] = P2_SPRITE_NORMAL if role == 2 else P1_SPRITE

        # ── 3 & 4. 障礙物物理 + P1 碰撞 ────────────────────
        new_obstacles = []
        p1 = gs.game_state['players'].get(1)
        for obs in gs.game_state['obstacles']:
            obs['x'] -= OBSTACLE_SPEED

            if obs.get('jumping'):
                if obs.get('bounce_cooldown', 0) > 0:
                    obs['bounce_cooldown'] -= 1
                    if obs['bounce_cooldown'] <= 0:
                        obs['vy'] = obs.get('current_bounce_vy', OBS_BOUNCE_VY_START)
                else:
                    obs['vy'] += GRAVITY
                    obs['y']  += obs['vy']
                    if obs['y'] >= GROUND_Y:
                        obs['y']  = GROUND_Y
                        obs['vy'] = 0.0
                        nv = obs.get('current_bounce_vy', OBS_BOUNCE_VY_START) + OBS_BOUNCE_VY_DECREMENT
                        obs['current_bounce_vy'] = min(nv, OBS_BOUNCE_VY_MIN)
                        obs['bounce_cooldown']   = OBS_BOUNCE_COOLDOWN_TICKS

            if p1 and p1['active'] and gs.check_collision(p1, obs):
                gs.game_state['gameOver']       = True
                gs.game_state['gameOverReason'] = 'P1 hit obstacle'

            if not obs.get('scored') and obs['x'] + OBSTACLE_WIDTH < (p1['x'] if p1 else 0):
                gs.game_state['score'] += 1
                obs['scored'] = True

            if obs['x'] + OBSTACLE_WIDTH > 0:
                new_obstacles.append(obs)

        gs.game_state['obstacles'] = new_obstacles

        # ── 5. 生成新障礙物 ─────────────────────────────────
        spawn_t += 1
        if spawn_t >= SPAWN_INTERVAL_TICKS:
            spawn_t = 0
            gs.game_state['obstacles'].append({
                'x':                 CANVAS_WIDTH,
                'y':                 GROUND_Y,
                'scored':            False,
                'jumping':           False,
                'vy':                0.0,
                'bounce_cooldown':   0,
                'current_bounce_vy': OBS_BOUNCE_VY_START,
            })

        # ── 6. 地面外觀動畫推進 ─────────────────────────────
        ga = gs.game_state.get('ground_animation')
        if ga and (ga.get('vy', 0.0) != 0.0 or ga.get('offset', 0.0) != 0.0):
            ga['vy']     += GRAVITY
            ga['offset'] += ga['vy']
            if ga['offset'] > 0:
                ga['offset'] = 0.0
                ga['vy']     = 0.0

        # ── 7. 廣播 ─────────────────────────────────────────
        sio.emit('state', gs.game_state)
