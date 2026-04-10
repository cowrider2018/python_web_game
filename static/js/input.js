// ============================================================
// Input - 統一 Pointer（觸控 + 滑鼠）與鍵盤輸入
// ============================================================
const Input = (() => {
    let pointerStartX = 0;
    let pointerStartY = 0;
    let moveThreshold = 0;
    let jumpThreshold = 0;

    function init(canvas) {
        const canvasWidth  = canvas.clientWidth || window.innerWidth;
        const canvasHeight = canvas.clientHeight || window.innerHeight;
        moveThreshold = Math.max(1, Math.floor(canvasWidth * 0.1));
        jumpThreshold = Math.max(1, Math.floor(canvasHeight * 0.1));

        // ── Pointer（觸控 + 滑鼠統一）──
        canvas.addEventListener('pointerdown', e => {
            e.preventDefault();
            try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
            pointerStartX = e.clientX;
            pointerStartY = e.clientY;
        }, { passive: false });

        canvas.addEventListener('pointermove', e => {
            if (Network.assigned === 0) return;
            const state = Network.latestState;
            if (!state) return;
            if (state.gameOver || state.dying) return;

            const dx = e.clientX - pointerStartX;
            let dir = 0;
            if (dx > moveThreshold) dir = 1;
            else if (dx < -moveThreshold) dir = -1;
            Network.move(Network.assigned, dir);
        }, { passive: false });

        canvas.addEventListener('pointerup', e => {
            e.preventDefault();
            try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}

            if (Network.assigned === 0) return;
            const state = Network.latestState;
            if (!state) return;
            if (state.gameOver) { Network.reset(); return; }
            if (state.dying) return;

            const dx = e.clientX - pointerStartX;
            const dy = e.clientY - pointerStartY;
            Network.move(Network.assigned, 0);

            const horizontalMoved = Math.abs(dx) > moveThreshold;
            const verticalMoved = Math.abs(dy) > jumpThreshold;

            if (Network.assigned !== 2) {
                if (verticalMoved) {
                    Network.jump(Network.assigned);
                }
                return;
            }

            if (verticalMoved && Math.abs(dy) > Math.abs(dx)) {
                dy < 0 ? Network.swipeUp() : Network.swipeDown();
            } else if (!horizontalMoved && verticalMoved) {
                Network.jump(Network.assigned);
            }
        }, { passive: false });

        // ── 鍵盤 ──
        window.addEventListener('keydown', e => {
            // P1: Space 跳躍
            if (e.code === 'Space' && Network.assigned !== 0 && Network.assigned !== 2) {
                e.preventDefault();
                const state = Network.latestState;
                if (!state) { return; }
                if (state.gameOver) { Network.reset(); return; }
                if (state.dying) return;
                Network.jump(Network.assigned);
            }
        });
    }

    return { init };
})();
