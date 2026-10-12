# Network Test APP

在 q2 根目录执行：

```powershell
./run.ps1 -AppName network-test
# 或独立 APP 模式
./run.ps1 -SingleApp -AppName network-test
```

也可以从默认 Homepage 左右切换到 Network Test 打开。Prev / Next 选择目标，Start 发起 HTTP/HTTPS GET，请求过程中同一按钮变为 Cancel；界面显示 HTTP 状态码、耗时和响应前 240 字节。页面可纵向滚动，底部 Home 返回主页。圆盘 PREV/NEXT/PLAY/BACK 的单击分别切换、开始/取消、退出。切换目标会取消旧请求，调整窗口/状态栏保留请求状态。

默认测试目标在 [src/targets.lua](../apps/network-test/src/targets.lua)，可以修改 URL 再打包；当前图形 API 未提供文本输入控件。启动 APP 不自动联网，只有点击 Start 才发请求。

本地服务不需要公网：

```powershell
python platform/x86/test_network.py --serve
```

在 APP 选择 Local test server 后点击 Start。服务器仅绑定 127.0.0.1:18080，Ctrl+C 停止。默认 /health 返回 200；修改 targets.lua 可测试 /missing（404）、/redirect（302）、/large（响应超限）、/binary（不支持二进制）、/slow（延迟）。这只是调试服务。

所需 display.ui，网络权限为 optional network.http：组件关闭或未授权时仍可打开 APP 并显示不可用。根 q2.json 默认 components.network=true、app.grants 包含 network.http；旧配置缺字段默认 false。Wi-Fi/BLE 无线连接功能与此独立，仍未实现。

实现遵循 [Kernel Network](../../kernel/docs/network.md)。数据上限为 256 KiB、文本 GET，请求超时默认 5 秒，异常可直接重试；如果取消过多正在执行的请求导致 busy，稍等后重试。当前不保存响应文件、不执行 HTML、不自动跳转。
