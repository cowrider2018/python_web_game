# ============================================================
# 主遊戲迴圈（SERVER_FPS TICK/秒）
# ============================================================
from game import state as gs
from game.constants import *
import math
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

        # 遊戲已結束，完全暫停所有遊戲邏輯，只廣播狀態
        if gs.game_state['gameOver']:
            sio.emit('state', gs.game_state)
            continue

        # 死亡動畫模式：P1 掉落至 P2 或掉出畫面，障礙物繼續運動
        if gs.game_state['dying']:
            p1 = gs.game_state['players'].get(1)
            if p1 and p1['active']:
                # 應用重力，讓 P1 自由掉落
                p1['vel'] += GRAVITY
                p1['y']   += p1['vel']
                # 繼承水平速度（來自碰撞的障礙物 vx），讓 P1 水平移動
                p1['x']  -= p1.get('vx', 0)

                # 若 P2 在場且 P1 未被隱藏，檢查是否接觸到 P2
                p2 = gs.game_state['players'].get(2)
                if p2 and p2.get('active') and not p1.get('hidden'):
                    # AABB 碰撞檢查（使用各自的寬高）
                    p1_left = p1['x']
                    p1_right = p1['x'] + PLAYER_WIDTH[1]
                    p1_top = p1['y']
                    p1_bottom = p1['y'] + PLAYER_HEIGHT[1]

                    p2_left = p2['x']
                    p2_right = p2['x'] + PLAYER_WIDTH[2]
                    p2_top = p2['y']
                    p2_bottom = p2['y'] + PLAYER_HEIGHT[2]

                    horiz = (p1_right > p2_left) and (p1_left < p2_right)
                    vert = (p1_bottom > p2_top) and (p1_top < p2_bottom)
                    if horiz and vert:
                        # 觸碰到 P2：觸發 P2 的 eat 動畫、隱藏 P1，並在動畫結束後 0.5 秒結束 dying
                        gs.apply_sprite_schedule(p2, P2_SKILL_SETS['eat'])
                        p1['hidden'] = True
                        # 停止 P1 的移動
                        p1['vel'] = 0.0
                        p1['vx'] = 0.0
                        # schedule dying 結束的 tick（0.5 秒後）
                        gs.game_state['dying_end_tick'] = gs.tick_count + int(SERVER_FPS * 0.5)

                # 若已經排定 dying 結束時刻，則以該條件結束；否則維持原本掉出畫面判定
                if gs.game_state.get('dying_end_tick') is not None:
                    if gs.tick_count >= gs.game_state['dying_end_tick']:
                        gs.game_state['gameOver'] = True
                else:
                    if p1['y'] > CANVAS_HEIGHT:
                        gs.game_state['gameOver'] = True
            # 在死亡動畫期間，障礙物仍然移動和彈跳，但跳過P1碰撞檢查
            # 直接進入 obstacle 物理部分，稍後會跳過 P1 碰撞檢查

        # ── 1. 玩家物理 ─────────────────────────────────────
        for role, player in gs.game_state['players'].items():
            if not player['active']:
                continue
            # 死亡動畫期間，P1 已在早期單獨處理，跳過此部分
            if gs.game_state['dying'] and role == 1:
                continue

            gt_role = gs.ground_top(role)

            if player['y'] < gt_role or player['vel'] != 0.0:
                player['vel'] += GRAVITY
                player['y']   += player['vel']

                # P2 upskill 障礙物召喚計時
                if role == 2 and player.get('upskill_spawn_tick', -1) >= 0:
                    player['upskill_spawn_tick'] += 1
                    if player['upskill_spawn_tick'] == P2_UPSKILL_SPAWN_TICK:
                        player['upskill_spawn_tick'] = -1
                        fw, fh = OBSTACLE_SIZES['fire']
                        obs_x = player['x'] + PLAYER_WIDTH[role] * 4 // 5 - fw // 2
                        # Place fireball vertically centered on the player (not far above)
                        obs_y = int(player['y'] + PLAYER_HEIGHT[role] * 4 // 5 + fh // 2)
                        # clamp inside canvas
                        obs_y = max(fh, min(obs_y, CANVAS_HEIGHT))
                        gs.game_state['obstacles'].append({
                            'x':                 obs_x,
                            'y':                 obs_y,
                            'scored':            False,
                            'jumping':           True,
                            'vy':                P2_UPSKILL_FIREBALL_VY_START,
                            # 火球改為面向右側，並使用獨立初速，不再受一般障礙速度影響
                            'vx':                P2_UPSKILL_FIREBALL_VX,
                            'bounce_cooldown':   0,
                            'current_bounce_vy': P2_UPSKILL_FIREBALL_VY_START,
                            'is_fireball':       True,  # 標記為火球（不可踩）
                            'type':              'fire',
                            'w':                 fw,
                            'h':                 fh,
                            'angle':             math.atan2(0, P2_UPSKILL_FIREBALL_VX),
                        })
                        print(f"[upskill] fireball spawned tick={gs.tick_count}")

                # 落地
                if player['y'] >= gt_role:
                    player['y']         = gt_role
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
                                    # Give upward impulse to obstacles on ground
                                    obs['vy']            = P2_DOWNSKILL_LAND_IMPULSE
                                    obs['jumping']       = True
                                    obs['bounce_cooldown'] = 0
                                    # Special behavior for fireballs: stop horizontal motion and start fading
                                    if obs.get('is_fireball'):
                                        # clear bounce state
                                        obs.pop('current_bounce_vy', None)
                                        obs.pop('bounce_cooldown', None)
                                        # stop horizontal movement
                                        obs['vx'] = 0
                                        # start fade timer (0.2s)
                                        fade_ticks = int(SERVER_FPS * 0.2)
                                        obs['fading'] = True
                                        obs['fade_ticks_remaining'] = fade_ticks
                                        obs['fade_ticks_total'] = fade_ticks
                                    else:
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

        # ── 3 & 4. 障礙物物理 + P1 碰撞 / 站在障礙物上 ────────────────
        new_obstacles = []
        p1 = gs.game_state['players'].get(1)
        for obs in gs.game_state['obstacles']:
            ow, oh = _obs_size(obs)
            # 使用障礙物自身的 vx（如有），否則用預設速度；火球(vx=OBSTACLE_SPEED+P2_UPSKILL_FIREBALL_VX)
            # 移動：一般障礙向左移動（x 減少），火球向右移動（x 增加）且使用自己的初速
            if obs.get('is_fireball'):
                obs['x'] += obs.get('vx', P2_UPSKILL_FIREBALL_VX)
            else:
                obs['x'] -= obs.get('vx', OBSTACLE_SPEED)
            if obs.get('jumping'):
                if obs.get('bounce_cooldown', 0) > 0:
                    obs['bounce_cooldown'] -= 1
                    if obs['bounce_cooldown'] <= 0:
                        obs['vy'] = obs.get('current_bounce_vy', P2_UPSKILL_FIREBALL_VY_START)
                else:
                    obs['vy'] += GRAVITY
                    obs['y']  += obs['vy']
                    if obs['y'] >= GROUND_Y:
                        obs['y']  = GROUND_Y
                        # Fireballs do not bounce: stop vertical movement and remain rolling/flying horizontally
                        if obs.get('is_fireball'):
                            obs['vy'] = 0.0
                            obs['jumping'] = False
                            # ensure bounce-related state is cleared
                            obs.pop('current_bounce_vy', None)
                            obs.pop('bounce_cooldown', None)
                            # on landing, inherit obstacle horizontal motion: move left like regular obstacles
                            obs['vx'] = -OBSTACLE_SPEED
                        else:
                            obs['vy'] = 0.0
                            nv = obs.get('current_bounce_vy', OBS_BOUNCE_VY_START) + OBS_BOUNCE_VY_DECREMENT
                            obs['current_bounce_vy'] = min(nv, OBS_BOUNCE_VY_MIN)
                            obs['bounce_cooldown']   = OBS_BOUNCE_COOLDOWN_TICKS

            # 更新障礙物朝向：依其速度向量決定角度（使火球朝運動方向偏轉）
            try:
                # 注意：普通石塊的 vx 存儲的是速度大小，實際移動時 x -= vx（向左）
                # 火球的 vx 是有符號速度：x += vx（可向左或向右）
                obs_vy = obs.get('vy', 0.0)
                if obs.get('is_fireball'):
                    # 火球直接使用 vx（已是有符號速度）
                    obs_vx = obs.get('vx', P2_UPSKILL_FIREBALL_VX)
                else:
                    # 普通石塊：vx 是速度大小，實際移動是向左，所以取負
                    obs_vx = -obs.get('vx', OBSTACLE_SPEED)
                obs['angle'] = math.atan2(obs_vy, obs_vx)
            except Exception:
                obs['angle'] = obs.get('angle', 0.0)

            # ---- P1 landing on top of obstacle (可以站在障礙物上) ---- (死亡動畫期間跳過碰撞檢查)
            if not gs.game_state['dying'] and p1 and p1['active']:
                obs_top = obs['y'] - oh
                player_bottom = p1['y'] + PLAYER_HEIGHT[1]
                # previous tick bottom (before this tick's movement)
                prev_player_bottom = player_bottom - p1.get('vel', 0)
                # predicted next tick bottom (if needed)
                next_player_bottom = player_bottom + p1.get('vel', 0)
                # 更穩健的水平重疊判定：計算水平重疊寬度
                p_left = p1['x']
                p_right = p1['x'] + PLAYER_WIDTH[1]
                obs_left = obs['x']
                obs_right = obs['x'] + ow
                overlap = min(p_right, obs_right) - max(p_left, obs_left)
                # 只要有少量重疊即可視為水平對齊（容許緩衝）
                horiz_ok = overlap > max(2, PLAYER_WIDTH[1] * 0.2)
                # landing condition:
                # - falling (vel>0) and horizontal aligned, and
                # - either we crossed the top this tick (prev_bottom <= obs_top <= player_bottom)
                # - or we are above and would intersect next tick (player_bottom <= obs_top < next_player_bottom)
                vel = p1.get('vel', 0)
                crossed_this_tick = (vel > 0 and prev_player_bottom <= obs_top and player_bottom >= obs_top)
                will_cross_next = (vel > 0 and player_bottom <= obs_top and next_player_bottom >= obs_top)
                # 火球(is_fireball=True)不可踩踏，只有普通障礙物可以
                if horiz_ok and (crossed_this_tick or will_cross_next) and not obs.get('is_fireball', False):
                    # place player on top of obstacle and sync vertical velocity
                    p1['y'] = obs_top - PLAYER_HEIGHT[1]
                    # if obstacle is moving vertically, let player inherit its vy (可一起彈跳)
                    p1['vel'] = obs.get('vy', 0)
                    p1['isJumping'] = False
                    p1['canDouble'] = True
                    p1['standing_on'] = obs
                    print(f"[land] P1 landed on obs id={id(obs)} at tick={gs.tick_count} overlap={overlap:.1f} prev_bottom={prev_player_bottom:.1f} player_bottom={player_bottom:.1f} obs_top={obs_top:.1f} vel={vel:.2f}")
                else:
                    # If player is already standing on this obstacle, maintain support instead of treating as side collision
                    if p1.get('standing_on') is obs:
                        # refresh player's top alignment
                        p1['y'] = obs_top - PLAYER_HEIGHT[1]
                        p1['vel'] = obs.get('vy', 0)
                        # still considered standing
                        # small overlap may occur; do not treat as collision
                        # debug print for visibility
                        print(f"[support] P1 remains on obs id={id(obs)} overlap={overlap:.1f} tick={gs.tick_count}")
                    else:
                        # side / non-top collision -> death animation
                        if gs.check_collision(p1, obs):
                            print(f"[hit] P1 collision with obs id={id(obs)} overlap={overlap:.1f} p_bottom={player_bottom:.1f} obs_top={obs_top:.1f}")
                            # 進入死亡動畫模式：計算初速度使 P1 飛到 P2 身上
                            gs.game_state['dying']  = True
                            gs.game_state['gameOverReason'] = 'P1 hit obstacle'
                            p1['dying_from_obs']    = obs  # 保存碰撞物體以供動畫期間使用

                            # 參考公式：由已知水平速度與重力，反算所需初始垂直速度
                            def _get_jump_params(start_pos, target_pos, g, vx):
                                x1, y1 = start_pos
                                x2, y2 = target_pos
                                dx = x2 - x1
                                dy = y2 - y1
                                # 避免除以零
                                if vx == 0:
                                    return None
                                t = dx / vx
                                # 若飛行時間非正，則無法用此 vx 到達
                                if t <= 0:
                                    return None
                                vy = (dy - 0.5 * g * (t**2)) / t
                                return vx, vy

                            # 起點、終點採中心點
                            start_x = p1['x'] + PLAYER_WIDTH[1] / 2
                            start_y = p1['y'] + PLAYER_HEIGHT[1] / 2
                            p2 = gs.game_state['players'].get(2)
                            if p2 and p2.get('active'):
                                target_x = p2['x'] + PLAYER_WIDTH[2] / 2
                                target_y = p2['y'] + PLAYER_HEIGHT[2] / 2
                            else:
                                # 若 P2 不存在，則以畫面中間為目標
                                target_x = CANVAS_WIDTH / 2
                                target_y = gs.ground_top(1)  # 站在地上

                            raw_vx = obs.get('vx', 0)
                            # 轉換為世界座標的 vx（右為正）
                            if obs.get('is_fireball'):
                                world_vx = raw_vx
                            else:
                                world_vx = -raw_vx

                            params = _get_jump_params((start_x, start_y), (target_x, target_y), GRAVITY, world_vx)
                            if params is None:
                                # fallback: 使用預設行為（向上丟出）以避免數學錯誤
                                p1['vel'] = -10.0
                                p1['vx']  = obs.get('vx', 0) / 5
                            else:
                                vx_used, vy_used = params
                                # engine 的死亡移動使用 p1['x'] -= p1['vx']，因此存入的 vx 需取負
                                p1['vx']  = -vx_used
                                p1['vel'] = vy_used

                            p1['standing_on']      = None  # 解除登陸限制

            if not gs.game_state['dying'] and not obs.get('scored') and obs['x'] + ow < (p1['x'] if p1 else 0):
                gs.game_state['score'] += 1
                obs['scored'] = True

            # handle fading countdown for obstacles (server-side authoritative)
            if obs.get('fading'):
                obs['fade_ticks_remaining'] = max(0, obs.get('fade_ticks_remaining', 0) - 1)
                if obs['fade_ticks_remaining'] <= 0:
                    # fully faded -> remove
                    continue

            if obs['x'] + ow > 0:
                new_obstacles.append(obs)

        gs.game_state['obstacles'] = new_obstacles

        # 確保站在障礙物上的玩家跟隨障礙物的垂直運動或失去支撐時掉落（死亡動畫期間跳過）
        if not gs.game_state['dying']:
            for role, player in gs.game_state['players'].items():
                standing = player.get('standing_on')
                if not standing:
                    continue
                # if the obstacle was removed or moved away, clear standing flag
                if standing not in gs.game_state['obstacles']:
                    player.pop('standing_on', None)
                    continue
                # check horizontal still overlaps
                obs = standing
                ow, oh = _obs_size(obs)
                obs_top = obs['y'] - oh
                player_center_x = player['x'] + PLAYER_WIDTH[role] / 2
                obs_center_x = obs['x'] + ow / 2
                horiz_ok = abs(player_center_x - obs_center_x) <= (ow + PLAYER_WIDTH[role]) / 2
                if not horiz_ok:
                    # no longer supported
                    player.pop('standing_on', None)
                    continue
                # follow obstacle's vertical position
                player['y'] = obs_top - PLAYER_HEIGHT[role]
                # if obstacle has an upward impulse (vy), transfer it to player so they bounce together
                if obs.get('vy'):
                    player['vel'] = obs['vy']
                    player['isJumping'] = True

        # ── 5. 生成新障礙物 ─────────────────────────────────
        spawn_t += 1
        if spawn_t >= SPAWN_INTERVAL_TICKS:
            spawn_t = 0
            sw, sh = OBSTACLE_SIZES['stone']
            gs.game_state['obstacles'].append({
                'x':                 OBSTACLE_SPAWN_X,
                'y':                 GROUND_Y,
                'scored':            False,
                'jumping':           False,
                'vy':                0.0,
                'vx':                OBSTACLE_SPEED,  # 普通障礙物的水平速度
                'bounce_cooldown':   0,
                'current_bounce_vy': OBS_BOUNCE_VY_START,
                'is_fireball':       False,  # 普通障礙物，可踩踏
                'type':              'stone',
                'w':                 sw,
                'h':                 sh,
                'angle':             0.0,  # 初始水平，每 tick 根據速度向量更新
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
