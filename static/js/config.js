// ============================================================
// GameConfig - 預設值 + 從 /game_config 取得伺服器設定
// ============================================================
const GameConfig = {
    CANVAS_WIDTH:    800,
    CANVAS_HEIGHT:   600,
    GROUND_Y:        560,
    PLAYER_WIDTH:    [0, 64, 128],
    PLAYER_HEIGHT:   [0, 64, 128],
    OBSTACLE_SIZES:  { stone: [64, 64], fire: [64, 64] },
    SERVER_FPS:      120,

    // 背景樹設定：可在此調整出現頻率、大小範圍與水平移動速率
    TREE_SPAWN_INTERVAL_MIN: 5,
    TREE_SPAWN_INTERVAL_MAX: 60,
    TREE_SCALE_MIN:          2.5,
    TREE_SCALE_MAX:          7.0,
    TREE_SPEED:              4,

    _ready:     false,
    _callbacks: [],

    /** 等待 config 準備好後執行 callback（已準備則立即執行）。 */
    load(callback) {
        if (this._ready) { callback(); return; }
        this._callbacks.push(callback);
    },

    _resolve() {
        this._ready = true;
        this._callbacks.forEach(cb => cb());
        this._callbacks = [];
    },

    /** 從伺服器拉取並覆蓋預設值。 */
    fetch() {
        fetch('/game_config')
            .then(r => r.json())
            .then(cfg => {
                this.CANVAS_WIDTH    = cfg.canvas_width    || this.CANVAS_WIDTH;
                this.CANVAS_HEIGHT   = cfg.canvas_height   || this.CANVAS_HEIGHT;
                this.GROUND_Y        = cfg.ground_y        || (this.CANVAS_HEIGHT - 40);
                this.PLAYER_WIDTH    = cfg.player_width    || this.PLAYER_WIDTH;
                this.PLAYER_HEIGHT   = cfg.player_height   || this.PLAYER_HEIGHT;
                if (cfg.obstacle_sizes) this.OBSTACLE_SIZES = cfg.obstacle_sizes;
                this.SERVER_FPS      = cfg.server_fps      || this.SERVER_FPS;
                this.TREE_SPAWN_INTERVAL_MIN = cfg.tree_spawn_interval_min ?? this.TREE_SPAWN_INTERVAL_MIN;
                this.TREE_SPAWN_INTERVAL_MAX = cfg.tree_spawn_interval_max ?? this.TREE_SPAWN_INTERVAL_MAX;
                this.TREE_SCALE_MIN          = cfg.tree_scale_min ?? this.TREE_SCALE_MIN;
                this.TREE_SCALE_MAX          = cfg.tree_scale_max ?? this.TREE_SCALE_MAX;
                this.TREE_SPEED              = cfg.tree_speed ?? this.TREE_SPEED;
                this._resolve();
            })
            .catch(() => this._resolve());
    },
};
