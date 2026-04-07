# ============================================================
# 遊戲狀態 + 連線管理 + 純函式輔助
# ============================================================
from game.constants import (
    GROUND_Y, PLAYER_HEIGHT, PLAYER_WIDTH, CANVAS_WIDTH,
    P1_SPRITE, P2_SPRITE_NORMAL, SLOT_NAMES,
    OBSTACLE_HEIGHT, OBSTACLE_WIDTH,
)

# ---- 連線 / 槽位管理 ----
slot_owners:        dict = {1: None, 2: None}   # slot -> client_id
sid_to_slot:        dict = {}                   # sid  -> slot
role_map:           dict = {}                   # sid  -> slot (0=觀眾)
spawn_task_running: bool = False

# ---- 遊戲狀態 ----
game_state: dict = {
    'players':          {},
    'obstacles':        [],
    'score':            0,
    'gameOver':         False,
    'gameOverReason':   '',
    'ground_animation': {'offset': 0.0, 'vy': 0.0},
}
tick_count: int = 0


# ---- 輔助函式 ----

def ground_top() -> float:
    return GROUND_Y - PLAYER_HEIGHT


def rebuild_players() -> None:
    """根據 slot_owners 重建 players dict。"""
    new_players = {}
    for slot in (1, 2):
        owner  = slot_owners.get(slot)
        active = owner is not None
        x = 50 if slot == 1 else (CANVAS_WIDTH - 50 - PLAYER_WIDTH)
        new_players[slot] = {
            'x':                     x,
            'y':                     ground_top(),
            'vel':                   0.0,
            'active':                active,
            'name':                  SLOT_NAMES.get(slot, f'P{slot}'),
            'sprite':                P2_SPRITE_NORMAL if slot == 2 else P1_SPRITE,
            'isJumping':             False,
            'canDouble':             True,
            'skillLocked':           False,
            'sprite_schedule':       [],
            'schedule_tick':         0,
            'upskill_spawn_tick':    -1,
            'downskill_pending_land': False,
        }
    game_state['players'] = new_players


def apply_sprite_schedule(player: dict, schedule: dict) -> None:
    """將技能外觀排程套用到玩家（覆蓋先前排程）。"""
    player['sprite_schedule'] = [
        {'sprite': s, 'ticks': t}
        for s, t in zip(schedule['sequence'], schedule['frames'])
    ]
    player['schedule_tick'] = 0
    if player['sprite_schedule']:
        player['sprite'] = player['sprite_schedule'][0]['sprite']


def check_collision(player: dict, obs: dict) -> bool:
    """AABB 碰撞：player.y 為左上角，obs.y 為底邊。"""
    obs_top = obs['y'] - OBSTACLE_HEIGHT
    return (
        player['x'] + PLAYER_WIDTH  > obs['x'] and
        player['x']                 < obs['x'] + OBSTACLE_WIDTH and
        player['y'] + PLAYER_HEIGHT > obs_top and
        player['y']                 < obs['y']
    )


def reset_game() -> None:
    rebuild_players()
    game_state['obstacles']         = []
    game_state['score']             = 0
    game_state['gameOver']          = False
    game_state['gameOverReason']    = ''
    game_state['ground_animation']  = {'offset': 0.0, 'vy': 0.0}


def _parse_role(data) -> int | None:
    role = data.get('role') if isinstance(data, dict) else None
    try:
        return int(role) if role is not None else None
    except Exception:
        return None


def _owns(role: int, client_id: str) -> bool:
    return slot_owners.get(role) == client_id
