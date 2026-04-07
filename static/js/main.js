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

    // ── 等待 config + sprites 都準備好再啟動 ──
    let _configOk  = false;
    let _spritesOk = false;

    function tryStart() {
        if (!_configOk || !_spritesOk) return;
        canvas.width  = GameConfig.CANVAS_WIDTH;
        canvas.height = GameConfig.CANVAS_HEIGHT;
        Input.init(canvas);
        Renderer.startLoop(canvas, scoreDisplay);
    }

    Renderer.loadSprites(() => { _spritesOk = true; tryStart(); });
    GameConfig.load(     () => { _configOk  = true; tryStart(); });
    GameConfig.fetch();
})();
