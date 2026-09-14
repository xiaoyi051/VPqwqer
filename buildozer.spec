[app]

# 应用信息
title = VidPlayer
package.name = vidplayer
package.domain = org.vidplayer

# 源码目录（main.py、vidcore.py、vidutil.py 都在当前目录）
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,ttf,ttc,otf

version = 1.0.0

# 依赖：python3 + kivy 界面 + ffpyplayer(含 ffmpeg 解码) + pillow(默认封面生成)
requirements = python3, kivy, ffpyplayer, pillow

# 屏幕方向：all 允许横竖屏（看视频可横屏）
orientation = all

# 安卓权限：读取视频、写入 VidPic 封面、安卓11+管理所有文件
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_VIDEO, READ_MEDIA_IMAGES, MANAGE_EXTERNAL_STORAGE

# 目标 SDK / 最低 SDK / 架构
android.api = 34
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a

# 自动接受 SDK 协议、开启 AndroidX
android.accept_sdk_license = True
android.enable_androidx = True

# 固定 python-for-android 版本，保证每次云端构建结果一致（含 ffpyplayer/ffmpeg 配方）
p4a.version = v2024.01.21

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
