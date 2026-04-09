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

    function _drawPlayer(ctx, player, role, offsetX, offsetY) {
        const cfg  = GameConfig;
        const name = player.sprite || (Number(role) === 2 ? 'player_2_normal.png' : 'player_1.png');
        const img  = _spriteImg(name);
        const logicalW = cfg.PLAYER_WIDTH[role];
        const logicalH = cfg.PLAYER_HEIGHT[role];
        const spriteW  = cfg.PLAYER_WIDTH[role];
        const spriteH  = cfg.PLAYER_HEIGHT[role];
        const drawX = player.x + (logicalW - spriteW) / 2 + offsetX;
        const drawY = player.y + (logicalH - spriteH) + offsetY;
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
        const _obsSize = cfg.OBSTACLE_SIZES && cfg.OBSTACLE_SIZES[obs.type || 'stone'];
        const w = obs.w || (_obsSize && _obsSize[0]) || 64;
        const h = obs.h || (_obsSize && _obsSize[1]) || 64;
        // apply fade alpha when server marks obstacle as fading
        let prevAlpha = null;
        if (obs.fading && obs.fade_ticks_total && obs.fade_ticks_remaining !== undefined) {
            const alpha = Math.max(0, obs.fade_ticks_remaining / obs.fade_ticks_total);
            prevAlpha = ctx.globalAlpha;
            ctx.globalAlpha = alpha;
        }
        ctx.drawImage(img, obs.x + (obs._offsetX || 0), obs.y - h + (obs._offsetY || 0), w, h);
        if (prevAlpha !== null) ctx.globalAlpha = prevAlpha;
    }

    function startLoop(canvas, scoreDisplay) {
        const ctx = canvas.getContext('2d');

        function update() {
            const cfg   = GameConfig;
            const state = Network.latestState;
            const gameTime = Date.now();
            const cw = canvas.width;
            const ch = canvas.height;
            // 計算偏移：寬螢幕時 offsetX 水平居中，窄螢幕時 offsetY 垂直延伸天空
            const offsetX = Math.max(0, cw - cfg.CANVAS_WIDTH) / 2;
            const offsetY = Math.max(0, ch - cfg.CANVAS_HEIGHT);

            // 全畫布填天空色
            ctx.clearRect(0, 0, cw, ch);
            ctx.fillStyle = '#87ceeb';
            ctx.fillRect(0, 0, cw, ch);

            // 地面：從邊界到邊界（水平和豎直都完整）
            const groundOffset = state?.ground_animation?.offset ?? 0;
            ctx.fillStyle = '#2d5016';
            const groundDrawY = cfg.GROUND_Y + groundOffset + offsetY;
            ctx.fillRect(0, groundDrawY, cw, ch - groundDrawY);

            if (state) {
                // 玩家
                if (state.players) {
                    for (const role in state.players) {
                        const player = state.players[role];
                        if (!player.active) continue;
                        if (player.hidden) continue;
                        _drawPlayer(ctx, player, role, offsetX, offsetY);
                        ctx.font = '12px Arial';
                        if (Number(role) === Network.assigned) {
                            ctx.fillStyle = 'yellow';
                            ctx.textAlign = 'center';
                            ctx.fillText('YOU', player.x + cfg.PLAYER_WIDTH[role] / 2 + offsetX, player.y + offsetY - 10);
                            ctx.textAlign = 'left';
                        }
                    }
                }

                // 障礙物
                if (state.obstacles) state.obstacles.forEach(obs => {
                    obs._offsetX = offsetX;
                    obs._offsetY = offsetY;
                    _drawObstacle(ctx, obs, gameTime);
                });

                // 分數
                scoreDisplay.innerText = `Score: ${state.score}`;

                // 遊戲結束 overlay
                if (state.gameOver) {
                    ctx.fillStyle = 'rgba(0,0,0,0.45)';
                    ctx.fillRect(0, 0, cw, ch);
                    ctx.textAlign = 'center';
                    ctx.fillStyle = 'white';
                    ctx.font = 'bold 48px Arial';
                    ctx.fillText('GAME OVER!', cw / 2, ch / 2 - 40);
                    ctx.font = '24px Arial';
                    ctx.fillText(`SCORE: ${state.score}`, cw / 2, ch / 2 + 20);
                    ctx.font = '18px Arial';
                    ctx.fillText('TAP TO RESTART', cw / 2, ch / 2 + 70);
                    ctx.textAlign = 'left';
                }
            }

            requestAnimationFrame(update);
        }

        requestAnimationFrame(update);
    }

    return { loadSprites, startLoop };
})();
