[app]

# 应用信息
title = VidPlayer
package.name = vidplayer
package.domain = org.vidplayer

# 源码目录（main.py、vidcore.py、vidutil.py 都在当前目录）
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,ttf,ttc,otf

version = 1.0.0

# 依赖：python3 + kivy 界面 + ffpyplayer(含 ffmpeg 解码) + pillow(默认封面生成)
requirements = python3, kivy, ffpyplayer, pillow

# 屏幕方向：四个方向都列出 = 可自由横竖屏旋转（buildozer 1.5.0 不支持写 all）
orientation = portrait, landscape, portrait-reverse, landscape-reverse

# 安卓权限：读取视频、写入 VidPic 封面、安卓11+管理所有文件
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_VIDEO, READ_MEDIA_IMAGES, MANAGE_EXTERNAL_STORAGE

# 目标 SDK / 最低 SDK / 架构
android.api = 34
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a

# 自动接受 SDK 协议、开启 AndroidX
android.accept_sdk_license = True
android.enable_androidx = True

# 固定 python-for-android 版本（buildozer 1.5.0 只认 p4a.branch，tag 也写这里），
# 保证每次云端构建结果一致（含 ffpyplayer/ffmpeg 配方，配套 NDK r25b）
p4a.branch = v2024.01.21

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
