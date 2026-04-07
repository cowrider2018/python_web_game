// ============================================================
// Input - 統一 Pointer（觸控 + 滑鼠）與鍵盤輸入
// ============================================================
const Input = (() => {
    const SWIPE_THRESHOLD = 30;
    let pointerStartX = 0;
    let pointerStartY = 0;

    function init(canvas) {
        // ── Pointer（觸控 + 滑鼠統一）──
        canvas.addEventListener('pointerdown', e => {
            e.preventDefault();
            try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
            pointerStartX = e.clientX;
            pointerStartY = e.clientY;

            // P1（非 P2）：按下即跳
            if (Network.assigned !== 0 && Network.assigned !== 2) {
                const state = Network.latestState;
                if (!state || state.gameOver) { Network.reset(); return; }
                Network.jump(Network.assigned);
            }
        }, { passive: false });

        canvas.addEventListener('pointerup', e => {
            e.preventDefault();
            try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}

            // P2：鬆開時判斷上 / 下滑
            if (Network.assigned !== 2) return;
            const state = Network.latestState;
            if (!state || state.gameOver) { Network.reset(); return; }
            const dx = e.clientX - pointerStartX;
            const dy = e.clientY - pointerStartY;
            if (Math.abs(dy) > SWIPE_THRESHOLD && Math.abs(dy) > Math.abs(dx)) {
                dy < 0 ? Network.swipeUp() : Network.swipeDown();
            }
        }, { passive: false });

        // ── 鍵盤 ──
        window.addEventListener('keydown', e => {
            // P1: Space 跳躍
            if (e.code === 'Space' && Network.assigned !== 0 && Network.assigned !== 2) {
                e.preventDefault();
                const state = Network.latestState;
                if (!state || state.gameOver) { Network.reset(); return; }
                Network.jump(Network.assigned);
            }
        });
    }

    return { init };
})();
