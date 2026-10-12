# Homepage 与出厂 APP

homepage 的 UUID 为 1fc0ea0c-2986-4626-8e35-5940462546bd，更新版本不得重新生成。它与 settings 同为产品清单中的 factory APP，并被指定为 default_app。此角色不属于应用自报的 manifest 字段。

主页从 q.apps 查询注册目录，过滤自身，以横向单应用方式显示：中央图标、下方居中名称、两侧箭头；主页内容区不混入状态栏、列表标题或出厂标记（系统状态栏另由生命周期层绘制）；图标缺失时显示包内 app-default。左右箭头在目录中循环切换，只有点击中央图标才调用 launch，权限拒绝会留在主页显示原因。默认壁纸使用 home-background.png，颜色方案由共享 appearance 读取。

常驻模式：启动目标时 Home VM 保留，目标退出直接显示 Home。q.apps.home 让当前 APP 隐藏但继续运行，q.os.exit 才释放它；进程重启仍需显式持久保存。settings、ui-demo、device-info 提供 Home 按钮；PC 的 Esc/浏览器返回键由平台请求回主页。设置页面内 Back 仍只返回设置上一页。

系统设置通过 appearance.set 改主页与设置的共享背景。没有存储时仅本次运行有效；保存失败不伪装成功。旧 settings 私有偏好仅用于 SingleApp 调试。普通 APP 获授 appearance.read 后可采用系统背景，未经产品标记为 factory 不得修改它。

目录注册上限 8（包含 Home）；目前启动前固定。factory.json 必须含 homepage 和 settings 且标记 factory=true，default_app 必须是 homepage；UUID、目录名不得重复。出厂身份仅由可信开发者配置，不由下载 APP 定义。没有安装、卸载或 OTA 实现。

验证：scripts/test_apps.py；scripts/test_homepage_ui.py --runner /path/q2_x86.exe。后者用临时包和介质检查真实点击、背景跨进程持久化、反复切换、权限拒绝、普通 APP 故障返回和主页故障退出。

0.2.0：图标以等比例正方形视口显示（最高 144 px），位置随宽高计算；名称使用真实文字居中对齐。只有一个应用时不显示箭头，无应用时显示 No apps，低于 240×240 显示小屏提示。左右切换候选项只刷新主页控件，不启动另一个 VM；启动失败显示简短底部信息。

0.3.0：homepage 的 src/shell.lua 管理 home/status/saver 场景、on_tick 空闲计时、模板内容与解锁手势。默认双击 POWER 解锁；所有被锁定输入由 Home 消耗。最多 8 个独立 VM（含 Home），普通 APP 的 UI 操作不能覆盖系统层。配置见产品 system-ui.md，独立 Kernel 契约见 Lua API。

## 状态栏图标（0.5.0）

素材来自用户提供的 `q2-ui/status-icons`，19 张透明 24×24 PNG 已复制为
`apps/homepage/assets/status-*.png`，运行和打包不依赖外部目录。保留原有许可归属，未额外声明素材许可证。
状态栏由 `src/status_icons.lua` 选择素材，`src/shell.lua` 订阅数据并绘制，只在可见状态改变时刷新控件。

- `{wifi}`：未连接显示断开图标；连接且 RSSI ≥ -60 dBm 为强，-75～-61 dBm 为中，小于 -75 dBm 为弱。
- `{ble}`：已连接显示 connected，未连接显示 idle；不代表经典蓝牙 BT 状态。
- `{battery}`：0 为 0 档，1～25 / 26～50 / 51～75 / 76～100 分别使用 25 / 50 / 75 / 100 档；充电使用对应闪电图标，旁边显示实际百分比。
- 数据缺失、权限拒绝、超时或错误显示 `--`，不假装电量为 0 或无线已断开。
- `wifi-off` 和 BLE off/pairing 素材已预留；只有未来 provider 明确提供
  `wireless.wifi.enabled=false` 或 `wireless.ble.state=off|idle|pairing|connected` 才会使用。
  当前 x86 数据提供者没有这两个 key，订阅 not_found 被安全忽略；Web 的 mode=off 表示数据不可用，不代表关闭无线。

`q2.json` 的 status_left/status_right 模板和系统设置仍可选择图标；每半栏文字在前，图标按模板顺序排列在后。
窄屏空间不足时省略百分比并限制图标数。时间与 `{bt}` 仍为文本，屏保中的同名变量仍展开为文本。
禁用数据组件时保留旧文本状态。状态栏开关、前台 APP 遮挡隔离及锁屏策略不变。

验证（从 q2 根目录）：

```sh
python app/scripts/test_status_icons.py --runner build/x86/bin/q2_x86.exe --artifacts build/status-icons
```

测试用临时包与介质、随机 Web 端口注入 Wi-Fi/BLE/电池数据，通过截图像素验证实际 LVGL 图标，覆盖 settings 前台。
APP 包源条目上限从 24 增为 32 以容纳图标组，总内容 1 MiB、单资产 256 KiB 配额保持不变。

Homepage 的 input.keys 为可选能力；无按键 provider 或被拒绝时保留触摸导航，不调用 q.keys.watch。ESP32-S3 内置同一出厂源码和分辨率图片，不携带 PC 调试 APP。
