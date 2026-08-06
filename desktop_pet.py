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
from collections import deque

from PyQt5.QtWidgets import (
    QApplication, QWidget, QMenu, QAction, QSystemTrayIcon, QDesktopWidget
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRectF
from PyQt5.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QFontMetrics,
    QPixmap, QImage, QIcon, QPainterPath
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
ANIMATION_FPS = 30         # 动画帧率
STATE_INTERVAL_MIN = 10000 # 状态自动切换最小间隔（毫秒）
STATE_INTERVAL_MAX = 20000 # 状态自动切换最大间隔（毫秒）
BLINK_INTERVAL = 3000      # 眨眼间隔（毫秒）
TYPING_TIMEOUT = 2000      # 停止打字超过2秒后恢复发呆（毫秒）
TYPING_FATIGUE_TIME = 1000# 连续打字超过30秒触发疲劳（毫秒）
BUBBLE_SHOW_DURATION = 3000# 气泡显示时长（毫秒）

# 疲劳提示文案，固定顺序轮播
BUBBLE_TEXTS = ["唱🎤", "跳💃", "Rap🎶", "打🏀"]
# 被戳专属文案
BUBBLE_POKE_TEXT = "你干嘛~"


def _find_image_path():
    """多路径查找 ikun.jpg，兼容 .py 脚本和 PyInstaller 打包后的运行方式。"""
    candidates = [
        r"D:\iKun\iKun\DesktopSprite\images\ikun.jpg",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "ikun.jpg"),
        os.path.join(getattr(sys, '_MEIPASS', ""), "images", "ikun.jpg"),
        os.path.join(os.path.dirname(sys.executable), "images", "ikun.jpg"),
        os.path.join(os.getcwd(), "images", "ikun.jpg"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images", "ikun.jpg"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


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

        # 启动默认位置：屏幕右下角（预留任务栏空间）
        screen = QDesktopWidget().screenGeometry()
        self.move(
            screen.width() - WINDOW_SIZE - 10,
            screen.height() - WINDOW_SIZE - 40
        )
        self._default_pos = self.pos()

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
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_animation)
        self._anim_timer.start(1000 // ANIMATION_FPS)

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
        self._load_image()

        # ---- 系统托盘 ----
        self._setup_tray()

        # ---- 其他动画参数 ----
        self._hidden = False
        self._bounce_y = 0          # 弹跳偏移
        self._shake_x = 0           # 抖动/摇晃偏移
        self._mouth_open = 0        # 嘴巴张开程度 (0~1)
        self._eye_openness = 1.0    # 眼睛睁开程度 (0~1)
        self._cheek_blush = 0       # 腮红强度
        self._tear_drop = 0         # 眼泪动画
        self._head_tilt = 0         # 头部倾斜角度
        self._arm_offset = 0        # 手臂敲击偏移
        self._stretch_y = 0         # 伸懒腰纵向拉伸比例

        self.setWindowTitle("iKun桌面精灵")
        self.show()

        # ---- 启动键盘监听（独立线程，不阻塞 UI）----
        self._keyboard_listener = None
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
        """在独立线程启动 pynput 全局键盘监听。"""
        if not PYNPUT_AVAILABLE:
            print("警告：未安装 pynput，键盘联动功能不可用。请执行: pip install pynput")
            return

        def on_press(key):
            """
            按键回调（运行于子线程）。
            仅记录时间戳，UI 状态切换通过 QTimer.singleShot 交由主线程处理。
            """
            current_time = int(time.time() * 1000)
            self._last_key_time = current_time
            if not self._typing:
                self._typing = True
                self._typing_start_time = current_time
                QTimer.singleShot(0, self._on_typing_start)
            else:
                typing_duration = current_time - self._typing_start_time
                if typing_duration >= TYPING_FATIGUE_TIME:
                    QTimer.singleShot(0, self._on_typing_fatigue)

        try:
            self._keyboard_listener = keyboard.Listener(on_press=on_press)
            self._keyboard_listener.daemon = True
            self._keyboard_listener.start()
        except Exception as e:
            print(f"键盘监听启动失败：{e}（部分环境需要管理员权限）")

    def _on_typing_start(self):
        """用户开始打字，切换为打字状态。"""
        if self.state != PetState.POKE:
            self._set_state(PetState.TYPING)

    def _on_typing_fatigue(self):
        """连续打字超过 30 秒，触发疲劳提示（伸懒腰 + 轮播气泡）。"""
        if self.state == PetState.TYPING and not self._stretching:
            self._stretching = True
            text = BUBBLE_TEXTS[self._bubble_index % len(BUBBLE_TEXTS)]
            self._bubble_index += 1
            self._show_bubble(text)
            QTimer.singleShot(2000, self._end_stretch)

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
        加载外部图片，去除边缘连通的白色背景（保留主体内部白色如眼睛等），
        失败则使用默认纯色方块占位，确保程序不崩溃。
        """
        path = _find_image_path()
        if path:
            img = QImage(path)
            if not img.isNull():
                # 先等比缩放至目标尺寸
                pixmap = QPixmap.fromImage(img)
                scaled = pixmap.scaled(
                    PET_SIZE, PET_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                image = scaled.toImage().convertToFormat(QImage.Format_ARGB32)
                w, h = image.width(), image.height()
                transparent = QColor(0, 0, 0, 0)

                def is_bg_white(x, y):
                    c = image.pixelColor(x, y)
                    return c.red() > 240 and c.green() > 240 and c.blue() > 240

                visited = [[False] * h for _ in range(w)]
                queue = deque()

                # 从四条边寻找背景白色起点
                for x in range(w):
                    for y in (0, h - 1):
                        if is_bg_white(x, y) and not visited[x][y]:
                            queue.append((x, y))
                            visited[x][y] = True
                for y in range(h):
                    for x in (0, w - 1):
                        if is_bg_white(x, y) and not visited[x][y]:
                            queue.append((x, y))
                            visited[x][y] = True

                # Flood Fill：只将与边缘连通的白色设为背景透明
                while queue:
                    x, y = queue.popleft()
                    image.setPixelColor(x, y, transparent)
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and not visited[nx][ny] and is_bg_white(nx, ny):
                            visited[nx][ny] = True
                            queue.append((nx, ny))

                self._pixmap = QPixmap.fromImage(image)
                self._image_mode = True
                return

        # 加载失败：纯色方块占位
        self._pixmap = None
        self._image_mode = False

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
        """设置宠物状态并重置相关动画参数。"""
        self.state = state
        self._frame = 0
        if state == PetState.IDLE:
            self._mouth_open = 0
            self._cheek_blush = 0
            self._tear_drop = 0
            self._head_tilt = 0
            self._arm_offset = 0
            self._stretch_y = 0
        elif state == PetState.HAPPY:
            self._mouth_open = 0.3
            self._cheek_blush = 1
            self._tear_drop = 0
            self._head_tilt = 0
            self._arm_offset = 0
        elif state == PetState.SLEEPY:
            self._mouth_open = 0.6
            self._cheek_blush = 0
            self._tear_drop = 0
            self._head_tilt = 0
            self._arm_offset = 0
        elif state == PetState.POKE:
            self._mouth_open = 0.8
            self._cheek_blush = 0
            self._tear_drop = 1
            self._head_tilt = 0
            self._arm_offset = 0
            self._poke_timer.start(1500)
        elif state == PetState.TYPING:
            self._mouth_open = 0.1
            self._cheek_blush = 0
            self._tear_drop = 0
            self._head_tilt = 0
            self._arm_offset = 0
        self.update()

    def _recover_from_poke(self):
        """从被戳状态恢复为发呆。"""
        self._set_state(PetState.IDLE)

    def _trigger_blink(self):
        """触发眨眼动画。"""
        if self.state in (PetState.SLEEPY, PetState.POKE):
            return
        self._blinking = True
        QTimer.singleShot(200, self._end_blink)
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
        t = self._frame / ANIMATION_FPS

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
        self._bubble_opacity = 0.0
        self._bubble_fade_in = True
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
            moved = (event.globalPos() - self._drag_start_pos).manhattanLength()
            if moved < 5:
                self._set_state(PetState.POKE)
                self._show_bubble(BUBBLE_POKE_TEXT)
            self._dragging = False
            event.accept()

    # ========================================================
    # 右键菜单
    # ========================================================
    def _show_context_menu(self, pos):
        """显示右键上下文菜单：隐藏宠物、重置位置、退出程序。"""
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

        menu.exec_(pos)

    # ========================================================
    # 功能动作
    # ========================================================
    def hide_pet(self):
        """隐藏宠物窗口（托盘图标保留，可再次显示）。"""
        self._hidden = True
        self.hide()

    def show_pet(self):
        """显示宠物窗口。"""
        self._hidden = False
        self.show()
        self.raise_()
        self.activateWindow()

    def reset_position(self):
        """重置宠物位置到屏幕右下角。"""
        screen = QDesktopWidget().screenGeometry()
        self.move(
            screen.width() - WINDOW_SIZE - 10,
            screen.height() - WINDOW_SIZE - 40
        )
        self._default_pos = self.pos()

    def quit_app(self):
        """退出程序，清理托盘图标和键盘监听线程。"""
        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
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
        """居中绘制宠物图片（已去除白底）。"""
        pw = self._pixmap.width()
        ph = self._pixmap.height()
        x = (PET_SIZE - pw) // 2
        y = (PET_SIZE - ph) // 2
        painter.drawPixmap(x, y, self._pixmap)

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

        font = QFont("Microsoft YaHei", 9, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self._bubble_text) + 16
        th = fm.height() + 8

        # 宠物头顶中心坐标
        pet_cx = WINDOW_SIZE // 2 + self._shake_x
        pet_top = (WINDOW_SIZE - PET_SIZE) // 2 + self._bounce_y
        by = pet_top - th - 12
        if by < 5:
            by = 5
        bx = pet_cx - tw // 2

        # 圆角矩形
        rect = QRectF(bx, by, tw, th)
        painter.drawRoundedRect(rect, 8, 8)

        # 小三角指向宠物中心
        tri = QPainterPath()
        tri.moveTo(pet_cx - 6, by + th)
        tri.lineTo(pet_cx, by + th + 8)
        tri.lineTo(pet_cx + 6, by + th)
        painter.drawPath(tri)

        # 文字
        painter.setPen(QColor(60, 60, 60))
        painter.drawText(rect, Qt.AlignCenter, self._bubble_text)
        painter.setOpacity(1.0)


# ============================================================
# 入口
# ============================================================
def main():
    """程序入口：隐藏控制台黑框并启动应用。"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 隐藏时保持运行

    pet = DesktopPet()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
