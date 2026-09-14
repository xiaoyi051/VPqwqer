# -*- coding: utf-8 -*-
"""
VidPlayer —— 本地视频播放器（Python + Kivy，可打包为安卓 APK）

功能：
1. 手动选择手机上的视频文件夹，以“文件管理器”方式浏览子文件夹/视频，点击播放；
2. 1 / 1.5 / 2 / 3 / 5 倍速切换（全部带声音、保音调、音画同步），进度条可拖动快进/后退；
3. 播放中暂停后可把“当前画面”一键设为该视频的封面；
4. 封面永久保存在所选文件夹下的 VidPic 镜像目录中（结构与视频文件夹一致，
   封面名为“视频完整文件名.png”），下次启动自动加载，未设置的视频用默认封面。

界面：可爱少女动漫风（樱粉配色 + 圆角卡片 + 可爱中文字体）。
电脑上直接运行：python main.py
安卓打包见 buildozer.spec 与《使用说明与手机安装流程.txt》。
"""
import os
from os.path import join, isdir, basename, relpath, dirname, exists, abspath

# 缩略图优先用 PIL 在加载线程解码，避免与 SDL 音频初始化发生原生竞争
os.environ.setdefault("KIVY_IMAGE", "pil,dds,sdl2")

from kivy.app import App
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.recycleview import RecycleView
from kivy.uix.image import AsyncImage, Image
from kivy.uix.label import Label
from kivy.properties import StringProperty
from kivy.clock import Clock
from kivy.cache import Cache
from kivy.lang import Builder
from kivy.factory import Factory
from kivy.metrics import dp

import vidutil
from vidcore import SpeedVideo

SPEEDS = [1.0, 1.5, 2.0, 3.0, 5.0]
SETTINGS_NAME = "settings.json"

# ------------------------------------------------------------ 可爱中文字体
# Kivy 自带 Roboto 不含中文字形，APK 内中文会显示为豆腐块；
# 注册 ZCOOL KuaiLe（OFL 授权，随包打包）覆盖默认字体名 Roboto。
FONT_PATH = join(dirname(abspath(__file__)), "fonts", "ZCOOLKuaiLe-Regular.ttf")
if exists(FONT_PATH):
    LabelBase.register("Roboto",
                       fn_regular=FONT_PATH, fn_bold=FONT_PATH,
                       fn_italic=FONT_PATH, fn_bolditalic=FONT_PATH)

# ------------------------------------------------------------ 樱粉配色（0~1 RGBA）
C_BG = (255 / 255, 241 / 255, 246 / 255, 1)        # 粉底 #FFF1F6
C_BAR = (255 / 255, 201 / 255, 221 / 255, 1)       # 浅粉 #FFC9DD
C_PINK = (255 / 255, 143 / 255, 187 / 255, 1)      # 主粉 #FF8FBB
C_PINK_D = (255 / 255, 111 / 255, 166 / 255, 1)    # 深粉 #FF6FA6
C_CARD = (1, 1, 1, 1)                              # 白卡片
C_PLUM = (138 / 255, 59 / 255, 91 / 255, 1)        # 深梅色文字 #8A3B5B
C_PLUM_SOFT = (190 / 255, 110 / 255, 145 / 255, 1)


KV = r"""
#:import dp kivy.metrics.dp

# ------------------------------------------------------------ 通用可爱按钮
<CuteButton@Button>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    background_disabled_normal: ''
    color: 1, 1, 1, 1
    opacity: .55 if self.disabled else 1
    font_size: '16sp'
    canvas.before:
        Color:
            rgba: (1, 0.56, 0.73, 1) if self.state == 'normal' else (0.98, 0.44, 0.65, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(18)]

# ------------------------------------------------------------ 倍速切换按钮
<CuteToggle@ToggleButton>:
    background_normal: ''
    background_down: ''
    background_disabled_normal: ''
    background_color: 0, 0, 0, 0
    font_size: '14sp'
    color: (1, 1, 1, 1) if self.state == 'down' else (0.54, 0.23, 0.36, 1)
    canvas.before:
        Color:
            rgba: (1, 0.56, 0.73, 1) if self.state == 'down' else (1, 1, 1, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
        Color:
            rgba: 1, 0.56, 0.73, 1
        Line:
            width: 1.6
            rounded_rectangle: (self.x + 1, self.y + 1, self.width - 2, self.height - 2, dp(14), dp(14), dp(14), dp(14), 24)

# ------------------------------------------------------------ 文件列表项（白色圆角卡片）
<FileItem>:
    orientation: 'horizontal'
    padding: '8dp'
    spacing: '10dp'
    size_hint_y: None
    height: '110dp'
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.x + dp(4), self.y + dp(3)
            size: self.width - dp(8), self.height - dp(6)
            radius: [dp(16)]
        Color:
            rgba: 1, 0.79, 0.87, 1
        Line:
            width: 1.4
            rounded_rectangle: (self.x + dp(4.5), self.y + dp(3.5), self.width - dp(9), self.height - dp(7), dp(16), dp(16), dp(16), dp(16), 24)
    AsyncImage:
        source: root.cover_source
        size_hint_x: None
        width: '124dp'
        pos_hint: {'center_y': .5}
        allow_stretch: True
        keep_ratio: True
    Label:
        text: ('[文件夹] ' if root.item_type == 'folder' else '') + root.name
        halign: 'left'
        valign: 'middle'
        max_lines: 2
        shorten: True
        shorten_from: 'right'
        bold: root.item_type == 'folder'
        font_size: '16sp'
        color: 0.54, 0.23, 0.36, 1
        text_size: self.width - dp(12), self.height
        padding: [dp(6), 0]

<BrowserList>:
    viewclass: 'FileItem'
    scroll_type: ['bars', 'content']
    bar_width: '8dp'
    bar_color: 1, 0.56, 0.73, 0.9
    bar_inactive_color: 1, 0.79, 0.87, 0.6
    RecycleBoxLayout:
        default_size_hint: 1, None
        default_size: None, '110dp'
        size_hint_y: None
        height: self.minimum_height
        orientation: 'vertical'
        spacing: '8dp'
        padding: '10dp'

# ------------------------------------------------------------ 首页
<HomeScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: '24dp'
        spacing: '14dp'
        canvas.before:
            Color:
                rgba: 1, 0.945, 0.965, 1
            Rectangle:
                pos: self.pos
                size: self.size
        Widget:
            size_hint_y: 0.18
        BoxLayout:
            size_hint_y: None
            height: '64dp'
            spacing: '10dp'
            Image:
                source: app.assets.get('heart_pink', '')
                size_hint_x: None
                width: '46dp'
                allow_stretch: True
            Label:
                text: 'VidPlayer'
                font_size: '38sp'
                bold: True
                color: 0.54, 0.23, 0.36, 1
            Image:
                source: app.assets.get('heart_pink', '')
                size_hint_x: None
                width: '46dp'
                allow_stretch: True
        Label:
            text: '少女心本地视频播放器  ·  倍速带声  ·  自定义封面'
            font_size: '15sp'
            color: 0.75, 0.35, 0.52, 1
            size_hint_y: None
            height: '30dp'
        Widget:
            size_hint_y: 0.12
        CuteButton:
            text: '选择视频文件夹'
            font_size: '20sp'
            size_hint_y: None
            height: '62dp'
            on_release: root.app().open_folder_chooser()
        CuteButton:
            id: btn_resume
            text: '进入上次选择的文件夹'
            font_size: '17sp'
            size_hint_y: None
            height: '54dp'
            disabled: True
            on_release: root.app().enter_browser()
        Label:
            id: home_status
            text: ''
            font_size: '13sp'
            color: 0.62, 0.36, 0.48, 1
            halign: 'center'
            valign: 'middle'
            shorten: True
            text_size: self.width, self.height
            size_hint_y: None
            height: '24dp'
        Widget:
        BoxLayout:
            orientation: 'vertical'
            padding: '16dp'
            spacing: '8dp'
            size_hint_y: None
            height: '118dp'
            canvas.before:
                Color:
                    rgba: 1, 1, 1, 1
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(18)]
                Color:
                    rgba: 1, 0.79, 0.87, 1
                Line:
                    width: 1.4
                    rounded_rectangle: (self.x + 1, self.y + 1, self.width - 2, self.height - 2, dp(18), dp(18), dp(18), dp(18), 24)
            Label:
                text: '自定义封面保存在所选文件夹的 VidPic 目录中'
                font_size: '13sp'
                color: 0.54, 0.23, 0.36, 1
            Label:
                text: '目录结构与视频文件夹完全一致，永久保存，下次打开自动加载'
                font_size: '13sp'
                color: 0.54, 0.23, 0.36, 1

# ------------------------------------------------------------ 文件浏览页
<BrowserScreen>:
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: 1, 0.945, 0.965, 1
            Rectangle:
                pos: self.pos
                size: self.size
        BoxLayout:
            size_hint_y: None
            height: '54dp'
            spacing: '6dp'
            padding: '8dp'
            canvas.before:
                Color:
                    rgba: 1, 0.79, 0.87, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
            CuteButton:
                id: up_btn
                text: '< 返回上级'
                size_hint_x: None
                width: '104dp'
                font_size: '14sp'
                on_release: root.up_level()
            CuteButton:
                text: '更换文件夹'
                size_hint_x: None
                width: '110dp'
                font_size: '14sp'
                on_release: root.app().open_folder_chooser()
            Label:
                id: path_label
                text: ''
                halign: 'left'
                valign: 'middle'
                shorten: True
                bold: True
                font_size: '14sp'
                color: 0.54, 0.23, 0.36, 1
                text_size: self.width - dp(8), self.height
        BrowserList:
            id: file_list
        Label:
            id: empty_tip
            text: '该文件夹下没有视频哦～'
            halign: 'center'
            font_size: '15sp'
            color: 0.62, 0.36, 0.48, 1
            opacity: 0
            size_hint_y: None
            height: '0dp'

# ------------------------------------------------------------ 播放页
<PlayerScreen>:
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: 0.06, 0.05, 0.07, 1
            Rectangle:
                pos: self.pos
                size: self.size
        RelativeLayout:
            id: video_area
            SpeedVideo:
                id: video
            BoxLayout:
                orientation: 'horizontal'
                pos_hint: {'top': 1}
                size_hint_y: None
                height: '48dp'
                spacing: '6dp'
                padding: '6dp'
                canvas.before:
                    Color:
                        rgba: 1, 0.62, 0.78, 0.92
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [0, 0, dp(16), dp(16)]
                CuteButton:
                    text: '< 返回'
                    size_hint_x: None
                    width: '92dp'
                    font_size: '14sp'
                    on_release: root.back_to_browser()
                Label:
                    id: video_name
                    text: ''
                    halign: 'left'
                    valign: 'middle'
                    shorten: True
                    bold: True
                    font_size: '15sp'
                    color: 1, 1, 1, 1
                    text_size: self.width - dp(8), self.height
            BoxLayout:
                orientation: 'vertical'
                pos_hint: {'bottom': 1}
                size_hint_y: None
                height: '118dp'
                spacing: '6dp'
                padding: ['10dp', '8dp', '10dp', '10dp']
                canvas.before:
                    Color:
                        rgba: 1, 0.90, 0.94, 0.97
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(20), dp(20), 0, 0]
                BoxLayout:
                    size_hint_y: None
                    height: '46dp'
                    spacing: '6dp'
                    CuteButton:
                        id: btn_play
                        text: '暂停'
                        size_hint_x: None
                        width: '80dp'
                        font_size: '14sp'
                        on_release: root.toggle_play()
                    Label:
                        id: cur_time
                        text: '0:00'
                        size_hint_x: None
                        width: '62dp'
                        font_size: '13sp'
                        color: 0.54, 0.23, 0.36, 1
                    Slider:
                        id: seek_bar
                        min: 0
                        max: 1
                        value: 0
                        step: 0
                    Label:
                        id: total_time
                        text: '0:00'
                        size_hint_x: None
                        width: '62dp'
                        font_size: '13sp'
                        color: 0.54, 0.23, 0.36, 1
                BoxLayout:
                    size_hint_y: None
                    height: '48dp'
                    spacing: '4dp'
                    BoxLayout:
                        id: speed_box
                        spacing: '4dp'
                    CuteButton:
                        text: '暂停并设为封面'
                        size_hint_x: None
                        width: '132dp'
                        font_size: '12sp'
                        on_release: root.set_cover()
"""


# ============================================================== 列表项
class FileItem(BoxLayout):
    item_type = StringProperty("video")     # folder / video
    name = StringProperty("")
    path = StringProperty("")
    cover_source = StringProperty("")

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            app = App.get_running_app()
            if app is not None:
                app.open_item(self.path, self.item_type)
                return True
        return super(FileItem, self).on_touch_up(touch)


class BrowserList(RecycleView):
    pass


# ============================================================== 各页面
class HomeScreen(Screen):
    def app(self):
        return App.get_running_app()


class BrowserScreen(Screen):
    def app(self):
        return App.get_running_app()

    def on_pre_enter(self, *a):
        self.rescan()

    def rescan(self):
        app = self.app()
        root = app.root_folder
        data = []
        if root and isdir(root):
            folders, videos = vidutil.list_folder(root, app.current_rel)
            base = join(root, app.current_rel) if app.current_rel else root
            for name in folders:
                data.append({
                    "item_type": "folder",
                    "name": name,
                    "path": join(base, name),
                    "cover_source": app.assets["folder"],
                })
            for name in videos:
                p = join(base, name)
                cp = vidutil.cover_path_for(root, p)
                data.append({
                    "item_type": "video",
                    "name": name,
                    "path": p,
                    "cover_source": cp if exists(cp) else app.assets["cover"],
                })
            self.ids.path_label.text = base
            self.ids.up_btn.disabled = (app.current_rel == "")
            self.ids.empty_tip.opacity = 0 if data else 1
            self.ids.empty_tip.height = "0dp" if data else "60dp"
        self.ids.file_list.data = data

    def up_level(self):
        app = self.app()
        rel = app.current_rel
        if not rel:
            app.sm.current = "home"
            return
        parent = dirname(rel.replace("/", os.sep))
        app.current_rel = "" if parent in (".", "") else parent
        app.save_current_settings()
        self.rescan()


class PlayerScreen(Screen):
    def __init__(self, **kw):
        super(PlayerScreen, self).__init__(**kw)
        self.current_path = None
        self._scrubbing = False
        self._tick = None
        self._speed_buttons = {}

    def app(self):
        return App.get_running_app()

    def on_enter(self):
        app = self.app()
        for sp in SPEEDS:
            if sp not in self._speed_buttons:
                tb = Factory.CuteToggle(
                    text=("%gx" % sp).replace(".0x", "x"),
                    group="speed",
                    state=("down" if sp == 1.0 else "normal"),
                    size_hint_x=None,
                    width="46dp",
                )
                tb.bind(on_release=lambda _b, v=sp: self.on_speed(v))
                self.ids.speed_box.add_widget(tb)
                self._speed_buttons[sp] = tb
        if not getattr(self, "_slider_bound", False):
            bar = self.ids.seek_bar
            bar.bind(on_touch_down=self._slider_down, on_touch_up=self._slider_up)
            self._slider_bound = True
        # 粉色进度条素材
        bar = self.ids.seek_bar
        bar.background_horizontal = app.assets["slider_track"]
        bar.background_disabled_horizontal = app.assets["slider_track"]
        bar.cursor_image = app.assets["slider_cursor"]
        bar.cursor_disabled_image = app.assets["slider_cursor"]
        bar.cursor_size = (dp(26), dp(26))
        bar.background_border = (10, 8, 10, 8)
        bar.padding = dp(7)

    # ------------------------------------------------ 播放控制
    def play_video(self, path):
        self.current_path = path
        self.ids.video_name.text = basename(path)
        self._reset_speed_ui()
        bar = self.ids.seek_bar
        bar.value = 0
        bar.max = 1
        self.ids.cur_time.text = "0:00"
        self.ids.total_time.text = "0:00"
        ok = self.ids.video.load(path, autoplay=True)
        if not ok:
            self.app().show_message("无法播放", self.ids.video.last_error or "解码器打开失败")
        else:
            Clock.schedule_once(self._check_open_failed, 2.0)
        if self._tick:
            self._tick.cancel()
        self._tick = Clock.schedule_interval(self.tick, 0.05)

    def _check_open_failed(self, _dt):
        v = self.ids.video
        if self.current_path is not None and v.state == "stop" and v.last_error:
            self.app().show_message("无法播放", v.last_error)

    def on_leave(self, *a):
        if self._tick:
            self._tick.cancel()
            self._tick = None
        self.ids.video.unload()
        self.current_path = None

    def toggle_play(self):
        v = self.ids.video
        if v.state == "stop":
            v.play()
        else:
            v.toggle()

    def on_speed(self, sp):
        self._speed_buttons[sp].state = "down"
        self.ids.video.set_speed(sp)

    def _reset_speed_ui(self):
        for sp, tb in self._speed_buttons.items():
            tb.state = "down" if sp == 1.0 else "normal"
        self.ids.video.set_speed(1.0)

    # ------------------------------------------------ 进度条
    def _slider_down(self, slider, touch):
        if slider.collide_point(*touch.pos):
            self._scrubbing = True

    def _slider_up(self, slider, touch):
        if self._scrubbing and slider.collide_point(*touch.pos):
            self.ids.video.seek(slider.value)
        self._scrubbing = False

    def tick(self, _dt):
        v = self.ids.video
        bar = self.ids.seek_bar
        if v.duration > 0 and bar.max != v.duration:
            bar.max = v.duration
            self.ids.total_time.text = vidutil.format_time(v.duration)
        pos = v.position
        if not self._scrubbing:
            bar.value = min(pos, bar.max)
        self.ids.cur_time.text = vidutil.format_time(pos)
        if v.state == "playing":
            self.ids.btn_play.text = "暂停"
        elif v.state == "paused":
            self.ids.btn_play.text = "播放"
        else:
            self.ids.btn_play.text = "重播"
            if not self._scrubbing and v.duration:
                bar.value = v.duration

    # ------------------------------------------------ 封面
    def set_cover(self):
        if not self.current_path:
            return
        v = self.ids.video
        v.pause()  # 按需求：先暂停，再截取当前画面
        Clock.schedule_once(self._capture_cover, 0.25)

    def _capture_cover(self, _dt):
        app = self.app()
        cover = vidutil.ensure_cover_dir(app.root_folder, self.current_path)
        ok = self.ids.video.grab_cover(cover)
        if ok:
            # 清掉 Kivy 图片缓存，保证列表里立刻显示新封面
            Cache.remove("kv.image", cover)
            Cache.remove("kv.texture", cover)
            app.show_message("封面已保存",
                             "封面图片已写入：\n" + relpath(cover, app.root_folder))
        else:
            app.show_message("设置失败", "当前没有可用画面，请稍等画面出现后再试。")

    def back_to_browser(self):
        self.app().sm.current = "browser"


# ============================================================== 应用
class VidPlayerApp(App):
    def build(self):
        self.title = "VidPlayer"
        # 主题素材必须在 KV 加载前就绪：KV 中 app.assets.get(...) 只在规则
        # 求值时读取一次，dict 后续变更不会触发重新绑定
        self.assets = vidutil.ensure_default_assets(self.user_data_dir)
        Builder.load_string(KV)
        self.sm = ScreenManager(transition=NoTransition())
        self.sm.add_widget(HomeScreen(name="home"))
        self.sm.add_widget(BrowserScreen(name="browser"))
        self.sm.add_widget(PlayerScreen(name="player"))
        Window.bind(on_keyboard=self._on_key)
        self.root_folder = ""
        self.current_rel = ""
        return self.sm

    def on_start(self):
        self.assets = vidutil.ensure_default_assets(self.user_data_dir)
        self.settings_path = join(self.user_data_dir, SETTINGS_NAME)
        data = vidutil.load_settings(self.settings_path)
        root = data.get("root", "")
        if root and isdir(root):
            self.root_folder = root
            self.current_rel = data.get("last_rel", "") or ""
        self._refresh_home()
        if vidutil.is_android():
            vidutil.request_android_permissions()

    def on_pause(self):
        # 安卓切后台时暂停播放
        if self.sm.current == "player":
            self.sm.get_screen("player").ids.video.pause()
        return True

    def on_stop(self):
        try:
            self.sm.get_screen("player").ids.video.unload()
        except Exception:
            pass

    # ------------------------------------------------ 弹窗美化
    def style_popup(self, popup):
        if self.assets.get("popup_bg"):
            popup.background = self.assets["popup_bg"]
            popup.border = (18, 18, 18, 18)
        popup.separator_color = C_PINK
        popup.title_color = C_PLUM

    # ------------------------------------------------ 硬件/ESC 返回键
    def _on_key(self, _window, key, _scancode, _codepoint, _mods):
        if key == 27:
            cur = self.sm.current
            if cur == "player":
                self.sm.get_screen("player").back_to_browser()
                return True
            if cur == "browser":
                b = self.sm.get_screen("browser")
                if self.current_rel:
                    b.up_level()
                else:
                    self.sm.current = "home"
                return True
        return False

    # ------------------------------------------------ 首页状态
    def _refresh_home(self):
        home = self.sm.get_screen("home")
        btn = home.ids.btn_resume
        status = home.ids.home_status
        if self.root_folder and isdir(self.root_folder):
            btn.disabled = False
            status.text = "上次选择：" + self.root_folder
        else:
            btn.disabled = True
            status.text = "尚未选择视频文件夹"

    def save_current_settings(self):
        vidutil.save_settings(self.settings_path, {
            "root": self.root_folder,
            "last_rel": self.current_rel,
        })

    # ------------------------------------------------ 文件夹选择
    def open_folder_chooser(self):
        if vidutil.is_android():
            vidutil.request_android_permissions()
        start = self.root_folder if self.root_folder and isdir(self.root_folder) else None
        if start is None:
            sc = vidutil.storage_shortcuts()
            start = sc[0] if sc else os.path.expanduser("~")

        def dir_filter(folder, name):
            return isdir(join(folder, name))

        fc = FileChooserListView(path=start, dirselect=True,
                                 filters=[dir_filter], show_hidden=False)
        box = BoxLayout(orientation="vertical", spacing="6dp", padding="6dp")

        sc_box = BoxLayout(size_hint_y=None, height="42dp", spacing="6dp")
        for p in vidutil.storage_shortcuts()[:5]:
            b = Factory.CuteButton(text=basename(p) or p, font_size="12sp")
            b.bind(on_release=lambda _b, x=p: fc._set_path(x))
            sc_box.add_widget(b)
        box.add_widget(sc_box)
        box.add_widget(fc)

        btns = BoxLayout(size_hint_y=None, height="50dp", spacing="10dp")
        btn_cancel = Factory.CuteButton(text="取消")
        btn_ok = Factory.CuteButton(text="选择此文件夹")
        btns.add_widget(btn_cancel)
        btns.add_widget(btn_ok)
        box.add_widget(btns)

        popup = Popup(title="选择视频文件夹（点选文件夹后点“选择此文件夹”）",
                      content=box, size_hint=(0.97, 0.95))
        self.style_popup(popup)
        btn_cancel.bind(on_release=popup.dismiss)

        def confirm(_b=None):
            sel = fc.selection
            chosen = sel[-1] if sel else fc.path
            if chosen and isdir(chosen):
                self._on_folder_chosen(chosen)
                popup.dismiss()
            else:
                self.show_message("提示", "请先点选一个文件夹")

        btn_ok.bind(on_release=confirm)
        popup.open()

    def _on_folder_chosen(self, path):
        self.root_folder = path
        self.current_rel = ""
        vidutil.ensure_mirror(path)
        self.save_current_settings()
        self._refresh_home()
        self.enter_browser()

    def enter_browser(self):
        if not self.root_folder or not isdir(self.root_folder):
            self.show_message("提示", "文件夹不存在，请重新选择。")
            self._refresh_home()
            return
        vidutil.ensure_mirror(self.root_folder)
        self.sm.current = "browser"

    # ------------------------------------------------ 列表点击
    def open_item(self, path, item_type):
        if self.sm.current != "browser":
            return
        if item_type == "folder":
            self.current_rel = relpath(path, self.root_folder)
            self.save_current_settings()
            self.sm.get_screen("browser").rescan()
        else:
            self.save_current_settings()
            self.sm.current = "player"
            self.sm.get_screen("player").play_video(path)

    # ------------------------------------------------ 通用提示
    def show_message(self, title, text):
        box = BoxLayout(orientation="vertical", spacing="12dp", padding="14dp")
        lab = Label(text=text, halign="center", valign="middle",
                    color=C_PLUM, font_size="15sp",
                    text_size=(None, None))
        lab.bind(width=lambda i, v: setattr(i, "text_size", (v - 20, None)))
        btn = Factory.CuteButton(text="知道了", size_hint_y=None, height="48dp")
        box.add_widget(lab)
        box.add_widget(btn)
        popup = Popup(title=title, content=box, size_hint=(0.8, 0.5), auto_dismiss=True)
        self.style_popup(popup)
        btn.bind(on_release=popup.dismiss)
        popup.open()


if __name__ == "__main__":
    VidPlayerApp().run()
