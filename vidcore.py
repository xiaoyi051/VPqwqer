# -*- coding: utf-8 -*-
"""
vidcore.py —— 支持倍速播放（带声音、音画同步）的 Kivy 视频控件 SpeedVideo

线程模型（严格单线程串行调用解码器，避免原生崩溃）：
* 取帧线程（pump thread）是唯一调用 ffpyplayer 的线程：打开/重开/seek/
  暂停/变速/取帧/关闭全部在该线程内完成；
* 主线程只下发命令标志（播放、暂停、seek、变速、重播），读取缓存的播放
  位置，不直接碰解码器；
* 帧像素在取帧线程内立即拷贝成 bytes，再由主线程 blit 到 GL 纹理。

倍速声音方案（重点）：
* ffpyplayer 没有 set_speed，但 ff_opts 支持音频滤镜 'af'。倍速时用
  FFmpeg 的 atempo 滤镜（保音调变速）重开播放器：
      1.5x -> atempo=1.5；2x -> atempo=2.0；
      3x -> atempo=2.0,atempo=1.5；5x -> atempo=2.0,atempo=2.0,atempo=1.25
  音频经滤镜后内容时间缩短，SDL 以硬件速率播放 => 声音以倍速、保音调播出。
* 倍速下视频帧不依赖音频时钟调度（infbuf 预读时音频时钟初期滞后，
  remaining_time 不可靠），改用自建墙钟 PTS 时钟节流，与 atempo 音频
  同为“内容时间 = 墙钟 × 倍速”，天然同步；有音轨等音频 eof，无音轨用
  “片末持续无新帧”兜底结束。
* 1.0 倍速走原生音频时钟节奏（有声音、音画同步）。
* grab_cover() 把当前显示纹理保存为封面 PNG（方向正向）。
"""
import os
import threading
import time

if os.environ.get("VID_DEBUG"):
    def _dbg(*a):
        print("[vidcore]", *a, flush=True)
else:
    def _dbg(*a):
        pass

from kivy.clock import Clock
from kivy.uix.image import Image
from kivy.graphics.texture import Texture
from kivy.properties import NumericProperty, StringProperty

from ffpyplayer.player import MediaPlayer


def atempo_chain(speed):
    """atempo 单级只支持 0.5~2.0，超出范围串联多级。"""
    chain = []
    s = float(speed)
    while s > 2.0 + 1e-6:
        chain.append("atempo=2.0")
        s /= 2.0
    chain.append("atempo=%.4f" % s)
    return ",".join(chain)


class SpeedVideo(Image):
    # state: 'stop' / 'playing' / 'paused'
    state = StringProperty("stop")
    duration = NumericProperty(0.0)
    speed = NumericProperty(1.0)
    last_error = StringProperty("")

    def __init__(self, **kw):
        super(SpeedVideo, self).__init__(**kw)
        self.allow_stretch = True
        self.keep_ratio = True

        self._path = ""
        self._player = None
        self._thread = None
        self._quit = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()

        # 主线程下发、取帧线程消费的命令/状态
        self._seek_target = None       # 需要 seek 到的秒数
        self._want_paused = None       # None=不变；True/False=期望暂停状态
        self._want_speed = None        # 期望倍速
        self._want_restart = False     # 期望从头重播（eof 后）
        self._want_play = False        # 首次打开后是否自动播放

        # 取帧线程维护的播放状态
        self._cur_speed = 1.0
        self._last_pts = -1.0
        self._pts_live = 0.0
        self._anchor_wall = 0.0
        self._anchor_pts = 0.0
        self._needs_resync = False
        self._open_error = False
        self._stall_since = None

        self._pending_frame = None     # ((w,h), rgba_bytes)
        self._tex_size = None
        self._blit_trigger = Clock.create_trigger(self._blit_frame, 0)

    # ================================================================== 生命周期
    def load(self, path, autoplay=True):
        """打开视频。MediaPlayer 在取帧线程内创建（解码器调用全部串行化）。"""
        self.unload()
        time.sleep(0.1)   # 给 SDL 音频设备一点释放时间
        self._path = path
        self.last_error = ""
        self.duration = 0.0
        self.speed = 1.0
        self._cur_speed = 1.0
        self._last_pts = -1.0
        self._pts_live = 0.0
        self._pending_frame = None
        self._tex_size = None
        self._open_error = False
        self._seek_target = None
        self._want_speed = None
        self._want_paused = None
        self._want_restart = False
        self._stall_since = None
        self._quit.clear()
        self._want_play = autoplay
        self.state = "playing" if autoplay else "paused"
        self._thread = threading.Thread(target=self._pump_loop, daemon=True)
        self._thread.start()
        return True

    def unload(self):
        """关闭视频、释放解码器（close_player 在取帧线程内完成）。"""
        _dbg("unload: begin")
        self._quit.set()
        self._wake.set()
        t = self._thread
        if t is not None:
            t.join(timeout=3.0)
            if t.is_alive():
                _dbg("unload: pump thread still alive after join")
        self._thread = None
        self._player = None
        self._pending_frame = None
        self._seek_target = None
        self._want_paused = None
        self._want_speed = None
        self._want_restart = False
        self.state = "stop"

    def _player_callback(self, selector, value):
        if selector in ("read:error",) and self._last_pts < 0:
            self._open_error = True
            self._wake.set()

    # ================================================================== 主线程 API（不直接调用 ffpyplayer）
    def play(self):
        if self.state == "stop":
            with self._lock:
                self._want_restart = True
                self._seek_target = 0.0
                self._want_paused = False
            self.state = "playing"
        else:
            with self._lock:
                self._want_paused = False
            self.state = "playing"
        self._wake.set()

    def pause(self):
        with self._lock:
            self._want_paused = True
        self.state = "paused"
        self._wake.set()

    def toggle(self):
        if self.state == "playing":
            self.pause()
        else:
            self.play()

    def seek(self, pts):
        """拖动进度条（秒），由取帧线程执行。"""
        pts = max(0.0, float(pts))
        if self.duration:
            pts = min(pts, self.duration)
        with self._lock:
            self._seek_target = pts
        self._wake.set()

    def set_speed(self, speed):
        """切换倍速（带声音：atempo 滤镜重开；视频按墙钟 PTS 时钟同步）。"""
        speed = float(speed)
        with self._lock:
            self._want_speed = speed
        self.speed = speed   # 立即反映到 UI，实际切换由取帧线程完成
        self._wake.set()

    @property
    def position(self):
        """当前播放位置（秒）。纯 Python 读取，线程安全。"""
        if self.state == "paused":
            return max(self._last_pts, 0.0)
        if self._cur_speed > 1.0:
            t = self._anchor_pts + (time.monotonic() - self._anchor_wall) * self._cur_speed
            dur = self.duration
            if dur:
                t = min(t, dur)
            return max(t, 0.0)
        return max(self._pts_live, 0.0)

    def grab_cover(self, path):
        """保存当前画面为 PNG。纹理创建时已 flip_vertical() 翻转 tex_coords
        保证屏幕正立，像素内存仍是原始上->下顺序，保存时不能再翻转。"""
        if self.texture is None:
            return False
        try:
            self.texture.save(path, flipped=False)
            return True
        except Exception:
            return False

    # ================================================================== 取帧线程
    def _sleep(self, sec):
        if sec <= 0:
            return
        self._wake.wait(min(sec, 0.2))
        self._wake.clear()

    def _pump_loop(self):
        p = None
        try:
            p = self._open_player(self._cur_speed)
            if p is None:
                return
            self._player = p
            if not self._prepare_player(p, start_pts=0.0,
                                        want_paused=not self._want_play):
                return
            self._pump_body(p)
        except Exception as e:
            _dbg("pump: exception", e)
        finally:
            p = self._player
            if p is not None:
                try:
                    p.close_player()
                except Exception:
                    pass
            self._player = None
            _dbg("pump: player closed")

    def _ff_opts(self, speed):
        opts = {"out_fmt": "rgba", "paused": True, "infbuf": True}
        if speed and speed > 1.0:
            # atempo：保音调的音频变速；无音轨时滤镜被忽略，无副作用
            opts["af"] = atempo_chain(speed)
        return opts

    def _open_player(self, speed):
        """构造 MediaPlayer 并等待元数据，失败返回 None。"""
        _dbg("open: creating MediaPlayer speed=%s" % speed)
        try:
            p = MediaPlayer(self._path,
                            callback=self._player_callback,
                            ff_opts=self._ff_opts(speed),
                            thread_lib="SDL",
                            loglevel="error")
        except Exception as e:
            _dbg("open: construct failed", e)
            Clock.schedule_once(self._on_open_failed, 0)
            return None
        t0 = time.monotonic()
        dur = 0.0
        while not self._quit.is_set():
            try:
                dur = p.get_metadata().get("duration") or 0.0
            except Exception:
                dur = 0.0
            if dur > 0:
                break
            if self._open_error:
                Clock.schedule_once(self._on_open_failed, 0)
                return None
            if time.monotonic() - t0 > 8:
                break
            self._sleep(0.02)
        _dbg("open: metadata dur=%s" % dur)
        if dur > 0:
            Clock.schedule_once(lambda dt: setattr(self, "duration", dur), -1)
        elif self._open_error or p.get_metadata().get("src_vid_size") == (0, 0):
            Clock.schedule_once(self._on_open_failed, 0)
            return None
        return p

    def _prepare_player(self, p, start_pts, want_paused):
        """seek 到起始位置并设置暂停/播放状态；暂停时抓出首帧。"""
        self._last_pts = -1.0
        self._pts_live = start_pts
        if want_paused:
            self._do_seek_and_surface(p, start_pts, True)
        else:
            try:
                p.seek(start_pts, relative=False, accurate=True)
                p.set_pause(False)
            except Exception:
                pass
        self._reset_clock(start_pts)
        return True

    def _reset_clock(self, start_pts):
        """重置墙钟 PTS 时钟（倍速时节流视频帧用）。"""
        self._anchor_pts = max(start_pts, 0.0)
        self._anchor_wall = time.monotonic()
        self._stall_since = None

    def _reopen(self, new_speed, start_pts=None):
        """在取帧线程内以新倍速（atempo 滤镜）重开播放器。
        start_pts=None 时保持当前位置，否则从指定位置开始。"""
        old = self._player
        if start_pts is None:
            cur = max(self._last_pts, self._pts_live, 0.0)
            if self.duration:
                cur = min(cur, self.duration)
            want_paused = (self.state == "paused")
        else:
            cur = start_pts
            want_paused = False
        if old is not None:
            try:
                old.close_player()
            except Exception:
                pass
            self._player = None
        time.sleep(0.12)   # 让 SDL 音频设备完成释放
        self._open_error = False
        self._cur_speed = new_speed
        p = self._open_player(new_speed)
        if p is None:
            return None
        self._player = p
        if not self._prepare_player(p, cur, want_paused):
            return None
        _dbg("reopen: speed=%s cur=%.2f paused=%s" % (new_speed, cur, want_paused))
        return p

    def _pump_body(self, p):
        idle = 0
        while not self._quit.is_set():
            p = self._player if self._player is not None else p

            # ---- 重播（eof 后从头）：合并挂起的变速命令，只重开一次 ----
            if self._want_restart:
                with self._lock:
                    self._want_restart = False
                    ws = self._want_speed
                    self._want_speed = None
                    self._seek_target = None
                if ws is not None:
                    self._cur_speed = ws
                np = self._reopen(self._cur_speed, start_pts=0.0)
                if np is None:
                    return
                p = np
                idle = 0

            # ---- 暂停/恢复 ----
            with self._lock:
                want_paused = self._want_paused
                self._want_paused = None
            if want_paused is not None and bool(p.get_pause()) != want_paused:
                if want_paused:
                    p.set_pause(True)
                else:
                    p.set_pause(False)
                    if self._needs_resync:
                        self._needs_resync = False
                        self._apply_seek(p, max(self._last_pts, 0.0), False)
                        self._reset_clock(max(self._last_pts, 0.0))
                _dbg("pump: set_pause", want_paused)

            # ---- 倍速：atempo 滤镜重开（1x 原生、>1x 带保音调声音）----
            with self._lock:
                want_speed = self._want_speed
                self._want_speed = None
            if want_speed is not None and abs(want_speed - self._cur_speed) > 1e-6:
                if self.state == "stop":
                    self._cur_speed = want_speed   # 重播时生效
                else:
                    np = self._reopen(want_speed)
                    if np is None:
                        return
                    p = np
                _dbg("pump: speed ->", want_speed)

            # ---- seek ----
            with self._lock:
                tgt = self._seek_target
                self._seek_target = None
            if tgt is not None and self.state != "stop":
                was_paused = bool(p.get_pause())
                self._last_pts = -1.0
                self._do_seek_and_surface(p, tgt, was_paused)
                self._reset_clock(tgt)
                self._pts_live = tgt
                idle = 0

            # ---- 取帧 ----
            try:
                frame, val = p.get_frame()
            except Exception:
                self._sleep(0.02)
                continue

            if val == "eof":
                Clock.schedule_once(self._on_eos, 0)
                self._sleep(0.25)
                continue
            if val == "paused":
                self._pts_live = max(self._last_pts, 0.0)
                self._sleep(0.1)
                continue

            if frame is not None:
                img, pts = frame
                if pts <= self._last_pts + 1e-3:
                    # 首帧预卷或 seek 后的重复/陈旧帧
                    self._sleep(0.005)
                    continue
                if self.state == "playing":
                    if self._cur_speed > 1.0:
                        # 倍速：按墙钟 PTS 时钟节流（与 atempo 音频同速，天然同步）
                        target = self._anchor_pts + \
                            (time.monotonic() - self._anchor_wall) * self._cur_speed
                        if pts > target:
                            self._sleep((pts - target) / self._cur_speed)
                    elif isinstance(val, float) and val > 0:
                        # 1x：跟随原生音频时钟
                        self._sleep(val)
                self._last_pts = pts
                self._store_frame(img)
                self._refresh_live_pts()
                self._stall_since = None
                idle = 0
                # 倍速片末兜底（无音轨时等不到音频 eof）
                if self._cur_speed > 1.0 and self.duration and \
                        pts >= self.duration - 0.12:
                    if self._confirm_video_end(p, pts, self.duration):
                        Clock.schedule_once(self._on_eos, 0)
                        self._sleep(0.25)
            else:
                self._refresh_live_pts()
                if self._cur_speed > 1.0 and self.duration and \
                        self._last_pts >= self.duration - 0.12 and \
                        self.state == "playing":
                    now = time.monotonic()
                    if self._stall_since is None:
                        self._stall_since = now
                    elif now - self._stall_since > 0.6:
                        if self._confirm_video_end(p, self._last_pts, self.duration):
                            Clock.schedule_once(self._on_eos, 0)
                            self._sleep(0.25)
                        self._stall_since = None
                    idle += 1
                wait_s = 0.005
                if isinstance(val, float) and val > 0:
                    # 倍速下不按音频时钟等待（初期 val 会被预读缓冲放大）
                    wait_s = min(val, 0.01 if self._cur_speed > 1.0 else 0.05)
                self._sleep(wait_s)

    # -------------------------------------------------------------- 节奏
    def _refresh_live_pts(self):
        if self._cur_speed > 1.0:
            t = self._anchor_pts + (time.monotonic() - self._anchor_wall) * self._cur_speed
            self._pts_live = min(t, self.duration) if self.duration else t
        else:
            p = self._player
            try:
                self._pts_live = p.get_pts() if p is not None else max(self._last_pts, 0.0)
            except Exception:
                self._pts_live = max(self._last_pts, 0.0)

    def _apply_seek(self, p, tgt, was_paused):
        try:
            p.seek(tgt, relative=False, accurate=True)
        except Exception:
            pass

    def _do_seek_and_surface(self, p, tgt, was_paused):
        try:
            p.seek(tgt, relative=False, accurate=True)
        except Exception:
            return
        if was_paused:
            self._needs_resync = True
        else:
            self._needs_resync = False
        if not was_paused:
            return
        try:
            p.set_volume(0.0)
            p.set_pause(False)
            try:
                deadline = time.monotonic() + 2.5
                last_frame = None
                while time.monotonic() < deadline:
                    frame, val = p.get_frame(show=False)
                    if val in ("paused", "eof"):
                        break
                    if frame is None:
                        time.sleep(0.01)
                        continue
                    last_frame = frame
                    if frame[1] >= tgt - 0.05:
                        break
                if last_frame is None:
                    ff, _v = p.get_frame(force_refresh=True)
                    last_frame = ff
                if last_frame is not None:
                    self._store_frame(last_frame[0])
                    self._last_pts = last_frame[1]
            finally:
                p.set_pause(True)
                p.set_volume(1.0)
        except Exception:
            pass

    def _confirm_video_end(self, p, last_pts, dur):
        """倍速片末确认：0.25s 内没有更新的视频帧即判定播完
        （有音轨时音频 eof 也会触发结束，这里是无音轨兜底）。"""
        t1 = time.monotonic()
        newest = last_pts
        while time.monotonic() - t1 < 0.25 and not self._quit.is_set():
            try:
                nf, nv = p.get_frame()
            except Exception:
                break
            if nv == "eof":
                return True
            if nf is not None:
                img, pts = nf
                if pts > newest + 1e-3:
                    newest = pts
                    self._store_frame(img)
                    self._last_pts = pts
                    if newest < dur - 0.12:
                        return False
            else:
                time.sleep(0.01)
        return newest >= dur - 0.12

    # ================================================================== 帧像素与纹理
    def _store_frame(self, img):
        try:
            size = img.get_size()
            data = bytes(img.to_memoryview()[0])
            self._pending_frame = (size, data)
            if not getattr(self, "_dbg_stored", False):
                self._dbg_stored = True
                _dbg("pump: first frame stored", size)
            self._blit_trigger()
        except Exception:
            pass

    def _blit_frame(self, *_a):
        pending = self._pending_frame
        if pending is None:
            return
        if not getattr(self, "_dbg_blitted", False):
            self._dbg_blitted = True
            _dbg("main: first blit")
        (w, h), data = pending
        if self.texture is None or self._tex_size != (w, h):
            tex = Texture.create(size=(w, h), colorfmt="rgba")
            tex.flip_vertical()
            self.texture = tex
            self._tex_size = (w, h)
        self.texture.blit_buffer(data, colorfmt="rgba", bufferfmt="ubyte")
        self.canvas.ask_update()

    # ================================================================== 结束/失败
    def _on_eos(self, *_a):
        if self.state == "stop":
            return
        self.state = "stop"
        self._want_paused = True

    def _on_open_failed(self, *_a):
        self.last_error = "无法打开视频（文件不存在、已损坏，或编码格式不受支持）"
        self.state = "stop"
