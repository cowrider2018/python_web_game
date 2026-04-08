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
                this._resolve();
            })
            .catch(() => this._resolve());
    },
};
