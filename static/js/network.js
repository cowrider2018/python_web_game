// ============================================================
// Network - socket.io 封裝、狀態儲存、事件巴士
// ============================================================
const Network = (() => {
    const socket = io();

    let _assigned    = 0;
    let _playerCount = 0;
    let _latestState = null;

    // 簡易事件巴士（供 main.js 訂閱）
    const _listeners = {};
    function _on(event, cb) {
        (_listeners[event] = _listeners[event] || []).push(cb);
    }
    function _emit(event, data) {
        (_listeners[event] || []).forEach(cb => cb(data));
    }

    socket.on('connect',      ()     => _emit('connect'));
    socket.on('assign',       data   => { _assigned    = data.assigned; _playerCount = data.count || _playerCount; _emit('assign', data); });
    socket.on('player_count', data   => { _playerCount = data.count || _playerCount; _emit('player_count', data); });
    socket.on('state',        data   => { if (data) _latestState = data; });
    socket.on('skill_event',  data   => _emit('skill_event', data));

    return {
        // 訂閱
        on: _on,

        // 發送
        join:      ()      => socket.emit('join'),
        leave:     ()      => socket.emit('leave'),
        reset:     ()      => socket.emit('request_reset'),
        jump:      (role, dx = 0)  => socket.emit('jump', { role, dx }),
        move:      (role, dir) => socket.emit('move', { role, dir }),
        swipeUp:   (role, dx = 0)  => socket.emit('swipe_up', { role, dx }),
        swipeDown: (role, dx = 0)  => socket.emit('swipe_down', { role, dx }),

        // 唯讀狀態
        get assigned()    { return _assigned;    },
        get playerCount() { return _playerCount; },
        get latestState() { return _latestState; },
    };
})();
