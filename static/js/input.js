// ============================================================
// Input - 統一 Pointer（觸控 + 滑鼠）與鍵盤輸入
// ============================================================
const Input = (() => {
    let pointerStartX = 0;
    let pointerStartY = 0;
    let pointerCurrentX = 0;
    let pointerCurrentY = 0;
    let pointerActive = false;
    let moveThreshold = 0;
    let jumpThreshold = 0;

    function init(canvas) {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        moveThreshold = Math.max(1, Math.floor(canvas.width * 0.1));
        jumpThreshold = Math.max(1, Math.floor(canvas.height * 0.1));

        // ── Pointer（觸控 + 滑鼠統一）──
        canvas.addEventListener('pointerdown', e => {
            e.preventDefault();
            try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            pointerStartX = (e.clientX - rect.left) * scaleX;
            pointerStartY = (e.clientY - rect.top) * scaleY;
            pointerCurrentX = pointerStartX;
            pointerCurrentY = pointerStartY;
            pointerActive = true;
        }, { passive: false });

        canvas.addEventListener('pointermove', e => {
            if (!pointerActive) return;
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            pointerCurrentX = (e.clientX - rect.left) * scaleX;
            pointerCurrentY = (e.clientY - rect.top) * scaleY;
            if (Network.assigned === 0) return;
            const state = Network.latestState;
            if (!state) return;
            if (state.gameOver || state.dying) return;

            const dx = pointerCurrentX - pointerStartX;
            let dir = 0;
            if (dx > moveThreshold) dir = 1;
            else if (dx < -moveThreshold) dir = -1;
            Network.move(Network.assigned, dir);
            // send full pointer hint to server for per-tick decision
            Network.pointerState(Network.assigned, {
                startX: pointerStartX,
                startY: pointerStartY,
                currentX: pointerCurrentX,
                currentY: pointerCurrentY,
                moveThreshold,
                jumpThreshold,
            });
        }, { passive: false });

        canvas.addEventListener('pointerup', e => {
            e.preventDefault();
            try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}

            if (!pointerActive) return;
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            pointerCurrentX = (e.clientX - rect.left) * scaleX;
            pointerCurrentY = (e.clientY - rect.top) * scaleY;
            pointerActive = false;

            if (Network.assigned === 0) return;
            const state = Network.latestState;
            if (!state) return;
            if (state.gameOver) { Network.reset(); return; }
            if (state.dying) return;

            const dx = pointerCurrentX - pointerStartX;
            const dy = pointerCurrentY - pointerStartY;
            Network.move(Network.assigned, 0);

            // notify server pointer released (clear hint)
            Network.pointerState(Network.assigned, null);

            const absDX = Math.abs(dx);
            const absDY = Math.abs(dy);
            const isHorizontalDominant = absDX >= absDY;
            const horizontalMoved = absDX > moveThreshold;
            const verticalMoved = absDY > jumpThreshold;

            if (Network.assigned !== 2) {
                if (verticalMoved && dy < 0) {
                    Network.jump(Network.assigned, dx);
                }
                return;
            }

            if (!isHorizontalDominant && verticalMoved) {
                dy < 0 ? Network.swipeUp(Network.assigned, dx) : Network.swipeDown(Network.assigned, dx);
            } else if (isHorizontalDominant && horizontalMoved) {
                // Horizontal dominant gesture for P2: movement is already handled by pointermove.
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

    function getPointerHint() {
        if (!pointerActive) return null;
        return {
            startX: pointerStartX,
            startY: pointerStartY,
            currentX: pointerCurrentX,
            currentY: pointerCurrentY,
            moveThreshold,
            jumpThreshold,
        };
    }

    return { init, getPointerHint };
})();
