[app]
# 应用信息
title = VidPlayer
package.name = vidplayer
package.domain = org.vidplayer
# 源码目录（main.py、vidcore.py、vidutil.py 都在当前目录）
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,ttf,ttc,otf
version = 1.0.0
# 锁定版本，规避版本不兼容编译问题
requirements = python3, kivy==2.3.0, ffpyplayer==4.5.1, pillow
# 先固定竖屏打包，打包成功后再改回多方向
orientation = portrait
# 安卓权限，移除MANAGE_EXTERNAL_STORAGE（放到extra_manifest）
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_VIDEO, READ_MEDIA_IMAGES
# 单独声明MANAGE_EXTERNAL_STORAGE
android.extra_manifest = <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" android:maxSdkVersion="34" />
# 目标 SDK / 最低 SDK / 架构
android.api = 34
android.minapi = 21
android.archs = arm64-v8a
# 自动接受 SDK 协议、开启 AndroidX
android.accept_sdk_license = True
android.enable_androidx = True
# 换成更稳的p4a版本，ffpyplayer编译成功率更高
p4a.branch = v2023.10.04
# 应用图标与启动画面（可爱粉主题素材，PIL 预生成）
icon.filename = assets/icon.png
presplash.filename = assets/presplash.png
# 非全屏（保留状态栏，方便操作文件选择器）
fullscreen = 0
# 编译日志级别
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1
