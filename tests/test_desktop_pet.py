# -*- coding: utf-8 -*-
"""
desktop_pet 核心逻辑回归测试。

全部在 Qt 的 offscreen 平台下运行：不弹窗、不挂钩真实键盘，
可安全地在本地和 CI 中执行。

运行：
    pip install -r requirements-dev.txt
    pytest -q
"""

import os
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication

import desktop_pet as dp


@pytest.fixture(scope="session")
def app():
    """全局唯一的 QApplication（offscreen）。"""
    instance = QApplication.instance() or QApplication(sys.argv)
    instance.setQuitOnLastWindowClosed(False)
    yield instance


@pytest.fixture
def pet(app, monkeypatch):
    """构造宠物实例；禁用 pynput，避免测试机被挂上全局键盘钩子。"""
    monkeypatch.setattr(dp, "PYNPUT_AVAILABLE", False)
    p = dp.DesktopPet()
    yield p
    p._set_timers_active(False)
    p.close()
    p.deleteLater()
    app.processEvents()


# ----------------------------------------------------------------------
# 配置与资源
# ----------------------------------------------------------------------
def test_fatigue_interval_is_30_seconds():
    """疲劳判定必须是 30 秒（曾被写成 1000ms，导致气泡每 2 秒乱弹）。"""
    assert dp.TYPING_FATIGUE_TIME == 30000
    assert dp.TYPING_FATIGUE_TIME > dp.TYPING_TIMEOUT


def test_no_hardcoded_dev_path():
    """源码里不能再出现开发机绝对路径。"""
    with open(dp.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "D:\\iKun" not in source
    assert "_MEIPASS" in source


def test_image_background_removed(pet):
    """白底必须被去干净，而主体（脸）必须保留不透明。"""
    assert pet._image_mode is True
    assert pet._pixmap is not None
    img = pet._pixmap.toImage()
    w, h = img.width(), img.height()
    # 左下角是原图的白底 -> 应完全透明
    assert img.pixelColor(1, h - 2).alpha() == 0
    # 右下角同理
    assert img.pixelColor(w - 2, h - 2).alpha() == 0
    # 中心是脸 / 头发 -> 必须不透明
    assert img.pixelColor(w // 2, h // 2).alpha() > 0
    assert not pet._pet_region.isEmpty()


def test_processing_pipeline_is_fast(pet):
    """整条预处理链（裁边 -> 缩放 -> 去底）要快，启动不能明显卡顿。"""
    src = dp._find_image_path()
    rounds = 3
    start = time.perf_counter()
    for _ in range(rounds):
        raw = dp.QImage(src)
        raw = dp.DesktopPet._trim_border_bands(raw)
        img = raw.scaled(
            dp.PET_SIZE, dp.PET_SIZE, dp.Qt.KeepAspectRatio, dp.Qt.SmoothTransformation
        ).convertToFormat(dp.QImage.Format_ARGB32)
        img.setDevicePixelRatio(1.0)
        dp.DesktopPet._flood_fill_background(img)
    elapsed = (time.perf_counter() - start) / rounds
    assert elapsed < 0.5, f"预处理耗时 {elapsed * 1000:.0f}ms，过慢"


def test_top_border_band_removed(pet):
    """源图顶部 5px 灰边必须裁掉，否则宠物头顶会留下一条可见灰线。"""
    img = pet._pixmap.toImage()
    for x in (2, img.width() // 2, img.width() - 3):
        assert img.pixelColor(x, 0).alpha() == 0, "顶部仍残留不透明边框"


def test_trim_border_bands_synthetic():
    """同色边框带裁剪：灰边要被去掉，且不会把整幅图剪没。"""
    img = dp.QImage(60, 60, dp.QImage.Format_ARGB32)
    img.fill(dp.QColor(255, 255, 255))
    for y in range(6):
        for x in range(60):
            img.setPixelColor(x, y, dp.QColor(93, 93, 93))

    out = dp.DesktopPet._trim_border_bands(img)
    assert out.height() < 60
    assert dp.DesktopPet._same_color(out.pixelColor(0, 0), dp.QColor(255, 255, 255))
    assert out.height() > 40, "裁过头了"


# ----------------------------------------------------------------------
# 键盘联动（跨线程信号）
# ----------------------------------------------------------------------
def test_key_signal_from_worker_thread(pet, app):
    """
    pynput 线程 emit 信号后，主线程处理事件时必须进入 TYPING。
    原实现从子线程调 QTimer.singleShot，子线程没有 Qt 事件循环 -> 回调不执行。
    """
    pet._typing = False
    worker = threading.Thread(target=pet._key_event.emit)
    worker.start()
    worker.join()
    app.processEvents()
    assert pet.state == dp.PetState.TYPING
    assert pet._typing is True


def test_keyboard_listener_does_not_touch_ui():
    """监听回调里不允许出现 QTimer / singleShot 之类的跨线程 UI 调用（注释不算）。"""
    import ast

    with open(dp.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    func = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "on_press"
    )
    # 去掉 docstring 后再看真正的执行语句
    func.body = [
        node for node in func.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    code = ast.unparse(func)
    assert "singleShot" not in code
    assert "_key_event" in code


def test_fatigue_fires_once_per_30s(pet):
    """连续打字每满 30 秒才轮播一条气泡，不是每个按键都弹。"""
    pet._on_key_pressed()
    assert pet.state == dp.PetState.TYPING
    assert pet._bubble_index == 0

    pet._typing_start_time -= 30000          # 拨快 30 秒
    pet._on_key_pressed()
    assert pet._bubble_index == 1
    assert pet._bubble_text == dp.BUBBLE_TEXTS[0]

    pet._on_key_pressed()                    # 紧接着按键：不应重复触发
    assert pet._bubble_index == 1

    pet._end_stretch()                       # 伸懒腰已结束
    pet._typing_start_time -= 30000
    pet._on_key_pressed()
    assert pet._bubble_index == 2
    assert pet._bubble_text == dp.BUBBLE_TEXTS[1]


def test_typing_timeout_returns_to_idle(pet):
    """停手超过 2 秒回到发呆。"""
    pet._on_key_pressed()
    assert pet.state == dp.PetState.TYPING
    pet._last_key_time -= (dp.TYPING_TIMEOUT + 100)
    pet._check_typing_timeout()
    assert pet._typing is False
    assert pet.state == dp.PetState.IDLE


# ----------------------------------------------------------------------
# 被戳 / 气泡
# ----------------------------------------------------------------------
def test_poke_does_not_steal_typing_state(pet):
    """被戳时打字不抢状态；被戳结束后若手还在敲，要接回 TYPING。"""
    pet._on_key_pressed()
    pet._set_state(dp.PetState.POKE)
    assert pet.state == dp.PetState.POKE

    pet._on_typing_start()
    assert pet.state == dp.PetState.POKE       # 被戳优先

    pet._recover_from_poke()
    assert pet.state == dp.PetState.TYPING     # 原实现这里会一直卡在 IDLE


def test_poke_bubble_does_not_move_rotation(pet):
    """被戳文案固定，且不推进疲劳轮播索引。"""
    pet._show_bubble(dp.BUBBLE_POKE_TEXT)
    assert pet._bubble_text == "你干嘛~"
    assert pet._bubble_index == 0


def test_bubble_replaced_without_flash(pet):
    """气泡切换时保持不透明，不再闪一下。"""
    pet._show_bubble(dp.BUBBLE_TEXTS[0])
    pet._bubble_opacity = 1.0
    pet._bubble_fade_in = False
    pet._show_bubble(dp.BUBBLE_TEXTS[1])
    assert pet._bubble_opacity == 1.0
    assert pet._bubble_fade_in is False


# ----------------------------------------------------------------------
# 点击穿透 / 窗口行为
# ----------------------------------------------------------------------
def test_transparent_pixels_pass_clicks_through(pet):
    """透明区域必须不在命中区里，否则会变成一块 220x220 的隐形挡板。"""
    region = pet._opaque_region()
    assert region.contains(QPoint(dp.WINDOW_SIZE // 2, dp.WINDOW_SIZE // 2))
    # 画面左下角（白底已被去掉）应可穿透
    assert not region.contains(QPoint(36, dp.WINDOW_SIZE - 36))


def test_bubble_area_is_clickable(pet):
    """气泡可见时，气泡本身要在命中区内。"""
    pet._show_bubble(dp.BUBBLE_TEXTS[0])
    pet._bubble_opacity = 1.0
    rect = pet._bubble_rect()
    assert pet._opaque_region().contains(rect.center().toPoint())


def test_fps_switches_by_state(pet):
    """活跃状态 30fps，发呆/困倦降帧省 CPU。"""
    pet._set_state(dp.PetState.IDLE)
    assert pet._fps == dp.IDLE_FPS
    assert pet._anim_timer.interval() == max(1, int(1000 / dp.IDLE_FPS))

    pet._set_state(dp.PetState.HAPPY)
    assert pet._fps == dp.ANIMATION_FPS
    assert pet._anim_timer.interval() == max(1, int(1000 / dp.ANIMATION_FPS))


def test_hide_stops_timers(pet):
    """隐藏时停掉动画/眨眼/打字轮询，避免后台空转。"""
    pet.hide_pet()
    assert pet._anim_timer.isActive() is False
    assert pet._blink_timer.isActive() is False
    assert pet._typing_check_timer.isActive() is False

    pet.show_pet()
    assert pet._anim_timer.isActive() is True


def test_context_menu_reused(pet):
    """右键菜单只构建一次，避免长跑累积 QMenu 子对象。"""
    assert isinstance(pet._context_menu, dp.QMenu)
    assert pet._context_menu is pet._context_menu
    assert len(pet._context_menu.actions()) == 4   # 隐藏 / 重置 / 分隔 / 退出


def test_default_position_inside_available_area(pet):
    """默认位置必须落在屏幕可用区域内（不压任务栏）。"""
    geo = dp._screen_available_geometry()
    pos = pet._default_position()
    assert geo.contains(pos)
    assert geo.contains(pos + QPoint(dp.WINDOW_SIZE - 1, dp.WINDOW_SIZE - 1))
