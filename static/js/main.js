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

    // ── 統一 Overlay UI ──
    // 用單一的 overlay 控制加入、滿人、遊戲結束等所有狀態
    function updateOverlay() {
        const assigned = Network.assigned;
        const playerCount = Network.playerCount;
        const gameState = Network.latestState;
        const isGameOver = gameState?.gameOver || false;

        if (isGameOver) {
            // 遊戲結束：顯示重啟提示
            statusText.innerText = 'TAP TO RESTART';
            statusText.style.cursor = 'pointer';
            statusText.style.display = 'block';
        } else if (assigned === 0) {
            // 未加入
            if (playerCount >= 2) {
                statusText.innerText = 'GAME FULL';
                statusText.style.cursor = 'default';
            } else {
                statusText.innerText = 'TAP TO JOIN';
                statusText.style.cursor = 'pointer';
            }
            statusText.style.display = 'block';
        } else {
            // 已加入且遊戲中：隱藏 overlay
            statusText.style.display = 'none';
        }
    }

    // 監聽狀態變化
    Network.on('connect', () => { updateOverlay(); });
    Network.on('assign', () => { updateOverlay(); });
    Network.on('player_count', () => { updateOverlay(); });
    Network.on('skill_event', data => {
        if (data.skill === 'upskill' && data.event === 'roar') playSound(p2SoundRoar);
    });

    // 統一點擊處理：根據狀態判斷是加入還是重啟（全螢幕都可點擊）
    canvas.addEventListener('click', () => {
        const gameState = Network.latestState;
        const isGameOver = gameState?.gameOver || false;

        if (isGameOver) {
            // 重啟遊戲
            Network.reset();
        } else if (Network.assigned === 0 && Network.playerCount < 2) {
            // 加入遊戲
            Network.join();
        }
    });

    // statusText 的點擊也保留（作為備選方案）
    statusText.addEventListener('click', (e) => {
        e.stopPropagation();  // 防止事件冒泡到 canvas
        const gameState = Network.latestState;
        const isGameOver = gameState?.gameOver || false;

        if (isGameOver) {
            Network.reset();
        } else if (Network.assigned === 0 && Network.playerCount < 2) {
            Network.join();
        }
    });

    // 監聽狀態推送以自動更新 overlay（gameOver 狀態變化時)
    function setupStateListener() {
        const originalLatestState = Network.latestState;
        setInterval(() => {
            if (Network.latestState !== originalLatestState) {
                updateOverlay();
            }
        }, 100);
    }

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
        setupStateListener();
        Renderer.startLoop(canvas, scoreDisplay);
        updateOverlay();  // 初始化 overlay 狀態
    }

    Renderer.loadSprites(() => { _spritesOk = true; tryStart(); });
    GameConfig.load(     () => { _configOk  = true; tryStart(); });
    GameConfig.fetch();
})();
