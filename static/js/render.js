// ============================================================
// Renderer - Sprite 載入 + Canvas 繪製 + 渲染迴圈
// ============================================================
const Renderer = (() => {
    const SPRITE_FILES = [
        'player_1.png',
        'player_2_normal.png',
        'player_2_roar.png',
        'player_2_squat.png',
        'stone.png',
        'fire_1.png',
        'fire_2.png',
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

    // Helper: draw an image flipped horizontally around its center
    function _drawFlippedImage(ctx, img, x, y, w, h) {
        ctx.save();
        ctx.translate(x + w / 2, y + h / 2);
        ctx.scale(-1, 1);
        ctx.drawImage(img, -w / 2, -h / 2, w, h);
        ctx.restore();
    }

    function _drawPlayer(ctx, player, role) {
        const cfg  = GameConfig;
        const name = player.sprite || (Number(role) === 2 ? 'player_2_normal.png' : 'player_1.png');
        const img  = _spriteImg(name);
        // Use role-specific logical and sprite sizes so rendering is dynamic
        const logicalW = cfg.PLAYER_WIDTH[role];
        const logicalH = cfg.PLAYER_HEIGHT[role];
        const spriteW  = cfg.PLAYER_WIDTH[role];
        const spriteH  = cfg.PLAYER_HEIGHT[role];

        // center the sprite horizontally on the logical player box and align bottoms
        const drawX = player.x + (logicalW - spriteW) / 2;
        const drawY = player.y + (logicalH - spriteH);
        // Draw without horizontal flip
        ctx.drawImage(img, drawX, drawY, spriteW, spriteH);
    }

    function _drawObstacle(ctx, obs, gameTime) {
        const cfg = GameConfig;
        let spriteName;
        
        if (obs.is_fireball) {
            // 火球每 30 ticks 轮换一次（在 120 FPS 下，约 0.25 秒；可调为 0.5 秒 = 60 ticks）
            // 使用 gameTime（ms）或 obs 外部提供的 tick 来决定
            const fireFrame = Math.floor((gameTime || Date.now()) / 500) % 2;  // 每 0.5 秒轮换
            spriteName = fireFrame === 0 ? 'fire_1.png' : 'fire_2.png';
        } else {
            spriteName = 'stone.png';
        }
        
        const img = _spriteImg(spriteName);
        const w = obs.w || cfg.OBSTACLE_WIDTH;
        const h = obs.h || cfg.OBSTACLE_HEIGHT;
        // apply fade alpha when server marks obstacle as fading
        let prevAlpha = null;
        if (obs.fading && obs.fade_ticks_total && obs.fade_ticks_remaining !== undefined) {
            const alpha = Math.max(0, obs.fade_ticks_remaining / obs.fade_ticks_total);
            prevAlpha = ctx.globalAlpha;
            ctx.globalAlpha = alpha;
        }
        ctx.drawImage(img, obs.x, obs.y - h, w, h);
        if (prevAlpha !== null) ctx.globalAlpha = prevAlpha;
    }

    function startLoop(canvas, scoreDisplay) {
        const ctx = canvas.getContext('2d');

        function update() {
            const cfg   = GameConfig;
            const state = Network.latestState;
            const gameTime = Date.now();  // 用於火球輪換
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
                        if (player.hidden) continue;
                        _drawPlayer(ctx, player, role);
                        ctx.fillStyle = Number(role) === Network.assigned ? 'yellow' : 'white';
                        ctx.font = '12px Arial';
                        ctx.fillText(player.name || `P${role}`, player.x+cfg.PLAYER_WIDTH[role]/2, player.y - cfg.PLAYER_HEIGHT[role]);
                    }
                }

                // 障礙物
                if (state.obstacles) state.obstacles.forEach(obs => _drawObstacle(ctx, obs, gameTime));

                // 分數
                scoreDisplay.innerText = `Score: ${state.score}`;

                // 遊戲結束 overlay
                if (state.gameOver) {
                    ctx.fillStyle = 'rgba(0,0,0,0)';
                    ctx.fillRect(0, 0, cfg.CANVAS_WIDTH, cfg.CANVAS_HEIGHT);
                    ctx.textAlign = 'center';
                    ctx.fillStyle = 'white';
                    ctx.font = 'bold 48px Arial';
                    ctx.fillText('GAME OVER!', cfg.CANVAS_WIDTH / 2, cfg.CANVAS_HEIGHT / 2 - 40);
                    ctx.font = '24px Arial';
                    ctx.fillText(`SCORE: ${state.score}`, cfg.CANVAS_WIDTH / 2, cfg.CANVAS_HEIGHT / 2 + 20);
                    ctx.font = '18px Arial';
                    ctx.fillText('TAP TO RESTART', cfg.CANVAS_WIDTH / 2, cfg.CANVAS_HEIGHT / 2 + 70);
                    ctx.textAlign = 'left';
                }
            }

            requestAnimationFrame(update);
        }

        requestAnimationFrame(update);
    }

    return { loadSprites, startLoop };
})();
