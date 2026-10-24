#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows 桌面悬浮宠物 - iKun 桌面精灵
使用 PyQt5 + pynput 实现，支持全局键盘联动、状态自动轮换、气泡提示等。
"""

import sys
import os
import random
import math
import time
from enum import Enum, auto

from PyQt5.QtWidgets import (
    QApplication, QWidget, QMenu, QAction, QSystemTrayIcon
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRect, QRectF, pyqtSignal
)
from PyQt5.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QFontMetrics,
    QPixmap, QImage, QIcon, QPainterPath, QGuiApplication, QRegion
)

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

# ============================================================
# 配置常量
# ============================================================
WINDOW_SIZE = 220          # 窗口大小（预留顶部空间给状态气泡）
PET_SIZE = 150             # 宠物绘制区域大小
ANIMATION_FPS = 30         # 活跃状态帧率（开心 / 被戳 / 打字）
IDLE_FPS = 12              # 发呆 / 困倦 时的低帧率，显著降低空转 CPU
STATE_INTERVAL_MIN = 10000 # 状态自动切换最小间隔（毫秒）
STATE_INTERVAL_MAX = 20000 # 状态自动切换最大间隔（毫秒）
BLINK_INTERVAL = 3000      # 眨眼间隔（毫秒）
BLINK_DURATION = 200       # 单次眨眼时长（毫秒）
TYPING_TIMEOUT = 2000      # 停止打字超过 2 秒后恢复发呆（毫秒）
TYPING_FATIGUE_TIME = 30000  # 连续打字每满 30 秒触发一次疲劳提示（毫秒）
POKE_RECOVER_TIME = 1500   # 被戳状态持续时间（毫秒）
STRETCH_DURATION = 2000    # 伸懒腰动画时长（毫秒）
BUBBLE_SHOW_DURATION = 3000  # 气泡显示时长（毫秒）
CLICK_THRESHOLD = 5.0      # 判定"单击"的最大移动距离（像素，欧氏距离）
MAX_BORDER_TRIM = 8        # 最多裁掉多少像素的"同色边框带"（源图顶部灰边等）

# ---- Windows 点击穿透相关常量 ----
PYWIN = sys.platform == "win32"
WM_NCHITTEST = 0x0084      # 命中测试消息
HTTRANSPARENT = -1         # 让系统把鼠标事件交给下层窗口
if PYWIN:
    import ctypes
    from ctypes import wintypes

# 疲劳提示文案，固定顺序轮播
BUBBLE_TEXTS = ["唱🎤", "跳💃", "Rap🎶", "打🏀"]
# 被戳专属文案
BUBBLE_POKE_TEXT = "你干嘛~"


def _find_image_path():
    """
    多路径查找 ikun.jpg，兼容源码运行与 PyInstaller 打包后的运行方式。
    不再包含任何开发机绝对路径：分发给别人时不会误加载无关图片。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "images", "ikun.jpg"),
        os.path.join(here, "images", "ikun.jpg"),
        os.path.join(os.path.dirname(sys.executable), "images", "ikun.jpg"),
        os.path.join(os.getcwd(), "images", "ikun.jpg"),
        os.path.join(os.path.dirname(here), "images", "ikun.jpg"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _screen_available_geometry(anchor=None):
    """返回锚点所在屏幕（默认主屏）的可用区域，已扣除任务栏，支持多显示器。"""
    screen = None
    if anchor is not None:
        screen = QGuiApplication.screenAt(anchor)
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def _hide_own_console():
    """
    隐藏黑框，但只在本进程拥有该控制台时动手。
    原实现无条件调用 GetConsoleWindow()+ShowWindow，若用户是在 cmd/PowerShell
    里敲 python desktop_pet.py 启动的，会把用户自己的终端窗口一起隐藏掉。
    """
    if not PYWIN:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == kernel32.GetCurrentProcessId():
            user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


# ============================================================
# 状态枚举
# ============================================================
class PetState(Enum):
    IDLE = auto()      # 发呆：默认静止，轻微呼吸动效
    HAPPY = auto()     # 开心：上下弹跳动画
    SLEEPY = auto()    # 困倦：左右摇晃 + 眼睛半闭效果
    POKE = auto()      # 被戳：鼠标点击触发，短暂震动后恢复
    TYPING = auto()    # 打字中：键盘输入时触发


# ============================================================
# 桌面宠物主窗口
# ============================================================
class DesktopPet(QWidget):
    # 跨线程信号：pynput 监听线程只负责"报信"，所有 UI 状态一律回到主线程处理
    _key_event = pyqtSignal()

    def __init__(self):
        super().__init__()

        # ---- 窗口属性 ----
        self.setWindowFlags(
            Qt.FramelessWindowHint |      # 无边框
            Qt.WindowStaysOnTopHint |     # 始终置顶
            Qt.Tool |                     # 不在任务栏显示
            Qt.WindowDoesNotAcceptFocus | # 不抢夺焦点
            Qt.CustomizeWindowHint        # 禁用默认窗口边框，防止顶部残留横杠
        )
        self.setAttribute(Qt.WA_TranslucentBackground)  # 背景透明
        self.setAttribute(Qt.WA_NoSystemBackground)     # 禁用系统背景绘制
        self.setFixedSize(WINDOW_SIZE, WINDOW_SIZE)

        # 启动默认位置：主屏可用区域（已扣任务栏）右下角
        self.move(self._default_position())

        # ---- 拖拽相关（严格区分拖拽和点击）----
        self._dragging = False
        self._drag_offset = QPoint()
        self._drag_start_pos = QPoint()  # 记录鼠标按下时的全局坐标

        # ---- 宠物状态 ----
        self.state = PetState.IDLE
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._auto_switch_state)
        self._schedule_next_state()

        # ---- 动画帧 ----
        self._frame = 0
        self._fps = IDLE_FPS           # 当前帧率，随状态切换
        self._anim_time = 0.0          # 动画时间轴（秒），与帧率解耦
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_animation)
        self._anim_timer.start(1000 // self._fps)

        # ---- 眨眼 ----
        self._blinking = False
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._trigger_blink)
        self._blink_timer.start(BLINK_INTERVAL)

        # ---- 气泡系统 ----
        self._bubble_index = 0          # 全局轮播索引
        self._bubble_text = ""          # 当前气泡文字
        self._bubble_opacity = 0.0      # 气泡透明度（0.0 ~ 1.0）
        self._bubble_fade_in = False    # 是否正在淡入
        self._bubble_fade_out = False   # 是否正在淡出
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._start_bubble_fade_out)

        # ---- 被戳恢复 ----
        self._poke_timer = QTimer(self)
        self._poke_timer.setSingleShot(True)
        self._poke_timer.timeout.connect(self._recover_from_poke)

        # ---- 打字相关 ----
        self._typing = False
        self._typing_start_time = 0
        self._last_key_time = 0
        self._typing_check_timer = QTimer(self)
        self._typing_check_timer.timeout.connect(self._check_typing_timeout)
        self._typing_check_timer.start(500)

        self._stretching = False        # 是否正在伸懒腰

        # ---- 图片资源 ----
        self._image_mode = False
        self._pixmap = None
        self._pet_region = QRegion()   # 宠物非透明区域（逻辑像素，未含动画偏移）
        self._load_image()

        # ---- 右键菜单（只构建一次，避免每次右键累积 QMenu 子对象）----
        self._context_menu = self._build_context_menu()

        # ---- 系统托盘 ----
        self._setup_tray()

        # ---- 其他动画参数 ----
        self._bounce_y = 0          # 弹跳偏移
        self._shake_x = 0           # 抖动/摇晃偏移
        self._head_tilt = 0         # 头部倾斜角度
        self._arm_offset = 0        # 手臂敲击偏移
        self._stretch_y = 0         # 伸懒腰纵向拉伸比例

        self.setWindowTitle("iKun桌面精灵")
        self.show()

        # ---- 启动键盘监听：先把跨线程信号接好，再启动线程 ----
        self._keyboard_listener = None
        self._key_event.connect(self._on_key_pressed)
        self._start_keyboard_listener()

    # ========================================================
    # 状态切换调度
    # ========================================================
    def _schedule_next_state(self):
        """设置下一次自动状态切换时间（10~20 秒随机）。"""
        interval = random.randint(STATE_INTERVAL_MIN, STATE_INTERVAL_MAX)
        self._state_timer.start(interval)

    # ========================================================
    # 键盘监听
    # ========================================================
    def _start_keyboard_listener(self):
        """在独立线程启动 pynput 全局键盘监听（线程内不做任何 UI 操作）。"""
        if not PYNPUT_AVAILABLE:
            print("警告：未安装 pynput，键盘联动功能不可用。请执行: pip install pynput")
            return

        def on_press(key):
            """
            按键回调（运行于 pynput 子线程）。
            只记录时间戳并 emit 跨线程信号；真正的状态切换由主线程的
            _on_key_pressed 完成。原实现直接调 QTimer.singleShot 是错的
            —— Qt 定时器依赖调用线程的事件循环，子线程没有事件循环，回调会静默失效。
            """
            self._last_key_time = int(time.time() * 1000)
            self._key_event.emit()

        try:
            self._keyboard_listener = keyboard.Listener(on_press=on_press)
            self._keyboard_listener.daemon = True
            self._keyboard_listener.start()
        except Exception as e:
            print(f"键盘监听启动失败：{e}（部分环境需要管理员权限）")

    def _on_key_pressed(self):
        """
        主线程处理一次按键（由 _key_event 信号排队投递）：
        - 本轮首个按键：进入 TYPING 状态；
        - 连续打字每满 TYPING_FATIGUE_TIME（30 秒）触发一次疲劳提示，
          并把起算点推向当前时刻，实现"每 30 秒一次"而不是"每个按键一次"。
        """
        now = int(time.time() * 1000)
        self._last_key_time = now
        if not self._typing:
            self._typing = True
            self._typing_start_time = now
            self._on_typing_start()
            return
        if now - self._typing_start_time >= TYPING_FATIGUE_TIME:
            self._typing_start_time = now
            self._on_typing_fatigue()

    def _on_typing_start(self):
        """用户开始打字，切换为打字状态（被戳动画优先级更高，播完自动接回）。"""
        if self.state != PetState.POKE:
            self._set_state(PetState.TYPING)

    def _on_typing_fatigue(self):
        """连续打字满一个周期：伸懒腰 + 轮播一条气泡文案。"""
        if self.state != PetState.TYPING or self._stretching:
            return
        self._stretching = True
        text = BUBBLE_TEXTS[self._bubble_index % len(BUBBLE_TEXTS)]
        self._bubble_index += 1
        self._show_bubble(text)
        QTimer.singleShot(STRETCH_DURATION, self._end_stretch)

    def _end_stretch(self):
        """结束伸懒腰动画。"""
        self._stretching = False
        self._stretch_y = 0

    def _check_typing_timeout(self):
        """检查打字超时：停止输入超过 2 秒则自动恢复发呆状态。"""
        if not self._typing:
            return
        current_time = int(time.time() * 1000)
        if current_time - self._last_key_time > TYPING_TIMEOUT:
            self._typing = False
            self._typing_start_time = 0
            self._stretching = False
            self._stretch_y = 0
            if self.state == PetState.TYPING:
                self._set_state(PetState.IDLE)

    # ========================================================
    # 图片加载
    # ========================================================
    def _load_image(self):
        """
        加载外部图片，去除与边缘连通的白色背景（保留主体内部白色如眼睛等），
        失败则回退到矢量绘制，确保程序不崩溃。

        去底改为直接操作 QImage 的原始像素缓冲区（扫描线洪水填充）：
        原实现每像素调 pixelColor/setPixelColor，一两万像素就要几十万次跨语言
        调用，启动时会明显卡顿。
        """
        dpr = max(1.0, self.devicePixelRatioF())
        image = None
        path = _find_image_path()
        if path:
            raw = QImage(path)
            if not raw.isNull():
                raw = self._trim_border_bands(raw)
                # 按设备像素缩放到目标尺寸，高分屏下不会发虚
                target = int(round(PET_SIZE * dpr))
                image = raw.scaled(
                    target, target,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                ).convertToFormat(QImage.Format_ARGB32)
                image.setDevicePixelRatio(1.0)   # 统一按设备像素计算，最后再挂 DPR

        if image is not None and not image.isNull():
            self._flood_fill_background(image)
            self._pixmap = QPixmap.fromImage(image)
            self._pixmap.setDevicePixelRatio(dpr)
            self._image_mode = True
            self._pet_region = self._build_pet_region(image)
            return

        # 加载失败：矢量模式，命中区域取内切圆（比整块方形更贴近实际可见范围）
        self._pixmap = None
        self._image_mode = False
        self._pet_region = QRegion(QRect(0, 0, PET_SIZE, PET_SIZE), QRegion.Ellipse)

    @staticmethod
    def _flood_fill_background(image: QImage):
        """
        从四条边出发，把与边缘连通的近白色像素置为全透明（原地修改）。
        直接读写 ARGB32 的原始字节：小端下内存顺序为 B,G,R,A。
        """
        w, h = image.width(), image.height()
        if w <= 0 or h <= 0 or sys.byteorder != "little":
            return
        bpl = image.bytesPerLine()
        try:
            ptr = image.bits()
            ptr.setsize(bpl * h)
            buf = memoryview(ptr).cast("B")
        except Exception:
            return   # 拿不到可写缓冲区就放弃去底（仅影响观感，不影响功能）

        visited = bytearray(w * h)
        stack = []

        def seed(x, y):
            """把近白色像素加入待扩散栈（同一像素只入栈一次）。"""
            index = y * w + x
            if visited[index]:
                return
            off = y * bpl + x * 4
            if buf[off] > 240 and buf[off + 1] > 240 and buf[off + 2] > 240:
                visited[index] = 1
                stack.append(index)

        for x in range(w):
            seed(x, 0)
            seed(x, h - 1)
        for y in range(h):
            seed(0, y)
            seed(w - 1, y)

        while stack:
            index = stack.pop()
            y, x = divmod(index, w)
            off = y * bpl + x * 4
            buf[off:off + 4] = b"\x00\x00\x00\x00"
            if x > 0:
                seed(x - 1, y)
            if x < w - 1:
                seed(x + 1, y)
            if y > 0:
                seed(x, y - 1)
            if y < h - 1:
                seed(x, y + 1)

    @staticmethod
    def _same_color(a, b, tolerance: int = 10) -> bool:
        """判断两个颜色是否近似相同（用于边框带检测）。"""
        return (abs(a.red() - b.red()) <= tolerance
                and abs(a.green() - b.green()) <= tolerance
                and abs(a.blue() - b.blue()) <= tolerance)

    @classmethod
    def _trim_border_bands(cls, image: QImage, limit: int = MAX_BORDER_TRIM) -> QImage:
        """
        裁掉图像四周"整行/整列同色"的窄边框带。
        ikun.jpg 顶部有 5 像素灰边，缩放后会在宠物头顶留下一条可见灰线，
        白底也是一圈同色边框。只裁 limit 像素以内，避免把正常画面边距当成边框。
        """
        w, h = image.width(), image.height()
        if w < 3 * limit or h < 3 * limit:
            return image

        def row_uniform(y):
            ref = image.pixelColor(0, y)
            return all(cls._same_color(image.pixelColor(x, y), ref)
                       for x in range(0, w, 4))

        def col_uniform(x):
            ref = image.pixelColor(x, 0)
            return all(cls._same_color(image.pixelColor(x, y), ref)
                       for y in range(0, h, 4))

        top = 0
        while top < limit and row_uniform(top):
            top += 1
        bottom = 0
        while bottom < limit and row_uniform(h - 1 - bottom):
            bottom += 1
        left = 0
        while left < limit and col_uniform(left):
            left += 1
        right = 0
        while right < limit and col_uniform(w - 1 - right):
            right += 1

        if not (top or bottom or left or right):
            return image
        return image.copy(left, top, w - left - right, h - top - bottom)

    @staticmethod
    def _build_pet_region(image: QImage) -> QRegion:
        """由去底后的图像生成逻辑像素下的非透明区域（供点击穿透判定使用）。"""
        logical = image.scaled(
            PET_SIZE, PET_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        logical.setDevicePixelRatio(1.0)
        return QRegion(QPixmap.fromImage(logical).mask())

    # ========================================================
    # 系统托盘
    # ========================================================
    def _setup_tray(self):
        """初始化系统托盘图标和右键菜单。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        # 代码绘制 16x16 迷你图标
        tray_pix = QPixmap(16, 16)
        tray_pix.fill(Qt.transparent)
        tp = QPainter(tray_pix)
        tp.setBrush(QBrush(QColor(255, 200, 50)))
        tp.setPen(Qt.NoPen)
        tp.drawEllipse(1, 1, 14, 14)
        tp.setBrush(QBrush(Qt.white))
        tp.drawEllipse(4, 5, 3, 3)
        tp.drawEllipse(9, 5, 3, 3)
        tp.end()
        self._tray.setIcon(QIcon(tray_pix))
        self._tray.setToolTip("iKun桌面精灵")

        tray_menu = QMenu()
        act_show = QAction("显示宠物", self)
        act_show.triggered.connect(self.show_pet)
        act_hide = QAction("隐藏宠物", self)
        act_hide.triggered.connect(self.hide_pet)
        act_reset = QAction("重置位置", self)
        act_reset.triggered.connect(self.reset_position)
        act_quit = QAction("退出程序", self)
        act_quit.triggered.connect(self.quit_app)

        tray_menu.addAction(act_show)
        tray_menu.addAction(act_hide)
        tray_menu.addSeparator()
        tray_menu.addAction(act_reset)
        tray_menu.addSeparator()
        tray_menu.addAction(act_quit)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_activated(self, reason):
        """托盘图标激活事件（双击显示）。"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_pet()

    # ========================================================
    # 状态切换
    # ========================================================
    def _auto_switch_state(self):
        """定时自动轮换状态（排除被戳和打字状态）。"""
        if self.state in (PetState.POKE, PetState.TYPING):
            self._schedule_next_state()
            return
        choices = [PetState.IDLE, PetState.HAPPY, PetState.SLEEPY]
        weights = [5, 3, 2]
        new_state = random.choices(choices, weights=weights)[0]
        self._set_state(new_state)
        self._schedule_next_state()

    def _set_state(self, state: PetState):
        """
        切换宠物状态：重置帧计数与动画时间轴，并按状态调整刷新率。
        表情差异全部在绘制层按 state 分支实现，这里不再维护一堆没人读的表情变量。
        """
        self.state = state
        self._frame = 0
        self._anim_time = 0.0
        if state == PetState.POKE:
            self._poke_timer.start(POKE_RECOVER_TIME)
        self._apply_fps()
        self.update()

    def _apply_fps(self):
        """按当前状态选择帧率：活跃动画 30fps，发呆/困倦 12fps，减少无谓重绘。"""
        self._fps = ANIMATION_FPS if self.state in (
            PetState.HAPPY, PetState.POKE, PetState.TYPING
        ) else IDLE_FPS
        interval = max(1, int(1000 / self._fps))
        if self._anim_timer.interval() != interval:
            self._anim_timer.start(interval)

    def _recover_from_poke(self):
        """
        被戳结束：若用户手还在打字就接回 TYPING，否则回到发呆。
        （原实现无条件回 IDLE，且 _typing 仍为 True，导致"边打字边被戳"后
          宠物会一直发呆，必须停手 2 秒再打才恢复。）
        """
        if self._typing and int(time.time() * 1000) - self._last_key_time <= TYPING_TIMEOUT:
            self._set_state(PetState.TYPING)
        else:
            self._set_state(PetState.IDLE)

    def _trigger_blink(self):
        """触发眨眼动画。"""
        if self.state in (PetState.SLEEPY, PetState.POKE):
            return
        self._blinking = True
        QTimer.singleShot(BLINK_DURATION, self._end_blink)
        self.update()

    def _end_blink(self):
        """结束眨眼。"""
        self._blinking = False
        self.update()

    # ========================================================
    # 动画更新
    # ========================================================
    def _update_animation(self):
        """更新动画帧，根据当前状态计算身体偏移、表情参数和气泡透明度。"""
        self._frame += 1
        self._anim_time += 1.0 / self._fps   # 按实际帧间隔累加，换帧率后动画速度不变
        t = self._anim_time

        if self.state == PetState.HAPPY:
            # 开心：正弦波弹跳
            self._bounce_y = int(-10 * abs(math.sin(t * 4)))
            self._shake_x = 0
            self._head_tilt = 0
        elif self.state == PetState.SLEEPY:
            # 困倦：缓慢上下浮动 + 左右摇晃
            self._bounce_y = int(-4 * math.sin(t * 1.5))
            self._shake_x = int(4 * math.sin(t * 2))
            self._head_tilt = int(5 * math.sin(t * 1))
        elif self.state == PetState.POKE:
            # 被戳：高频震动
            self._bounce_y = int(-5 * abs(math.sin(t * 15)))
            self._shake_x = random.randint(-5, 5)
            self._head_tilt = 0
        elif self.state == PetState.TYPING:
            # 打字中：轻微呼吸 + 头部左右晃动 + 手臂交替敲击
            self._bounce_y = int(-2 * math.sin(t * 3))
            self._shake_x = 0
            self._head_tilt = int(4 * math.sin(t * 5))
            self._arm_offset = int(5 * math.sin(t * 8))
        else:
            # 发呆：轻微呼吸浮动
            self._bounce_y = int(-3 * math.sin(t * 2))
            self._shake_x = 0
            self._head_tilt = 0
            self._arm_offset = 0

        # 伸懒腰动画（疲劳时身体纵向拉伸）
        if self._stretching:
            self._stretch_y = 0.12 * abs(math.sin(t * 4))

        # 气泡淡入淡出处理
        if self._bubble_fade_in:
            self._bubble_opacity += 0.15
            if self._bubble_opacity >= 1.0:
                self._bubble_opacity = 1.0
                self._bubble_fade_in = False
        elif self._bubble_fade_out:
            self._bubble_opacity -= 0.08
            if self._bubble_opacity <= 0:
                self._bubble_opacity = 0.0
                self._bubble_fade_out = False
                self._bubble_text = ""

        self.update()

    # ========================================================
    # 气泡系统
    # ========================================================
    def _show_bubble(self, text: str):
        """
        显示气泡文案。
        新气泡出现时旧气泡立即关闭，带淡入效果，3 秒后自动淡出消失。
        """
        self._bubble_text = text
        if self._bubble_opacity <= 0.0:
            # 原本没有气泡：从透明淡入
            self._bubble_opacity = 0.0
            self._bubble_fade_in = True
        else:
            # 已有气泡在显示：直接换字保持不透明，避免"闪一下"
            self._bubble_opacity = 1.0
            self._bubble_fade_in = False
        self._bubble_fade_out = False
        self._bubble_timer.stop()
        self._bubble_timer.start(BUBBLE_SHOW_DURATION)
        self.update()

    def _start_bubble_fade_out(self):
        """开始气泡淡出。"""
        self._bubble_fade_in = False
        self._bubble_fade_out = True
        self.update()

    # ========================================================
    # 鼠标事件
    # ========================================================
    def mousePressEvent(self, event):
        """鼠标按下：记录拖拽起始位置。"""
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._drag_start_pos = event.globalPos()
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动：处理拖拽。"""
        if self._dragging and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPos() - self._drag_offset
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        """
        鼠标释放：严格区分拖拽和单击。
        若移动距离小于 5 像素，视为左键单击，触发被戳反应。
        """
        if event.button() == Qt.LeftButton:
            delta = event.globalPos() - self._drag_start_pos
            if math.hypot(delta.x(), delta.y()) < CLICK_THRESHOLD:
                self._set_state(PetState.POKE)
                self._show_bubble(BUBBLE_POKE_TEXT)
            self._dragging = False
            event.accept()

    # ========================================================
    # 右键菜单
    # ========================================================
    def _build_context_menu(self) -> QMenu:
        """构建右键菜单（只构建一次，反复使用，避免长跑累积 QMenu 子对象）。"""
        menu = QMenu(self)
        act_hide = QAction("隐藏宠物", self)
        act_hide.triggered.connect(self.hide_pet)
        menu.addAction(act_hide)

        act_reset = QAction("重置位置", self)
        act_reset.triggered.connect(self.reset_position)
        menu.addAction(act_reset)

        menu.addSeparator()

        act_quit = QAction("退出程序", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)
        return menu

    def _show_context_menu(self, pos):
        """显示右键上下文菜单：隐藏宠物、重置位置、退出程序。"""
        self._context_menu.exec_(pos)

    # ========================================================
    # 点击穿透（透明像素不吞鼠标事件）
    # ========================================================
    def _opaque_region(self) -> QRegion:
        """
        当前帧真正"实体"的区域（窗口坐标）= 宠物非透明区域 + 可见气泡。
        宠物区域按当前动画偏移平移，避免抖动时命中判定错位。
        """
        offset_x = self._shake_x + (WINDOW_SIZE - PET_SIZE) // 2
        offset_y = self._bounce_y + (WINDOW_SIZE - PET_SIZE) // 2
        region = self._pet_region.translated(offset_x, offset_y)
        if self._bubble_text and self._bubble_opacity > 0.05:
            bubble = self._bubble_rect().toRect().adjusted(-2, -2, 2, 2)
            region = region.united(QRegion(bubble))
        if region.isEmpty():
            # 兜底：拿不到掩码时宁可让整个窗口可点，也不要变成点不到的幽灵
            return QRegion(self.rect())
        return region

    def nativeEvent(self, event_type, message):
        """
        Windows：拦截 WM_NCHITTEST，把透明区域的命中结果改成 HTTRANSPARENT，
        让鼠标事件落到宠物身后的窗口/桌面上，而不是被 220x220 的透明窗吞掉。
        """
        if PYWIN and event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_NCHITTEST:
                    # lParam 低 16 位是屏幕 x，高 16 位是屏幕 y（均为有符号短整型）
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    if not self._opaque_region().contains(self.mapFromGlobal(QPoint(x, y))):
                        return True, HTTRANSPARENT
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    # ========================================================
    # 功能动作
    # ========================================================
    def hide_pet(self):
        """隐藏宠物窗口（托盘图标保留，可再次显示），同时停掉动画定时器省 CPU。"""
        self._set_timers_active(False)
        self.hide()

    def show_pet(self):
        """显示宠物窗口并恢复定时器（窗口本身不接收焦点，故不调用 activateWindow）。"""
        self.show()
        self.raise_()
        self._set_timers_active(True)

    def _set_timers_active(self, active: bool):
        """统一开关与可见性相关的定时器：隐藏时不空转，避免白白烧 CPU。"""
        if active:
            self._anim_timer.start(max(1, int(1000 / self._fps)))
            self._blink_timer.start(BLINK_INTERVAL)
            self._typing_check_timer.start(500)
            if not self._state_timer.isActive():
                self._schedule_next_state()
        else:
            self._anim_timer.stop()
            self._blink_timer.stop()
            self._typing_check_timer.stop()

    def _default_position(self, anchor=None) -> QPoint:
        """默认停靠位置：锚点所在屏幕（默认主屏）可用区域的右下角。"""
        geo = _screen_available_geometry(anchor)
        return QPoint(geo.right() - WINDOW_SIZE - 10, geo.bottom() - WINDOW_SIZE - 10)

    def reset_position(self):
        """把宠物重置到当前所在屏幕的右下角（多屏下不会跳回主屏）。"""
        self.move(self._default_position(self.pos()))

    def quit_app(self):
        """退出程序，清理托盘图标和键盘监听线程。"""
        if self._keyboard_listener is not None:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
            self._keyboard_listener = None
        if hasattr(self, '_tray'):
            self._tray.hide()
        QApplication.instance().quit()

    # ========================================================
    # 绘制核心
    # ========================================================
    def paintEvent(self, event):
        """绘制宠物主体和状态气泡。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 先清除整个窗口为透明，防止任何绘制残留（如顶部横杠）
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.eraseRect(self.rect())
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 整体偏移（动画）
        offset_x = self._shake_x + (WINDOW_SIZE - PET_SIZE) // 2
        offset_y = self._bounce_y + (WINDOW_SIZE - PET_SIZE) // 2
        painter.translate(offset_x, offset_y)

        # 应用头部倾斜 / 伸懒腰变换（以宠物中心为轴）
        cx = PET_SIZE // 2
        cy = PET_SIZE // 2
        painter.translate(cx, cy)
        painter.rotate(self._head_tilt)
        painter.scale(1.0, 1.0 + self._stretch_y)
        painter.translate(-cx, -cy)

        if self._image_mode and self._pixmap is not None:
            self._draw_image_mode(painter)
        else:
            self._draw_fallback_mode(painter)

        # 打字状态绘制键盘与双手（键盘在手下方）
        if self.state == PetState.TYPING:
            self._draw_keyboard(painter)
            self._draw_typing_hands(painter)

        # 在绝对坐标系中绘制状态气泡（避免被窗口边缘裁切）
        painter.resetTransform()
        self._draw_state_bubble_absolute(painter)

        painter.end()

    # --------------------------------------------------------
    # 图片模式绘制
    # --------------------------------------------------------
    def _draw_image_mode(self, painter: QPainter):
        """居中绘制宠物图片（已去除白底，按设备像素比换算成逻辑尺寸）。"""
        dpr = self._pixmap.devicePixelRatio() or 1.0
        pw = self._pixmap.width() / dpr
        ph = self._pixmap.height() / dpr
        painter.drawPixmap(
            QPointF((PET_SIZE - pw) / 2.0, (PET_SIZE - ph) / 2.0), self._pixmap
        )

    # --------------------------------------------------------
    # Fallback 模式绘制（图片加载失败时的默认绘制）
    # --------------------------------------------------------
    def _draw_fallback_mode(self, painter: QPainter):
        """默认纯色方块占位 + 简化矢量形象。"""
        size = PET_SIZE
        cx, cy = size // 2, size // 2
        body_radius = 55

        # 身体（黄色圆脸）
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 220, 80)))
        painter.drawEllipse(cx - body_radius, cy - body_radius + 8, body_radius * 2, body_radius * 2)

        # 中分头发
        self._draw_fallback_hair(painter, cx, cy, body_radius)

        # 眼睛（根据状态变化）
        eye_y = cy - 2
        if self.state == PetState.SLEEPY:
            self._draw_fallback_sleepy_eyes(painter, cx, eye_y)
        elif self.state == PetState.HAPPY:
            self._draw_fallback_happy_eyes(painter, cx, eye_y)
        elif self.state == PetState.POKE:
            self._draw_fallback_poke_eyes(painter, cx, eye_y)
        elif self.state == PetState.TYPING:
            self._draw_fallback_typing_eyes(painter, cx, eye_y)
        else:
            self._draw_fallback_normal_eyes(painter, cx, eye_y)

        # 腮红
        if self.state in (PetState.HAPPY, PetState.POKE):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 120, 120, 120)))
            for dx in (-40, 40):
                painter.drawEllipse(cx + dx - 12, cy + 12, 24, 16)

        # 嘴巴
        self._draw_fallback_mouth(painter, cx, cy)

        # 篮球
        self._draw_fallback_basketball(painter, cx, cy, body_radius)

    def _draw_fallback_hair(self, painter: QPainter, cx: int, cy: int, body_radius: int):
        """绘制简化中分头发。"""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(50, 40, 40)))
        hair_y = cy - body_radius + 12
        painter.drawEllipse(cx - 45, hair_y, 90, 45)

        path = QPainterPath()
        path.moveTo(cx - 6, hair_y + 14)
        path.quadTo(cx - 30, hair_y - 20, cx - 50, hair_y + 20)
        path.quadTo(cx - 38, hair_y + 40, cx - 6, hair_y + 35)
        painter.drawPath(path)

        path2 = QPainterPath()
        path2.moveTo(cx + 6, hair_y + 14)
        path2.quadTo(cx + 30, hair_y - 20, cx + 50, hair_y + 20)
        path2.quadTo(cx + 38, hair_y + 40, cx + 6, hair_y + 35)
        painter.drawPath(path2)

        painter.setBrush(QBrush(QColor(80, 70, 70)))
        painter.drawEllipse(cx - 5, hair_y + 10, 10, 20)

    def _draw_fallback_normal_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """正常状态眼睛（支持眨眼）。"""
        eye_rx, eye_ry = 18, 22
        eye_open = 0.15 if self._blinking else 1.0
        for dx in (-22, 22):
            ex = cx + dx
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(ex - eye_rx, eye_y - int(eye_ry * eye_open), eye_rx * 2, int(eye_ry * 2 * eye_open))
            painter.setPen(QPen(QColor(40, 40, 40), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ex - eye_rx, eye_y - int(eye_ry * eye_open), eye_rx * 2, int(eye_ry * 2 * eye_open))
            if not self._blinking:
                painter.setBrush(QBrush(QColor(40, 40, 40)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(ex - 7, eye_y + 3, 14, 14)
                painter.setBrush(QBrush(Qt.white))
                painter.drawEllipse(ex - 3, eye_y - 1, 6, 6)

    def _draw_fallback_happy_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """开心状态：笑眯眯弧线。"""
        painter.setPen(QPen(QColor(40, 40, 40), 3))
        painter.setBrush(Qt.NoBrush)
        for dx in (-22, 22):
            path = QPainterPath()
            path.moveTo(cx + dx - 14, eye_y + 4)
            path.quadTo(cx + dx, eye_y - 10, cx + dx + 14, eye_y + 4)
            painter.drawPath(path)

    def _draw_fallback_sleepy_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """困倦状态：半闭眼。"""
        painter.setPen(QPen(QColor(40, 40, 40), 2))
        painter.setBrush(Qt.NoBrush)
        for dx in (-22, 22):
            path = QPainterPath()
            path.moveTo(cx + dx - 12, eye_y - 4)
            path.quadTo(cx + dx, eye_y + 8, cx + dx + 12, eye_y - 4)
            painter.drawPath(path)
            path2 = QPainterPath()
            path2.moveTo(cx + dx - 12, eye_y - 4)
            path2.lineTo(cx + dx + 12, eye_y - 4)
            painter.drawPath(path2)

    def _draw_fallback_poke_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """被戳状态：惊讶大眼 + 眼泪。"""
        eye_rx, eye_ry = 14, 18
        for dx in (-22, 22):
            ex = cx + dx
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(ex - eye_rx, eye_y - eye_ry, eye_rx * 2, eye_ry * 2)
            painter.setPen(QPen(QColor(40, 40, 40), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ex - eye_rx, eye_y - eye_ry, eye_rx * 2, eye_ry * 2)
            painter.setBrush(QBrush(QColor(40, 40, 40)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(ex - 5, eye_y - 5, 10, 10)
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(ex - 2, eye_y - 7, 4, 4)
        # 眼泪
        tear_offset = (self._frame * 3) % 16
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(150, 200, 255, 180)))
        for dx in (-22, 22):
            ty = eye_y + 22 + tear_offset
            painter.drawEllipse(cx + dx - 3, ty, 6, 9)

    def _draw_fallback_typing_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """打字中状态：专注横线眼。"""
        painter.setPen(QPen(QColor(40, 40, 40), 3))
        painter.setBrush(Qt.NoBrush)
        for dx in (-22, 22):
            painter.drawLine(cx + dx - 10, eye_y, cx + dx + 10, eye_y)
            painter.drawLine(cx + dx - 10, eye_y + 3, cx + dx + 10, eye_y + 3)

    def _draw_fallback_mouth(self, painter: QPainter, cx: int, cy: int):
        """根据状态绘制嘴巴。"""
        mouth_y = cy + 22
        if self.state == PetState.HAPPY:
            painter.setPen(QPen(QColor(180, 60, 60), 2))
            painter.setBrush(QBrush(QColor(255, 100, 100)))
            path = QPainterPath()
            path.moveTo(cx - 18, mouth_y - 4)
            path.quadTo(cx, mouth_y + 18, cx + 18, mouth_y - 4)
            path.quadTo(cx, mouth_y + 4, cx - 18, mouth_y - 4)
            painter.drawPath(path)
        elif self.state == PetState.SLEEPY:
            openness = 8 + int(8 * abs(math.sin(self._frame / ANIMATION_FPS * 3)))
            painter.setPen(QPen(QColor(160, 60, 60), 2))
            painter.setBrush(QBrush(QColor(80, 30, 40)))
            painter.drawEllipse(cx - 9, mouth_y, 18, openness)
        elif self.state == PetState.POKE:
            painter.setPen(QPen(QColor(180, 60, 60), 2))
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - 12, mouth_y + 4)
            path.quadTo(cx - 4, mouth_y - 4, cx, mouth_y + 4)
            path.quadTo(cx + 4, mouth_y - 4, cx + 12, mouth_y + 4)
            painter.drawPath(path)
        else:
            painter.setPen(QPen(QColor(180, 60, 60), 2))
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - 9, mouth_y)
            path.quadTo(cx, mouth_y + 8, cx + 9, mouth_y)
            painter.drawPath(path)

    def _draw_fallback_basketball(self, painter: QPainter, cx: int, cy: int, body_radius: int):
        """绘制篮球（iKun 元素）。"""
        bx = cx + 35
        by = cy + 40
        br = 18
        painter.setPen(QPen(QColor(160, 80, 20), 2))
        painter.setBrush(QBrush(QColor(255, 140, 40)))
        painter.drawEllipse(bx - br, by - br, br * 2, br * 2)
        painter.setPen(QPen(QColor(120, 50, 10), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(bx - br + 2, by, bx + br - 2, by)
        arc1 = QPainterPath()
        arc1.moveTo(bx, by - br + 2)
        arc1.quadTo(bx - br, by, bx, by + br - 2)
        painter.drawPath(arc1)
        arc2 = QPainterPath()
        arc2.moveTo(bx, by - br + 2)
        arc2.quadTo(bx + br, by, bx, by + br - 2)
        painter.drawPath(arc2)

    def _draw_keyboard(self, painter: QPainter):
        """打字状态：在宠物下方绘制简化键盘，并根据手部动作高亮对应按键。"""
        kb_w = 88
        kb_h = 34
        kb_x = (PET_SIZE - kb_w) // 2
        kb_y = PET_SIZE - 22

        # 键盘底板
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.setBrush(QBrush(QColor(230, 230, 230)))
        painter.drawRoundedRect(kb_x, kb_y, kb_w, kb_h, 4, 4)

        # 按键绘制
        key_w, key_h = 9, 7
        gap = 2
        start_x = kb_x + 5
        start_y = kb_y + 4

        for row in range(3):
            for col in range(7):
                x = start_x + col * (key_w + gap)
                y = start_y + row * (key_h + gap)

                # 根据手部位移动态高亮对应半区按键
                highlight = False
                if self._arm_offset > 2 and col < 3:
                    highlight = True
                elif self._arm_offset < -2 and col >= 4:
                    highlight = True

                if highlight:
                    painter.setBrush(QBrush(QColor(100, 180, 255)))
                    painter.setPen(QPen(QColor(60, 140, 220), 1))
                else:
                    painter.setBrush(QBrush(QColor(200, 200, 200)))
                    painter.setPen(QPen(QColor(160, 160, 160), 1))
                painter.drawRoundedRect(x, y, key_w, key_h, 1, 1)

    def _draw_typing_hands(self, painter: QPainter):
        """打字状态：在身体两侧绘制上下交替敲击的小手。"""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 200, 80)))
        left_y = PET_SIZE - 10 + self._arm_offset
        right_y = PET_SIZE - 10 - self._arm_offset
        painter.drawEllipse(20, left_y, 14, 10)
        painter.drawEllipse(PET_SIZE - 34, right_y, 14, 10)

    # --------------------------------------------------------
    # 气泡绘制
    # --------------------------------------------------------
    def _bubble_rect(self) -> QRectF:
        """
        气泡外框（窗口坐标）：位于宠物头顶正上方，超出窗口顶部时贴边。
        绘制与点击穿透判定共用这一份计算，保证"看起来在哪就能点到哪"。
        """
        font = QFont("Microsoft YaHei", 9, QFont.Bold)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self._bubble_text) + 16
        th = fm.height() + 8
        pet_cx = WINDOW_SIZE // 2 + self._shake_x
        pet_top = (WINDOW_SIZE - PET_SIZE) // 2 + self._bounce_y
        by = max(5, pet_top - th - 12)
        bx = max(2, pet_cx - tw // 2)
        return QRectF(bx, by, tw, th)

    def _draw_state_bubble_absolute(self, painter: QPainter):
        """
        在窗口绝对坐标系中绘制气泡。
        气泡位于宠物头顶正上方，带淡入淡出，圆角矩形，支持 emoji。
        """
        if not self._bubble_text or self._bubble_opacity <= 0:
            return

        painter.setOpacity(self._bubble_opacity)
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))

        painter.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        rect = self._bubble_rect()
        pet_cx = rect.center().x()

        # 圆角矩形
        painter.drawRoundedRect(rect, 8, 8)

        # 小三角指向宠物中心
        tri = QPainterPath()
        tri.moveTo(pet_cx - 6, rect.bottom())
        tri.lineTo(pet_cx, rect.bottom() + 8)
        tri.lineTo(pet_cx + 6, rect.bottom())
        painter.drawPath(tri)

        # 文字
        painter.setPen(QColor(60, 60, 60))
        painter.drawText(rect, Qt.AlignCenter, self._bubble_text)
        painter.setOpacity(1.0)


# ============================================================
# 入口
# ============================================================
def main():
    """程序入口：隐藏自身控制台、启用高 DPI 缩放并启动应用。"""
    _hide_own_console()

    # 高 DPI 相关属性必须在创建 QApplication 之前设置
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 隐藏时保持运行

    pet = DesktopPet()   # noqa: F841  持有主窗口引用，避免被 GC 回收
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
