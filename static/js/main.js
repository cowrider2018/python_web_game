// ============================================================
// Main - 初始化：串接 GameConfig / Network / Input / Renderer
// ============================================================
(function () {
    const canvas       = document.getElementById('gameCanvas');
    const scoreDisplay = document.getElementById('scoreDisplay');
    const statusText   = document.getElementById('statusText');
    const p2SoundRoar  = document.getElementById('p2SoundRoar');

    // ── 音效 ──
    function playSound(el) {
        try {
            el.currentTime = 0;
            const p = el.play();
            if (p?.catch) p.catch(() => {});
        } catch (_) {}
    }

    // ── UI ──
    function updateStatusText() {
        if (Network.assigned === 0) {
            if (Network.playerCount >= 2) {
                statusText.innerText = 'GAME FULL';
                statusText.style.cursor = 'default';
            } else {
                statusText.innerText = 'TAP TO JOIN';
                statusText.style.cursor = 'pointer';
            }
        } else {
            statusText.style.display = 'none';
        }
    }

    Network.on('connect',      ()   => { updateStatusText(); });
    Network.on('assign',       data => { updateStatusText(); });
    Network.on('player_count', ()   => { updateStatusText(); });
    Network.on('skill_event',  data => { if (data.skill === 'upskill' && data.event === 'roar') playSound(p2SoundRoar); });

    statusText.addEventListener('click', () => {
        if (Network.assigned === 0 && Network.playerCount < 2) {
            Network.join();
        }
    });

    // ── 畫布尺寸：永遠填滿螢幕，但邏輯寬度最小 = CANVAS_WIDTH ──
    //   寬螢幕(橫式)：邏輯高 600，寬依比例延伸
    //   窄螢幕(直式)：邏輯寬 800，高依比例延伸（多出的空間為天空）
    function resizeCanvas() {
        const vw    = window.innerWidth;
        const vh    = window.innerHeight;
        const baseW = GameConfig.CANVAS_WIDTH  || 800;
        const baseH = GameConfig.CANVAS_HEIGHT || 600;
        let logW, logH;
        if (vw / vh >= baseW / baseH) {
            // 寬螢幕：高固定，寬延伸
            logH = baseH;
            logW = Math.round(baseH * vw / vh);
        } else {
            // 窄螢幕：寬鎖定最小值，高往上延伸補滿天空
            logW = baseW;
            logH = Math.round(baseW * vh / vw);
        }
        canvas.width  = logW;
        canvas.height = logH;
    }

    window.addEventListener('resize', resizeCanvas);

    // ── 等待 config + sprites 都準備好再啟動 ──
    let _configOk  = false;
    let _spritesOk = false;

    function tryStart() {
        if (!_configOk || !_spritesOk) return;
        resizeCanvas();
        Input.init(canvas);
        Renderer.startLoop(canvas, scoreDisplay);
    }

    Renderer.loadSprites(() => { _spritesOk = true; tryStart(); });
    GameConfig.load(     () => { _configOk  = true; tryStart(); });
    GameConfig.fetch();
})();
