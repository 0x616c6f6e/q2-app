# QR Code APP

一个固定文本显示示例，默认将 `Q2-Kernel` 编码为二维码。启动后居中显示二维码和原文，Back 按钮或圆盘 BACK 单击退出；管理模式回到主页。无键盘、内容编辑、网络请求或存储权限。

在 q2 根目录运行：

```powershell
./run.ps1 -AppName qrcode
# 独立运行
./run.ps1 -SingleApp -AppName qrcode
```

已加入主页应用列表。修改 [main.lua](../apps/qrcode/main.lua) 顶部的 `local content = "Q2-Kernel"`，重新运行即可更换固定内容。空字符串不支持，上限 255 UTF-8 字节；过长内容在小尺寸上可能无法生成，APP 会显示错误信息。QR 内的 UTF-8 不受显示字体限制，但当前界面的字体不含中文字形。

Kernel 提供 `q.ui.qrcode(x,y,text,size)`，需要 display.ui；在 `kernel/components/display/lv_conf.h` 保留 `LV_USE_QRCODE=1`。二维码使用黑白、高对比度、整数模块尺寸和白色静区。退出或改变系统视口会正确释放/重建，不保留过期控件句柄。

测试：`python app/scripts/test_qrcode_ui.py --runner build/data/bin/q2_x86.exe --artifacts build/qrcode-test/verified`，需 Pillow 与 zxing-cpp，仅测试工具使用解码库，APP/运行时无此依赖。测试使用临时包，不改固定字符串或用户存储。
