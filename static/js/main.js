// ============================================================
// Main - 初始化：串接 GameConfig / Network / Input / Renderer
// ============================================================
(function () {
    const canvas       = document.getElementById('gameCanvas');
    const scoreDisplay = document.getElementById('scoreDisplay');
    const statusText   = document.getElementById('statusText');
    const joinBtn      = document.getElementById('joinBtn');
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
    function updateJoinBtn() {
        if (Network.assigned !== 0) {
            joinBtn.disabled  = false;
            joinBtn.innerText = '退出遊戲';
        } else if (Network.playerCount >= 2) {
            joinBtn.disabled  = true;
            joinBtn.innerText = '已滿';
        } else {
            joinBtn.disabled  = false;
            joinBtn.innerText = '加入遊戲';
        }
    }

    Network.on('connect',      ()   => { statusText.innerText = '連線已建立，請按「加入遊戲」'; });
    Network.on('assign',       data => { statusText.innerText = data.assigned ? `玩家 ${data.assigned}` : '觀眾身份'; updateJoinBtn(); });
    Network.on('player_count', ()   => updateJoinBtn());
    Network.on('skill_event',  data => { if (data.skill === 'upskill' && data.event === 'roar') playSound(p2SoundRoar); });

    joinBtn.addEventListener('click', () => {
        Network.assigned === 0 ? Network.join() : Network.leave();
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
