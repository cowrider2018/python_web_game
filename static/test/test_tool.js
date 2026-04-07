// ============================================================
// 測試工具 - 電腦鍵盤輸入模擬
// ============================================================

// P2: ArrowUp / ArrowDown 當作上／下滑（桌面端鍵盤支援）
window.addEventListener('keydown', e => {
    if ((e.code === 'ArrowUp' || e.code === 'ArrowDown') && assigned === 2) {
        e.preventDefault();
        if (!latestState || latestState.gameOver) { socket.emit('request_reset'); return; }
        socket.emit(e.code === 'ArrowUp' ? 'swipe_up' : 'swipe_down', {});
    }
});
