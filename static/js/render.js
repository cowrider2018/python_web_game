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
        'tree.png',
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

    function _randomFloat(min, max) {
        return min + Math.random() * (max - min);
    }

    // ============================================================
    // 背景樹
    // ============================================================
    const TREE_TINT_MAX = 0.6;  // 最大染色強度（0=無，1=完全背景色）可隨時調整

    let _trees = [];
    let _treeSpawnCountdown = 0;
    let _pointerParticles = [];
    let _pointerParticleStepTimer = 0;

    function _createPointerParticle(hint, t) {
        const dx = hint.currentX - hint.startX;
        const dy = hint.currentY - hint.startY;
        const lineDist = Math.max(Math.hypot(dx, dy), 1);
        const normalX = -(dy / lineDist);
        const normalY = dx / lineDist;
        const normalOffset = (t - 0.5) * lineDist * 0.5;

        _pointerParticles.push({
            x: hint.startX,
            y: hint.startY,
            t,
            speedFactor: 0.3 + t * 0.7,
            alpha: 0.5,
            radius: 6,
            life: 1.5,
            normalOffset,
            normalX,
            normalY,
        });
    }

    function _ensurePointerParticles(hint) {
        if (_pointerParticles.length === 0) {
            for (let i = 0; i < 10; i++) {
                _createPointerParticle(hint, i / 9);
            }
            return;
        }
        while (_pointerParticles.length < 10) {
            _createPointerParticle(hint, Math.random());
        }
        if (_pointerParticles.length > 10) {
            _pointerParticles.length = 10;
        }
    }

    function _stepPointerParticles(hint) {
        const dx = hint.currentX - hint.startX;
        const dy = hint.currentY - hint.startY;
        const lineDist = Math.max(Math.hypot(dx, dy), 1);
        const lineDirX = dx / lineDist;
        const lineDirY = dy / lineDist;
        const normalX = -lineDirY;
        const normalY = lineDirX;

        _pointerParticles = _pointerParticles.filter(p => {
            const desiredX = hint.startX + lineDirX * lineDist * p.t + normalX * p.normalOffset;
            const desiredY = hint.startY + lineDirY * lineDist * p.t + normalY * p.normalOffset;
            p.x = desiredX;
            p.y = desiredY;
            return true;
        });
    }

    function _drawPointerParticles(ctx, baseRgb) {
        ctx.save();
        const rgb = baseRgb || '255,255,255';
        _pointerParticles.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${rgb},${p.alpha})`;
            ctx.fill();
        });
        ctx.restore();
    }

    // 在離屏 canvas 上完成染色，只影響有像素的區域，返回處理完的 canvas
    function _buildTintedTreeCanvas(w, h, tintStrength) {
        const off = document.createElement('canvas');
        off.width  = w;
        off.height = h;
        const offCtx = off.getContext('2d');

        // 步驟1：畫去背原圖
        offCtx.drawImage(_spriteImg('tree.png'), 0, 0, w, h);

        // 步驟2：source-atop 只在有像素的區域蓋上背景色，透明區域不受影響
        if (tintStrength > 0) {
            offCtx.globalCompositeOperation = 'source-atop';
            offCtx.globalAlpha = tintStrength;
            offCtx.fillStyle = '#87ceeb';
            offCtx.fillRect(0, 0, w, h);
        }

        return off;
    }

    function _spawnTree(cfg, cw, groundDrawY) {
        const img   = _spriteImg('tree.png');
        const scale = Math.max(0.1, _randomFloat(cfg.TREE_SCALE_MIN, cfg.TREE_SCALE_MAX));
        const w     = Math.max(1, Math.round((img.naturalWidth  || 64) * scale));
        const h     = Math.max(1, Math.round((img.naturalHeight || 64) * scale));

        // normalized: 0=最小樹, 1=最大樹
        const normalized    = cfg.TREE_SCALE_MAX > cfg.TREE_SCALE_MIN
            ? (scale - cfg.TREE_SCALE_MIN) / (cfg.TREE_SCALE_MAX - cfg.TREE_SCALE_MIN)
            : 0;
        const tintStrength  = (1 - normalized) * TREE_TINT_MAX;

        _trees.push({
            x:          cw + w,
            y:          groundDrawY - h,
            w,
            h,
            speed:      cfg.TREE_SPEED,
            normalized,                     // 0(小) ~ 1(大)，供圖層排序
            canvas:     _buildTintedTreeCanvas(w, h, tintStrength), // 生成時一次性完成染色
        });
    }

    function _drawTree(ctx, tree) {
        // 直接貼已染色完成的去背圖，不需要每幀重複合成
        ctx.drawImage(tree.canvas, tree.x, tree.y, tree.w, tree.h);
    }

    function _nextTreeSpawnInterval(cfg) {
        return Math.max(1, Math.floor(_randomFloat(cfg.TREE_SPAWN_INTERVAL_MIN, cfg.TREE_SPAWN_INTERVAL_MAX)));
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
        
        // 绘制位置（偏移考虑）
        const drawX = obs.x + (obs._offsetX || 0);
        const drawY = obs.y - h + (obs._offsetY || 0);
        const centerX = drawX + w / 2;
        const centerY = drawY + h / 2;
        
        // 火球或障碍物落地时，角度一律设为 Math.PI/2
        let displayAngle = obs.angle !== undefined ? obs.angle : 0;
        if (obs.y >= cfg.GROUND_Y) {
            displayAngle = Math.PI / 2;
        }
        
        // 如果有角度信息，根据运动轨迹旋转绘制（石块随速度方向偏转）
        if (displayAngle !== 0) {
            ctx.save();
            ctx.translate(centerX, centerY);
            ctx.rotate(displayAngle - Math.PI/2);  // 加 90 度使默认朝上改为朝右
            ctx.drawImage(img, -w / 2, -h / 2, w, h);
            ctx.restore();
        } else {
            // 无角度或角度为 0，正常绘制
            ctx.drawImage(img, drawX, drawY, w, h);
        }
        
        if (prevAlpha !== null) ctx.globalAlpha = prevAlpha;
    }

    function _drawPointerHint(ctx, gameTime) {
        if (typeof Input === 'undefined' || !Input.getPointerHint) return;
        const hint = Input.getPointerHint();
        if (!hint) return;

        const dx = hint.currentX - hint.startX;
        const dy = hint.currentY - hint.startY;
        const absDX = Math.abs(dx);
        const absDY = Math.abs(dy);
        const horizontalMoved = absDX > hint.moveThreshold;
        const verticalMoved = absDY > hint.jumpThreshold;
        const isHorizontalDominant = absDX >= absDY;

        let actionLabel = null;
        if (Network.assigned === 2) {
            if (!isHorizontalDominant) {
                actionLabel = dy < 0 ? 'upskill' : 'downskill';
            } else {
                actionLabel = 'walk';
            }
        } else if (Network.assigned === 1) {
            actionLabel = dy < 0 ? 'jump' : 'run';
        }

        // highlight when gesture exceeds any threshold (horizontal OR vertical)
        const highlight = (absDX > hint.moveThreshold) || (absDY > hint.jumpThreshold);
        const baseRgb = highlight ? '255,215,0' : '255,255,255';

        _drawPointerParticles(ctx, baseRgb);

        const pulsePhase = (gameTime % 200) / 200;
        const pulseRadius = Math.round(pulsePhase * 60);
        const pulseAlpha = Math.max(0, 0.3 * (1 - pulsePhase));
        ctx.save();
        ctx.beginPath();
        ctx.arc(hint.startX, hint.startY, pulseRadius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${baseRgb}, ${pulseAlpha})`;
        ctx.fill();

        if (actionLabel) {
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.lineWidth = 4;
            ctx.strokeText(actionLabel, hint.startX, hint.startY);
            ctx.fillStyle = highlight ? '#FFD700' : '#fff';
            ctx.fillText(actionLabel, hint.startX, hint.startY);
        }
        ctx.restore();
    }

    function startLoop(canvas, scoreDisplay) {
        const ctx = canvas.getContext('2d');
        _trees = [];
        _treeSpawnCountdown = _nextTreeSpawnInterval(GameConfig);
        let _lastFrameTime = null;
        const BASE_FRAME_RATE = 120; // 用於將原始 tick 速度轉為時間基準

        function update(now) {
            const cfg   = GameConfig;
            const state = Network.latestState;
            const gameTime = Date.now();
            const cw = canvas.width;
            const ch = canvas.height;
            const deltaMs = _lastFrameTime === null ? 0 : now - _lastFrameTime;
            _lastFrameTime = now;
            const deltaSeconds = Math.min(deltaMs / 1000, 0.1);
            // 計算偏移：寬螢幕時 offsetX 水平居中，窄螢幕時 offsetY 垂直延伸天空
            const offsetX = Math.max(0, cw - cfg.CANVAS_WIDTH) / 2;
            const extraSky = Math.max(0, ch - cfg.CANVAS_HEIGHT);
            const safeUpShift = Math.round(ch * 0.3)
            const offsetY = extraSky - safeUpShift;

            // 全畫布填天空色
            ctx.clearRect(0, 0, cw, ch);
            ctx.fillStyle = '#87ceeb';
            ctx.fillRect(0, 0, cw, ch);

            // 背景樹：依指定頻率、大小與速度出現，僅作背景裝飾
            // 樹木高度要鎖定在靜態地板高度，不會跟隨 downskill 振起的地面偏移
            const treeGroundDrawY = cfg.GROUND_Y + offsetY;
            if (_treeSpawnCountdown <= 0) {
                _spawnTree(cfg, cw, treeGroundDrawY);
                _treeSpawnCountdown = _nextTreeSpawnInterval(cfg);
            } else {
                _treeSpawnCountdown -= deltaSeconds * BASE_FRAME_RATE;
            }
            _trees.sort((a, b) => a.normalized - b.normalized);
            _trees.forEach(tree => {
                tree.x -= tree.speed * deltaSeconds * BASE_FRAME_RATE;
                _drawTree(ctx, tree);
            });
            _trees = _trees.filter(tree => tree.x + tree.w > 0);

            const hint = Input.getPointerHint();
            if (hint) {
                _ensurePointerParticles(hint);
                _pointerParticleStepTimer += deltaSeconds;
                while (_pointerParticleStepTimer >= 0.025) {
                    _pointerParticleStepTimer -= 0.025;
                    _stepPointerParticles(hint);
                }
            } else {
                _pointerParticles = [];
                _pointerParticleStepTimer = 0;
            }

            // 地面：從邊界到邊界（水平和豎直都完整），並置於樹之上
            const groundOffset = state?.ground_animation?.offset ?? 0;
            const groundDrawY = cfg.GROUND_Y + groundOffset + offsetY;
            ctx.fillStyle = '#2d5016';
            ctx.fillRect(0, groundDrawY, cw, ch - groundDrawY);

            _drawPointerHint(ctx, gameTime);

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
            }

            requestAnimationFrame(update);
        }

        requestAnimationFrame(update);
    }

    return { loadSprites, startLoop };
})();
