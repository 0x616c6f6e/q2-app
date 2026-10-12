# 自定义屏保 / 歌词页面

在 manifest 的 capabilities.optional 增加 `screensaver.inhibit`。使用普通 APP 内容区绘制歌词，状态栏仍受 lifecycle 控制。以下片段演示续期机制，不提供音频播放实现：

```lua
local q = require("q2")
local lyrics_visible, next_renew = false, 0
local allowed = false
return {
    on_start = function()
        local available, granted = q.os.capability("screensaver.inhibit")
        allowed = available and granted
        -- Only enable this while the user's own lyrics view is active.
        lyrics_visible = true
    end,
    on_tick = function(now_ms)
        if not allowed or not lyrics_visible or now_ms < next_renew then return end
        next_renew = now_ms + 250
        local ok, err = q.shell.keep_awake()
        if not ok then
            -- permission_denied is expected when hidden, asleep or locked.
            -- Keep the APP alive; never retry in a blocking loop or assert success.
            if err.code ~= "permission_denied" then lyrics_visible = false end
        end
    end,
    on_event = function(event)
        if event.type == "ui.resize" then
            -- Rebuild your own view with q.ui.width()/height(), preserving playback state.
        end
    end,
}
```

续期只刷新空闲时间，不关闭屏保开关。停止调用后，到期自动回归系统屏保。隐藏、已睡眠或锁定的 APP 无权续期/解锁。`q.apps.home()` 保持 APP 在后台；`q.os.exit()` 结束它。回调在同一 owner 线程协作执行，不应阻塞。
