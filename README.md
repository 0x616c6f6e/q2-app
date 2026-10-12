# Q2-App

独立 Lua 应用项目，面向 **Q2-Kernel Lua API 2 / manifest format 2**。可以在没有 Kernel、SoC SDK、编译器的机器上创建、验证和打包，工具只依赖 Python 3.10+ 标准库。

```text
factory.json         可信产品清单：默认主页、出厂 APP 与普通 APP
apps/homepage/       出厂默认主页：背景、应用图标/名称、启动和返回入口
apps/settings/       系统设置：图标、背景选择、设备信息及偏好保存
apps/key-demo/       按键单击/双击/长按透传验证，需 input.keys
apps/device-info/    最小设备信息示例
apps/ui-demo/        LVGL 标签/按钮及点击事件示例（需要 display.ui）
schemas/             JSON manifest schema
scripts/             创建、验证、打包与自动测试
docs/                应用契约和开发说明
dist/                生成的包、校验记录、宿主运行目录（忽略提交）
```

```sh
python scripts/q2app.py create apps/my-app --name "My App"
python scripts/q2app.py validate apps/settings
python scripts/q2app.py pack apps/settings -o dist/settings.q2app
python scripts/test_apps.py
```

每个 APP 保存自己的 `main.lua`、`src/`、`manifest.json`、`assets/`。UUID 在创建时生成，后续版本和重复打包保留原 UUID。不要在每次构建时生成新身份。

阅读 [APP 开发协议](docs/app-contract.md)、[AI 开发说明](../ai/app.md)。本版打包工具已实现；设备端 ZIP 安装器、签名验证、下载与 OTA 尚未实现，不能直接把开发包当作已支持的设备安装格式。

运行示例需要独立 Q2-Platform 的 host runner，传入 `dist/settings.run/manifest.json`、`main.lua` 和明确授权列表。Q2-App 本身不链接 Kernel 源码，也不依赖 ESP-IDF。

图形 APP 使用 platform/x86 运行端。ui-demo 需要明确授权 system.info、display.ui；点击 Play/Next 可验证 Lua 事件和文字更新，不代表音频播放已经接入。

## 默认系统入口

`python scripts/q2app.py factory . -o dist` 打包产品目录；homepage、settings 为出厂 APP，ui-demo、device-info 为普通示例。q2 根目录 run.ps1 默认启动 Homepage。左右箭头切换当前应用，点击中央图标进入应用，点击 Home 或按 Esc 返回；关闭窗口退出运行端。

设置中的背景选择同时作用于主页并保存。缺少应用图标时使用通用图标；每屏最多显示一个应用，图标居中、名称在下方，左右箭头首尾循环切换。新增应用需加入产品 factory.json，当前并无设备下载安装器。详细协议见 [应用管理](docs/homepage.md)。

[Key Demo](apps/key-demo/main.lua) 订阅按键事件并显示最近类型与累计次数；在 x86 上通过 Key Lab 网页产生模拟事件。按键操作策略应写在 APP 中，不能依赖 Kernel 的名称映射。

[Network Test](docs/network-test.md)：HTTP/HTTPS 请求、状态/耗时/响应预览，网络不可用或未授权时降级提示。

[QR Code](docs/qrcode.md)：固定字符串生成与显示二维码，离线运行，无编辑功能。

[Music](docs/music-player.md)：保存并恢复网易云登录，自动播放“我喜欢的音乐”；Windows 支持真实 MP3 播放、暂停/继续和自动切歌，保留简洁播放页，歌词显示与请求暂时关闭。
