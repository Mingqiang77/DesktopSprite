#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows 桌面悬浮宠物 - iKun 桌面精灵
使用 PyQt5 实现，支持代码绘制矢量卡通形象与外部图片加载
"""

import sys
import os
import random
import math
from enum import Enum, auto

from PyQt5.QtWidgets import (
    QApplication, QWidget, QMenu, QAction, QSystemTrayIcon, QDesktopWidget
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRectF
from PyQt5.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QFontMetrics,
    QPixmap, QImage, QIcon, QPainterPath
)

# ============================================================
# 配置常量
# ============================================================
WINDOW_SIZE = 340          # 窗口大小（预留顶部空间给状态气泡）
PET_SIZE = 240             # 宠物绘制区域大小
ANIMATION_FPS = 30         # 动画帧率
STATE_INTERVAL = 4000      # 状态自动切换间隔（毫秒）
BLINK_INTERVAL = 3000      # 眨眼间隔（毫秒）
BUBBLE_TEXTS = ["唱🎤", "跳💃", "Rap🎶打🏀"]  # 气泡文案固定轮播顺序
BUBBLE_POKE_TEXT = "你干嘛~"   # 仅鼠标点击（被戳）时显示
BUBBLE_INTERVAL = 2000     # 气泡文案切换间隔（毫秒）

def _find_image_path():
    """多路径查找 ikun.jpg，兼容 .py 和 .exe 运行方式"""
    candidates = [
        # 脚本/exe 同级目录
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "ikun.jpg"),
        # PyInstaller 打包后 _MEIPASS 临时目录
        os.path.join(getattr(sys, '_MEIPASS', ""), "images", "ikun.jpg"),
        # exe 所在目录
        os.path.join(os.path.dirname(sys.executable), "images", "ikun.jpg"),
        # 当前工作目录
        os.path.join(os.getcwd(), "images", "ikun.jpg"),
        # 上级目录（exe 在 dist/ 子目录时的常见情况）
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
    IDLE = auto()      # 发呆：正常表情，偶尔眨眼
    HAPPY = auto()     # 开心：笑眯眯，轻微弹跳
    SLEEPY = auto()    # 困倦：半闭眼，打哈欠
    POKE = auto()      # 被戳：惊讶/委屈，抖动


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
            Qt.WindowDoesNotAcceptFocus   # 不抢夺焦点
        )
        self.setAttribute(Qt.WA_TranslucentBackground)  # 背景透明
        self.setFixedSize(WINDOW_SIZE, WINDOW_SIZE)

        # 居中显示
        screen = QDesktopWidget().screenGeometry()
        self.move(
            (screen.width() - WINDOW_SIZE) // 2,
            (screen.height() - WINDOW_SIZE) // 2
        )
        self._default_pos = self.pos()

        # ---- 拖拽相关 ----
        self._dragging = False
        self._drag_offset = QPoint()

        # ---- 宠物状态 ----
        self.state = PetState.IDLE
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._auto_switch_state)
        self._state_timer.start(STATE_INTERVAL)

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

        # ---- 气泡文案轮播 ----
        self._bubble_index = 0
        self._bubble_timer = QTimer(self)
        self._bubble_timer.timeout.connect(self._next_bubble_text)
        self._bubble_timer.start(BUBBLE_INTERVAL)

        # ---- 被戳恢复 ----
        self._poke_timer = QTimer(self)
        self._poke_timer.setSingleShot(True)
        self._poke_timer.timeout.connect(self._recover_from_poke)

        # ---- 图片资源 ----
        self._image_mode = False
        self._pixmap = None
        self._load_image()

        # ---- 系统托盘 ----
        self._setup_tray()

        # ---- 其他 ----
        self._hidden = False
        self._bounce_y = 0          # 弹跳偏移
        self._shake_x = 0           # 抖动偏移
        self._mouth_open = 0        # 嘴巴张开程度 (0~1)
        self._eye_openness = 1.0    # 眼睛睁开程度 (0~1)
        self._cheek_blush = 0       # 腮红强度
        self._tear_drop = 0         # 眼泪动画

        self.setWindowTitle("iKun桌面精灵")
        self.show()

    # ========================================================
    # 图片加载
    # ========================================================
    def _load_image(self):
        """尝试加载外部图片，若失败则使用代码绘制模式"""
        path = _find_image_path()
        if path:
            img = QImage(path)
            if not img.isNull():
                # 等比缩放至 PET_SIZE，保持原画完整不做裁切
                pixmap = QPixmap.fromImage(img)
                self._pixmap = pixmap.scaled(
                    PET_SIZE, PET_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._image_mode = True
                return
        self._image_mode = False

    # ========================================================
    # 系统托盘
    # ========================================================
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        # 用简单图标（代码绘制一个16x16的迷你图标）
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
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_pet()

    # ========================================================
    # 状态切换
    # ========================================================
    def _auto_switch_state(self):
        """定时自动轮换状态（排除被戳状态）"""
        if self.state == PetState.POKE:
            return
        choices = [PetState.IDLE, PetState.HAPPY, PetState.SLEEPY]
        weights = [5, 3, 2]
        new_state = random.choices(choices, weights=weights)[0]
        self._set_state(new_state)

    def _set_state(self, state: PetState):
        self.state = state
        self._frame = 0
        if state == PetState.IDLE:
            self._mouth_open = 0
            self._cheek_blush = 0
            self._tear_drop = 0
        elif state == PetState.HAPPY:
            self._mouth_open = 0.3
            self._cheek_blush = 1
            self._tear_drop = 0
        elif state == PetState.SLEEPY:
            self._mouth_open = 0.6
            self._cheek_blush = 0
            self._tear_drop = 0
        elif state == PetState.POKE:
            self._mouth_open = 0.8
            self._cheek_blush = 0
            self._tear_drop = 1
            self._poke_timer.start(1500)
        self.update()

    def _recover_from_poke(self):
        self._set_state(PetState.IDLE)

    def _trigger_blink(self):
        """触发眨眼"""
        if self.state in (PetState.SLEEPY, PetState.POKE):
            return
        self._blinking = True
        QTimer.singleShot(200, self._end_blink)
        self.update()

    def _end_blink(self):
        self._blinking = False
        self.update()

    # ========================================================
    # 动画更新
    # ========================================================
    def _update_animation(self):
        self._frame += 1
        t = self._frame / ANIMATION_FPS  # 秒

        if self.state == PetState.HAPPY:
            # 开心：正弦波弹跳
            self._bounce_y = int(-8 * abs(math.sin(t * 4)))
            self._shake_x = 0
        elif self.state == PetState.SLEEPY:
            # 困倦：缓慢上下浮动
            self._bounce_y = int(-3 * math.sin(t * 1.5))
            self._shake_x = 0
        elif self.state == PetState.POKE:
            # 被戳：高频抖动
            self._bounce_y = int(-4 * abs(math.sin(t * 15)))
            self._shake_x = random.randint(-4, 4)
        else:
            # 发呆：轻微呼吸浮动
            self._bounce_y = int(-2 * math.sin(t * 2))
            self._shake_x = 0

        self.update()

    def _next_bubble_text(self):
        """按固定顺序切换到下一条气泡文案，循环展示"""
        self._bubble_index = (self._bubble_index + 1) % len(BUBBLE_TEXTS)
        self.update()

    # ========================================================
    # 鼠标事件
    # ========================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 开始拖拽
            self._dragging = True
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            # 左键点击触发被戳反应
            self._set_state(PetState.POKE)
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPos() - self._drag_offset
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()

    # ========================================================
    # 右键菜单
    # ========================================================
    def _show_context_menu(self, pos):
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
        self._hidden = True
        self.hide()

    def show_pet(self):
        self._hidden = False
        self.show()
        self.raise_()
        self.activateWindow()

    def reset_position(self):
        screen = QDesktopWidget().screenGeometry()
        self.move(
            (screen.width() - WINDOW_SIZE) // 2,
            (screen.height() - WINDOW_SIZE) // 2
        )
        self._default_pos = self.pos()

    def quit_app(self):
        if hasattr(self, '_tray'):
            self._tray.hide()
        QApplication.instance().quit()

    # ========================================================
    # 绘制核心
    # ========================================================
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 整体偏移（动画）
        offset_x = self._shake_x + (WINDOW_SIZE - PET_SIZE) // 2
        offset_y = self._bounce_y + (WINDOW_SIZE - PET_SIZE) // 2
        painter.translate(offset_x, offset_y)

        if self._image_mode and self._pixmap is not None:
            self._draw_image_mode(painter)
        else:
            self._draw_vector_pet(painter)

        # 在绝对坐标系中绘制状态气泡（避免被窗口边缘裁切）
        painter.resetTransform()
        self._draw_state_bubble_absolute(painter)

        painter.end()

    # --------------------------------------------------------
    # 图片模式绘制（圆形裁切 + 状态特效叠加）
    # --------------------------------------------------------
    def _draw_image_mode(self, painter: QPainter):
        size = PET_SIZE
        cx, cy = size // 2, size // 2
        radius = size // 2 - 4

        # 圆形裁切路径
        painter.save()
        clip = QPainterPath()
        clip.addEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.setClipPath(clip)

        # 绘制图片
        painter.drawPixmap(0, 0, self._pixmap)
        painter.restore()

        # 边框
        pen = QPen(QColor(80, 80, 80), 3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # 状态特效叠加
        if self.state == PetState.SLEEPY:
            # 困倦：暗化蒙版
            painter.setBrush(QBrush(QColor(0, 0, 60, 60)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        elif self.state == PetState.POKE:
            # 被戳：红色抖动蒙版
            painter.setBrush(QBrush(QColor(255, 0, 0, 40)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
            # 眼泪
            self._draw_tears(painter, cx, cy)
        elif self.state == PetState.HAPPY:
            # 开心：星星/腮红
            self._draw_cheek_blush(painter, cx, cy)

    # --------------------------------------------------------
    # 矢量绘制模式（纯代码绘制可爱小鸡 / iKun）
    # --------------------------------------------------------
    def _draw_vector_pet(self, painter: QPainter):
        size = PET_SIZE
        cx, cy = size // 2, size // 2

        # ---- 身体（黄色圆脸） ----
        body_radius = 90
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 220, 80)))
        painter.drawEllipse(cx - body_radius, cy - body_radius + 10, body_radius * 2, body_radius * 2)

        # ---- 中分头发（ikun灵魂） ----
        self._draw_hair(painter, cx, cy, body_radius)

        # ---- 眼睛 ----
        eye_y = cy - 10
        if self.state == PetState.SLEEPY:
            # 困倦：半闭眼线
            self._draw_sleepy_eyes(painter, cx, eye_y)
        elif self.state == PetState.HAPPY:
            # 开心：笑眯眯弧线
            self._draw_happy_eyes(painter, cx, eye_y)
        elif self.state == PetState.POKE:
            # 被戳：惊讶大眼 + 眼泪
            self._draw_poke_eyes(painter, cx, eye_y)
        else:
            # 发呆：正常大眼，支持眨眼
            self._draw_normal_eyes(painter, cx, eye_y)

        # ---- 腮红 ----
        if self.state in (PetState.HAPPY, PetState.POKE):
            self._draw_cheek_blush(painter, cx, cy)

        # ---- 嘴巴 ----
        self._draw_mouth(painter, cx, cy)

        # ---- 篮球 ----
        self._draw_basketball(painter, cx, cy, body_radius)

    # --------------------------------------------------------
    # 各部件绘制
    # --------------------------------------------------------
    def _draw_hair(self, painter: QPainter, cx: int, cy: int, body_radius: int):
        """绘制中分头发"""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(50, 40, 40)))

        # 头发基座（头顶覆盖）
        hair_y = cy - body_radius + 15
        painter.drawEllipse(cx - 75, hair_y, 150, 70)

        # 左分头发束
        left_lock = QPainterPath()
        left_lock.moveTo(cx - 10, hair_y + 20)
        left_lock.quadTo(cx - 50, hair_y - 30, cx - 80, hair_y + 30)
        left_lock.quadTo(cx - 60, hair_y + 60, cx - 10, hair_y + 50)
        painter.drawPath(left_lock)

        # 右分头发束
        right_lock = QPainterPath()
        right_lock.moveTo(cx + 10, hair_y + 20)
        right_lock.quadTo(cx + 50, hair_y - 30, cx + 80, hair_y + 30)
        right_lock.quadTo(cx + 60, hair_y + 60, cx + 10, hair_y + 50)
        painter.drawPath(right_lock)

        # 中间发际线高光
        painter.setBrush(QBrush(QColor(80, 70, 70)))
        painter.drawEllipse(cx - 8, hair_y + 15, 16, 30)

    def _draw_normal_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """正常状态眼睛（支持眨眼）"""
        eye_rx, eye_ry = 28, 32
        eye_open = 0.15 if self._blinking else 1.0

        for dx in (-35, 35):
            ex = cx + dx
            # 眼白
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(ex - eye_rx, eye_y - int(eye_ry * eye_open), eye_rx * 2, int(eye_ry * 2 * eye_open))
            # 边框
            painter.setPen(QPen(QColor(40, 40, 40), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ex - eye_rx, eye_y - int(eye_ry * eye_open), eye_rx * 2, int(eye_ry * 2 * eye_open))
            # 眼珠
            if not self._blinking:
                painter.setBrush(QBrush(QColor(40, 40, 40)))
                painter.setPen(Qt.NoPen)
                pupil_y = eye_y + 5
                painter.drawEllipse(ex - 10, pupil_y - 10, 20, 20)
                # 高光
                painter.setBrush(QBrush(Qt.white))
                painter.drawEllipse(ex - 4, pupil_y - 14, 10, 10)

    def _draw_happy_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """开心状态：笑眯眯弧线"""
        painter.setPen(QPen(QColor(40, 40, 40), 4))
        painter.setBrush(Qt.NoBrush)
        for dx in (-35, 35):
            path = QPainterPath()
            path.moveTo(cx + dx - 20, eye_y + 5)
            path.quadTo(cx + dx, eye_y - 15, cx + dx + 20, eye_y + 5)
            painter.drawPath(path)

    def _draw_sleepy_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """困倦状态：半闭眼"""
        painter.setPen(QPen(QColor(40, 40, 40), 3))
        painter.setBrush(Qt.NoBrush)
        for dx in (-35, 35):
            path = QPainterPath()
            path.moveTo(cx + dx - 18, eye_y - 5)
            path.quadTo(cx + dx, eye_y + 10, cx + dx + 18, eye_y - 5)
            painter.drawPath(path)
            # 下方眼线
            path2 = QPainterPath()
            path2.moveTo(cx + dx - 18, eye_y - 5)
            path2.lineTo(cx + dx + 18, eye_y - 5)
            painter.drawPath(path2)

    def _draw_poke_eyes(self, painter: QPainter, cx: int, eye_y: int):
        """被戳状态：惊讶大眼 + 眼泪"""
        eye_rx, eye_ry = 22, 26
        for dx in (-35, 35):
            ex = cx + dx
            # 眼白
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(ex - eye_rx, eye_y - eye_ry, eye_rx * 2, eye_ry * 2)
            # 边框
            painter.setPen(QPen(QColor(40, 40, 40), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ex - eye_rx, eye_y - eye_ry, eye_rx * 2, eye_ry * 2)
            # 小眼珠（震惊）
            painter.setBrush(QBrush(QColor(40, 40, 40)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(ex - 6, eye_y - 6, 12, 12)
            # 高光
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(ex - 3, eye_y - 10, 6, 6)

        # 眼泪
        self._draw_tears(painter, cx, eye_y + 30)

    def _draw_tears(self, painter: QPainter, cx: int, base_y: int):
        """绘制眼泪"""
        tear_offset = (self._frame * 3) % 20
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(150, 200, 255, 180)))
        for dx in (-35, 35):
            ty = base_y + 20 + tear_offset
            painter.drawEllipse(cx + dx - 4, ty, 8, 12)

    def _draw_cheek_blush(self, painter: QPainter, cx: int, cy: int):
        """绘制腮红"""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 120, 120, 120)))
        for dx in (-65, 65):
            painter.drawEllipse(cx + dx - 18, cy + 15, 36, 24)

    def _draw_mouth(self, painter: QPainter, cx: int, cy: int):
        """绘制嘴巴"""
        mouth_y = cy + 35

        if self.state == PetState.HAPPY:
            # 开心：大笑弧线
            painter.setPen(QPen(QColor(180, 60, 60), 3))
            painter.setBrush(QBrush(QColor(255, 100, 100)))
            path = QPainterPath()
            path.moveTo(cx - 25, mouth_y - 5)
            path.quadTo(cx, mouth_y + 25, cx + 25, mouth_y - 5)
            path.quadTo(cx, mouth_y + 5, cx - 25, mouth_y - 5)
            painter.drawPath(path)
        elif self.state == PetState.SLEEPY:
            # 困倦：打哈欠（大O型）
            openness = 10 + int(10 * abs(math.sin(self._frame / ANIMATION_FPS * 3)))
            painter.setPen(QPen(QColor(160, 60, 60), 2))
            painter.setBrush(QBrush(QColor(80, 30, 40)))
            painter.drawEllipse(cx - 12, mouth_y, 24, openness)
        elif self.state == PetState.POKE:
            # 被戳：委屈波浪嘴
            painter.setPen(QPen(QColor(180, 60, 60), 3))
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - 15, mouth_y + 5)
            path.quadTo(cx - 5, mouth_y - 5, cx, mouth_y + 5)
            path.quadTo(cx + 5, mouth_y - 5, cx + 15, mouth_y + 5)
            painter.drawPath(path)
        else:
            # 发呆：小微笑
            painter.setPen(QPen(QColor(180, 60, 60), 3))
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - 12, mouth_y)
            path.quadTo(cx, mouth_y + 10, cx + 12, mouth_y)
            painter.drawPath(path)

    def _draw_basketball(self, painter: QPainter, cx: int, cy: int, body_radius: int):
        """绘制篮球（ikun元素）"""
        bx = cx + 55
        by = cy + 55
        br = 28

        # 球体
        painter.setPen(QPen(QColor(160, 80, 20), 2))
        painter.setBrush(QBrush(QColor(255, 140, 40)))
        painter.drawEllipse(bx - br, by - br, br * 2, br * 2)

        # 篮球纹路
        painter.setPen(QPen(QColor(120, 50, 10), 2))
        painter.setBrush(Qt.NoBrush)
        # 横线
        painter.drawLine(bx - br + 3, by, bx + br - 3, by)
        # 弧线
        arc1 = QPainterPath()
        arc1.moveTo(bx, by - br + 3)
        arc1.quadTo(bx - br, by, bx, by + br - 3)
        painter.drawPath(arc1)
        arc2 = QPainterPath()
        arc2.moveTo(bx, by - br + 3)
        arc2.quadTo(bx + br, by, bx, by + br - 3)
        painter.drawPath(arc2)

    def _draw_state_bubble_absolute(self, painter: QPainter):
        """在窗口绝对坐标系中绘制气泡文案，按固定顺序每隔两秒切换下一条"""
        if self.state == PetState.POKE:
            # 被戳时固定显示点击文案
            text = BUBBLE_POKE_TEXT
        else:
            text = BUBBLE_TEXTS[self._bubble_index]

        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))

        font = QFont("Microsoft YaHei", 10, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(text) + 16
        th = fm.height() + 8

        # 固定在窗口顶部，x 跟随抖动偏移
        cx = WINDOW_SIZE // 2 + self._shake_x
        by = 10  # 顶部留边，确保不被裁切
        bx = cx - tw // 2

        # 气泡圆角矩形
        rect = QRectF(bx, by, tw, th)
        painter.drawRoundedRect(rect, 8, 8)

        # 小三角（指向宠物中心）
        tri = QPainterPath()
        tri.moveTo(cx - 6, by + th)
        tri.lineTo(cx, by + th + 8)
        tri.lineTo(cx + 6, by + th)
        painter.drawPath(tri)

        # 文字
        painter.setPen(QColor(60, 60, 60))
        painter.drawText(rect, Qt.AlignCenter, text)


# ============================================================
# 入口
# ============================================================
def main():
    # Windows 下隐藏控制台窗口
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
