# -*- coding: utf-8 -*-
"""
vidutil.py —— VidPlayer 的纯工具函数
包含：视频类型判断、自然排序、VidPic 封面目录映射与镜像维护、
      配置读写、默认封面生成、安卓存储权限申请。
不依赖 Kivy，方便在电脑上单独测试。
"""
import os
import re
import json
import struct
import zlib
from os.path import join, isdir, isfile, basename, relpath, splitext, exists

# ---------------------------------------------------------------- 常量
VIDPIC_DIRNAME = "VidPic"          # 封面根目录名（建在用户所选视频文件夹内）
COVER_EXT = ".png"

# 支持的视频扩展名（ffpyplayer/ffmpeg 可解的常见格式）
VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".ts",
    ".m4v", ".3gp", ".3gpp", ".rmvb", ".rm", ".f4v", ".vob",
    ".mpg", ".mpeg", ".m2ts", ".divx", ".ogv",
}

DEFAULT_COVER_NAME = "default_cover.png"
FOLDER_ICON_NAME = "folder_icon.png"


# ---------------------------------------------------------------- 环境判断
def is_android():
    return "ANDROID_ROOT" in os.environ or "ANDROID_ARGUMENT" in os.environ


def is_video_file(name):
    return splitext(name)[1].lower() in VIDEO_EXTS


# ---------------------------------------------------------------- 自然排序
def natural_key(text):
    """让 视频2 排在 视频10 前面。"""
    return [int(p) if p.isdigit() else p.lower()
            for p in re.split(r"(\d+)", text)]


# ---------------------------------------------------------------- VidPic 封面映射
def vidpic_root(root):
    """所选视频文件夹对应的 VidPic 根目录。"""
    return join(root, VIDPIC_DIRNAME)


def cover_path_for(root, video_path):
    """
    视频  <root>/sub/a.mp4
    封面  <root>/VidPic/sub/a.mp4.png
    封面名 = 视频完整文件名 + .png，保证同名不同后缀的视频不会互相覆盖。
    """
    rel = relpath(video_path, root)
    return join(vidpic_root(root), rel + COVER_EXT)


def ensure_mirror(root):
    """
    创建并维护 VidPic 镜像：遍历所选文件夹的全部子文件夹，
    在 VidPic 下建立一模一样的目录结构（VidPic 自身与隐藏目录跳过）。
    """
    if not root or not isdir(root):
        return
    vp = vidpic_root(root)
    os.makedirs(vp, exist_ok=True)
    for dirpath, dirnames, _files in os.walk(root):
        # 原地剪枝：不进入 VidPic 自身与隐藏目录
        dirnames[:] = sorted(
            [d for d in dirnames if d != VIDPIC_DIRNAME and not d.startswith(".")],
            key=natural_key,
        )
        for d in dirnames:
            src_dir = join(dirpath, d)
            rel = relpath(src_dir, root)
            os.makedirs(join(vp, rel), exist_ok=True)


def ensure_cover_dir(root, video_path):
    """保存封面前，确保对应的 VidPic 子目录存在（新建文件夹也能即时维护）。"""
    cover = cover_path_for(root, video_path)
    os.makedirs(dirname_of(cover), exist_ok=True)
    return cover


def dirname_of(p):
    return os.path.dirname(p)


# ---------------------------------------------------------------- 目录浏览
def list_folder(root, rel):
    """
    列出 root/rel 下的内容，返回 (folders, videos)（均为文件名列表，已自然排序）。
    - 根目录下的 VidPic 不显示
    - 隐藏文件/文件夹（以 . 开头）不显示
    - 非视频文件不显示
    """
    base = join(root, rel) if rel else root
    folders, videos = [], []
    if not isdir(base):
        return folders, videos
    for name in os.listdir(base):
        if name.startswith("."):
            continue
        if not rel and name == VIDPIC_DIRNAME:
            continue
        p = join(base, name)
        if isdir(p):
            folders.append(name)
        elif isfile(p) and is_video_file(name):
            videos.append(name)
    folders.sort(key=natural_key)
    videos.sort(key=natural_key)
    return folders, videos


# ---------------------------------------------------------------- 配置读写
def load_settings(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_settings(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------- 默认封面生成
def _solid_png(path, w, h, rgb):
    """无 Pillow 时的兜底：手写一张纯色 PNG。"""
    raw = bytearray()
    row = bytes(rgb) * w
    for _ in range(h):
        raw.append(0)
        raw.extend(row)

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


# ---------------------------------------------------------------- 可爱少女风主题素材
# 配色（樱粉系）
PINK_BG_TOP = (255, 226, 239)
PINK_BG_BOT = (255, 247, 251)
PINK_MAIN = (255, 143, 187)      # #FF8FBB
PINK_DEEP = (255, 111, 166)      # #FF6FA6
PINK_LIGHT = (255, 201, 221)     # #FFC9DD
PINK_PALE = (255, 224, 236)
WHITE = (255, 255, 255)
PLUM = (138, 59, 91)             # #8A3B5B 深梅色文字

HEART_PINK_NAME = "heart_pink.png"
HEART_WHITE_NAME = "heart_white.png"
SLIDER_TRACK_NAME = "slider_track.png"
SLIDER_CURSOR_NAME = "slider_cursor.png"
POPUP_BG_NAME = "popup_bg.png"


def _vgradient(size, top, bot):
    """竖向渐变 RGB 图。"""
    from PIL import Image
    w, h = size
    img = Image.new("RGB", size, top)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        row = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    return img


def _heart_points(cx, cy, s):
    """经典心形参数曲线，s 为整体缩放，返回多边形顶点。"""
    import math
    pts = []
    for i in range(60):
        t = 2 * math.pi * i / 60.0
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s / 16.0, cy - y * s / 16.0))
    return pts


def _draw_heart(d, cx, cy, s, fill, outline=None, width=0):
    pts = _heart_points(cx, cy, s)
    d.polygon(pts, fill=fill)
    if outline and width:
        d.line(pts + [pts[0]], fill=outline, width=width, joint="curve")


def _rrect(d, box, r, **kw):
    """圆角矩形（兼容旧版 Pillow：rounded_rectangle 不可用时退化为普通矩形）。"""
    try:
        d.rounded_rectangle(box, radius=r, **kw)
    except Exception:
        d.rectangle(box, **kw)


def make_default_cover(path):
    """可爱风默认视频封面：樱粉渐变 + 白色圆 + 粉色播放三角 + 小爱心。"""
    try:
        from PIL import Image, ImageDraw
        w, h = 480, 270
        img = _vgradient((w, h), PINK_BG_TOP, PINK_BG_BOT)
        d = ImageDraw.Draw(img)
        # 散落的小爱心与圆点装饰
        deco = [(52, 44, 12, PINK_LIGHT), (428, 52, 14, PINK_LIGHT),
                (74, 226, 10, PINK_PALE), (410, 220, 12, PINK_PALE),
                (240, 34, 8, PINK_LIGHT)]
        for cx, cy, s, col in deco:
            _draw_heart(d, cx, cy, s, col)
        for cx, cy, r in ((120, 96, 5), (366, 108, 4), (300, 236, 5), (170, 150, 4)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PINK_LIGHT)
        # 中央白色圆 + 粉边 + 播放三角
        cx, cy, r = w // 2, h // 2 + 4, 62
        d.ellipse([cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5], fill=PINK_MAIN)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
        s = 30
        d.polygon([(cx - int(s * 0.7), cy - s),
                   (cx - int(s * 0.7), cy + s),
                   (cx + int(s * 1.05), cy)], fill=PINK_DEEP)
        # 顶部小爱心点缀
        _draw_heart(d, cx, cy - r - 22, 12, PINK_MAIN)
        img.save(path)
        return
    except Exception:
        pass
    _solid_png(path, 320, 240, PINK_BG_TOP)


def make_folder_icon(path):
    """可爱风文件夹图标：粉色文件夹 + 白色小爱心。"""
    try:
        from PIL import Image, ImageDraw
        w, h = 480, 270
        img = _vgradient((w, h), PINK_BG_TOP, PINK_BG_BOT)
        d = ImageDraw.Draw(img)
        for cx, cy, s in ((60, 52, 11), (424, 60, 12), (70, 224, 9), (414, 222, 10)):
            _draw_heart(d, cx, cy, s, PINK_LIGHT)
        # 文件夹后身与标签
        _rrect(d, [116, 104, 366, 206], 18, fill=PINK_MAIN)
        _rrect(d, [116, 82, 226, 116], 16, fill=PINK_MAIN)
        # 文件夹前面板
        _rrect(d, [104, 128, 378, 214], 18, fill=(255, 185, 212))
        d.arc([104, 110, 140, 146], 180, 270, fill=PINK_DEEP, width=4)
        # 面板上的白色爱心
        _draw_heart(d, 240, 168, 26, WHITE)
        img.save(path)
        return
    except Exception:
        pass
    _solid_png(path, 320, 240, PINK_MAIN)


def make_heart(path, color, size=96):
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        _draw_heart(d, size // 2, size // 2 + 2, int(size * 0.72), color)
        img.save(path)
        return True
    except Exception:
        return False


def make_slider_track(path):
    """进度条轨道：粉色圆角胶囊。"""
    try:
        from PIL import Image, ImageDraw
        w, h = 48, 24
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        _rrect(d, [2, 7, w - 3, h - 8], 8, fill=PINK_LIGHT, outline=PINK_MAIN, width=2)
        img.save(path)
        return True
    except Exception:
        return False


def make_slider_cursor(path):
    """进度条滑块：白色圆 + 粉边 + 小爱心。"""
    try:
        from PIL import Image, ImageDraw
        s = 48
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([3, 3, s - 4, s - 4], fill=WHITE, outline=PINK_DEEP, width=4)
        _draw_heart(d, s // 2, s // 2 + 2, 15, PINK_MAIN)
        img.save(path)
        return True
    except Exception:
        return False


def make_popup_bg(path):
    """弹窗背景：白色圆角（供 Popup.background 九宫格拉伸）。"""
    try:
        from PIL import Image, ImageDraw
        s = 48
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        _rrect(d, [1, 1, s - 2, s - 2], 18, fill=WHITE, outline=PINK_MAIN, width=3)
        img.save(path)
        return True
    except Exception:
        return False


def ensure_default_assets(user_data_dir):
    """生成并返回全部主题素材路径（dict）。默认封面/文件夹图标缺失即重绘，
    其余主题素材同样按需生成，可安全反复调用。"""
    os.makedirs(user_data_dir, exist_ok=True)
    paths = {
        "cover": join(user_data_dir, DEFAULT_COVER_NAME),
        "folder": join(user_data_dir, FOLDER_ICON_NAME),
        "heart_pink": join(user_data_dir, HEART_PINK_NAME),
        "heart_white": join(user_data_dir, HEART_WHITE_NAME),
        "slider_track": join(user_data_dir, SLIDER_TRACK_NAME),
        "slider_cursor": join(user_data_dir, SLIDER_CURSOR_NAME),
        "popup_bg": join(user_data_dir, POPUP_BG_NAME),
    }
    if not exists(paths["cover"]):
        make_default_cover(paths["cover"])
    if not exists(paths["folder"]):
        make_folder_icon(paths["folder"])
    if not exists(paths["heart_pink"]):
        make_heart(paths["heart_pink"], PINK_MAIN)
    if not exists(paths["heart_white"]):
        make_heart(paths["heart_white"], WHITE)
    if not exists(paths["slider_track"]):
        make_slider_track(paths["slider_track"])
    if not exists(paths["slider_cursor"]):
        make_slider_cursor(paths["slider_cursor"])
    if not exists(paths["popup_bg"]):
        make_popup_bg(paths["popup_bg"])
    return paths


# ---------------------------------------------------------------- 安卓权限
def request_android_permissions(callback=None):
    """
    安卓运行时权限：先申请读存储/读视频权限，再跳转“所有文件访问”授权页。
    电脑端直接执行回调。
    """
    try:
        from android.permissions import request_permissions, Permission
    except Exception:
        if callback:
            callback()
        return

    perms = []
    for name in ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE",
                 "READ_MEDIA_VIDEO", "READ_MEDIA_IMAGES"):
        p = getattr(Permission, name, None)
        if p is not None and p not in perms:
            perms.append(p)

    def _cb(_permissions, _grants):
        request_manage_all_files()
        if callback:
            callback()

    try:
        request_permissions(perms, _cb)
    except Exception:
        request_manage_all_files()
        if callback:
            callback()


def request_manage_all_files():
    """跳转系统“允许管理所有文件”页面（安卓 11+ 向任意文件夹写 VidPic 需要）。"""
    try:
        from jnius import autoclass
        Environment = autoclass("android.os.Environment")
        try:
            if Environment.isExternalStorageManager():
                return
        except Exception:
            pass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        Settings = autoclass("android.provider.Settings")
        ctx = PythonActivity.mActivity
        intent = None
        try:
            intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
            intent.setData(Uri.parse("package:" + ctx.getPackageName()))
        except Exception:
            intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
        intent.addFlags(0x10000000)  # FLAG_ACTIVITY_NEW_TASK
        ctx.startActivity(intent)
    except Exception:
        pass


def storage_shortcuts():
    """文件夹选择器的快捷入口列表。"""
    if is_android():
        roots = ["/storage/emulated/0", "/sdcard"]
        out = []
        for r in roots:
            if isdir(r) and r not in out:
                out.append(r)
        for sub in ("Movies", "DCIM", "Download", "Pictures", "Video"):
            p = join("/storage/emulated/0", sub)
            if isdir(p):
                out.append(p)
        return out
    home = os.path.expanduser("~")
    out = [home]
    for sub in ("Desktop", "Videos", "Downloads", "桌面", "视频", "下载"):
        p = join(home, sub)
        if isdir(p):
            out.append(p)
    return out


def format_time(sec):
    """秒 -> H:MM:SS / M:SS。"""
    try:
        sec = max(0, int(round(float(sec))))
    except Exception:
        return "0:00"
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%d:%02d" % (m, s)
