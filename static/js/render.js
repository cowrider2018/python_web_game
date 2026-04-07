// ============================================================
// Renderer - Sprite 載入 + Canvas 繪製 + 渲染迴圈
// ============================================================
const Renderer = (() => {
    const SPRITE_FILES = [
        'player_1.png',
        'player_2_normal.png',
        'player_2_roar.png',
        'player_2_squat.png',
    ];
    const SPRITE_MAP = {};
    let _loadedCount = 0;
    let _onSpritesReady = null;

    function _checkSpritesReady() {
        if (_loadedCount >= SPRITE_FILES.length && _onSpritesReady) {
            _onSpritesReady();
            _onSpritesReady = null;
        }
    }

    function loadSprites(onReady) {
        _onSpritesReady = onReady;
        SPRITE_FILES.forEach(name => {
            const img = new Image();
            img.src = `/static/img/${name}`;
            img.onload = () => { _loadedCount++; _checkSpritesReady(); };
            if (img.complete) _loadedCount++;
            SPRITE_MAP[name] = img;
        });
        _checkSpritesReady();
    }

    function _spriteImg(name) {
        return SPRITE_MAP[name] || SPRITE_MAP['player_1.png'];
    }

    function _drawPlayer(ctx, player, role) {
        const cfg  = GameConfig;
        const name = player.sprite || (Number(role) === 2 ? 'player_2_normal.png' : 'player_1.png');
        const img  = _spriteImg(name);
        const s    = cfg.PLAYER_WIDTH;

        if (Number(role) === 2) {
            const s2 = s * 3;
            ctx.drawImage(img, player.x + (s - s2) / 2, player.y + (s - s2), s2, s2);
        } else {
            ctx.save();
            ctx.translate(player.x + s / 2, player.y + s / 2);
            ctx.scale(-1, 1);
            ctx.drawImage(img, -s / 2, -s / 2, s, s);
            ctx.restore();
        }
    }

    function _drawObstacle(ctx, obs) {
        const cfg = GameConfig;
        ctx.fillStyle = '#8b4513';
        ctx.fillRect(obs.x, obs.y - cfg.OBSTACLE_HEIGHT, cfg.OBSTACLE_WIDTH, cfg.OBSTACLE_HEIGHT);
    }

    function startLoop(canvas, scoreDisplay) {
        const ctx = canvas.getContext('2d');

        function update() {
            const cfg   = GameConfig;
            const state = Network.latestState;
            ctx.clearRect(0, 0, cfg.CANVAS_WIDTH, cfg.CANVAS_HEIGHT);

            // 地面
            const groundOffset = state?.ground_animation?.offset ?? 0;
            ctx.fillStyle = '#2d5016';
            ctx.fillRect(0, cfg.GROUND_Y + groundOffset, cfg.CANVAS_WIDTH, 40);

            if (state) {
                // 玩家
                if (state.players) {
                    for (const role in state.players) {
                        const player = state.players[role];
                        if (!player.active) continue;
                        _drawPlayer(ctx, player, role);
                        ctx.fillStyle = Number(role) === Network.assigned ? 'yellow' : 'white';
                        ctx.font = '12px Arial';
                        ctx.fillText(player.name || `P${role}`, player.x + 5, player.y - 10);
                    }
                }

                // 障礙物
                if (state.obstacles) state.obstacles.forEach(obs => _drawObstacle(ctx, obs));

                // 分數
                scoreDisplay.innerText = `Score: ${state.score}`;

                // 遊戲結束 overlay
                if (state.gameOver) {
                    ctx.fillStyle = 'rgba(0,0,0,0.6)';
                    ctx.fillRect(0, 0, cfg.CANVAS_WIDTH, cfg.CANVAS_HEIGHT);
                    ctx.textAlign = 'center';
                    ctx.fillStyle = 'white';
                    ctx.font = 'bold 48px Arial';
                    ctx.fillText('遊戲結束!', cfg.CANVAS_WIDTH / 2, cfg.CANVAS_HEIGHT / 2 - 40);
                    ctx.font = '24px Arial';
                    ctx.fillText(`最終分數: ${state.score}`, cfg.CANVAS_WIDTH / 2, cfg.CANVAS_HEIGHT / 2 + 20);
                    ctx.font = '18px Arial';
                    ctx.fillText('點擊重新開始', cfg.CANVAS_WIDTH / 2, cfg.CANVAS_HEIGHT / 2 + 70);
                    ctx.textAlign = 'left';
                }
            }

            requestAnimationFrame(update);
        }

        requestAnimationFrame(update);
    }

    return { loadSprites, startLoop };
})();
