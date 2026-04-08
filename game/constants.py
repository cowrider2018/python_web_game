# ============================================================
# 伺服器常數（集中管理，可在此調整所有數值）
# ============================================================

# ---- 伺服器 ----
PORT       = 8515
SERVER_FPS = 120.0

# ---- 畫布 / 場景 ----
CANVAS_WIDTH  = 800
CANVAS_HEIGHT = 600
GROUND_Y      = CANVAS_HEIGHT - 40   # 地面底邊 Y

# ---- 玩家 (indexed by role: 0=unused, 1=P1, 2=P2) ----
PLAYER_WIDTH  = [0, 64, 128]      # [unused, P1_width, P2_width]
PLAYER_HEIGHT = [0, 64, 128]      # [unused, P1_height, P2_height]
GRAVITY       = 0.6

P1_JUMP_VY        = -15.0   # 一段跳初速（向上為負）
P1_DOUBLE_JUMP_VY = -12.0   # 二段跳初速

P2_UPSKILL_JUMP_VY        = -12.0  # upskill 起跳速度
P2_DOWNSKILL_JUMP_VY      = -15.0  # downskill 起跳速度
P2_UPSKILL_SPAWN_TICK     = 30     # upskill 起跳後第幾 TICK 召喚障礙物
P2_UPSKILL_FIREBALL_VX    = 2.0    # upskill 火球額外水平速度（加到基本障礙速度）
P2_DOWNSKILL_LAND_IMPULSE = -9.0   # downskill 落地時給地面障礙物的向上速度
GROUND_ANIM_VY_START      = -5.0   # 地面外觀初始向上速度

# ---- 障礙物 ----
OBSTACLE_WIDTH        = 64
OBSTACLE_HEIGHT       = 64
OBSTACLE_SPEED        = 5     # 每 TICK 水平移動像素
SPAWN_INTERVAL_TICKS  = 300   # 每隔幾 TICK 生成一個障礙物

# 支援多種障礙物尺寸（type -> (w,h)），可擴充更多種類
OBSTACLE_SIZES = {
    'stone': (OBSTACLE_WIDTH, OBSTACLE_HEIGHT),
    'fire':  (48, 48),
}
OBSTACLE_DEFAULT_TYPE = 'stone'

OBS_BOUNCE_VY_START       = -7.0  # 初始反彈速度（向上）
OBS_BOUNCE_VY_DECREMENT   =  1.0  # 每次反彈速度衰減量
OBS_BOUNCE_VY_MIN         = -3.0  # 反彈速度下限
OBS_BOUNCE_COOLDOWN_TICKS =  1    # 落地後冷卻 TICK 數

# ---- Sprite 名稱 ----
P1_SPRITE        = 'player_1.png'
P2_SPRITE_NORMAL = 'player_2_normal.png'
P2_SPRITE_ROAR   = 'player_2_roar.png'
P2_SPRITE_SQUAT  = 'player_2_squat.png'

# ---- P2 技能外觀排程 ----
P2_SKILL_SETS = {
    'upskill': {
        'sequence': [P2_SPRITE_SQUAT, P2_SPRITE_ROAR, P2_SPRITE_SQUAT],
        'frames':   [15,              20,               15],
    },
    'downskill': {
        'sequence': [P2_SPRITE_SQUAT],
        'frames':   [80],
    },
}
DEFAULT_P2_SKILL = 'upskill'

SLOT_NAMES = {1: 'P1', 2: 'P2'}
