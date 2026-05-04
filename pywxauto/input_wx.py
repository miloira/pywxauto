"""
pywxauto 微信控件输入模块。

对 uiautomation 控件的高层操作封装，根据 _state.background 自动选择：
- 前台模式: 使用 uiautomation 原生方法（需要窗口可见）
- 后台模式: 使用 input_wm 的 SendMessage 方式（不需要窗口在前台）
"""

from __future__ import annotations

import random
import time

import uiautomation as auto
import win32api
import win32con
import win32gui

from . import _state
from . import input_wm


def _rand_ratio() -> float:
    """返回 0.2~0.6 之间的随机比例，用于模拟人类点击偏移"""
    return random.uniform(0.2, 0.6)

def _get_hwnd(control) -> int:
    """从 uiautomation 控件获取所属窗口句柄，向上遍历父控件查找。"""
    hwnd = control.NativeWindowHandle
    if hwnd:
        return hwnd
    parent = control
    while parent:
        hwnd = parent.NativeWindowHandle
        if hwnd:
            return hwnd
        parent = parent.GetParentControl()
    return 0

def _screen_to_client(control) -> tuple[int, int, int]:
    """
    获取控件中心的屏幕坐标，并转换为所属窗口的客户区坐标。

    Returns:
        (hwnd, client_x, client_y)

    Raises:
        RuntimeError: 无法获取窗口句柄
    """
    rect = control.BoundingRectangle
    screen_x = (rect.left + rect.right) // 2
    screen_y = (rect.top + rect.bottom) // 2

    hwnd = _get_hwnd(control)
    if not hwnd:
        raise RuntimeError("无法获取控件所属窗口句柄")

    client_x, client_y = win32gui.ScreenToClient(hwnd, (screen_x, screen_y))
    return hwnd, client_x, client_y

def focus(control) -> None:
    """
    让控件获得焦点。

    前台模式: uiautomation SetFocus
    后台模式: SendMessage WM_SETFOCUS
    """
    if not _state.background:
        control.SetFocus()
    else:
        hwnd = _get_hwnd(control)
        if hwnd:
            input_wm.focus_window(hwnd)

def click(control, button: str = "left", click: str = "once") -> None:
    """
    点击控件。

    前台模式: uiautomation Click/RightClick/DoubleClick
    后台模式: SendMessage 虚拟鼠标消息

    Args:
        control: uiautomation 控件对象
        button:  "left" / "right" / "middle"
        click:   "once" / "double"
    """
    if not _state.background:
        if click == "double":
            control.DoubleClick()
        elif button == "right":
            control.RightClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        else:
            control.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
    else:
        hwnd, cx, cy = _screen_to_client(control)

        if button == "left":
            if click == "double":
                input_wm.double_click_window(hwnd, cx, cy)
            else:
                input_wm.click_window(hwnd, cx, cy)
        elif button == "right":
            input_wm.right_click_window(hwnd, cx, cy)
        elif button == "middle":
            input_wm.middle_click_window(hwnd, cx, cy)
        else:
            raise ValueError(f"无效的 button: {button!r}，可选: left/right/middle")

def send_keys(control, text: str) -> None:
    """
    向控件发送按键。

    前台模式: uiautomation SendKeys
    后台模式: 通过 SendMessage 发送虚拟按键

    支持 SendKeys 格式：
    - 普通字符: "abc"
    - 特殊键: "{Enter}", "{Esc}", "{Del}" 等
    - 组合键: "{Ctrl}a", "{Ctrl}{Shift}a"

    Args:
        control: uiautomation 控件对象，None 时发送到当前焦点窗口
        text:    SendKeys 格式字符串
    """
    if not _state.background:
        if control is None:
            auto.SendKeys(text)
        else:
            control.SendKeys(text)
    else:
        hwnd = 0
        if control is not None:
            hwnd = _get_hwnd(control)
        if not hwnd:
            hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise RuntimeError("无法获取目标窗口句柄")

        input_wm.focus_window(hwnd)
        _send_keys(hwnd, text)

def move_to(control) -> None:
    """
    将鼠标移动到控件中心。

    前台模式: 物理移动鼠标
    后台模式: SendMessage WM_MOUSEMOVE
    """
    rect = control.BoundingRectangle
    screen_x = (rect.left + rect.right) // 2
    screen_y = (rect.top + rect.bottom) // 2

    if not _state.background:
        auto.SetCursorPos(screen_x, screen_y)
    else:
        hwnd = _get_hwnd(control)
        if not hwnd:
            raise RuntimeError("无法获取控件所属窗口句柄")
        client_x, client_y = win32gui.ScreenToClient(hwnd, (screen_x, screen_y))
        input_wm.move_window(hwnd, client_x, client_y)

def scroll_at(x: int, y: int, delta: int) -> None:
    """
    在屏幕指定坐标处滚动鼠标滚轮。

    前台模式: 物理移动鼠标 + mouse_event 滚轮
    后台模式: SendMessage WM_MOUSEWHEEL

    Args:
        x:     屏幕 x 坐标
        y:     屏幕 y 坐标
        delta: 滚动量，正值向上，负值向下（120=一格）
    """
    if not _state.background:
        win32api.SetCursorPos((x, y))
        time.sleep(0.1)
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, x, y, delta, 0)
    else:
        hwnd = win32gui.WindowFromPoint((x, y))
        if hwnd:
            client_x, client_y = win32gui.ScreenToClient(hwnd, (x, y))
            input_wm.scroll_window(hwnd, client_x, client_y, delta)

# ---- 内部：SendKeys 格式解析与后台按键发送 ----
_SENDKEYS_MAP = {
    "{Enter}": win32con.VK_RETURN,
    "{Tab}": win32con.VK_TAB,
    "{Esc}": win32con.VK_ESCAPE,
    "{Escape}": win32con.VK_ESCAPE,
    "{Del}": win32con.VK_DELETE,
    "{Delete}": win32con.VK_DELETE,
    "{Back}": win32con.VK_BACK,
    "{Backspace}": win32con.VK_BACK,
    "{Home}": win32con.VK_HOME,
    "{End}": win32con.VK_END,
    "{Up}": win32con.VK_UP,
    "{Down}": win32con.VK_DOWN,
    "{Left}": win32con.VK_LEFT,
    "{Right}": win32con.VK_RIGHT,
    "{PageUp}": win32con.VK_PRIOR,
    "{PageDown}": win32con.VK_NEXT,
    "{Space}": win32con.VK_SPACE,
    "{F1}": win32con.VK_F1,
    "{F2}": win32con.VK_F2,
    "{F3}": win32con.VK_F3,
    "{F4}": win32con.VK_F4,
    "{F5}": win32con.VK_F5,
}

def _parse_send_keys(text: str) -> list:
    """
    解析 SendKeys 格式字符串为操作序列。

    Returns:
        操作列表，每项为 ("char", ch) / ("key", vk) / ("mod_down", vk) / ("mod_up", vk)
    """
    ops = []
    i = 0
    mod_stack = []

    while i < len(text):
        if text[i] == '{':
            end = text.find('}', i)
            if end == -1:
                ops.append(("char", text[i]))
                i += 1
                continue
            token = text[i:end + 1]
            i = end + 1

            token_lower = token.lower()
            if token_lower == "{ctrl}":
                ops.append(("mod_down", win32con.VK_CONTROL))
                mod_stack.append(win32con.VK_CONTROL)
                continue
            elif token_lower == "{alt}":
                ops.append(("mod_down", win32con.VK_MENU))
                mod_stack.append(win32con.VK_MENU)
                continue
            elif token_lower == "{shift}":
                ops.append(("mod_down", win32con.VK_SHIFT))
                mod_stack.append(win32con.VK_SHIFT)
                continue
            elif token_lower == "{win}":
                ops.append(("mod_down", win32con.VK_LWIN))
                mod_stack.append(win32con.VK_LWIN)
                continue

            vk = _SENDKEYS_MAP.get(token)
            if vk is not None:
                ops.append(("key", vk))
                while mod_stack:
                    ops.append(("mod_up", mod_stack.pop()))
            else:
                for ch in token:
                    ops.append(("char", ch))
        else:
            ops.append(("char", text[i]))
            if mod_stack:
                while mod_stack:
                    ops.append(("mod_up", mod_stack.pop()))
            i += 1

    while mod_stack:
        ops.append(("mod_up", mod_stack.pop()))

    return ops

def _send_keys(hwnd: int, text: str) -> None:
    """
    通过 SendMessage 向窗口发送 SendKeys 格式的按键序列。

    Args:
        hwnd: 窗口句柄
        text: SendKeys 格式字符串
    """
    ops = _parse_send_keys(text)
    active_mods = 0
    for op_type, value in ops:
        if op_type == "char":
            if active_mods > 0:
                vk = ord(value.upper()) if value.isalpha() else ord(value)
                input_wm.key_press_window(hwnd, vk)
            else:
                code = ord(value)
                if code > 127:
                    # 非 ASCII（中文等）使用 WM_IME_CHAR
                    win32gui.SendMessage(hwnd, 0x0286, code, 0)
                else:
                    win32gui.SendMessage(hwnd, win32con.WM_CHAR, code, 0)
        elif op_type == "key":
            input_wm.key_press_window(hwnd, value)
        elif op_type == "mod_down":
            input_wm.key_down_window(hwnd, value)
            active_mods += 1
        elif op_type == "mod_up":
            input_wm.key_up_window(hwnd, value)
            active_mods -= 1

# ---- 快捷键与剪贴板操作 ----
def send_shortcut(text: str) -> None:
    """
    发送快捷键到当前焦点窗口。

    使用 auto.SendKeys 直接发送，不区分前台/后台模式，
    因为快捷键通常需要触发应用的加速键机制。

    Args:
        text: SendKeys 格式字符串，如 "{Ctrl}a", "{Ctrl}c", "{Ctrl}v", "{Enter}"

    用法::

        send_shortcut("{Ctrl}a")   # 全选
        send_shortcut("{Ctrl}c")   # 复制
        send_shortcut("{Ctrl}v")   # 粘贴
        send_shortcut("{Enter}")   # 回车
        send_shortcut("{Ctrl}z")   # 撤销
    """
    auto.SendKeys(text)

def select_all() -> None:
    """全选（Ctrl+A）"""
    send_shortcut("{Ctrl}a")

def copy() -> None:
    """复制（Ctrl+C）"""
    send_shortcut("{Ctrl}c")

def paste(content) -> None:
    """
    通过剪贴板粘贴内容。

    保存当前剪贴板 → 设置内容到剪贴板 → Ctrl+V 粘贴 → 恢复剪贴板。

    Args:
        content: str 粘贴文本，list[str] 粘贴文件路径列表
    """
    from .utils import save_clipboard, restore_clipboard, copy_text, copy_files

    saved = save_clipboard()
    try:
        if isinstance(content, str):
            copy_text(content)
        elif isinstance(content, list):
            copy_files(content)
        else:
            raise TypeError(f"不支持的类型: {type(content)}")
        send_shortcut("{Ctrl}v")
    finally:
        restore_clipboard(saved)
