# ============================================================
# Socket.IO 事件 handlers（由 app.py 透過 register() 掛載）
# ============================================================
from flask import request, session
from flask_socketio import emit

from game import state as gs, engine
from game.constants import (
    P1_JUMP_VY, P1_DOUBLE_JUMP_VY,
    P2_UPSKILL_JUMP_VY, P2_DOWNSKILL_JUMP_VY,
    P2_SKILL_SETS,
    PLAYER_H_MAX_VX, PLAYER_JUMP_H_VELOCITY_SCALE,
)


def register(socketio) -> None:
    """將所有 Socket.IO 事件 handler 掛載到 socketio 實例。"""

    @socketio.on('connect')
    def on_connect():
        print(f"[socket] connect: {request.sid}")

    @socketio.on('disconnect')
    def on_disconnect():
        sid  = request.sid
        slot = gs.sid_to_slot.pop(sid, None)
        gs.role_map.pop(sid, None)

        if slot:
            gs.slot_owners[slot] = None
            gs.game_state['gameOver']       = True
            gs.game_state['gameOverReason'] = 'player disconnected'
            print(f"[socket] slot {slot} disconnected - game stopped")

        occupied = sum(1 for v in gs.slot_owners.values() if v is not None)
        socketio.emit('state', gs.game_state)
        socketio.emit('player_count', {'count': occupied})
        print(f"[socket] disconnect: sid={sid} slot={slot}")

    @socketio.on('join')
    def handle_join():
        sid       = request.sid
        client_id = session.get('client_id')
        existing  = next((s for s, o in gs.slot_owners.items() if o == client_id), None)

        if existing:
            assigned = existing
        else:
            empty = next((s for s, o in gs.slot_owners.items() if o is None), None)
            if empty is not None:
                gs.slot_owners[empty] = client_id
                assigned = empty
            else:
                assigned = 0

        gs.role_map[sid] = assigned
        if assigned:
            gs.sid_to_slot[sid] = assigned

        gs.rebuild_players()
        occupied = sum(1 for v in gs.slot_owners.values() if v is not None)
        
        # 遊戲即將開始：清除舊狀態
        if occupied >= 2 and not gs.spawn_task_running:
            gs.reset_game()
        
        emit('assign', {'assigned': assigned, 'count': occupied})
        socketio.emit('state', gs.game_state)
        socketio.emit('player_count', {'count': occupied})

        if not gs.spawn_task_running and occupied > 0:
            gs.spawn_task_running = True
            socketio.start_background_task(target=engine.game_loop)

        print(f"[socket] join: sid={sid} assigned={assigned} occupied={occupied}")

    @socketio.on('leave')
    def handle_leave():
        sid       = request.sid
        client_id = session.get('client_id')
        slot = next((s for s, o in gs.slot_owners.items() if o == client_id), None)
        if slot:
            gs.slot_owners[slot] = None
            for s, sl in list(gs.sid_to_slot.items()):
                if sl == slot:
                    gs.sid_to_slot.pop(s, None)
                    gs.role_map.pop(s, None)
        gs.role_map[sid] = 0
        gs.rebuild_players()
        occupied = sum(1 for v in gs.slot_owners.values() if v is not None)
        emit('assign', {'assigned': 0, 'count': occupied})
        socketio.emit('state', gs.game_state)
        socketio.emit('player_count', {'count': occupied})
        print(f"[socket] leave: sid={sid} slot_cleared={slot}")

    @socketio.on('request_reset')
    def handle_reset():
        gs.reset_game()
        socketio.emit('state', gs.game_state)
        print(f"[socket] reset by sid={request.sid}")

    # ---- P1 輸入 ----

    @socketio.on('jump')
    def handle_jump(data):
        """P1 按下 → 一段跳；空中按下 → 二段跳（最多一次）。"""
        role      = gs._parse_role(data)
        client_id = session.get('client_id')
        if not gs._owns(role, client_id):
            return
        player = gs.game_state['players'].get(role)
        if not player or not player['active'] or gs.game_state['gameOver']:
            return
        # If death animation running, ignore input
        if gs.game_state.get('dying'):
            return

        gt        = gs.ground_top(role)
        # Can jump if on ground OR standing on an obstacle
        on_ground = player['y'] >= gt - 1 or player.get('standing_on') is not None

        try:
            raw_dx = float(data.get('dx', 0))
        except Exception:
            raw_dx = 0.0

        if on_ground:
            jump_h_vel = max(-PLAYER_H_MAX_VX, min(PLAYER_H_MAX_VX, raw_dx * PLAYER_JUMP_H_VELOCITY_SCALE))
            player['vel']       = P1_JUMP_VY
            player['jump_h_vel'] = jump_h_vel
            player['vel_x']     = jump_h_vel
            player['isJumping'] = True
            player['canDouble'] = True
            player['standing_on'] = None  # Clear standing state when jumping
            print(f"[jump] role={role} 一段跳 dx={raw_dx:.1f} h_vel={jump_h_vel:.2f}")
        elif role == 1 and player.get('canDouble', False):
            jump_h_vel = max(-PLAYER_H_MAX_VX, min(PLAYER_H_MAX_VX, raw_dx * PLAYER_JUMP_H_VELOCITY_SCALE))
            player['vel']       = P1_DOUBLE_JUMP_VY
            player['jump_h_vel'] = jump_h_vel
            player['vel_x']     = jump_h_vel
            player['canDouble'] = False
            player['isJumping'] = True
            player['standing_on'] = None
            print(f"[jump] role={role} 二段跳 dx={raw_dx:.1f} h_vel={jump_h_vel:.2f}")

    @socketio.on('move')
    def handle_move(data):
        """Pointer move 事件：動態設定左右移動方向。"""
        role      = gs._parse_role(data)
        client_id = session.get('client_id')
        if not gs._owns(role, client_id):
            return
        player = gs.game_state['players'].get(role)
        if not player or not player['active'] or gs.game_state['gameOver']:
            return
        if gs.game_state.get('dying'):
            return

        try:
            move_dir = int(data.get('dir', 0))
        except Exception:
            return
        if move_dir not in (-1, 0, 1):
            return
        player['move_dir'] = move_dir

    # ---- P2 輸入 ----

    @socketio.on('swipe_up')
    def handle_swipe_up(data):
        """P2 上滑 → upskill：起跳 + 外觀排程 + 召喚反彈障礙物。"""
        client_id = session.get('client_id')
        if not gs._owns(2, client_id):
            return
        player = gs.game_state['players'].get(2)
        if not player or not player['active'] or gs.game_state['gameOver']:
            return
        # Ignore inputs during dying animation
        if gs.game_state.get('dying'):
            return

        gt = gs.ground_top(2)
        # Allow skill if on ground OR standing on obstacle
        on_ground_or_obs = player['y'] >= gt - 1 or player.get('standing_on') is not None
        if not on_ground_or_obs or player.get('skillLocked'):
            return

        player['vel']                = P2_UPSKILL_JUMP_VY
        player['isJumping']          = True
        player['skillLocked']        = True
        player['standing_on'] = None  # Clear standing state when jumping
        player['upskill_spawn_tick'] = 0
        gs.apply_sprite_schedule(player, P2_SKILL_SETS['upskill'])
        print(f"[swipe_up] P2 upskill triggered")

    @socketio.on('swipe_down')
    def handle_swipe_down(data):
        """P2 下滑 → downskill：起跳 + 外觀排程 + 落地衝量。"""
        client_id = session.get('client_id')
        if not gs._owns(2, client_id):
            return
        player = gs.game_state['players'].get(2)
        if not player or not player['active'] or gs.game_state['gameOver']:
            return
        # Ignore inputs during dying animation
        if gs.game_state.get('dying'):
            return

        gt = gs.ground_top(2)
        # Allow skill if on ground OR standing on obstacle
        on_ground_or_obs = player['y'] >= gt - 1 or player.get('standing_on') is not None
        if not on_ground_or_obs or player.get('skillLocked'):
            return

        player['vel']                    = P2_DOWNSKILL_JUMP_VY
        player['isJumping']              = True
        player['skillLocked']            = True
        player['standing_on'] = None  # Clear standing state when jumping
        player['downskill_pending_land'] = True
        gs.apply_sprite_schedule(player, P2_SKILL_SETS['downskill'])
        print(f"[swipe_down] P2 downskill triggered")
