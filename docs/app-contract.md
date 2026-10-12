# APP 开发协议

## 目录和 manifest

```text
my-app/
  manifest.json
  main.lua
  src/view.lua
  assets/icon.png
```

```json
{
  "format": 2,
  "id": "71f147c6-3604-4474-9e3d-af2d949fb38f",
  "name": "System Settings",
  "description": "系统设置应用",
  "version": "0.1.0",
  "type": "app",
  "entry": "main.lua",
  "api": 2,
  "capabilities": {
    "required": ["system.info"],
    "optional": ["display.text", "storage.private"]
  },
  "resources": {"lua_heap_kib": 64}
}
```

示例 UUID 属于 settings，新应用应使用 create 命令获得自己的 UUID。ID 必须为小写 UUID v4，版本遵循 SemVer。上面的 API 2 是精确版本，不是 SemVer 范围。required/optional 各最多 16 项，不能重复；资源配额整数 32–384 KiB。

可选字段：`description` 最多 512 UTF-8 字节；`icon` 必须指向包内 assets，路径最多 96 字节；`dynamic_resources`、`ota` 为最多 256 字节的 HTTPS URL。两类 URL 当前只保存元数据，不会自动下载或申请网络权限。支持最多 8 个 APP VM 协作运行；仍不支持 scopes、单独 service 包类型、多入口、API 版本范围；未知字段会拒绝，不能无声忽略。

`schemas/manifest.schema.json` 供编辑器提示；工具还校验 UTF-8 字节长度、跨数组重复、路径及实际资源，不能只依赖 JSON Schema。

## Lua 与错误处理

```lua
local q = require("q2")
local view = require("view") -- 对应 src/view.lua，由打包器合并
return {
    on_start = function()
        local available, granted = q.os.capability("storage.private")
        if available and granted then
            local value, err = q.storage.get("theme")
            if value == nil and err.code ~= "not_found" then
                -- 以默认值降级；拒绝权限或 I/O 失败不是成功。
                return
            end
        end
    end,
}
```

组件存在但拒绝权限时，API 返回 `nil, {code, number}`；未注册模块可能为 nil，应先查询 capability。缺少 required 能力或授权使 APP 启动被拒绝，optional 则由 APP 降级。模块被打包为局部函数，不开放宿主文件系统、load、io、os、package 或原生模块。循环模块依赖会报错。

当前业务 API：system.ui.read、system.settings（出厂）、system.lifecycle（resident）、screensaver.inhibit、input.keys、apps.list、apps.launch、apps.navigate、appearance.read、appearance.write、system.info、storage.private、storage.fatfs、storage.database、display.text、display.ui、usb.cdc。display.ui 为可选 LVGL 标签/按钮/图片/背景/尺寸查询扩展，参考 apps/ui-demo。可调用方法以目标 Kernel 的 Lua API 文档和运行时可用性为准。不存在通用寄存器、SDK调用、任意 SQL 或路径访问接口。

## 包与限额

`.q2app` 是确定性 ZIP_STORED：manifest、合并后的 main.lua、assets、checksums.json。源资源项最多 32 个、总内容最多 1 MiB，单资产最多 256 KiB；checksums.json 和 ZIP 元数据另计。manifest 最大 4 KiB，合并源码最大 32 KiB。所有路径相对、禁止符号链接。

SHA-256 表用于发现内容变化，不是发布者签名，也不能让不可信包变可信。生成的 `.run/` 仅给宿主开发执行；Kernel 接收已加载的 manifest/source；打包器同步 assets 到 .run，PC 端按 APP UUID 注册包内 PNG，LVGL 在 boot 或实例切换时解码。仍未实现 ZIP 安装或 OTA。

## 发布检查

验证 manifest → 打包 → 工具测试 → 宿主实际运行 → 核对目标支持的 API/能力 → 实机测试。settings 已提供背景选择与偏好保存入口，真实亮度、音量、Wi-Fi 等应待对应组件迁移后添加，不可在 UI 上伪装设置成功。

出厂身份、默认入口和共享背景见 [Homepage](homepage.md)。共享背景写权限只授予产品认可的出厂 APP；结束自己使用 q.os.exit，管理模式会回主页。

input.keys：count/name/last/watch。watch(true) 后在 on_event 收到 key.action，text 是名称，value 为 1=单击、2=双击、3=长按。处理逻辑位于 APP；不要将输入 value 当成按下/释放电平。APP 退出自动取消订阅。参考 apps/key-demo。

## 系统 UI 与 APP 视口

`q.ui.width()/height()` 为可用内容区，系统状态栏启用时 height 不含其高度。使用这些尺寸布局，无需关心物理顶部偏移。APP 清屏/退出不删除状态栏，屏保期间 APP 实例继续存在，首次唤醒输入被系统消耗。注入指针的宿主测试使用物理屏幕坐标，应按实际状态栏高度偏移。


可选 on_tick(now_ms) 在每次 Kernel poll 中运行，隐藏 APP 继续接收 tick。自行用单调截止时间限流，不能阻塞或假设固定帧率。q.apps.home 保留实例；q.os.exit 结束实例。状态栏切换的 ui.resize 应重布局而不是重置业务。

Settings 提供可滚动系统 UI 配置。锁屏开启时普通 APP 收不到按键，双击 POWER 解锁动作也不传入 APP。自定义歌词/屏保应申请 screensaver.inhibit 并持续前台续期，见 [示例](custom-screensaver.md)。

设备数据接口：q.data.get/info/subscribe/unsubscribe；基础权限 data.read 加各 key 的领域权限。on_event 接受 data.changed / data.event；value 为原生布尔/整数/字符串，valid=false 时 nil，处理状态失效。订阅随实例退出回收。Key Demo 展示经 lifecycle 放行的通用按键主题。

## 分辨率声明与图标变体

manifest 可选 `supported_resolutions`：1–16 个不重复的 `WIDTHxHEIGHT` 字符串；宽高各 64–1024、小写 x、无前导零。省略表示未声明，不限制启动；APP 要为未列出的尺寸提供回退 UI。需要 `display.ui` 的 `q.ui.resolution()` 返回整屏尺寸字符串，`q.ui.width()/height()` 继续返回内容区尺寸。

图标默认放 `assets/name.png`，尺寸变体放 `assets/502x410/name.png` 等目录。x86 只注册当前尺寸版本（不存在则默认），Lua 和 manifest.icon 继续引用平铺逻辑名。四组目录由矢量源生成原生尺寸图标：368 系列 128×128、410 系列 144×144；尺寸配置和生成命令见 artwork/README.md。未提供资产加载器的平台需自行实现选取和注册。打包递归保留资源路径与现有大小/数量配额。
