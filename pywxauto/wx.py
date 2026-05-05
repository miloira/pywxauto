"""
pywxauto - 微信自动化库（单文件合并版）

将所有模块合并为单个文件，便于编译为 .pyd。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from queue import Empty, Queue
from typing import Optional
from typing import Optional, Iterable
import ctypes
import ctypes.wintypes
import fnmatch
import functools
import glob
import io
import json
import logging
import os
import random
import re
import struct
import subprocess
import tempfile
import threading
import time
import urllib

from PIL import Image
from PIL import Image # pip install pillow
from pyee.base import EventEmitter
from rapidocr import RapidOCR
from windows_capture import WindowsCapture, Frame, InternalCaptureControl # pip install windows-capture
import requests
import uiautomation as auto
import win32api
import win32clipboard
import win32con
import win32gui
import win32ui
import winreg

try:
    from pywxauto import wcocr
except ImportError:
    wcocr = None


# ======================================================================
# 模块: _state
# ======================================================================

"""
pywxauto 全局状态模块。

存放跨模块共享的可变状态（如后台模式标志）。
各模块通过 import _state 引用，避免循环依赖。
"""

# 全局后台模式标志，由 Weixin.__init__ 设置
background: bool = False


# ======================================================================
# 模块: exceptions
# ======================================================================

"""
pywxauto 异常体系。
"""


class WxAutoError(Exception):
    """pywxauto 异常基类"""
    pass


class WindowNotFoundError(WxAutoError):
    """窗口或控件未找到"""
    pass


class ControlTimeoutError(WxAutoError):
    """控件查找或操作超时"""
    pass


class SendError(WxAutoError):
    """消息发送失败"""
    pass


class OCRError(WxAutoError):
    """OCR 识别失败"""
    pass


class LoginError(WxAutoError):
    """登录相关异常"""
    pass


class RegistryError(Exception):
    """注册表操作异常"""
    pass


# ======================================================================
# 模块: pim
# ======================================================================

"""
PIM (Physical Input Monitor) - 物理键盘/鼠标输入监控器。
"""


# ---- 底层钩子常量与结构体 ----
_LLKHF_INJECTED = 0x00000010
_LLMHF_INJECTED = 0x00000001
_WH_KEYBOARD_LL = 13
_WH_MOUSE_LL = 14
_WM_QUIT = 0x0012

_LowLevelHookProc = ctypes.WINFUNCTYPE(
    ctypes.c_long,       # LRESULT
    ctypes.c_int,        # nCode
    ctypes.c_ulonglong,  # wParam (WPARAM)
    ctypes.c_void_p,     # lParam (LPARAM)
)

# 设置 CallNextHookEx 参数类型，避免 64 位系统上 lParam 溢出
ctypes.windll.user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,     # hhk (HHOOK)
    ctypes.c_int,        # nCode
    ctypes.c_ulonglong,  # wParam (WPARAM)
    ctypes.c_void_p,     # lParam (LPARAM)
]
ctypes.windll.user32.CallNextHookEx.restype = ctypes.c_long


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class PIM:
    """
    物理键盘/鼠标输入监控器 (Physical Input Monitor)。

    所有状态存储在类变量上，通过类方法操作，全局单例。
    `@PIM.guard` 装饰器可在类定义时使用，参数在实例化后生效。

    用法::

        # 方式1: 上下文管理器
        with PIM(idle_wait=3):
            wx = Weixin()
            wx.send_text("写诗喂狗", "hello")  # 自动等 3 秒物理空闲

        # 方式2: 手动管理
        pim = PIM(idle_wait=3)
        pim.start()
        ...
        pim.stop()

        # 方式3: 类方法装饰器（类定义时使用）
        class Chat:
            @PIM.guard
            def send_text(self, content): ...

            @PIM.guard(5)  # 固定 5 秒，忽略 idle_wait
            def send_file(self, path): ...
    """

    # ---- 类变量（全局单例状态） ----
    idle_wait: float = 0
    lock_input: bool = False
    _running: bool = False
    _last_physical_input: float = 0
    _lock: threading.Lock = threading.Lock()
    _thread: Optional[threading.Thread] = None
    _thread_id: Optional[int] = None
    _kb_proc = None
    _mouse_proc = None

    def __init__(self, idle_wait: float = 0, lock_input: bool = False):
        PIM.idle_wait = idle_wait
        PIM.lock_input = lock_input

    def __call__(self, idle_wait: float = None, lock_input: bool = None) -> "PIM":
        if idle_wait is not None:
            PIM.idle_wait = idle_wait
        if lock_input is not None:
            PIM.lock_input = lock_input
        return self

    def __enter__(self) -> "PIM":
        PIM.start()
        return self

    def __exit__(self, *exc) -> None:
        PIM.stop()

    # ---- 钩子回调 ----

    @staticmethod
    def _touch() -> None:
        with PIM._lock:
            PIM._last_physical_input = time.monotonic()

    @staticmethod
    def _keyboard_hook(nCode, wParam, lParam) -> int:
        if nCode >= 0 and lParam:
            kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if not (kb.flags & _LLKHF_INJECTED):
                PIM._touch()
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    @staticmethod
    def _mouse_hook(nCode, wParam, lParam) -> int:
        if nCode >= 0 and lParam:
            ms = ctypes.cast(lParam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            if not (ms.flags & _LLMHF_INJECTED):
                PIM._touch()
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    @staticmethod
    def _hook_thread() -> None:
        PIM._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        # 回调必须保持引用防止 GC
        PIM._kb_proc = _LowLevelHookProc(PIM._keyboard_hook)
        PIM._mouse_proc = _LowLevelHookProc(PIM._mouse_hook)

        kb_hook = ctypes.windll.user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL, PIM._kb_proc, None, 0,
        )
        mouse_hook = ctypes.windll.user32.SetWindowsHookExW(
            _WH_MOUSE_LL, PIM._mouse_proc, None, 0,
        )

        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

        if kb_hook:
            ctypes.windll.user32.UnhookWindowsHookEx(kb_hook)
        if mouse_hook:
            ctypes.windll.user32.UnhookWindowsHookEx(mouse_hook)

    # ---- 公开方法 ----

    @staticmethod
    def start() -> None:
        """启动物理输入监控"""
        if PIM._running:
            return
        PIM._running = True
        PIM._last_physical_input = time.monotonic()
        PIM._thread = threading.Thread(
            target=PIM._hook_thread, daemon=True, name="pim",
        )
        PIM._thread.start()
        for _ in range(50):
            if PIM._thread_id is not None:
                break
            time.sleep(0.01)

    @staticmethod
    def stop() -> None:
        """停止物理输入监控"""
        if not PIM._running:
            return
        PIM._running = False
        if PIM._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                PIM._thread_id, _WM_QUIT, 0, 0,
            )
        if PIM._thread:
            PIM._thread.join(timeout=3)
        PIM._thread = None
        PIM._thread_id = None

    @staticmethod
    def get_idle_duration() -> float:
        """获取物理空闲秒数"""
        with PIM._lock:
            return time.monotonic() - PIM._last_physical_input

    @staticmethod
    def wait_for_idle(min_idle: float = 3.0, check_interval: float = 0.5) -> None:
        """阻塞等待物理空闲达到指定秒数"""
        while PIM.get_idle_duration() < min_idle:
            time.sleep(check_interval)

    # ---- 锁定/解锁物理输入 ----

    @staticmethod
    def block_input() -> None:
        """锁定物理键盘鼠标输入（需要管理员权限）"""
        ctypes.windll.user32.BlockInput(True)

    @staticmethod
    def unblock_input() -> None:
        """解锁物理键盘鼠标输入"""
        ctypes.windll.user32.BlockInput(False)

    # ---- 装饰器 ----

    @staticmethod
    def guard(func_or_wait=None):
        """
        类装饰器：被装饰的方法执行前等待物理输入空闲。

        等待时间和是否锁定输入由 PIM.idle_wait 和 PIM.lock_input 控制，
        通过 PIM(idle_wait=3, lock_input=True) 或 Weixin(idle_wait=3, lock_input=True) 设置。

        Args:
            func_or_wait: 函数或等待秒数（覆盖 idle_wait）

        用法::

            @PIM.guard
            def send_text(self, content): ...

            @PIM.guard(5)  # 固定 5 秒
            def send_file(self, path): ...
        """
        def _make_wrapper(fn, idle_wait=None, lock_input=None):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                if PIM._running and PIM.idle_wait > 0:
                    t = idle_wait if idle_wait is not None else PIM.idle_wait
                    PIM.wait_for_idle(t)
                should_lock = lock_input if lock_input is not None else PIM.lock_input
                if should_lock:
                    PIM.block_input()
                try:
                    return fn(*args, **kwargs)
                finally:
                    if should_lock:
                        PIM.unblock_input()
            return wrapper

        if callable(func_or_wait):
            return _make_wrapper(func_or_wait)

        if isinstance(func_or_wait, (int, float)):
            fixed = float(func_or_wait)
            def decorator(fn):
                return _make_wrapper(fn, idle_wait=fixed)
            return decorator

        if func_or_wait is None:
            def decorator(fn):
                return _make_wrapper(fn)
            return decorator

        raise TypeError(f"PIM.guard 参数类型错误: {type(func_or_wait)}")


# ======================================================================
# 模块: input_wm
# ======================================================================

######## 窗口操作
def minimize_window(hwnd):
    """最小化窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MINIMIZE, 0)

def maximize_window(hwnd):
    """最大化窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MAXIMIZE, 0)

def restore_window(hwnd):
    """还原窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)

def close_window(hwnd):
    """关闭窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)

def focus_window(hwnd):
    """聚焦窗口（不激活）"""
    win32gui.SendMessage(hwnd, win32con.WM_SETFOCUS, 0, 0)

def activate_window(hwnd):
    """激活窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)

def deactivate_window(hwnd):
    """取消激活窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_INACTIVE, 0)

def move_window(hwnd, x, y):
    """移动窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_MOVE, 0, (y << 16) | x)

def resize_window(hwnd, width, height):
    """设置窗口大小"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SIZE, 0, (height << 16) | width)

def show_window(hwnd):
    """显示窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_SHOWWINDOW, True, 0)

def hide_window(hwnd):
    """隐藏窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_SHOWWINDOW, False, 0)

def toggle_window(hwnd, status):
    """切换窗口状态

    Args:
        hwnd: 窗口句柄
        status: 目标状态
            - "minimize": 最小化/还原 切换
            - "maximize": 最大化/还原 切换
            - "show": 显示/隐藏 切换
    """
    placement = win32gui.GetWindowPlacement(hwnd)
    current = placement[1]

    if status == "minimize":
        if current == win32con.SW_SHOWMINIMIZED:
            return restore_window(hwnd)
        else:
            return minimize_window(hwnd)

    elif status == "maximize":
        if current == win32con.SW_SHOWMAXIMIZED:
            return restore_window(hwnd)
        else:
            return maximize_window(hwnd)

    elif status == "show":
        if win32gui.IsWindowVisible(hwnd):
            return hide_window(hwnd)
        else:
            return show_window(hwnd)

######## 鼠标操作
def move_window(hwnd, x, y):
    """鼠标移动到指定位置"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lParam)

def click_window(hwnd, x, y):
    """鼠标左键单击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)

def double_click_window(hwnd, x, y):
    """鼠标左键双击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)

def right_click_window(hwnd, x, y):
    """鼠标右键单击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_RBUTTONUP, 0, lParam)

def middle_click_window(hwnd, x, y):
    """鼠标中键单击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_MBUTTONDOWN, win32con.MK_MBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_MBUTTONUP, 0, lParam)

def scroll_window(hwnd, x, y, delta=120):
    """鼠标滚轮滚动

    Args:
        hwnd: 窗口句柄
        x, y: 鼠标位置
        delta: 滚动量，正值向上滚，负值向下滚（默认120=向上一格）
    """
    lParam = win32api.MAKELONG(x, y)
    wParam = win32api.MAKELONG(0, delta)
    return not win32gui.SendMessage(hwnd, win32con.WM_MOUSEWHEEL, wParam, lParam)

######## 键盘操作
def key_down_window(hwnd, key):
    """按下一个键（不释放）"""
    vk = ord(key.upper()) if isinstance(key, str) else key
    return not win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)

def key_up_window(hwnd, key):
    """释放一个键"""
    vk = ord(key.upper()) if isinstance(key, str) else key
    return not win32gui.SendMessage(hwnd, win32con.WM_KEYUP, vk, 0)

def key_press_window(hwnd, key):
    """按下并释放一个键

    Args:
        hwnd: 窗口句柄
        key: 按键，可以是字符('A')或虚拟键码(win32con.VK_RETURN)
    """
    return key_down_window(hwnd, key) and key_up_window(hwnd, key)

def key_hotkey_window(hwnd, modifier, key):
    """发送热键消息（需要目标窗口已注册该热键）

    Args:
        hwnd: 窗口句柄
        modifier: 修饰键，如 win32con.MOD_CONTROL, win32con.MOD_ALT, win32con.MOD_SHIFT
                  可组合使用：win32con.MOD_CONTROL | win32con.MOD_ALT
        key: 按键的虚拟键码，如 ord('A'), win32con.VK_F4
    """
    lParam = (key << 16) | modifier
    return not win32gui.SendMessage(hwnd, win32con.WM_HOTKEY, 0, lParam)

def key_type_window(hwnd, text):
    """输入一段文本

    Args:
        hwnd: 窗口句柄
        text: 要输入的文本字符串
    """
    results = []
    for c in text:
        results.append(win32gui.SendMessage(hwnd, win32con.WM_CHAR, ord(c), 0))
    return all(results)



# ---- input_wm 命名空间（供其他模块通过 input_wm.xxx 调用） ----
class _InputWmNamespace:
    """模拟 input_wm 模块命名空间，使 input_wm.xxx() 调用方式继续工作"""
    minimize_window = staticmethod(minimize_window)
    maximize_window = staticmethod(maximize_window)
    restore_window = staticmethod(restore_window)
    close_window = staticmethod(close_window)
    focus_window = staticmethod(focus_window)
    activate_window = staticmethod(activate_window)
    deactivate_window = staticmethod(deactivate_window)
    move_window = staticmethod(move_window)
    resize_window = staticmethod(resize_window)
    show_window = staticmethod(show_window)
    hide_window = staticmethod(hide_window)
    toggle_window = staticmethod(toggle_window)
    click_window = staticmethod(click_window)
    double_click_window = staticmethod(double_click_window)
    right_click_window = staticmethod(right_click_window)
    middle_click_window = staticmethod(middle_click_window)
    scroll_window = staticmethod(scroll_window)
    key_down_window = staticmethod(key_down_window)
    key_up_window = staticmethod(key_up_window)
    key_press_window = staticmethod(key_press_window)
    key_hotkey_window = staticmethod(key_hotkey_window)
    key_type_window = staticmethod(key_type_window)

input_wm = _InputWmNamespace()

# ======================================================================
# 模块: utils
# ======================================================================

"""
pywxauto 工具函数模块。

包含注册表查询、微信路径检测、剪贴板操作、窗口查找等底层工具。
"""




# ---- 常量 ----
# DROPFILES struct: pFiles(uint), x(long), y(long), fNC(int), fWide(bool)
DROPFILES_FORMAT = "Illii"
DROPFILES_SIZE = struct.calcsize(DROPFILES_FORMAT)

# 剪贴板保存/恢复时优先尝试的格式（按优先级排列）
CLIPBOARD_SAVE_FORMATS = [
    win32con.CF_HDROP,         # 文件列表
    win32con.CF_DIB,           # 图片 (DIB)
    win32con.CF_UNICODETEXT,   # Unicode 文本
    win32con.CF_TEXT,          # ANSI 文本
]

# ---- 注册表与路径工具 ----
def query_reg_install_path(reg_path: str) -> Optional[str]:
    try:
        root_map = {
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
        }

        root_name, sub_key = reg_path.split("\\", 1)
        root = root_map.get(root_name)

        if not root:
            return None

        with winreg.OpenKey(root, sub_key) as key:
            for value_name in ["InstallLocation", "InstallPath", "Path", "UninstallString"]:
                try:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    if value:
                        return value
                except FileNotFoundError:
                    continue
    except Exception:
        return None

    return None

def get_weixin_install_path():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Tencent\Weixin",
        )
        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
        winreg.CloseKey(key)
        return install_path
    except FileNotFoundError:
        raise LoginError("未找到微信安装路径，请确认微信已安装")

def get_wechat_install_path(version: Optional[int] = None) -> Optional[str]:
    reg_paths_map = {
        3: [
            r"HKCU\Software\Tencent\WeChat",
        ],
        4: [
            r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Weixin",
            r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Weixin",
        ],
    }

    if version in reg_paths_map:
        reg_paths = reg_paths_map[version]
    else:
        reg_paths = reg_paths_map[3] + reg_paths_map[4]

    for reg in reg_paths:
        path = query_reg_install_path(reg)
        if path:
            path = path.replace('"', '')

        if path and os.path.exists(path):
            result = glob.glob(fr'{path}\*\WeChatOcr.bin')
            if result:
                return os.path.dirname(result[0])

    default_dirs = [
        r"C:\Program Files\Tencent\WeChat",
        r"C:\Program Files (x86)\Tencent\WeChat",
        r"D:\Program Files\WeChat",
        r"D:\Tencent\WeChat",
    ]

    for path in default_dirs:
        if os.path.exists(path):
            result = glob.glob(fr'{path}\*\WeChatOcr.bin')
            if result:
                return os.path.dirname(result[0])

    return None

def get_wechat_wxocr_path() -> Optional[str]:
    appdata_path = os.getenv('APPDATA')

    ocr_dir = os.path.join(appdata_path, r"Tencent\xwechat\XPlugin\Plugins\WeChatOcr")
    if not os.path.exists(ocr_dir):
        return None

    result = glob.glob(fr"{ocr_dir}\*\extracted\wxocr.dll")
    if len(result) == 0:
        return None

    return os.path.join(os.path.dirname(result[0]), "wxocr.dll")

def _wechat3_version_int2str(v: int) -> str:
    """将微信3.x的版本号整数转换为字符串，如 0x63090a13 -> '3.9.10.19'"""
    major = (v >> 24) & 0xFF
    minor = (v >> 16) & 0xFF
    build = (v >> 8) & 0xFF
    patch = v & 0xFF
    major = major - 0x60
    return f"{major}.{minor}.{build}.{patch}"

def _wechat4_version_int2str(v: int) -> str:
    """将微信4.x的版本号整数转换为字符串，如 0x04000112 -> '4.0.1.18'"""
    version = hex(v)
    ver_str = version[5:]
    major = int(ver_str[0], 16)
    minor = int(ver_str[1], 16)
    build = int(ver_str[2], 16)
    patch = int(ver_str[3:], 16)
    return f"{major}.{minor}.{build}.{patch}"

def get_wechat_version(version: int = 3) -> str:
    """
    从注册表读取微信版本号字符串。

    Args:
        version: 微信大版本号，3 或 4

    Returns:
        版本号字符串，如 "3.9.10.19" 或 "4.0.1.18"

    Raises:
        ValueError: 不支持的版本号
        FileNotFoundError: 注册表中未找到版本信息
    """
    if version == 3:
        reg_path = r"Software\Tencent\WeChat"
        to_wechat_version = _wechat3_version_int2str
    elif version == 4:
        reg_path = r"Software\Tencent\Weixin"
        to_wechat_version = _wechat4_version_int2str
    else:
        raise ValueError(f"Not support WeChat version: {version}")

    for KEY in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
        try:
            key = winreg.OpenKey(KEY, reg_path)
            ver_int, _ = winreg.QueryValueEx(key, "Version")
            winreg.CloseKey(key)
            return to_wechat_version(ver_int)
        except FileNotFoundError:
            continue
        except Exception as e:
            raise e

    raise FileNotFoundError(f"未在注册表中找到微信{version}.x版本信息")

def get_hwnd(title=None, mode="exact"):
    """根据窗口标题获取窗口句柄

    Args:
        title: 窗口标题，传None获取当前激活的窗口句柄
        mode: 匹配模式
            - "exact": 完全匹配
            - "wildcard": 通配符匹配（支持 * 和 ?）
            - "regex": 正则表达式匹配

    Returns:
        匹配到的窗口句柄
    """
    if title is None:
        return win32gui.GetForegroundWindow()

    results = []

    def enum_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        window_title = win32gui.GetWindowText(hwnd)
        if not window_title:
            return

        if mode == "exact":
            if window_title == title:
                results.append(hwnd)
        elif mode == "wildcard":
            if fnmatch.fnmatch(window_title, title):
                results.append(hwnd)
        elif mode == "regex":
            if re.search(title, window_title):
                results.append(hwnd)

    win32gui.EnumWindows(enum_callback, None)
    return results[0] if results else None

def ensure_narrator_registry() -> bool:
    """
    检查并修复 UI Automation 所需的注册表项。

    检查 HKCU\\SOFTWARE\\Microsoft\\Narrator\\NoRoam 下的 RunningState，
    如果值为 0 则设为 1。

    Returns:
        bool: True 表示修改了注册表，False 表示无需修改
    """
    reg_path = r"SOFTWARE\Microsoft\Narrator\NoRoam"
    key_name = "RunningState"
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, reg_path, 0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )
        try:
            try:
                value, _ = winreg.QueryValueEx(key, key_name)
                if value == 0:
                    winreg.SetValueEx(key, key_name, 0, winreg.REG_DWORD, 1)
                    return True
                return False
            except FileNotFoundError:
                winreg.SetValueEx(key, key_name, 0, winreg.REG_DWORD, 1)
                return True
        finally:
            winreg.CloseKey(key)
    except PermissionError as e:
        raise RegistryError(f"注册表访问被拒绝: {e}")
    except Exception as e:
        raise RegistryError(f"注册表访问失败: {e}")

# ---- 剪贴板操作 ----
def get_clipboard() -> str:
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return data
        return ""
    finally:
        win32clipboard.CloseClipboard()

def save_clipboard() -> Optional[tuple[int, object]]:
    """
    保存当前剪贴板中的一条数据（按优先级匹配格式）。

    Returns:
        (format, data) 元组，剪贴板为空时返回 None
    """
    win32clipboard.OpenClipboard()
    try:
        for fmt in CLIPBOARD_SAVE_FORMATS:
            if win32clipboard.IsClipboardFormatAvailable(fmt):
                try:
                    data = win32clipboard.GetClipboardData(fmt)
                    return (fmt, data)
                except Exception:
                    continue
        return None
    finally:
        win32clipboard.CloseClipboard()

def restore_clipboard(saved: Optional[tuple[int, object]]) -> None:
    """
    恢复之前保存的剪贴板数据。

    Args:
        saved: save_clipboard 返回的 (format, data)，None 则清空剪贴板
    """
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        if saved:
            fmt, data = saved
            try:
                win32clipboard.SetClipboardData(fmt, data)
            except Exception:
                pass
    finally:
        win32clipboard.CloseClipboard()

def set_clipboard(fmt, data) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(fmt, data)
    finally:
        win32clipboard.CloseClipboard()

def copy_text(text) -> None:
    if text.isdigit():
        text += "\0"
    set_clipboard(win32con.CF_UNICODETEXT, text)

def copy_files(file_paths) -> None:
    header = struct.pack(DROPFILES_FORMAT, DROPFILES_SIZE, 0, 0, 0, True)
    files = "\0".join(p.replace("/", "\\") for p in file_paths)
    payload = files.encode("utf-16-le") + b"\0\0\0\0"
    set_clipboard(win32con.CF_HDROP, header + payload)

# ---- 网络下载 ----
def is_url(path: str) -> bool:
    """判断路径是否为网络 URL"""
    return path.startswith("http://") or path.startswith("https://")

def download_to_temp(url: str, timeout: int = 60) -> str:
    """
    下载网络资源到临时文件，返回临时文件路径。

    从 URL 中提取原始文件名，保留后缀以便微信正确识别文件类型。
    下载失败时抛出 RuntimeError。
    """
    parsed = urllib.parse.urlparse(url)
    url_path = urllib.parse.unquote(parsed.path)
    basename = os.path.basename(url_path) if url_path else ""
    _, ext = os.path.splitext(basename) if basename else ("", "")
    if not ext:
        ext = ".tmp"
    if not basename:
        basename = f"download{ext}"

    tmp_dir = os.path.join(tempfile.gettempdir(), "pywxauto_downloads")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, basename)

    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        raise RuntimeError(f"下载文件失败: {url} -> {e}")

    return tmp_path

# ---- 其他工具 ----
def rand_ratio() -> float:
    """返回 0.2~0.6 之间的随机比例，用于模拟人类点击偏移"""
    return random.uniform(0.2, 0.6)

# 别名（原模块间 import as 的兼容）
_is_url = is_url
_download_to_temp = download_to_temp
_rand_ratio = rand_ratio


# ======================================================================
# 模块: capture
# ======================================================================

try:
    # https://docs.microsoft.com/en-us/windows/win32/api/shellscalingapi/nf-shellscalingapi-setprocessdpiawareness
    # Once SetProcessDpiAwareness is set for an app, any future calls to SetProcessDpiAwareness will fail.
    # Windows 8.1+
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # 支持每个显示器不同 DPI
except Exception as ex:
    pass


def capture_by_bitblt(
    hwnd: int, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0
) -> bytes:
    """BitBlt方式截取窗口图像（窗口必须可见）"""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    win_width = right - left
    win_height = bottom - top

    crop_width = win_width - offset_left - offset_right
    crop_height = win_height - offset_top - offset_bottom
    if crop_width <= 0 or crop_height <= 0:
        raise ValueError(f"裁剪后区域无效: {crop_width}x{crop_height}")

    hwndDC = win32gui.GetWindowDC(hwnd)
    try:
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitmap = win32ui.CreateBitmap()
        saveBitmap.CreateCompatibleBitmap(mfcDC, crop_width, crop_height)
        saveDC.SelectObject(saveBitmap)

        saveDC.BitBlt((0, 0), (crop_width, crop_height), mfcDC,
                      (offset_left, offset_top), win32con.SRCCOPY)

        bmp_info = saveBitmap.GetInfo()
        bmp_str = saveBitmap.GetBitmapBits(True)

        img = Image.frombuffer("RGB",
                               (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                               bmp_str, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(saveBitmap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def capture_by_print_window(
    hwnd: int, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0
) -> bytes:
    """PrintWindow方式截取窗口图像（支持后台截图）"""
    if hwnd == win32gui.GetDesktopWindow():
        raise ValueError("PrintWindow 不支持截取整个桌面，请使用 bitblt 或 window_capture 模式")

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    win_width = right - left
    win_height = bottom - top

    hwndDC = win32gui.GetWindowDC(hwnd)
    try:
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitmap = win32ui.CreateBitmap()
        saveBitmap.CreateCompatibleBitmap(mfcDC, win_width, win_height)
        saveDC.SelectObject(saveBitmap)

        ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

        bmp_info = saveBitmap.GetInfo()
        bmp_str = saveBitmap.GetBitmapBits(True)

        img = Image.frombuffer("RGB",
                               (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                               bmp_str, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(saveBitmap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

    if offset_left or offset_top or offset_right or offset_bottom:
        crop_box = (offset_left, offset_top,
                    win_width - offset_right, win_height - offset_bottom)
        img = img.crop(crop_box)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def capture_by_window_capture(
    hwnd: int, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0
) -> bytes:
    """Windows.Graphics.Capture方式截取窗口图像（支持后台截图）"""
    result = {}

    # 判断是否为桌面窗口，桌面用 monitor_index 截全屏
    desktop_hwnd = win32gui.GetDesktopWindow()
    if hwnd == desktop_hwnd:
        wc = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            monitor_index=1
        )
    else:
        wc = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            window_hwnd=hwnd
        )

    @wc.event
    def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
        arr = frame.frame_buffer
        h, w = arr.shape[:2]
        end_h = h - offset_bottom if offset_bottom else h
        end_w = w - offset_right if offset_right else w
        result["buffer"] = arr[offset_top:end_h, offset_left:end_w, :].copy()
        capture_control.stop()

    @wc.event
    def on_closed():
        pass

    wc.start()

    arr = result["buffer"]
    img = Image.fromarray(arr[:, :, 2::-1])  # BGRA -> RGB
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def capture_window(
    hwnd: int = None, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0, 
    mode: str = "bitblt"
) -> bytes:
    """统一截图接口

    Args:
        hwnd: 窗口句柄，传None截取整个屏幕
        offset_left: 左边裁剪偏移（正数向内裁剪）
        offset_top: 上边裁剪偏移（正数向内裁剪）
        offset_right: 右边裁剪偏移（正数向内裁剪）
        offset_bottom: 下边裁剪偏移（正数向内裁剪）
        mode: 截图模式
            - "bitblt": BitBlt方式（窗口必须可见）
            - "print_window": PrintWindow方式（支持后台截图）
            - "window_capture": Windows.Graphics.Capture方式（支持后台截图）

    Returns:
        PNG 格式的图像字节数据
    """
    if hwnd is None:
        hwnd = win32gui.GetDesktopWindow()

    if mode == "bitblt":
        return capture_by_bitblt(hwnd, offset_left, offset_top, offset_right, offset_bottom)
    elif mode == "print_window":
        return capture_by_print_window(hwnd, offset_left, offset_top, offset_right, offset_bottom)
    elif mode == "window_capture":
        return capture_by_window_capture(hwnd, offset_left, offset_top, offset_right, offset_bottom)
    else:
        raise ValueError(f"不支持的截图模式: {mode}")

def capture_control(
    hwnd: int, 
    uia_control,
    offset_left: int = 0, 
    offset_top: int = 0,
    offset_right: int = 0, 
    offset_bottom: int = 0, 
    mode: str = "bitblt"
) -> bytes:
    """
    通过截取窗口图像，然后裁剪出指定控件区域。

    Args:
        hwnd:          窗口句柄
        uia_control:   uiautomation 控件对象，需要有 BoundingRectangle 属性
        offset_left:   左边裁剪像素（正值向内收缩）
        offset_top:    上边裁剪像素（正值向内收缩）
        offset_right:  右边裁剪像素（正值向内收缩）
        offset_bottom: 下边裁剪像素（正值向内收缩）
        mode:          截图模式（bitblt / print_window / window_capture）

    Returns:
        PNG 格式的 bytes 数据（裁剪后的控件区域图像）
    """
    # 获取窗口位置
    win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)

    # 获取控件的屏幕坐标
    rect = uia_control.BoundingRectangle
    ctrl_left = rect.left - win_left + offset_left
    ctrl_top = rect.top - win_top + offset_top
    ctrl_right = rect.right - win_left - offset_right
    ctrl_bottom = rect.bottom - win_top - offset_bottom

    # 先截取完整窗口
    data = capture_window(hwnd, mode=mode)

    # 裁剪控件区域
    img = Image.open(io.BytesIO(data))
    img = img.crop((ctrl_left, ctrl_top, ctrl_right, ctrl_bottom))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ======================================================================
# 模块: input_wx
# ======================================================================

"""
pywxauto 微信控件输入模块。

对 uiautomation 控件的高层操作封装，根据 background 自动选择：
- 前台模式: 使用 uiautomation 原生方法（需要窗口可见）
- 后台模式: 使用 input_wm 的 SendMessage 方式（不需要窗口在前台）
"""


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

def _screen_to_client(control, randomize: bool = True) -> tuple[int, int, int]:
    """
    获取控件的屏幕坐标，并转换为所属窗口的客户区坐标。

    Args:
        control:   uiautomation 控件对象
        randomize: True 时在控件区域内随机偏移（模拟人类点击），
                   False 时取控件中心

    Returns:
        (hwnd, client_x, client_y)

    Raises:
        RuntimeError: 无法获取窗口句柄
    """
    rect = control.BoundingRectangle
    if randomize:
        # 在控件 20%~80% 区域内随机取点，避免点到边缘
        rx = random.uniform(0.2, 0.8)
        ry = random.uniform(0.2, 0.8)
        screen_x = int(rect.left + (rect.right - rect.left) * rx)
        screen_y = int(rect.top + (rect.bottom - rect.top) * ry)
    else:
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
    if not background:
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
    if not background:
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
    后台模式:
      - 组合键（含 {Ctrl}/{Alt}/{Shift}/{Win}）: 使用 auto.SendKeys 直接发送
      - 普通按键/文本: 通过 SendMessage 发送虚拟按键

    支持 SendKeys 格式：
    - 普通字符: "abc"
    - 特殊键: "{Enter}", "{Esc}", "{Del}" 等
    - 组合键: "{Ctrl}a", "{Ctrl}{Shift}a"

    Args:
        control: uiautomation 控件对象，None 时发送到当前焦点窗口
        text:    SendKeys 格式字符串
    """
    if not background:
        if control is None:
            auto.SendKeys(text, interval=0)
        else:
            control.SendKeys(text, interval=0)
    else:
        # 后台模式下，组合键必须使用 auto.SendKeys 发送，
        # 因为 WM_KEYDOWN 无法可靠模拟修饰键组合
        _MOD_TOKENS = ("{ctrl}", "{alt}", "{shift}", "{win}")
        has_modifier = any(tok in text.lower() for tok in _MOD_TOKENS)

        if has_modifier:
            auto.SendKeys(text, interval=0)
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

    if not background:
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
    if not background:
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
    auto.SendKeys(text, interval=0)

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



# ---- input_wx 命名空间（供其他模块通过 input_wx.xxx 调用） ----
class _InputWxNamespace:
    """模拟 input_wx 模块命名空间，使 input_wx.xxx() 调用方式继续工作"""
    focus = staticmethod(focus)
    click = staticmethod(click)
    send_keys = staticmethod(send_keys)
    move_to = staticmethod(move_to)
    scroll_at = staticmethod(scroll_at)
    send_shortcut = staticmethod(send_shortcut)
    select_all = staticmethod(select_all)
    copy = staticmethod(copy)
    paste = staticmethod(paste)

input_wx = _InputWxNamespace()

# ======================================================================
# 模块: messages
# ======================================================================

"""
pywxauto 消息类体系。

包含 Event 枚举、Message 基类及所有消息子类。
"""


from typing import TYPE_CHECKING


# ---- 消息事件类型 ----
class Event(str, Enum):
    """消息事件类型枚举"""
    ALL = "all_message"
    TEXT = "text_message"
    IMAGE = "image_message"
    VIDEO = "video_message"
    FILE = "file_message"
    VOICE = "voice_message"
    QUOTE = "quote_message"
    EMOTION = "emotion_message"
    LOCATION = "location_message"
    LINK = "link_message"
    CARD = "card_message"
    PERSONAL_CARD = "personal_card_message"
    MERGE = "merge_message"
    NOTE = "note_message"
    VOIP = "voip_message"
    RED_PACKET = "red_packet_message"
    TRANSFER = "transfer_message"
    MUSIC = "music_message"
    SYSTEM = "system_message"
    OTHER = "other_message"


# ---- 消息来源与状态 ----
class SenderType(Enum):
    """消息来源类型"""
    SYSTEM = "system"
    SELF = "self"
    FRIEND = "friend"
    UNKNOWN = "unknown"


class MessageStatus(Enum):
    """消息发送状态"""
    SENT = "sent"
    SENDING = "sending"
    FAILED = "failed"
    RECEIVED = "received"
    UNKNOWN = "unknown"


# ---- 消息基类 ----
class Message:
    """聊天消息基类"""

    def __init__(self, *, sender: str = "", sender_type: SenderType = SenderType.UNKNOWN,
                 content: str = "", raw_name: str = "",
                 status: MessageStatus = MessageStatus.UNKNOWN,
                 runtime_id: tuple = (), bubble_rect: tuple = ()):
        self.sender: str = sender
        self.sender_type: SenderType = sender_type
        self.content: str = content
        self.raw_name: str = raw_name
        self.status: MessageStatus = status
        self.runtime_id: tuple = runtime_id
        self.bubble_rect: tuple = bubble_rect
        self.chat: object = None

    @property
    def type_label(self) -> str:
        return "消息"

    def to_dict(self) -> dict:
        result = {
            "type": self.__class__.__name__,
            "type_label": self.type_label,
            "sender": self.sender,
            "sender_type": self.sender_type.value,
            "content": self.content,
            "raw_name": self.raw_name,
            "status": self.status.value,
        }
        _base_keys = {"sender", "sender_type", "content", "raw_name",
                      "status", "runtime_id", "chat"}
        for key, value in self.__dict__.items():
            if key.startswith("_") or key in _base_keys:
                continue
            if key not in result:
                result[key] = value
        return result

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        status_tag = f", status={self.status.value}" if self.status != MessageStatus.UNKNOWN else ""
        return (f"{cls}(sender_type={self.sender_type.value}, "
                f"sender={self.sender!r}, content={self.content!r}{status_tag})")

    def __str__(self) -> str:
        cls = self.__class__.__name__
        _skip = {"chat", "runtime_id", "raw_name", "bubble_rect"}
        parts = []
        for key, value in self.__dict__.items():
            if key.startswith("_") or key in _skip:
                continue
            if isinstance(value, Enum):
                parts.append(f"{key}={value.value}")
            else:
                parts.append(f"{key}={value!r}")
        return f"{cls}({', '.join(parts)})"

    def _find_ctrl(self) -> "auto.Control | None":
        if not self.chat or not self.runtime_id:
            return None
        lc = self.chat._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return None
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            try:
                rid = tuple(ctrl.GetRuntimeId())
            except Exception:
                continue
            if rid == self.runtime_id:
                return ctrl
        return None

    def scroll_to_visible(self) -> bool:
        if not self.chat or not self.runtime_id:
            return False

        lc = self.chat._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return False

        ctrl = self._find_ctrl()
        if ctrl:
            return self._ensure_visible(lc, ctrl)

        for _ in range(50):
            lc.WheelUp(wheelTimes=5)
            time.sleep(0.15)
            ctrl = self._find_ctrl()
            if ctrl:
                return self._ensure_visible(lc, ctrl)

        for _ in range(50):
            lc.WheelDown(wheelTimes=5)
            time.sleep(0.15)
        for _ in range(50):
            lc.WheelDown(wheelTimes=5)
            time.sleep(0.15)
            ctrl = self._find_ctrl()
            if ctrl:
                return self._ensure_visible(lc, ctrl)

        return False

    @staticmethod
    def _ensure_visible(lc, ctrl) -> bool:
        list_rect = lc.BoundingRectangle
        for _ in range(10):
            ctrl_rect = ctrl.BoundingRectangle
            if ctrl_rect.top >= list_rect.top and ctrl_rect.bottom <= list_rect.bottom - 10:
                return True
            if ctrl_rect.top < list_rect.top:
                lc.WheelUp(wheelTimes=2)
            else:
                lc.WheelDown(wheelTimes=2)
            time.sleep(0.2)
        return True

    def hover(self) -> bool:
        if not self.scroll_to_visible():
            return False

        target = self._find_ctrl()
        if not target:
            return False

        rect = target.BoundingRectangle
        cy = (rect.top + rect.bottom) // 2

        if self.bubble_rect:
            bl, bt, br, bb = self.bubble_rect
            cx = (bl + br) // 2
            cy = (bt + bb) // 2
        elif self.sender_type == SenderType.SELF:
            cx = rect.right - rect.width() // 4
        elif self.sender_type == SenderType.FRIEND:
            cx = rect.left + rect.width() // 4
        else:
            cx = (rect.left + rect.right) // 2

        if not background:
            auto.SetCursorPos(cx, cy)
        else:
            hwnd = target.NativeWindowHandle
            if not hwnd:
                parent = target
                while parent:
                    hwnd = parent.NativeWindowHandle
                    if hwnd:
                        break
                    parent = parent.GetParentControl()
            if hwnd:
                client_x, client_y = win32gui.ScreenToClient(hwnd, (cx, cy))
                input_wm.move_window(hwnd, client_x, client_y)

        time.sleep(0.3)
        return True


# ---- 消息子类 ----
class TextMessage(Message):
    """文本消息"""
    @property
    def type_label(self) -> str:
        return "文本消息"


class QuoteMessage(Message):
    """引用消息"""

    _QUOTE_RE = re.compile(
        r'^(.+?)引用\s+(.+?)\s+的消息\s*:\s*(.+?)[\n\r]*$',
        re.DOTALL,
    )

    def __init__(self, *, reply_content="", quote_sender="", quote_content="", **kw):
        super().__init__(**kw)
        self.reply_content: str = reply_content
        self.quote_sender: str = quote_sender
        self.quote_content: str = quote_content

    @property
    def type_label(self) -> str:
        return "引用消息"

    @staticmethod
    def match(raw_name: str) -> bool:
        return bool(QuoteMessage._QUOTE_RE.match(raw_name))

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str, str, str]:
        m = QuoteMessage._QUOTE_RE.match(raw_name)
        if m:
            reply_content = m.group(1).strip()
            quote_sender = m.group(2).strip()
            quote_content = m.group(3).strip()
            return reply_content, reply_content, quote_sender, quote_content
        return raw_name, raw_name, "", ""


class VoiceMessage(Message):
    """语音消息"""

    def __init__(self, *, duration=0, played=True, **kw):
        super().__init__(**kw)
        self.duration: int = duration
        self.played: bool = played

    @property
    def type_label(self) -> str:
        return "语音消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, int, bool]:
        m = re.match(r"语音(\d+)\"秒(.*)", raw_name)
        if m:
            dur = int(m.group(1))
            state = m.group(2).strip()
            played = "未播放" not in state
            return f"{dur}秒语音{'(未播放)' if not played else ''}", dur, played
        return raw_name, 0, True


class ImageMessage(Message):
    """图片消息"""
    @property
    def type_label(self) -> str:
        return "图片消息"


class VideoMessage(Message):
    """视频消息"""
    @property
    def type_label(self) -> str:
        return "视频消息"


class FileMessage(Message):
    """文件消息"""

    def __init__(self, *, file_name="", **kw):
        super().__init__(**kw)
        self.file_name: str = file_name

    @property
    def type_label(self) -> str:
        return "文件消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str]:
        parts = raw_name.split("\n", 1)
        fname = parts[1].strip() if len(parts) > 1 else raw_name
        return fname, fname


class LocationMessage(Message):
    """位置消息"""

    def __init__(self, *, address="", **kw):
        super().__init__(**kw)
        self.address: str = address

    @property
    def type_label(self) -> str:
        return "位置消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str]:
        addr = raw_name[2:] if raw_name.startswith("位置") else raw_name
        return addr, addr


class LinkMessage(Message):
    """链接消息"""

    def __init__(self, *, title="", source="", **kw):
        super().__init__(**kw)
        self.title: str = title
        self.source: str = source

    @property
    def type_label(self) -> str:
        return "链接消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str, str]:
        if raw_name.startswith("[链接]"):
            body = raw_name[len("[链接]"):]
            parts = [p.strip() for p in body.split("\n") if p.strip()]
            title = parts[0] if parts else body
            source = parts[1] if len(parts) > 1 else ""
            return title, title, source

        if raw_name.startswith("链接\n") or raw_name.startswith("链接\r"):
            parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
            title = parts[1] if len(parts) > 1 else raw_name
            source = parts[2] if len(parts) > 2 else ""
            return title, title, source

        parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
        title = parts[0] if parts else raw_name
        source = parts[1] if len(parts) > 1 else ""
        return title, title, source


class EmotionMessage(Message):
    """表情消息"""

    _EMOJI_NAME_RE = re.compile(r"\[(.+?)\]")

    def __init__(self, *, emoji_name="", **kw):
        super().__init__(**kw)
        self.emoji_name: str = emoji_name

    @property
    def type_label(self) -> str:
        return "表情消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str]:
        m = EmotionMessage._EMOJI_NAME_RE.search(raw_name)
        emoji_name = m.group(1) if m else ""
        return raw_name, emoji_name


class MergeMessage(Message):
    """合并消息"""
    @property
    def type_label(self) -> str:
        return "合并消息"


class PersonalCardMessage(Message):
    """名片消息"""

    def __init__(self, *, card_name="", **kw):
        super().__init__(**kw)
        self.card_name: str = card_name

    @property
    def type_label(self) -> str:
        return "名片消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str]:
        name = raw_name[:-5] if raw_name.endswith("_个人名片") else raw_name
        return name, name


class NoteMessage(Message):
    """笔记消息"""
    @property
    def type_label(self) -> str:
        return "笔记消息"


class MusicMessage(Message):
    """音乐分享消息"""

    _MUSIC_SOURCES = (
        "QQ音乐", "网易云音乐", "酷狗音乐", "酷我音乐",
        "虾米音乐", "咪咕音乐", "Apple Music", "Spotify",
    )

    def __init__(self, *, source="", song_name="", artist="", **kw):
        super().__init__(**kw)
        self.source: str = source
        self.song_name: str = song_name
        self.artist: str = artist

    @property
    def type_label(self) -> str:
        return "音乐消息"

    @staticmethod
    def match(raw_name: str) -> bool:
        return any(raw_name.startswith(src) for src in MusicMessage._MUSIC_SOURCES)

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str, str, str]:
        source = ""
        rest = raw_name
        for src in MusicMessage._MUSIC_SOURCES:
            if raw_name.startswith(src):
                source = src
                rest = raw_name[len(src):]
                break
        return rest, source, rest, ""


class CardMessage(Message):
    """卡片消息"""

    def __init__(self, *, title="", description="", **kw):
        super().__init__(**kw)
        self.title: str = title
        self.description: str = description

    @property
    def type_label(self) -> str:
        return "卡片消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str, str]:
        parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
        title = parts[0] if parts else raw_name
        description = parts[1] if len(parts) > 1 else ""
        content = title
        return content, title, description


class SystemMessage(Message):
    """系统消息"""

    def __init__(self, *, timestamp="", **kw):
        kw.setdefault("sender_type", SenderType.SYSTEM)
        kw.setdefault("sender", "系统")
        super().__init__(**kw)
        self.timestamp: str = timestamp

    @property
    def type_label(self) -> str:
        return "系统消息"


class VoipMessage(Message):
    """语音/视频通话消息"""

    def __init__(self, *, call_type="", call_status="", **kw):
        super().__init__(**kw)
        self.call_type: str = call_type
        self.call_status: str = call_status

    @property
    def type_label(self) -> str:
        return "通话消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str, str]:
        for prefix in ("语音通话", "视频通话"):
            if raw_name.startswith(prefix):
                call_status = raw_name[len(prefix):]
                return raw_name, prefix, call_status
        return raw_name, "", raw_name


class TransferMessage(Message):
    """微信转账消息"""

    _TRANSFER_RE = re.compile(r"^￥([\d.]+)\s+(.+?)\s+微信转账$")
    _TRANSFER_NO_REMARK_RE = re.compile(r"^￥([\d.]+)\s+微信转账$")

    def __init__(self, *, amount="", remark="", **kw):
        super().__init__(**kw)
        self.amount: str = amount
        self.remark: str = remark

    @property
    def type_label(self) -> str:
        return "转账消息"

    def accept(self) -> bool:
        return self._click_transfer_button("收款")

    def reject(self) -> bool:
        return self._click_transfer_button("退还")

    def _click_transfer_button(self, button_name: str) -> bool:
        if not self.hover():
            return False
        ctrl = self._find_ctrl()
        if not ctrl:
            return False
        input_wx.click(ctrl)
        time.sleep(1)
        win = self.chat._win
        btn = win.ButtonControl(Name=button_name, searchDepth=10)
        if not btn.Exists(maxSearchSeconds=3):
            return False
        btn.GetInvokePattern().Invoke()
        time.sleep(1)
        return True

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str, str]:
        m = TransferMessage._TRANSFER_RE.match(raw_name)
        if m:
            amount = m.group(1)
            remark = m.group(2).strip()
            return f"￥{amount}", amount, remark
        m = TransferMessage._TRANSFER_NO_REMARK_RE.match(raw_name)
        if m:
            amount = m.group(1)
            return f"￥{amount}", amount, ""
        return raw_name, "", ""


class RedPacketMessage(Message):
    """微信红包消息"""

    _RED_PACKET_RE = re.compile(r"^(.+?)\s{2,}微信红包$")

    def __init__(self, *, greeting="", **kw):
        super().__init__(**kw)
        self.greeting: str = greeting

    @property
    def type_label(self) -> str:
        return "红包消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str]:
        m = RedPacketMessage._RED_PACKET_RE.match(raw_name)
        if m:
            greeting = m.group(1).strip()
            return greeting, greeting
        return raw_name, raw_name


class OtherMessage(Message):
    """其他/未识别消息"""
    @property
    def type_label(self) -> str:
        return "其他消息"


# ---- 消息类 -> 事件类型映射 ----
MSG_CLASS_TO_EVENT: dict[type, Event] = {
    TextMessage: Event.TEXT,
    ImageMessage: Event.IMAGE,
    VideoMessage: Event.VIDEO,
    FileMessage: Event.FILE,
    VoiceMessage: Event.VOICE,
    QuoteMessage: Event.QUOTE,
    EmotionMessage: Event.EMOTION,
    LocationMessage: Event.LOCATION,
    LinkMessage: Event.LINK,
    CardMessage: Event.CARD,
    PersonalCardMessage: Event.PERSONAL_CARD,
    MergeMessage: Event.MERGE,
    NoteMessage: Event.NOTE,
    VoipMessage: Event.VOIP,
    RedPacketMessage: Event.RED_PACKET,
    TransferMessage: Event.TRANSFER,
    MusicMessage: Event.MUSIC,
    SystemMessage: Event.SYSTEM,
    OtherMessage: Event.OTHER,
}

_MSG_CLASS_TO_EVENT = MSG_CLASS_TO_EVENT


# ======================================================================
# 模块: windows
# ======================================================================

"""
pywxauto 窗口类模块。

包含 WeixinWindow 基类、Login、VoipCallWindow、NoteEditorWindow。
"""


logger = logging.getLogger(__name__)


class WeixinWindow:
    """
    微信窗口基类，封装通用的窗口操作。

    子类需要设置 self._win 为 uiautomation 的 WindowControl 实例。
    提供 activate、pin、unpin、minimize、maximize、restore、close 等通用操作，
    支持两种模式：
    - event=True（默认）: 通过 Windows 消息 API 操作，不需要窗口可见
    - event=False: 通过点击标题栏按钮操作，模拟用户行为
    """

    # 子类可覆盖，指定标题栏按钮的 ClassName
    _PIN_BTN_CLASS = "mmui::PinnedButton"
    _BTN_CLASS = "mmui::XButton"

    @property
    def _window(self) -> auto.WindowControl:
        """获取窗口控件，子类可覆盖"""
        return self._win

    @property
    def is_topmost(self) -> bool:
        """窗口是否已置顶"""
        return self._window.IsTopmost()

    @property
    def is_minimized(self) -> bool:
        """窗口是否已最小化"""
        return self._window.IsMinimize()

    @property
    def is_maximized(self) -> bool:
        """窗口是否已最大化"""
        return self._window.IsMaximize()

    @PIM.guard
    def activate(self) -> None:
        """激活窗口（置前并聚焦），后台模式下跳过"""
        if background:
            return
        self._window.SetActive()
        self._window.SetFocus()
        time.sleep(0.2)

    @PIM.guard
    def pin(self, event: bool = True, simulate_move: bool = True) -> None:
        """置顶窗口"""
        if event:
            self._window.SetTopmost(True)
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._PIN_BTN_CLASS, Name="置顶",
            )
            if btn.Exists(0, 0):
                input_wx.click(btn)

    @PIM.guard
    def unpin(self, event: bool = True, simulate_move: bool = True) -> None:
        """取消置顶窗口"""
        if event:
            self._window.SetTopmost(False)
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._PIN_BTN_CLASS, Name="取消置顶",
            )
            if btn.Exists(0, 0):
                input_wx.click(btn)

    @PIM.guard
    def minimize(self, event: bool = True, simulate_move: bool = True) -> None:
        """最小化窗口"""
        if event:
            self._window.Minimize()
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._BTN_CLASS, Name="最小化",
            )
            if not btn.Exists(maxSearchSeconds=1):
                raise RuntimeError("未找到最小化按钮")
            input_wx.click(btn)

    @PIM.guard
    def maximize(self, event: bool = True, simulate_move: bool = True) -> None:
        """最大化/还原窗口"""
        if event:
            if self.is_maximized:
                self._window.Restore()
            else:
                self._window.Maximize()
        else:
            self.activate()
            for name in ("最大化", "还原"):
                btn = self._window.ButtonControl(
                    ClassName=self._BTN_CLASS, Name=name,
                )
                if btn.Exists(0, 0):
                    input_wx.click(btn)
                    return
            raise RuntimeError("未找到最大化/还原按钮")

    def restore(self) -> None:
        """还原窗口"""
        self._window.Restore()

    @PIM.guard
    def close(self, event: bool = True, simulate_move: bool = True) -> None:
        """关闭窗口"""
        if event:
            wp = self._window.GetWindowPattern()
            if wp:
                wp.Close()
            else:
                raise RuntimeError("窗口不支持 WindowPattern.Close")
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._BTN_CLASS, Name="关闭",
            )
            if not btn.Exists(maxSearchSeconds=1):
                raise RuntimeError("未找到关闭按钮")
            input_wx.click(btn)


class Login(WeixinWindow):
    """
    微信登录窗口操作类。

    微信 4.x 的登录窗口在启动后、进入主界面前显示，
    提供"进入微信"、"切换账号"、"仅传输文件"等操作。

    关键控件信息（来自 desktop-ui-inspector 对微信 4.x 的实际检查）：
    - 窗口: WindowControl, ClassName="mmui::LoginWindow", Name="微信"
    - 标题栏: ToolBarControl, ClassName="mmui::TitleBar"
      - 关闭按钮: ButtonControl, ClassName="mmui::XButton", Name="关闭"
      - 标题文本: TextControl, ClassName="mmui::XTextView", Name="微信"
      - 网络代理设置: ButtonControl, ClassName="mmui::XButton", Name="网络代理设置"
    - 头像: ButtonControl, ClassName="mmui::XAvatarImage"
    - 用户名: TextControl, ClassName="mmui::XTextView",
              AutomationId="current_login_nick_name",
              Name 格式: "当前登录用户{昵称}"
    - 进入微信: ButtonControl, ClassName="mmui::XOutlineButton", Name="进入微信"
    - 切换账号: ButtonControl, ClassName="mmui::XButton", Name="切换账号"
    - 仅传输文件: ButtonControl, ClassName="mmui::XButton", Name="仅传输文件"
    """

    WINDOW_CLASS = "mmui::LoginWindow"
    WINDOW_NAME = "微信"
    NICKNAME_ID = "current_login_nick_name"
    ENTER_BTN_NAME = "进入微信"
    ENTER_BTN_CLASS = "mmui::XOutlineButton"
    SWITCH_ACCOUNT_BTN_NAME = "切换账号"
    TRANSFER_ONLY_BTN_NAME = "仅传输文件"
    PROXY_BTN_NAME = "网络代理设置"

    def __init__(self):
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            Name=self.WINDOW_NAME,
            Depth=1,
        )

    @property
    def exists(self) -> bool:
        """登录窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=3)

    def _ensure_exists(self) -> None:
        if not self._win.Exists(maxSearchSeconds=3):
            raise WindowNotFoundError("微信登录窗口未找到")

    @property
    def nickname(self) -> str:
        """
        获取当前登录用户昵称。

        从 AutomationId="current_login_nick_name" 的 TextControl 中提取，
        Name 格式为 "当前登录用户{昵称}"，去掉前缀后返回昵称部分。

        Returns:
            用户昵称字符串，未找到时返回空字符串
        """
        self._ensure_exists()
        txt = self._win.TextControl(
            AutomationId=self.NICKNAME_ID,
        )
        if not txt.Exists(maxSearchSeconds=2):
            return ""
        name = txt.Name or ""
        prefix = "当前登录用户"
        if name.startswith(prefix):
            return name[len(prefix):]
        return name

    @PIM.guard
    def enter(self, timeout: int = 30) -> bool:
        """
        点击"进入微信"按钮登录。

        点击后等待登录窗口消失（表示已进入主界面）。

        Args:
            timeout: 等待登录窗口消失的超时时间（秒），默认 30 秒

        Returns:
            True 登录成功（窗口已消失）

        Raises:
            RuntimeError: 未找到按钮或登录超时
        """
        self._ensure_exists()
        self.activate()
        btn = self._win.ButtonControl(
            ClassName=self.ENTER_BTN_CLASS,
            Name=self.ENTER_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'进入微信'按钮")
        input_wx.click(btn)

        # 等待登录窗口消失
        for _ in range(timeout):
            if not self._win.Exists(maxSearchSeconds=1):
                logger.info("已进入微信")
                return True
            time.sleep(1)

        raise LoginError("登录超时，登录窗口未关闭")

    @PIM.guard
    def switch_account(self) -> None:
        """
        点击"切换账号"按钮。

        切换到账号选择/扫码登录界面。
        """
        self._ensure_exists()
        self.activate()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.SWITCH_ACCOUNT_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'切换账号'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

    @PIM.guard
    def transfer_only(self) -> None:
        """
        点击"仅传输文件"按钮。

        进入仅文件传输模式，不登录完整微信。
        """
        self._ensure_exists()
        self.activate()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.TRANSFER_ONLY_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'仅传输文件'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

    # ---- 网络代理设置相关控件信息 ----
    # 代理设置页面在 LoginWindow 内部通过 QStackedWidget 切换显示，
    # 不是独立窗口，所有控件仍在 self._win 下。
    #
    # 标题栏变化:
    #   - "网络代理设置"按钮消失，出现"返回"按钮
    #   - 返回按钮: ButtonControl, ClassName="mmui::XButton", Name="返回"
    # 页面标题: TextControl, ClassName="mmui::XTextView", Name="网络代理设置"
    # 使用代理开关: CheckBoxControl, ClassName="mmui::XSwitchButton", Name="使用代理"
    #   支持 TogglePattern (toggleState: 0=关, 1=开)
    # 开启代理后显示的表单字段:
    #   - 地址: EditControl, ClassName="mmui::XLineEdit", Name="地址"
    #   - 端口: EditControl, ClassName="mmui::XLineEdit", Name="端口"
    #   - 账户: EditControl, ClassName="mmui::XLineEdit", Name="账户"
    #   - 密码: EditControl, ClassName="mmui::XLineEdit", Name="密码"
    # 保存按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="保存"

    PROXY_BACK_BTN_NAME = "返回"
    PROXY_SWITCH_NAME = "使用代理"
    PROXY_SWITCH_CLASS = "mmui::XSwitchButton"
    PROXY_SAVE_BTN_NAME = "保存"
    PROXY_SAVE_BTN_CLASS = "mmui::XOutlineButton"
    PROXY_EDIT_CLASS = "mmui::XLineEdit"
    PROXY_ADDR_NAME = "地址"
    PROXY_PORT_NAME = "端口"
    PROXY_USER_NAME = "账户"
    PROXY_PASS_NAME = "密码"

    def _is_proxy_page_open(self) -> bool:
        """判断当前是否在代理设置页面（通过检测"返回"按钮是否存在）"""
        back_btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.PROXY_BACK_BTN_NAME,
        )
        return back_btn.Exists(0, 0)

    def _ensure_proxy_page(self) -> None:
        """确保当前在代理设置页面，如果不在则打开"""
        if not self._is_proxy_page_open():
            self.open_proxy_settings()

    @PIM.guard
    def open_proxy_settings(self) -> None:
        """
        点击"网络代理设置"按钮，进入代理配置页面。

        代理设置页面在 LoginWindow 内部通过 QStackedWidget 切换显示，
        点击后标题栏的"网络代理设置"按钮消失，出现"返回"按钮。
        """
        self._ensure_exists()
        self.activate()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.PROXY_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'网络代理设置'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

        # 等待代理设置页面出现
        back_btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.PROXY_BACK_BTN_NAME,
        )
        if not back_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("代理设置页面未打开")

    @PIM.guard
    def close_proxy_settings(self) -> None:
        """
        点击"返回"按钮，从代理设置页面返回登录页面。
        """
        self._ensure_exists()
        if not self._is_proxy_page_open():
            return

        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.PROXY_BACK_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'返回'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

    @property
    def is_proxy_enabled(self) -> bool:
        """
        获取"使用代理"开关的当前状态。

        Returns:
            True 代理已开启，False 代理已关闭
        """
        self._ensure_exists()
        self._ensure_proxy_page()
        sw = self._win.CheckBoxControl(
            ClassName=self.PROXY_SWITCH_CLASS,
            Name=self.PROXY_SWITCH_NAME,
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'使用代理'开关")
        toggle = sw.GetTogglePattern()
        if toggle:
            return toggle.ToggleState == 1
        return False

    @PIM.guard
    def enable_proxy(self) -> None:
        """
        开启代理。

        如果代理已开启则不操作。
        """
        self._ensure_exists()
        self._ensure_proxy_page()
        if self.is_proxy_enabled:
            return
        sw = self._win.CheckBoxControl(
            ClassName=self.PROXY_SWITCH_CLASS,
            Name=self.PROXY_SWITCH_NAME,
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'使用代理'开关")
        input_wx.click(sw)
        time.sleep(0.5)

    @PIM.guard
    def disable_proxy(self) -> None:
        """
        关闭代理。

        如果代理已关闭则不操作。
        """
        self._ensure_exists()
        self._ensure_proxy_page()
        if not self.is_proxy_enabled:
            return
        sw = self._win.CheckBoxControl(
            ClassName=self.PROXY_SWITCH_CLASS,
            Name=self.PROXY_SWITCH_NAME,
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'使用代理'开关")
        input_wx.click(sw)
        time.sleep(0.5)

    def _find_proxy_edit(self, name: str) -> auto.EditControl:
        """
        在代理设置页面中查找指定名称的输入框。

        输入框: EditControl, ClassName="mmui::XLineEdit"

        Args:
            name: 输入框名称（"地址"、"端口"、"账户"、"密码"）

        Returns:
            EditControl 控件

        Raises:
            RuntimeError: 代理未开启或未找到输入框
        """
        if not self.is_proxy_enabled:
            raise RuntimeError("代理未开启，无法操作表单字段")
        edit = self._win.EditControl(
            ClassName=self.PROXY_EDIT_CLASS,
            Name=name,
        )
        if not edit.Exists(maxSearchSeconds=2):
            raise RuntimeError(f"未找到'{name}'输入框")
        return edit

    def _set_proxy_field(self, name: str, value: str) -> None:
        """设置代理表单字段的值"""
        edit = self._find_proxy_edit(name)
        input_wx.click(edit)
        time.sleep(0.2)
        input_wx.send_keys(edit, "{Ctrl}a{Del}")
        time.sleep(0.1)
        vp = edit.GetValuePattern()
        if vp:
            vp.SetValue(value)
        else:
            input_wx.send_keys(edit, value)
        time.sleep(0.2)

    def _get_proxy_field(self, name: str) -> str:
        """获取代理表单字段的值"""
        edit = self._find_proxy_edit(name)
        vp = edit.GetValuePattern()
        if vp:
            return vp.Value or ""
        return ""

    @PIM.guard
    def set_proxy(self, address: str = "", port: str = "",
                  username: str = "", password: str = "") -> None:
        """
        设置代理参数。

        自动打开代理设置页面，开启代理开关，填写表单字段。
        仅填写非空参数对应的字段。

        Args:
            address:  代理地址
            port:     代理端口
            username: 代理账户（可选）
            password: 代理密码（可选）
        """
        self._ensure_exists()
        self._ensure_proxy_page()
        self.enable_proxy()

        if address:
            self._set_proxy_field(self.PROXY_ADDR_NAME, address)
        if port:
            self._set_proxy_field(self.PROXY_PORT_NAME, port)
        if username:
            self._set_proxy_field(self.PROXY_USER_NAME, username)
        if password:
            self._set_proxy_field(self.PROXY_PASS_NAME, password)

    def get_proxy(self) -> dict:
        """
        获取当前代理配置。

        Returns:
            dict: {
                "enabled": bool,
                "address": str,
                "port": str,
                "username": str,
                "password": str,
            }
            代理未开启时 address/port/username/password 为空字符串。
        """
        self._ensure_exists()
        self._ensure_proxy_page()

        enabled = self.is_proxy_enabled
        result = {
            "enabled": enabled,
            "address": "",
            "port": "",
            "username": "",
            "password": "",
        }
        if enabled:
            result["address"] = self._get_proxy_field(self.PROXY_ADDR_NAME)
            result["port"] = self._get_proxy_field(self.PROXY_PORT_NAME)
            result["username"] = self._get_proxy_field(self.PROXY_USER_NAME)
            result["password"] = self._get_proxy_field(self.PROXY_PASS_NAME)
        return result

    @PIM.guard
    def save_proxy(self) -> None:
        """
        点击"保存"按钮保存代理设置。

        保存后自动返回登录页面。
        """
        self._ensure_exists()
        self._ensure_proxy_page()
        btn = self._win.ButtonControl(
            ClassName=self.PROXY_SAVE_BTN_CLASS,
            Name=self.PROXY_SAVE_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'保存'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

    @PIM.guard
    def close(self, event: bool = True, simulate_move: bool = True) -> None:
        """
        关闭登录窗口。

        Args:
            event: True — 通过 WindowPattern 关闭（默认）
                         False — 点击标题栏"关闭"按钮
            simulate_move: 是否模拟鼠标移动（仅 event=False 时有效）
        """
        self._ensure_exists()
        if event:
            wp = self._win.GetWindowPattern()
            if wp:
                wp.Close()
            else:
                raise RuntimeError("登录窗口不支持 WindowPattern.Close")
        else:
            self.activate()
            btn = self._win.ButtonControl(
                ClassName="mmui::XButton",
                Name="关闭",
            )
            if not btn.Exists(maxSearchSeconds=1):
                raise RuntimeError("未找到关闭按钮")
            input_wx.click(btn)
        time.sleep(0.3)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "Login(closed)"
        nick = self.nickname
        return f"Login(user={nick!r})"


class VoipCallWindow:
    """
    语音/视频通话窗口控制。

    窗口: mmui::VOIPWindow, AutomationId="VOIPWindow"
    标题栏: mmui::TitleBar (置顶/最小化/最大化/关闭)
    信息区: mmui::XStackedWidget
      - 呼叫者视图: AutomationId="voip_caller_view"
      - 联系人名称: AutomationId="voip_caller_view.voip_caller_name"
      - 通话状态: AutomationId="voip_caller_view.voip_caller_tips"
    工具栏: mmui::P2PVOIPToolBarView
      语音通话 (一行3按钮):
        - 麦克风: Name="麦克风已开"/"麦克风已关"
        - 取消/挂断: Name="取消"/"挂断"
        - 扬声器: Name="扬声器已开"/"扬声器已关"
      视频通话 (第一行3按钮 + 第二行1按钮):
        - 麦克风: Name="麦克风已开"/"麦克风已关"
        - 扬声器: Name="扬声器已开"/"扬声器已关"
        - 摄像头: Name="摄像头已开"/"摄像头已关"/"无摄像头"
        - 取消/挂断: Name="取消"/"挂断"
    """

    WINDOW_CLASS = "mmui::VOIPWindow"
    WINDOW_ID = "VOIPWindow"

    def __init__(self):
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            AutomationId=self.WINDOW_ID,
        )

    @property
    def exists(self) -> bool:
        """通话窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=2)

    def _ensure_exists(self) -> None:
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError("通话窗口未找到")

    @property
    def _toolbar(self) -> auto.GroupControl:
        return self._win.GroupControl(ClassName="mmui::P2PVOIPToolBarView")

    def _find_toolbar_button(self, *names: str) -> auto.ButtonControl:
        """在工具栏中查找按钮（按名称模糊匹配）"""
        self._ensure_exists()
        toolbar = self._toolbar
        for name in names:
            btn = toolbar.ButtonControl(
                ClassName="mmui::XButton", Name=name, searchDepth=5,
            )
            if btn.Exists(0, 0):
                return btn
        raise RuntimeError(f"工具栏中未找到按钮: {names}")

    @property
    def contact_name(self) -> str:
        """获取通话对方名称"""
        self._ensure_exists()
        txt = self._win.TextControl(
            AutomationId="voip_caller_view.voip_caller_name",
        )
        return txt.Name if txt.Exists(0, 0) else ""

    @property
    def status(self) -> str:
        """获取通话状态文本（如 '等待对方接受邀请...'、'通话中 01:23'）"""
        self._ensure_exists()
        txt = self._win.TextControl(
            AutomationId="voip_caller_view.voip_caller_tips",
        )
        return txt.Name if txt.Exists(0, 0) else ""

    @property
    def is_mic_on(self) -> bool:
        """麦克风是否开启"""
        try:
            self._find_toolbar_button("麦克风已开")
            return True
        except RuntimeError:
            return False

    @property
    def is_speaker_on(self) -> bool:
        """扬声器是否开启"""
        try:
            self._find_toolbar_button("扬声器已开")
            return True
        except RuntimeError:
            return False

    @property
    def is_camera_on(self) -> bool:
        """摄像头是否开启（仅视频通话）"""
        try:
            self._find_toolbar_button("摄像头已开")
            return True
        except RuntimeError:
            return False

    @property
    def has_camera(self) -> bool:
        """是否有可用摄像头（仅视频通话）"""
        try:
            self._find_toolbar_button("无摄像头")
            return False
        except RuntimeError:
            return True

    @PIM.guard
    def toggle_mic(self) -> None:
        """切换麦克风开关"""
        btn = self._find_toolbar_button("麦克风已开", "麦克风已关")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def toggle_speaker(self) -> None:
        """切换扬声器开关"""
        btn = self._find_toolbar_button("扬声器已开", "扬声器已关")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def toggle_camera(self) -> None:
        """切换摄像头开关（仅视频通话）"""
        btn = self._find_toolbar_button("摄像头已开", "摄像头已关", "无摄像头")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def cancel(self) -> None:
        """取消通话（呼叫中未接通时）"""
        btn = self._find_toolbar_button("取消")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def hangup(self) -> None:
        """挂断通话（通话中）"""
        btn = self._find_toolbar_button("挂断")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def end_call(self) -> None:
        """结束通话（自动识别取消/挂断）"""
        try:
            btn = self._find_toolbar_button("取消", "挂断")
        except RuntimeError:
            raise RuntimeError("未找到取消或挂断按钮")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def switch_to_video(self) -> None:
        """切换到视频通话（通话中可用）"""
        btn = self._find_toolbar_button("切换到视频通话")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def pin(self) -> None:
        """置顶窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::PinnedButton", Name="置顶",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @PIM.guard
    def minimize(self) -> None:
        """最小化通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="最小化",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @PIM.guard
    def maximize(self) -> None:
        """最大化通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="最大化",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @PIM.guard
    def close(self) -> None:
        """关闭通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="关闭",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "VoipCallWindow(closed)"
        return (f"VoipCallWindow(contact={self.contact_name!r}, "
                f"status={self.status!r})")


class NoteEditorWindow(WeixinWindow):
    """
    笔记编辑窗口控制。

    笔记窗口是基于 Chrome 内核的 WebView 弹窗，与微信主窗口独立。

    窗口: Chrome_WidgetWin_0, Name="笔记"
    标题栏:
      - 置顶按钮: ButtonControl, Name="置顶"/"取消置顶"
      - 标题文本: TextControl, Name="笔记"
      - 最小化: ButtonControl, Name="最小化"
      - 最大化: ButtonControl, Name="最大化"/"还原"
      - 关闭:   ButtonControl, Name="关闭"
    内容区: DocumentControl, ClassName="Chrome_RenderWidgetHostHWND"
      - 主容器: GroupControl, AutomationId="mainContainer"
      - 编辑器输入: EditControl, AutomationId="xeditorInputId"
        支持 ValuePattern (读写文本) 和 TextPattern (读取文档内容)
    底部工具栏: 渲染在 WebView 内部，不暴露为独立 UI Automation 控件，
               需通过键盘快捷键操作（Ctrl+B 加粗、Ctrl+I 斜体等）。
    """

    WINDOW_CLASS = "Chrome_WidgetWin_0"
    WINDOW_NAME = "笔记"
    EDITOR_INPUT_ID = "xeditorInputId"
    MAIN_CONTAINER_ID = "mainContainer"

    def __init__(self, handle: int = 0):
        if handle:
            self._handle = handle
            self._win = auto.ControlFromHandle(handle)
        else:
            win = auto.PaneControl(
                ClassName=self.WINDOW_CLASS,
                Name=self.WINDOW_NAME,
            )
            if not win.Exists(maxSearchSeconds=3):
                raise RuntimeError("笔记编辑窗口未找到")
            self._handle = win.NativeWindowHandle
            self._win = win

    def _refresh_win(self) -> None:
        """通过句柄刷新窗口引用（防止窗口对象失效）"""
        if self._handle:
            try:
                self._win = auto.ControlFromHandle(self._handle)
            except Exception:
                pass

    @property
    def exists(self) -> bool:
        try:
            self._refresh_win()
            return self._win.Exists(maxSearchSeconds=2)
        except Exception:
            return False

    def _ensure_exists(self) -> None:
        self._refresh_win()
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError("笔记编辑窗口未找到")

    def activate(self) -> None:
        self._ensure_exists()
        super().activate()

    # -- 笔记窗口特有的 pin/unpin（Chrome WebView 按钮无 ClassName 区分） --

    def pin(self, **kwargs) -> None:
        """置顶窗口（通过标题栏按钮）"""
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="置顶")
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    def unpin(self, **kwargs) -> None:
        """取消置顶窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="取消置顶")
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @property
    def is_pinned(self) -> bool:
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="取消置顶")
        return btn.Exists(0, 0)

    def minimize(self, **kwargs) -> None:
        """最小化窗口（Chrome WebView 优先用窗口 API）"""
        self._ensure_exists()
        self._win.Minimize()
        time.sleep(0.2)

    def maximize(self, **kwargs) -> None:
        """最大化/还原窗口"""
        self._ensure_exists()
        if self._win.IsMaximize():
            self._win.Restore()
        else:
            self._win.Maximize()
        time.sleep(0.2)

    def close(self, **kwargs) -> None:
        """关闭笔记窗口（窗口有两个关闭按钮，取可见的）"""
        self._ensure_exists()
        btns = self._win.GetChildren()
        for child in btns:
            btn = child.ButtonControl(Name="关闭")
            if btn.Exists(0, 0):
                rect = btn.BoundingRectangle
                if rect.width() > 0 and rect.height() > 0:
                    input_wx.click(btn)
                    time.sleep(0.2)
                    return
        wp = self._win.GetWindowPattern()
        if wp:
            wp.Close()
        else:
            raise RuntimeError("未找到可用的关闭按钮")

    # -- 编辑器操作 --

    @property
    def _editor(self) -> auto.EditControl:
        """获取编辑器输入控件"""
        return self._win.EditControl(AutomationId=self.EDITOR_INPUT_ID)

    @property
    def _main_container(self) -> auto.Control:
        """获取主容器控件（用于点击聚焦编辑区域）"""
        doc = self._win.DocumentControl(
            ClassName="Chrome_RenderWidgetHostHWND",
        )
        return doc.GroupControl(AutomationId=self.MAIN_CONTAINER_ID)

    @PIM.guard
    def focus_editor(self, force_click: bool = True) -> None:
        """
        使编辑器获得焦点。

        force_click=True:  点击 mainContainer 区域强制聚焦（会清除选区）。
                           适用于需要定位光标的操作（输入文本、清空等）。
        force_click=False: 仅激活窗口，不点击编辑区域，保留当前选区。
                           适用于格式快捷键（加粗、斜体等）。
        """
        self.activate()
        if force_click:
            container = self._main_container
            if container.Exists(maxSearchSeconds=2):
                input_wx.click(container)
                time.sleep(0.3)

    @property
    def content(self) -> str:
        """
        读取编辑器当前内容。

        优先通过 ValuePattern 读取，
        若为空则尝试 TextPattern.DocumentRange。
        """
        self._ensure_exists()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            return ""
        vp = editor.GetValuePattern()
        if vp and vp.Value:
            return vp.Value
        tp = editor.GetTextPattern()
        if tp:
            doc_range = tp.DocumentRange
            if doc_range:
                text = doc_range.GetText(-1)
                return text if text else ""
        return ""

    @PIM.guard
    def set_content(self, text: str) -> None:
        """
        设置编辑器内容（覆盖现有内容）。

        通过 ValuePattern.SetValue 写入文本。
        注意：这会替换编辑器中的全部内容。
        """
        self.focus_editor()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到笔记编辑器输入控件")
        vp = editor.GetValuePattern()
        if vp:
            vp.SetValue(text)
            time.sleep(0.3)
        else:
            raise RuntimeError("编辑器不支持 ValuePattern")

    @PIM.guard
    def type_text(self, text: str) -> None:
        """
        在编辑器中输入文本（追加到当前光标位置）。

        text: 要输入的文本
        """
        self.focus_editor()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到笔记编辑器输入控件")
        input_wx.send_keys(editor, text)
        time.sleep(0.2)

    @PIM.guard
    def clear(self) -> None:
        """清空编辑器内容"""
        self.focus_editor()
        editor = self._editor
        if editor.Exists(maxSearchSeconds=2):
            input_wx.send_keys(editor, "{Ctrl}a{Del}")
            time.sleep(0.2)

    @PIM.guard
    def select_all(self) -> None:
        """全选编辑器内容"""
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Ctrl}a")
        time.sleep(0.1)

    # -- 富文本格式快捷键 --
    # 底部工具栏渲染在 WebView 内部，不暴露为 UI Automation 控件，
    # 因此通过键盘快捷键操作格式。

    @PIM.guard
    def begin_voice_input(self) -> None:
        """
        开始语音输入：按下 Ctrl+Win 不松开。

        使用 keybd_event 分别按下 VK_CONTROL 和 VK_LWIN，
        保持按住状态直到调用 end_voice_input 释放。
        """
        self.focus_editor(force_click=False)
        VK_CONTROL = 0x11
        VK_LWIN = 0x5B
        KEYEVENTF_KEYDOWN = 0x0
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYDOWN, 0)
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYDOWN, 0)
        time.sleep(0.1)

    @PIM.guard
    def end_voice_input(self) -> None:
        """
        结束语音输入：释放 Ctrl+Win 按键。

        释放顺序与按下相反：先释放 Win，再释放 Ctrl。
        """
        VK_CONTROL = 0x11
        VK_LWIN = 0x5B
        KEYEVENTF_KEYUP = 0x2
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)

    @PIM.guard
    def add_file(self, file_path: str) -> None:
        """
        通过 Ctrl+O 打开文件选择对话框，输入路径并确认添加文件。

        file_path: 文件绝对路径
        """
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Ctrl}O")
        time.sleep(1)

        # 系统文件选择对话框
        dlg = auto.WindowControl(ClassName="#32770")
        if not dlg.Exists(maxSearchSeconds=5):
            raise RuntimeError("文件选择对话框未弹出")

        # Alt+N 激活文件名输入框，通过 ValuePattern 直接设置路径
        input_wx.send_keys(dlg, "{Alt}N")
        time.sleep(0.3)
        edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
        if not edit.Exists(0, 0):
            edit = dlg.EditControl(AutomationId="1148")
        edit.GetValuePattern().SetValue(file_path)
        time.sleep(0.3)
        # Alt+O 点击打开
        input_wx.send_keys(dlg, "{Alt}O")
        time.sleep(0.5)

    @PIM.guard
    def bold(self) -> None:
        """加粗（Ctrl+B）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}B")
        time.sleep(0.1)

    @PIM.guard
    def italic(self) -> None:
        """斜体（Ctrl+I）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}I")
        time.sleep(0.1)

    @PIM.guard
    def underline(self) -> None:
        """下划线（Ctrl+U）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}U")
        time.sleep(0.1)

    @PIM.guard
    def highlight(self) -> None:
        """高亮（Ctrl+Shift+H）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}{Shift}H")
        time.sleep(0.1)

    @PIM.guard
    def undo(self) -> None:
        """撤销（Ctrl+Z）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}z")
        time.sleep(0.1)

    @PIM.guard
    def redo(self) -> None:
        """重做（Ctrl+Y）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}y")
        time.sleep(0.1)

    @PIM.guard
    def new_line(self) -> None:
        """换行（Enter）"""
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Enter}")
        time.sleep(0.1)

    @PIM.guard
    def save(self) -> None:
        """保存笔记（Ctrl+S）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}s")
        time.sleep(0.3)

    @PIM.guard
    def add_tags(self, *tags: str) -> None:
        """
        添加标签。

        通过 Ctrl+T 打开标签输入弹窗，输入标签名后回车确认。
        支持一次添加多个标签。

        注意：标签弹窗渲染在 WebView 内部，不暴露为独立 UI Automation 控件，
        Ctrl+T 打开后焦点转移到弹窗内的输入框，此时需要通过窗口级别
        SendKeys 发送按键，而非通过 xeditorInputId 控件。

        tags: 一个或多个标签名称
        """
        self.focus_editor()
        for tag in tags:
            if not tag:
                continue
            # 通过窗口发送 Ctrl+T 打开标签弹窗
            input_wx.send_keys(self._editor, "{Ctrl}T")
            time.sleep(1)
            # 标签弹窗内的输入框不暴露为 UI Automation 控件，
            # 需要通过窗口级别 SendKeys 输入
            input_wx.send_keys(None, tag)
            time.sleep(0.3)
            input_wx.send_keys(None, "{Down}")
            input_wx.send_keys(None, "{Enter}")
            time.sleep(0.3)
        # 按 Esc 关闭标签弹窗
        input_wx.send_keys(None, "{Esc}")
        time.sleep(0.2)

    @PIM.guard
    def paste(self) -> None:
        """粘贴剪贴板内容（Ctrl+V）"""
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Ctrl}v")
        time.sleep(0.2)

    @PIM.guard
    def paste_file(self, file_path: str) -> None:
        """
        通过剪贴板粘贴文件到笔记中。

        file_path: 文件路径
        """
        self.focus_editor()
        input_wx.paste([file_path])
        time.sleep(0.5)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "NoteEditorWindow(closed)"
        content = self.content
        preview = content[:30] + "..." if len(content) > 30 else content
        return f"NoteEditorWindow(content={preview!r})"


# ======================================================================
# 模块: session
# ======================================================================

"""
pywxauto 会话模块。

包含 Navigator、Session、SessionItem 类。
"""


logger = logging.getLogger(__name__)


def _parse_session_name(raw: str, session: "Session | None" = None) -> "SessionItem":
    """
    解析会话 ListItem 的 Name 属性。

    典型格式（换行分隔）：
      "雕虫小技 一群\\n...\\n17:15\\n消息免打扰\\n"
    """
    parts = [p for p in raw.split("\n") if p.strip()]
    item = SessionItem(_session=session)
    item.name = parts[0] if parts else ""
    item.last_msg = parts[1] if len(parts) > 1 else ""
    item.msg_time = parts[2] if len(parts) > 2 else ""
    item.muted = "消息免打扰" in raw
    m = re.search(r"\[(\d+)条\]", raw)
    if m:
        item.unread = m.group(0)
    return item


class SessionItem:
    """会话列表中的一条会话"""

    def __init__(self, *, name="", last_msg="", msg_time="",
                 muted=False, unread="", active=False,
                 runtime_id: tuple = (),
                 _session: "Session | None" = None):
        self.name = name
        self.last_msg = last_msg
        self.msg_time = msg_time
        self.muted = muted
        self.unread = unread       # 未读条数文本，如 "[9条]"
        self.active = active       # 是否为当前选中（激活）的会话
        self.runtime_id: tuple = runtime_id  # UI Automation RuntimeId
        self._session = _session   # 关联的 Session 实例（用于执行操作）

    def __repr__(self):
        muted_tag = " [免打扰]" if self.muted else ""
        active_tag = " [激活]" if self.active else ""
        return f"SessionItem({self.name!r}, {self.msg_time}{muted_tag}{active_tag})"

    def _require_session(self) -> "Session":
        if self._session is None:
            raise RuntimeError("此 SessionItem 未关联 Session，无法执行操作")
        return self._session

    def pin(self) -> None:
        """置顶会话"""
        self._require_session()._session_context_action(self.name, "置顶")

    def unpin(self) -> None:
        """取消置顶会话"""
        self._require_session()._session_context_action(self.name, "取消置顶")

    def mark_as_unread(self) -> None:
        """标为未读"""
        self._require_session()._session_context_action(self.name, "标为未读")

    def mark_as_read(self) -> None:
        """标为已读"""
        self._require_session()._session_context_action(self.name, "标为已读")

    def mute(self) -> None:
        """消息免打扰"""
        self._require_session()._session_context_action(self.name, "消息免打扰")

    def unmute(self) -> None:
        """允许消息通知"""
        self._require_session()._session_context_action(self.name, "允许消息通知")

    def separate(self) -> None:
        """独立窗口显示"""
        self._require_session()._session_context_action(self.name, "独立窗口显示")

    def separate_by_click(self) -> "SeparateChat":
        """双击打开独立窗口，返回 SeparateChat 实例"""
        session = self._require_session()
        if session.wx:
            session.wx.activate()
        item = session._ensure_session_visible(self.name)
        input_wx.click(item, click="double")
        time.sleep(0.5)
        return SeparateChat(session.wx, self.name)

    def hide(self) -> None:
        """不显示该会话"""
        self._require_session()._session_context_action(self.name, "不显示")

    def delete(self) -> None:
        """删除会话（危险操作，会清除聊天记录）"""
        session = self._require_session()
        session._session_context_action(self.name, "删除")
        # 点击确认弹窗中的"删除"按钮
        confirm_btn = session._win.ButtonControl(Name="删除", ClassName="mmui::XOutlineButton")
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到删除确认弹窗")
        input_wx.click(confirm_btn)

    def open(self) -> None:
        """打开该会话"""
        self._require_session().open(self.name)

    def close(self) -> None:
        """关闭该会话（如果处于激活状态则取消选中）"""
        self._require_session().close(self.name)


class Navigator:
    TABS = {
        "微信": "微信",
        "通讯录": "通讯录",
        "收藏": "收藏",
        "朋友圈": "朋友圈",
        "视频号": "视频号",
        "搜一搜": "搜一搜",
        "手机": "手机",
        "更多": "更多",
    }

    def __init__(self, wx: "Weixin"):
        self.wx = wx
        self._win = wx._win
        self._tabbar = self._win.ToolBarControl(ClassName="mmui::MainTabBar", searchDepth=5)

    def switch_to(self, tab_name: str) -> None:
        if tab_name not in self.TABS:
            raise ValueError(f"未知标签页: {tab_name}，可选: {list(self.TABS.keys())}")

        if tab_name not in ["手机", "更多"]:
            btn = self._tabbar.ButtonControl(ClassName="mmui::XTabBarItem", Name=self.TABS[tab_name], searchDepth=1)
        else:
            btn = self._tabbar.ButtonControl(ClassName="mmui::MainTabBarSettingView", Name=self.TABS[tab_name], searchDepth=1)

        input_wx.click(btn)

    def __str__(self) -> str:
        tabs = ", ".join(self.TABS.keys())
        return f"Navigator(tabs=[{tabs}])"


class Session:
    """
    会话列表面板，包含搜索框和会话列表。

    关键控件：
    - 搜索框: EditControl, ClassName="mmui::XValidatorTextEdit", Name="搜索"
    - 会话列表: ListControl, ClassName="mmui::XTableView", AutomationId="session_list"
    - 会话项: ListItemControl, ClassName="mmui::ChatSessionCell",
              AutomationId="session_item_{name}"
    """

    def __init__(self, wx: "Weixin"):
        self.wx = wx
        self._win = wx._win

    @property
    def is_visible(self) -> bool:
        """会话列表面板是否可见"""
        return self._list_control.Exists(0, 0)

    @property
    def _list_control(self) -> auto.ListControl:
        return self._win.ListControl(ClassName="mmui::XTableView", AutomationId="session_list")

    def visible(self) -> list[SessionItem]:
        """获取当前可见的会话列表"""
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到会话列表控件")

        sessions: list[SessionItem] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            item = _parse_session_name(ctrl.Name, session=self)
            try:
                rid = tuple(ctrl.GetRuntimeId())
                item.runtime_id = rid
            except Exception:
                pass
            try:
                pattern = ctrl.GetSelectionItemPattern()
                if pattern and pattern.IsSelected:
                    item.active = True
            except Exception:
                pass
            sessions.append(item)
        return sessions

    def names(self) -> list[str]:
        """获取当前可见会话的名称列表"""
        return [s.name for s in self.visible()]

    def selected(self) -> Optional[str]:
        """获取当前选中的会话名称（通过 SelectionItemPattern）"""
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=2):
            return None
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            try:
                pattern = ctrl.GetSelectionItemPattern()
                if pattern and pattern.IsSelected:
                    parts = [p for p in ctrl.Name.split("\n") if p.strip()]
                    return parts[0] if parts else None
            except Exception:
                continue
        return None

    @PIM.guard
    def click(self, name: str) -> None:
        """通过 AutomationId 精确点击指定会话"""
        item = self._win.ListItemControl(
            ClassName="mmui::ChatSessionCell",
            AutomationId=f"session_item_{name}",
        )
        if not item.Exists(maxSearchSeconds=2):
            raise RuntimeError(f"会话列表中未找到: {name}")
        input_wx.click(item)
        time.sleep(0.3)

    def _get_search_edit(self) -> auto.EditControl:
        return self._win.EditControl(
            ClassName="mmui::XValidatorTextEdit",
            Name="搜索",
        )

    @PIM.guard
    def search(self, keyword: str, chat_type: Optional[list[str]] = None) -> None:
        """搜索并打开会话（search_and_select 的别名，失败时抛异常）"""
        if not self.search_and_select(keyword, chat_type):
            raise RuntimeError(f"搜索未找到结果: {keyword}")

    @PIM.guard
    def open_by_search(self, name: str, chat_type: Optional[list[str]] = None,
                       force_search: bool = False) -> None:
        """
        打开指定名称的会话。

        默认行为（force_search=False）：
        1. 如果当前聊天对象已经是目标会话，则不做任何操作
        2. 优先在会话列表中直接点击
        3. 找不到则通过搜索打开

        当 force_search=True 时，跳过前两步快捷方式，直接走搜索流程。

        Args:
            name:         会话名称
            chat_type:    优先匹配的分类，如 ["联系人", "群聊", "功能"]
            force_search: 是否强制走搜索流程，跳过标题检查和列表直接点击
        """
        if not force_search:
            # 检查当前聊天对象是否已经是目标会话
            for aid in Chat.TITLE_LABEL_IDS:
                title = self._win.TextControl(AutomationId=aid)
                if title.Exists(0, 0) and title.Name == name:
                    return

            # 先尝试直接在列表中点击
            item = self._win.ListItemControl(
                ClassName="mmui::ChatSessionCell",
                AutomationId=f"session_item_{name}",
            )
            if item.Exists(0, 0):
                # 如果已激活则不重复点击
                try:
                    pattern = item.GetSelectionItemPattern()
                    if pattern and pattern.IsSelected:
                        return
                except Exception:
                    pass
                click(item)
                # item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.3)
                return

        # 列表中没有（或强制搜索），走搜索
        self.search(name, chat_type)

    @PIM.guard
    def scroll(self, direction: str = "down", clicks: int = 3) -> None:
        """
        滚动会话列表。
        direction: "up" 或 "down"
        clicks: 滚动次数
        """
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到会话列表控件")
        delta = -clicks if direction == "down" else clicks
        rect = lc.BoundingRectangle
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        auto.WheelDown(cx, cy, abs(delta)) if direction == "down" else auto.WheelUp(cx, cy, abs(delta))
        time.sleep(0.3)

    def all(self, step: int = 5, max_scrolls: int = 500) -> list[SessionItem]:
        """
        通过滚动获取完整的会话列表。

        使用 RuntimeId 集合去重，精确识别新会话，
        支持重名会话（不同会话的 RuntimeId 不同）。

        step: 每次按 Down 键的次数（固定滚动幅度）
        max_scrolls: 最大滚动轮次

        Returns:
            按出现顺序排列的完整会话列表
        """
        self.wx.activate()
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到会话列表控件")

        time.sleep(0.1)
        input_wx.focus(lc)
        time.sleep(0.2)

        # 滚动到顶部
        scroll_pattern = lc.GetScrollPattern()
        if scroll_pattern:
            scroll_pattern.SetScrollPercent(-1, 0)
            time.sleep(0.3)
        else:
            input_wx.send_keys(lc, "{Home}")
            time.sleep(0.3)

        all_sessions: list[SessionItem] = []
        seen_rids: set[tuple] = set()
        no_new_count = 0

        for _ in range(max_scrolls):
            curr_visible = self.visible()

            # 用 RuntimeId 去重，按顺序追加新会话
            new_found = False
            for s in curr_visible:
                if s.runtime_id and s.runtime_id not in seen_rids:
                    seen_rids.add(s.runtime_id)
                    all_sessions.append(s)
                    new_found = True

            if new_found:
                no_new_count = 0
            else:
                no_new_count += 1
                if no_new_count >= 3:
                    break

            # 检查是否已滚动到底部
            sp = lc.GetScrollPattern()
            if sp:
                v_percent = sp.VerticalScrollPercent
                if v_percent >= 100 or v_percent < 0:
                    break

            input_wx.send_keys(lc, "{Down}" * step)
            time.sleep(0.1)

        return all_sessions

    def _ensure_session_visible(self, name: str) -> auto.ListItemControl:
        """
        确保指定会话在可见区域内，返回对应的 ListItemControl。
        如果会话不在当前可见列表中，则通过滚动查找。
        """
        item = self._win.ListItemControl(
            ClassName="mmui::ChatSessionCell",
            AutomationId=f"session_item_{name}",
        )
        if item.Exists(0, 0):
            return item

        # 会话不可见，通过滚动查找
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到会话列表控件")

        input_wx.focus(lc)
        time.sleep(0.2)

        # 先滚动到顶部
        scroll_pattern = lc.GetScrollPattern()
        if scroll_pattern:
            scroll_pattern.SetScrollPercent(-1, 0)
        else:
            input_wx.send_keys(lc, "{Home}")
        time.sleep(0.3)

        # 检查顶部是否可见
        if item.Exists(0, 0):
            return item

        # 逐步向下滚动查找
        step = 5
        no_new_count = 0
        prev_names: set[str] = set()
        for _ in range(500):
            sp = lc.GetScrollPattern()
            if sp:
                v = sp.VerticalScrollPercent
                if v >= 100 or v < 0:
                    break

            input_wx.send_keys(lc, "{Down}" * step)

            if item.Exists(0, 0):
                return item

            curr_names = {s.name for s in self.visible()}
            if curr_names and curr_names == prev_names:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0
            prev_names = curr_names

        raise RuntimeError(f"会话列表中未找到: {name}")

    def _right_click_session(self, name: str) -> None:
        """右键点击指定会话，弹出上下文菜单"""
        item = self._ensure_session_visible(name)
        input_wx.click(item, button="right")

    def _click_context_menu_item(self, menu_name: str) -> None:
        """
        点击当前已弹出的右键菜单中的指定项。
        菜单窗口: mmui::XMenu
        菜单项: mmui::XMenuView, AutomationId="XMenuItem"
        """
        menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
        if not menu_win.Exists(maxSearchSeconds=2):
            raise RuntimeError("右键菜单未弹出")
        menu_item = menu_win.MenuItemControl(
            ClassName="mmui::XMenuView",
            AutomationId="XMenuItem",
            Name=menu_name,
        )
        if not menu_item.Exists(maxSearchSeconds=1):
            # 关闭菜单
            input_wx.send_keys(self._win, "{Esc}")
            raise RuntimeError(f"菜单中未找到: {menu_name}")
        input_wx.click(menu_item)
        time.sleep(0.3)

    def _session_context_action(self, name: str, menu_name: str) -> None:
        """对指定会话执行右键菜单操作"""
        self.wx.activate()
        self._right_click_session(name)
        self._click_context_menu_item(menu_name)

    @PIM.guard
    def pin(self, name: str) -> None:
        """置顶会话"""
        self._session_context_action(name, "置顶")

    @PIM.guard
    def unpin(self, name: str) -> None:
        """取消置顶会话"""
        self._session_context_action(name, "取消置顶")

    @PIM.guard
    def mark_as_unread(self, name: str) -> None:
        """标为未读"""
        self._session_context_action(name, "标为未读")

    @PIM.guard
    def mark_as_read(self, name: str) -> None:
        """标为已读"""
        self._session_context_action(name, "标为已读")

    @PIM.guard
    def mute(self, name: str) -> None:
        """消息免打扰"""
        self._session_context_action(name, "消息免打扰")

    @PIM.guard
    def unmute(self, name: str) -> None:
        """允许消息通知"""
        self._session_context_action(name, "允许消息通知")

    @PIM.guard
    def separate(self, name: str) -> None:
        """独立窗口显示"""
        self._session_context_action(name, "独立窗口显示")

    @PIM.guard
    def hide(self, name: str) -> None:
        """不显示该会话"""
        self._session_context_action(name, "不显示")

    @PIM.guard
    def close(self, name: str) -> None:
        """关闭指定会话：如果该会话处于激活状态，点击一下取消选中"""
        self.wx.activate()
        item = self._ensure_session_visible(name)
        try:
            pattern = item.GetSelectionItemPattern()
            if not pattern or not pattern.IsSelected:
                return
        except Exception:
            return
        input_wx.click(item)

    @PIM.guard
    def open(self, name: str) -> None:
        """通过在会话列表中查找并点击来打开指定会话，如果已激活则不操作"""
        self.wx.activate()
        item = self._ensure_session_visible(name)
        try:
            pattern = item.GetSelectionItemPattern()
            if pattern and pattern.IsSelected:
                return
        except Exception:
            pass
        input_wx.click(item)

    @PIM.guard
    def delete(self, name: str) -> None:
        """删除会话（危险操作，会清除聊天记录）"""
        self._session_context_action(name, "删除")
        confirm_btn = self._win.ButtonControl(
            Name="删除", ClassName="mmui::XOutlineButton",
        )
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到删除确认弹窗")
        input_wx.click(confirm_btn)

    @PIM.guard
    def search_and_select(self, keyword: str, chat_type: Optional[list[str]] = None) -> bool:
        """
        在搜索框中输入关键词并点击第一个匹配结果。
        返回是否成功找到并点击了结果。

        keyword: 搜索关键词
        chat_type: 优先匹配的分类，如 ["联系人", "群聊", "功能", "公众号", "更多", "聊天记录", "聊天文件", "搜索网络结果", "收藏", "最近使用过的小程序", "服务号", "最近使用", "最常使用"]
        """
        chat_type = chat_type or ["联系人", "群聊", "功能"]
        edit = self._get_search_edit()
        input_wx.click(edit)
        edit.GetValuePattern().SetValue(keyword)
        time.sleep(0.5)

        # 按分类优先级查找搜索结果
        for category in ["最常使用", *chat_type]:
            category_item = self._win.ListItemControl(
                ClassName="mmui::XTableCell",
                Name=category,
            )
            if category_item.Exists(0, 0):
                result_item = category_item.GetNextSiblingControl()
                if result_item:
                    input_wx.click(result_item)
                    time.sleep(0.3)
                    return True
        return False

    @PIM.guard
    def cancel_search(self) -> None:
        """取消搜索（按 Esc 退出搜索模式）"""
        input_wx.send_keys(self._win, "{Esc}")
        time.sleep(0.2)

    @PIM.guard
    def search_contact(self, keyword: str) -> bool:
        """搜索联系人并打开会话"""
        return self.search_and_select(keyword, chat_type=["联系人"])

    @PIM.guard
    def search_group(self, keyword: str) -> bool:
        """搜索群聊并打开会话"""
        return self.search_and_select(keyword, chat_type=["群聊"])

    def _click_quick_action_button(self) -> None:
        """点击快捷操作按钮"""
        self.wx.activate()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name="快捷操作",
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到快捷操作按钮")
        input_wx.click(btn)
        time.sleep(0.3)

    def _click_quick_action_item(self, item_name: str) -> None:
        """
        点击快捷操作菜单中的指定项。
        菜单列表: AutomationId="chat_more_entry"
        菜单项: ClassName="mmui::ChatMoreCellView"
        """
        menu_list = self._win.ListControl(
            ClassName="mmui::XTableView",
            AutomationId="chat_more_entry",
        )
        if not menu_list.Exists(maxSearchSeconds=2):
            raise RuntimeError("快捷操作菜单未弹出")
        item = menu_list.ListItemControl(
            ClassName="mmui::ChatMoreCellView",
            Name=item_name,
        )
        if not item.Exists(maxSearchSeconds=1):
            # 关闭菜单
            self._click_quick_action_button()
            raise RuntimeError(f"快捷操作菜单中未找到: {item_name}")
        input_wx.click(item)
        time.sleep(0.3)

    def _quick_action(self, item_name: str) -> None:
        """执行快捷操作"""
        self._click_quick_action_button()
        self._click_quick_action_item(item_name)

    @PIM.guard
    def create_room(self, nickname_list: list[str]) -> None:
        """
        发起群聊。

        nickname_list: 好友昵称列表，至少需要两个好友才能创建群聊。

        流程：
        1. 通过快捷操作菜单打开"发起群聊"弹窗
        2. 在搜索框中逐个输入好友昵称
        3. 点击搜索结果中的第一条联系人进行勾选
        4. 全部添加完成后，点击"完成"按钮

        窗口控件信息：
        - 发起群聊窗口: mmui::SessionPickerWindow, Name="微信发起群聊"
        - 搜索框: mmui::XValidatorTextEdit, Name="搜索"
          (位于左侧 mmui::XSearchField 内)
        - 搜索前联系人列表: mmui::StickyHeaderRecyclerListView,
          AutomationId="sp_to_select_contact_list"
        - 搜索前联系人行: mmui::SPSelectionContactRow (CheckBoxControl)
        - 搜索后结果列表: mmui::XTableView,
          AutomationId="sp_search_new_chat_result_list"
        - 搜索后联系人行: mmui::SearchContactCellView (CheckBoxControl)
        - 完成按钮: mmui::XOutlineButton, AutomationId="confirm_btn", Name="完成"
        """
        if not nickname_list or len(nickname_list) < 2:
            raise ValueError("至少需要两个好友昵称才能创建群聊")

        self._quick_action("发起群聊")

        # --- 第1步：等待发起群聊窗口出现 ---
        picker_win = self._win.WindowControl(
            ClassName="mmui::SessionPickerWindow",
        )
        if not picker_win.Exists(maxSearchSeconds=3):
            raise RuntimeError("发起群聊窗口未打开")

        # --- 第2步：逐个搜索并勾选好友 ---
        for nickname in nickname_list:
            # 从主窗口查找 SessionPickerWindow（它是主窗口的直接子窗口），
            # 用 searchDepth=1 避免深入遍历右侧 SPDetailView 中的
            # 无限递归控件树 (SPChoiceContactRow → QWidget → SPChoiceContactRow → ...)
            fresh_picker = self._win.WindowControl(
                ClassName="mmui::SessionPickerWindow",
                searchDepth=1,
            )
            if not fresh_picker.Exists(maxSearchSeconds=3):
                raise RuntimeError("发起群聊窗口已关闭")
            if not background:
                fresh_picker.SetActive()
            input_wx.focus(fresh_picker)
            time.sleep(0.3)

            # 从左侧 SearchField 容器中查找搜索框，避开右侧面板
            search_field = fresh_picker.GroupControl(
                ClassName="mmui::XSearchField",
                searchDepth=3,
            )
            if not search_field.Exists(maxSearchSeconds=2):
                raise RuntimeError("发起群聊窗口中未找到搜索区域")
            search_edit = search_field.EditControl(
                ClassName="mmui::XValidatorTextEdit", Name="搜索",
                searchDepth=1,
            )
            if not search_edit.Exists(maxSearchSeconds=2):
                raise RuntimeError("发起群聊窗口中未找到搜索框")

            # 清空搜索框并通过键盘输入昵称
            input_wx.click(search_edit)
            time.sleep(0.3)
            input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
            time.sleep(0.3)
            input_wx.send_keys(search_edit, nickname)
            time.sleep(1.5)

            # 从左侧 SearchContactNewChatView 容器中查找搜索结果列表
            search_view = fresh_picker.GroupControl(
                ClassName="mmui::SearchContactNewChatView",
                searchDepth=3,
            )
            if not search_view.Exists(maxSearchSeconds=3):
                raise RuntimeError(f"搜索联系人 '{nickname}' 后未出现搜索视图")

            result_list = search_view.ListControl(
                ClassName="mmui::XTableView",
                AutomationId="sp_search_new_chat_result_list",
                searchDepth=1,
            )
            if not result_list.Exists(maxSearchSeconds=5):
                raise RuntimeError(f"搜索联系人 '{nickname}' 后未出现结果列表")

            contact_row = result_list.CheckBoxControl(
                ClassName="mmui::SearchContactCellView",
                searchDepth=1,
            )
            if not contact_row.Exists(maxSearchSeconds=3):
                raise RuntimeError(f"未找到联系人: {nickname}")

            input_wx.click(contact_row)
            time.sleep(0.5)

        # --- 第4步：点击完成按钮 ---
        # 先定位右侧 SPDetailView（searchDepth=3），
        # 再从中查找完成按钮（searchDepth=2 避免深入递归区域）
        final_picker = self._win.WindowControl(
            ClassName="mmui::SessionPickerWindow",
            searchDepth=1,
        )
        if not final_picker.Exists(maxSearchSeconds=3):
            raise RuntimeError("发起群聊窗口已关闭")
        detail_view = final_picker.GroupControl(
            ClassName="mmui::SPDetailView",
            searchDepth=3,
        )
        if not detail_view.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到详情面板")
        confirm_btn = detail_view.ButtonControl(
            ClassName="mmui::XOutlineButton",
            AutomationId="confirm_btn",
            Name="完成",
            searchDepth=2,
        )
        if not confirm_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到完成按钮")
        input_wx.click(confirm_btn)
        time.sleep(0.5)

    @PIM.guard
    def add_friend(self, keyword: str, message: Optional[str] = None, remark: Optional[str] = None,
                   permission: Optional[str] = None, hide_my_posts: bool = False,
                   hide_their_posts: bool = False) -> None:
        """
        添加朋友完整流程。

        keyword: 微信号/手机号
        message: 申请消息（None 则使用默认消息）
        remark: 备注名（None 则使用对方昵称）
        permission: 朋友权限，可选值:
            - "chatonly" : 仅聊天
            - None : 聊天、朋友圈、微信运动等（默认）
        hide_my_posts: 不让他（她）看我的朋友圈和状态
        hide_their_posts: 不看他（她）的朋友圈和状态

        返回值:
        - 填写表单并自动提交申请

        窗口控件信息:
        - 添加朋友窗口: mmui::AddFriendWindow
        - 搜索结果"添加到通讯录": AutomationId 含 "add_friend_button"
        - 申请表单: mmui::VerifyFriendWindow
          - 申请消息: EditControl, Name="发送添加朋友申请"
          - 备注: EditControl, Name="修改备注", ClassName="mmui::XLineEdit"
          - 朋友权限选项: GroupControl, ClassName="mmui::ProfileFormPermissionItemUi"
            - Name="聊天、朋友圈、微信运动等" (默认选中)
            - Name="仅聊天"
          - 朋友圈开关: CheckBoxControl, ClassName="mmui::XSwitchButton"
            - Name="不让他（她）看"
            - Name="不看他（她）"
          - 确定/取消按钮
        """
        self._quick_action("添加朋友")

        add_friend_win = auto.WindowControl(
            ClassName="mmui::AddFriendWindow",
            AutomationId="AddFriendWindow",
        )
        if not add_friend_win.Exists(maxSearchSeconds=3):
            raise RuntimeError("添加朋友窗口未打开")

        # --- 第1步：输入关键词并搜索 ---
        search_edit = add_friend_win.EditControl(
            ClassName="mmui::XValidatorTextEdit", Name="搜索",
        )
        if not search_edit.Exists(maxSearchSeconds=2):
            raise RuntimeError("添加朋友窗口中未找到搜索框")
        input_wx.click(search_edit)
        time.sleep(0.2)
        search_edit.GetValuePattern().SetValue(keyword)
        time.sleep(0.3)
        search_btn = add_friend_win.ButtonControl(
            ClassName="mmui::XOutlineButton", Name="搜索",
        )
        if not search_btn.Exists(maxSearchSeconds=1):
            raise RuntimeError("未找到搜索按钮")
        input_wx.click(search_btn)
        time.sleep(1)

        # --- 第2步：点击"添加到通讯录" ---
        add_btn = add_friend_win.ButtonControl(Name="添加到通讯录")
        if not add_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到'添加到通讯录'按钮，可能搜索无结果")
        input_wx.click(add_btn)
        time.sleep(1)

        # --- 第3步：填写申请表单 ---
        verify_win = auto.WindowControl(ClassName="mmui::VerifyFriendWindow")
        if not verify_win.Exists(maxSearchSeconds=3):
            raise RuntimeError("申请添加朋友窗口未打开")

        # 填写申请消息
        if message is not None:
            msg_edit = verify_win.EditControl(
                ClassName="mmui::XValidatorTextEdit", Name="发送添加朋友申请",
            )
            if msg_edit.Exists(maxSearchSeconds=1):
                input_wx.click(msg_edit)
                time.sleep(0.1)
                input_wx.send_keys(msg_edit, "{Ctrl}a{Del}")
                time.sleep(0.1)
                msg_edit.GetValuePattern().SetValue(message)
                time.sleep(0.2)

        # 填写备注
        if remark is not None:
            remark_edit = verify_win.EditControl(
                ClassName="mmui::XLineEdit", Name="修改备注",
            )
            if remark_edit.Exists(maxSearchSeconds=1):
                input_wx.click(remark_edit)
                time.sleep(0.1)
                input_wx.send_keys(remark_edit, "{Ctrl}a{Del}")
                time.sleep(0.1)
                remark_edit.GetValuePattern().SetValue(remark)
                time.sleep(0.2)

        # 设置朋友权限（单选：点击整行切换）
        if permission == "chatonly":
            perm_item = verify_win.GroupControl(
                ClassName="mmui::ProfileFormPermissionItemUi",
                Name="仅聊天",
            )
            if perm_item.Exists(maxSearchSeconds=1):
                input_wx.click(perm_item)
                time.sleep(0.2)

        # 设置朋友圈和状态开关
        if hide_my_posts:
            sw = verify_win.CheckBoxControl(
                ClassName="mmui::XSwitchButton", Name="不让他（她）看",
            )
            if sw.Exists(maxSearchSeconds=1):
                toggle = sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 0:
                    input_wx.click(sw)
                    time.sleep(0.2)

        if hide_their_posts:
            sw = verify_win.CheckBoxControl(
                ClassName="mmui::XSwitchButton", Name="不看他（她）",
            )
            if sw.Exists(maxSearchSeconds=1):
                toggle = sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 0:
                    input_wx.click(sw)
                    time.sleep(0.2)

        # --- 第4步：点击确定 ---
        confirm_btn = verify_win.ButtonControl(
            Name="确定", ClassName="mmui::XOutlineButton",
        )
        if not confirm_btn.Exists(maxSearchSeconds=1):
            raise RuntimeError("未找到确定按钮")
        input_wx.click(confirm_btn)
        time.sleep(0.5)

    @PIM.guard
    def new_note(self) -> "NoteEditorWindow":
        """
        新建笔记，返回笔记编辑窗口对象。

        通过快捷操作菜单打开新建笔记窗口，
        等待笔记编辑窗口出现后，通过句柄锁定窗口实例并返回。
        """
        self._quick_action("新建笔记")
        # 等待笔记窗口出现（新建时标题为"笔记"）
        win = auto.PaneControl(
            ClassName=NoteEditorWindow.WINDOW_CLASS,
            Name=NoteEditorWindow.WINDOW_NAME,
        )
        if not win.Exists(maxSearchSeconds=5):
            raise RuntimeError("新建笔记窗口未打开")
        time.sleep(0.5)
        # 通过句柄锁定窗口，避免标题变化后找不到
        handle = win.NativeWindowHandle
        return NoteEditorWindow(handle=handle)

    def __str__(self) -> str:
        try:
            sessions = self.visible()
            selected = self.selected()
            return f"Session(visible={len(sessions)}, active={selected!r})"
        except Exception as e:
            return f"Session(error={e!r})"


# ======================================================================
# 模块: friend_circle
# ======================================================================

"""
pywxauto 朋友圈模块。

包含 FriendCircle 和 Moment 类。
"""


logger = logging.getLogger(__name__)


class Moment:
    """朋友圈动态条目"""

    def __init__(self, friend_circle: "FriendCircle", runtime_id: tuple, *,
                 type="", sender="", content="",
                 raw_text="", timestamp="", image_count=0,
                 cell_type="", scroll_offset: int = 0):
        self.friend_circle = friend_circle
        self.runtime_id = runtime_id
        self.type = type
        self.sender = sender
        self.content = content
        self.raw_text = raw_text
        self.timestamp = timestamp
        self.image_count = image_count
        self.cell_type = cell_type
        self.scroll_offset = scroll_offset

    def like(self) -> bool:
        """
        点赞此条动态。

        如果已点赞则不重复操作，返回 True。
        """
        self.friend_circle._open_sns_window()
        ctrl = self._find_cell()
        if not ctrl:
            raise RuntimeError(f"未找到朋友圈动态: {self.sender}")
        self._scroll_into_view(ctrl)

        win = self.friend_circle._win
        if not self._open_action_bar(ctrl):
            return False

        # 已点赞时显示"取消"，未点赞时显示"赞"
        # 先检查是否已点赞（"取消"按钮），避免重复点赞
        for cls in ("mmui::XTextView", "mmui::XButton"):
            cancel_btn = win.Control(Name="取消", ClassName=cls)
            if cancel_btn.Exists(0, 0):
                # 已点赞，关闭操作栏
                input_wx.send_keys(None, "{Esc}")
                time.sleep(0.2)
                return True

        # 未点赞，点击"赞"
        btn = win.TextControl(Name="赞", ClassName="mmui::XTextView")
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.3)
            return True

        return False

    def unlike(self) -> bool:
        """
        取消点赞此条动态。

        如果未点赞则不操作，返回 True。
        """
        self.friend_circle._open_sns_window()
        ctrl = self._find_cell()
        if not ctrl:
            raise RuntimeError(f"未找到朋友圈动态: {self.sender}")
        self._scroll_into_view(ctrl)

        win = self.friend_circle._win
        if not self._open_action_bar(ctrl):
            return False

        # 检查是否已点赞（"取消"按钮）
        for cls in ("mmui::XTextView", "mmui::XButton"):
            cancel_btn = win.Control(Name="取消", ClassName=cls)
            if cancel_btn.Exists(0, 0):
                input_wx.click(cancel_btn)
                time.sleep(0.3)
                return True

        # 未点赞，关闭操作栏
        input_wx.send_keys(None, "{Esc}")
        time.sleep(0.2)
        return True

    def comment(self, content: str) -> bool:
        """
        评论此条动态。

        Args:
            content: 评论内容
        """
        if not content or not content.strip():
            raise ValueError("评论内容不能为空")

        self.friend_circle._open_sns_window()
        ctrl = self._find_cell()
        if not ctrl:
            raise RuntimeError(f"未找到朋友圈动态: {self.sender}")
        self._scroll_into_view(ctrl)

        if not self._click_action_button(ctrl, "评论"):
            raise RuntimeError("未能打开评论输入框")

        input_wx.paste(content)
        time.sleep(0.5)

        # 当前动态的下一个兄弟控件就是其评论区
        comment_cell = ctrl.GetNextSiblingControl()
        if (not comment_cell
                or comment_cell.ClassName != "mmui::TimelineCommentCell"):
            raise RuntimeError("未找到当前动态的评论区控件")

        rect = comment_cell.BoundingRectangle
        send_x = rect.right - 70
        send_y = rect.bottom - 50
        auto.MoveTo(send_x, send_y)
        time.sleep(0.1)
        auto.Click(send_x, send_y)
        time.sleep(0.5)
        return True

    def scroll_to_visible(self) -> bool:
        """将此条动态滚动到可见区域"""
        self.friend_circle._open_sns_window()
        ctrl = self._find_cell()
        if not ctrl:
            raise RuntimeError(f"未找到朋友圈动态: {self.sender}")
        return self._scroll_into_view(ctrl)

    def _find_cell(self) -> "auto.Control | None":
        """
        在朋友圈列表中查找此条动态的控件。

        利用 scroll_offset（前面所有朋友圈高度累加）快速定位：
        1. 先在当前可见区域查找（命中直接返回）
        2. 点击"刷新"回到列表顶部
        3. 边滚动边匹配：每滚一小段就检查可见区域，命中立即返回
        """
        lc = self.friend_circle._find_sns_list()

        def _match_in_visible():
            for ctrl, _ in auto.WalkControl(lc):
                if ctrl.ControlType != auto.ControlType.ListItemControl:
                    continue
                cls_name = ctrl.ClassName or ""
                if not cls_name.startswith(FriendCircle.TIMELINE_CELL_PREFIX):
                    continue
                if cls_name in FriendCircle.SKIP_CELL_CLASSES:
                    continue
                if (ctrl.Name
                        and self.sender in ctrl.Name
                        and self.content[:20] in ctrl.Name):
                    return ctrl
            return None

        # 先在当前可见区域查找
        result = _match_in_visible()
        if result:
            return result

        # 回到顶部
        refresh_btn = self.friend_circle._win.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name="刷新",
        )
        if refresh_btn.Exists(maxSearchSeconds=2):
            input_wx.click(refresh_btn)
            time.sleep(2)

        if self.scroll_offset <= 0:
            return _match_in_visible()

        # 边滚动边匹配
        # 每次滚动约 500px（wheelTimes=5），滚完立即检查
        scrolled = 0
        step = 5
        step_px = 500
        while scrolled < self.scroll_offset + step_px:
            result = _match_in_visible()
            if result:
                return result
            lc.WheelDown(wheelTimes=step)
            scrolled += step_px
            time.sleep(0.15)

        # 最后再检查一次
        return _match_in_visible()

    def _scroll_into_view(self, ctrl) -> bool:
        """将控件滚动到朋友圈列表可见区域内"""
        lc = self.friend_circle._find_sns_list()
        list_rect = lc.BoundingRectangle
        for _ in range(30):
            ctrl_rect = ctrl.BoundingRectangle
            if ctrl_rect.bottom <= list_rect.bottom - 10:
                return True
            lc.WheelDown(wheelTimes=3)
            time.sleep(0.3)
        return False

    def _open_action_bar(self, ctrl) -> bool:
        """
        触发朋友圈动态的操作栏（赞/评论按钮）。

        从动态右下角逐步向左移动鼠标并点击，直到操作栏出现。
        """
        win = self.friend_circle._win
        distance = 30
        while distance < 200:
            ctrl_rect = ctrl.BoundingRectangle
            auto.MoveTo(ctrl_rect.right - distance, ctrl_rect.bottom - 5)
            time.sleep(0.1)
            auto.Click(ctrl_rect.right - distance, ctrl_rect.bottom - 5)
            time.sleep(0.3)

            # 检查操作栏是否出现
            if (win.TextControl(Name="赞", ClassName="mmui::XTextView").Exists(0, 0)
                    or win.TextControl(Name="评论", ClassName="mmui::XTextView").Exists(0, 0)
                    or win.Control(Name="取消", ClassName="mmui::XTextView").Exists(0, 0)
                    or win.Control(Name="取消", ClassName="mmui::XButton").Exists(0, 0)):
                return True

            distance += 20
        return False

    def _click_action_button(self, ctrl, button_name: str) -> bool:
        """触发操作栏后点击指定按钮（用于评论等）"""
        win = self.friend_circle._win
        if not self._open_action_bar(ctrl):
            return False

        btn = win.TextControl(Name=button_name, ClassName="mmui::XTextView")
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.3)
            return True
        return False

    def __repr__(self):
        return (f"Moment(type={self.type!r}, sender={self.sender!r}, "
                f"content={self.content!r}, timestamp={self.timestamp!r})")

    def __str__(self):
        preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        return f"[{self.type}] [{self.timestamp}] {self.sender}: {preview}"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "type": self.type,
            "sender": self.sender,
            "content": self.content,
            "raw_text": self.raw_text,
            "timestamp": self.timestamp,
            "image_count": self.image_count,
        }


class FriendCircle(WeixinWindow):
    """
    朋友圈（FriendCircle）操作类。

    继承自 WeixinWindow，复用通用窗口操作（activate、pin、unpin、
    minimize、maximize、restore、close）。

    微信 4.x 的朋友圈通过左侧导航栏的"朋友圈"标签页打开，
    会弹出一个独立窗口。

    关键控件信息（来自 desktop-ui-inspector 对微信 4.x 的实际检查）：
    - 导航标签: ButtonControl, ClassName="mmui::XTabBarItem", Name="朋友圈"
    - 独立窗口: WindowControl, ClassName="mmui::SNSWindow",
                AutomationId="SNSWindow", Name="朋友圈"
    - 列表容器: ListControl, ClassName="mmui::TimeLineListView",
                AutomationId="sns_list", Name="朋友圈"
    - 单条动态: ListItemControl, ClassName 前缀 "mmui::Timeline"
      （如 mmui::TimelineGridImageCell 等）
    - 动态的 Name 属性包含完整信息，格式示例：
      "王芳 Ai漫剧的发展和出海的机遇[玫瑰] 包含2张图片 8小时前 "
      即: "昵称 正文内容 [附件描述] 时间戳"
    """

    MOMENT_TAB_NAME = "朋友圈"
    # 朋友圈独立窗口
    SNS_WINDOW_CLASS = "mmui::SNSWindow"
    SNS_WINDOW_ID = "SNSWindow"
    # 朋友圈 feed 列表
    SNS_LIST_CLASS = "mmui::TimeLineListView"
    SNS_LIST_ID = "sns_list"
    # 单条动态的 ClassName 前缀
    TIMELINE_CELL_PREFIX = "mmui::Timeline"
    # 需要跳过的非动态 Cell（评论区、辅助行等）
    SKIP_CELL_CLASSES = {
        "mmui::TimelineCommentCell",  # 评论区
        "mmui::TimelineCell",         # 辅助行（如 "余下0条"）
    }

    def __init__(self, wx: "Weixin"):
        self.wx = wx
        self._win = auto.WindowControl(
            ClassName=self.SNS_WINDOW_CLASS,
            AutomationId=self.SNS_WINDOW_ID,
            searchDepth=1
        )

    @property
    def exists(self) -> bool:
        """朋友圈窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=1)

    def _open_sns_window(self) -> None:
        """
        打开朋友圈独立窗口。

        如果窗口已存在则直接激活，否则通过导航栏点击"朋友圈"打开。

        窗口: WindowControl, ClassName="mmui::SNSWindow",
              AutomationId="SNSWindow", Name="朋友圈"
        """
        if self._win.Exists(maxSearchSeconds=1):
            self.activate()
            return

        # 窗口不存在，通过导航栏打开
        self.wx.activate()
        self.wx.navigator.switch_to(self.MOMENT_TAB_NAME)

        # 等待独立窗口出现
        if not self._win.Exists(maxSearchSeconds=5):
            raise RuntimeError("朋友圈窗口未打开")

        self.activate()

    def _find_sns_list(self) -> auto.ListControl:
        """
        在朋友圈窗口中查找 feed 列表控件。

        列表: ListControl, ClassName="mmui::TimeLineListView",
              AutomationId="sns_list"
        """
        lc = self._win.ListControl(
            ClassName=self.SNS_LIST_CLASS,
            AutomationId=self.SNS_LIST_ID,
        )
        if not lc.Exists(maxSearchSeconds=5):
            raise RuntimeError("未找到朋友圈列表控件 (sns_list)")
        return lc

    def _parse_moment_name(self, runtime_id: tuple, raw_name: str,
                           cls_name: str = "", scroll_offset: int = 0) -> Moment | None:
        """
        解析单条朋友圈动态 ListItem 的 Name 属性。

        Name 格式示例（空格分隔，末尾带时间戳）：
          "王芳 Ai漫剧的发展和出海的机遇[玫瑰] 包含2张图片 8小时前 "
          "张三 今天天气真好 3分钟前 "
          "七夏 放大看看[太阳] 包含1张图片 5天前 "

        已知 Cell ClassName 与类型的对应关系：
          mmui::TimelineGridImageCell  — 多图（九宫格）
          mmui::TimelineContentCell    — 单图/大图/内容
          mmui::TimelineVideoCell      — 视频（推测）
          mmui::TimelineLinkCell / mmui::TimelineUrlCell — 分享链接（推测）

        解析策略：
        1. 正则匹配末尾时间戳
        2. 提取 "包含X张图片" 中的图片数量
        3. 检测 Name 中的视频/链接关键词
        4. 结合 ClassName 判断类型标识
        5. 第一个空格前为昵称，中间为正文
        """
        if not raw_name or not raw_name.strip():
            return None

        text = raw_name.strip()

        # 匹配末尾时间戳
        ts_pattern = (
            r'(\d+分钟前|\d+小时前|\d+天前|昨天|前天|刚刚'
            r'|\d{1,2}月\d{1,2}日'
            r'|\d{4}年\d{1,2}月\d{1,2}日'
            r')\s*$'
        )
        ts_match = re.search(ts_pattern, text)
        timestamp = ""
        body = text
        if ts_match:
            timestamp = ts_match.group(1)
            body = text[:ts_match.start()].strip()

        if not body:
            return None

        # 提取图片数量
        image_count = 0
        img_match = re.search(r'包含(\d+)张图片', body)
        if img_match:
            image_count = int(img_match.group(1))
            body = (body[:img_match.start()] + body[img_match.end():]).strip()

        # 检测视频关键词
        has_video_kw = False
        video_match = re.search(r'包含\d*段?视频', body)
        if video_match:
            has_video_kw = True
            body = (body[:video_match.start()] + body[video_match.end():]).strip()

        # 检测链接/分享关键词
        has_link_kw = bool(re.search(r'链接|网页|分享', body))

        # 第一个空格前为昵称
        parts = body.split(None, 1)
        sender = parts[0] if parts else ""
        content = parts[1].strip() if len(parts) > 1 else ""

        # --- 判断类型标识（临时变量，不存入实例） ---
        cls_lower = cls_name.lower()
        has_image = image_count > 0 or "image" in cls_lower
        has_video = "video" in cls_lower or has_video_kw
        has_link = ("link" in cls_lower or "url" in cls_lower
                    or has_link_kw)
        has_text = bool(content)

        # 生成类型文本
        media = ""
        if has_image:
            media = "图片"
        elif has_video:
            media = "视频"
        elif has_link:
            media = "分享"

        if has_text and media:
            moment_type = f"文本{media}"
        elif has_text:
            moment_type = "文本"
        elif media:
            moment_type = media
        else:
            moment_type = "其他"

        return Moment(
            self, 
            runtime_id,
            type=moment_type,
            sender=sender,
            content=content,
            raw_text=raw_name,
            timestamp=timestamp,
            image_count=image_count,
            cell_type=cls_name,
            scroll_offset=scroll_offset,
        )

    def _collect_moments(self, lc) -> list[tuple[str, str, tuple, int]]:
        """
        收集当前可见的动态条目的 (raw_name, cls_name, runtime_id, ctrl_height) 列表。
        跳过评论区、辅助行等非动态 Cell。
        ctrl_height 为控件的高度（像素），用于累加计算滚动偏移。
        """
        items: list[tuple[str, str, tuple, int]] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            cls_name = ctrl.ClassName or ""
            if not cls_name.startswith(self.TIMELINE_CELL_PREFIX):
                continue
            if cls_name in self.SKIP_CELL_CLASSES:
                continue
            raw = ctrl.Name
            if raw:
                try:
                    rid = tuple(ctrl.GetRuntimeId())
                except Exception:
                    rid = ()
                try:
                    ctrl_height = ctrl.BoundingRectangle.height()
                except Exception:
                    ctrl_height = 0
                items.append((raw, cls_name, rid, ctrl_height))
        return items

    @PIM.guard
    def get_moments(self, count: int = 10, position: str = "top") -> list[Moment]:
        """
        获取朋友圈动态列表。

        持续滚动采集直到收集满 count 条动态才返回，
        如果朋友圈动态不足 count 条则返回全部。

        Args:
            count:    要获取的动态条数，默认 10 条，收集满后立即返回
            position: 起始位置
                - "top":     先点击"刷新"回到顶部，再从头采集（默认）
                - "current": 从当前滚动位置开始采集

        Returns:
            Moment 列表，长度 <= count
        """
        self._open_sns_window()

        if position == "top":
            refresh_btn = self._win.ButtonControl(
                ClassName="mmui::XTabBarItem",
                Name="刷新",
            )
            if refresh_btn.Exists(maxSearchSeconds=2):
                input_wx.click(refresh_btn)
                time.sleep(2)

        lc = self._find_sns_list()

        moments: list[Moment] = []
        seen_keys: set[tuple] = set()  # (runtime_id, raw_text) 组合去重
        cumulative_height: int = 0  # 已采集朋友圈的高度累加

        while len(moments) < count:
            new_found = False
            for raw, cls_name, rid, ctrl_height in self._collect_moments(lc):
                key = (rid, raw) if rid else ((), raw)
                if key in seen_keys:
                    continue
                item = self._parse_moment_name(
                    rid, raw, cls_name, scroll_offset=cumulative_height,
                )
                if item:
                    seen_keys.add(key)
                    moments.append(item)
                    cumulative_height += ctrl_height
                    new_found = True
                if len(moments) >= count:
                    break

            if len(moments) >= count:
                break

            if not new_found:
                input_wx.focus(lc)
                time.sleep(0.2)
                input_wx.send_keys(lc, "{PageDown}")
                time.sleep(1)
                found_after_scroll = False
                for raw, _, rid, _ in self._collect_moments(lc):
                    key = (rid, raw) if rid else ((), raw)
                    if key not in seen_keys:
                        found_after_scroll = True
                        break
                if not found_after_scroll:
                    break
            else:
                input_wx.focus(lc)
                time.sleep(0.2)
                input_wx.send_keys(lc, "{PageDown}")
                time.sleep(0.5)

        return moments[:count]

    @PIM.guard
    def iter_moments(self, count: int = 10, position: str = "top"):
        """
        逐条获取朋友圈动态（生成器）。

        与 get_moments 相同的采集逻辑，但每获取到一条新动态立即 yield，
        适合边获取边操作的场景（如逐条点赞）。

        注意：不使用 @PIM.guard 装饰器（装饰器与生成器不兼容），
        在首次迭代时手动执行一次 guard 等待。

        Args:
            count:    要获取的动态条数，默认 10 条
            position: "top" 从顶部开始，"current" 从当前位置

        Yields:
            Moment 实例

        用法::

            for item in wx.friend_circle.iter_moments(10):
                print(item)
                wx.friend_circle.like(item)
        """
        # 手动执行 guard 等待（替代 @PIM.guard）
        if PIM._running and PIM.idle_wait > 0:
            PIM.wait_for_idle(PIM.idle_wait)

        self._open_sns_window()

        if position == "top":
            refresh_btn = self._win.ButtonControl(
                ClassName="mmui::XTabBarItem",
                Name="刷新",
            )
            if refresh_btn.Exists(maxSearchSeconds=2):
                input_wx.click(refresh_btn)
                time.sleep(2)

        lc = self._find_sns_list()

        yielded = 0
        seen_keys: set[tuple] = set()
        cumulative_height: int = 0

        while yielded < count:
            new_found = False
            for raw, cls_name, rid, ctrl_height in self._collect_moments(lc):
                key = (rid, raw) if rid else ((), raw)
                if key in seen_keys:
                    continue
                item = self._parse_moment_name(
                    rid, raw, cls_name, scroll_offset=cumulative_height,
                )
                if item:
                    seen_keys.add(key)
                    cumulative_height += ctrl_height
                    yield item
                    yielded += 1
                    new_found = True
                if yielded >= count:
                    return

            if not new_found:
                input_wx.focus(lc)
                time.sleep(0.2)
                input_wx.send_keys(lc, "{PageDown}")
                time.sleep(1)
                found_after_scroll = False
                for raw, _, rid, _ in self._collect_moments(lc):
                    key = (rid, raw) if rid else ((), raw)
                    if key not in seen_keys:
                        found_after_scroll = True
                        break
                if not found_after_scroll:
                    return
            else:
                input_wx.focus(lc)
                time.sleep(0.2)
                input_wx.send_keys(lc, "{PageDown}")
                time.sleep(0.5)

    def like(self, moment: Moment) -> bool:
        """对指定动态点赞"""
        return moment.like()

    def unlike(self, moment: Moment) -> bool:
        """取消指定动态的点赞"""
        return moment.unlike()

    def comment(self, moment: Moment, content: str) -> bool:
        """对指定动态评论"""
        return moment.comment(content)

    def scroll_into_visible(self, moment: Moment) -> bool:
        """将指定动态滚动到可见区域"""
        return moment.scroll_to_visible()

    # ---- 发布相关控件信息 ----
    # 发布面板: GroupControl, ClassName="mmui::SnsPublishPanel",
    #           AutomationId="SnsPublishPanel"
    # 文本输入: EditControl, ClassName="mmui::XValidatorTextEdit"
    #           位于 mmui::PublishInputView > mmui::ReplyTextView 内
    # 表情按钮: ButtonControl, ClassName="mmui::XButton", Name="发送表情"
    # 提醒谁看: GroupControl, ClassName="mmui::PublishComponent", Name="提醒谁看"
    # 谁可以看: ButtonControl, ClassName="mmui::PublishPrivacyView", Name 以 "谁可以看" 开头
    # 发表按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="发表"
    # 取消按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="取消"
    # 工具栏发表: ButtonControl, ClassName="mmui::XTabBarItem", Name="发表"

    PUBLISH_PANEL_CLASS = "mmui::SnsPublishPanel"
    PUBLISH_PANEL_ID = "SnsPublishPanel"
    PUBLISH_INPUT_CLASS = "mmui::XValidatorTextEdit"
    PUBLISH_BTN_CLASS = "mmui::XOutlineButton"
    PUBLISH_BTN_NAME = "发表"
    CANCEL_BTN_NAME = "取消"
    PUBLISH_TAB_NAME = "发表"
    TOOLBAR_CLASS = "mmui::SNSWindowToolBar"
    TOOLBAR_ID = "sns_window_tool_bar"

    def _open_publish_panel(self, text_only: bool = False) -> auto.Control:
        """
        打开发布面板并返回面板控件。

        如果面板已打开则直接返回，否则通过工具栏"发表"按钮打开。

        当 text_only=True 时，移动鼠标到"发表"按钮并长按 3 秒，
        触发纯文本发布面板（微信通过长按相机图标进入文字发布模式）。

        当 text_only=False 时，直接左键点击"发表"按钮打开默认发布面板。

        面板: GroupControl, ClassName="mmui::SnsPublishPanel",
              AutomationId="SnsPublishPanel"
        """
        panel = self._win.GroupControl(
            ClassName=self.PUBLISH_PANEL_CLASS,
            AutomationId=self.PUBLISH_PANEL_ID,
        )
        if panel.Exists(maxSearchSeconds=1):
            return panel

        # 查找工具栏
        toolbar = self._win.ToolBarControl(
            ClassName=self.TOOLBAR_CLASS,
            AutomationId=self.TOOLBAR_ID,
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到朋友圈工具栏")

        # 查找工具栏中的"发表"按钮
        publish_tab = toolbar.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name=self.PUBLISH_TAB_NAME,
        )
        if not publish_tab.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到工具栏'发表'按钮")

        if text_only:
            # 纯文本发布：移动鼠标到"发表"按钮，长按 3 秒触发文字发布面板
            rect = publish_tab.BoundingRectangle
            cx = rect.left + int(rect.width() * _rand_ratio())
            cy = rect.top + int(rect.height() * _rand_ratio())
            if not background:
                win32api.SetCursorPos((cx, cy))
                time.sleep(0.1)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
                time.sleep(2)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
            else:
                hwnd_tmp = win32gui.WindowFromPoint((cx, cy))
                if hwnd_tmp:
                    client_x, client_y = win32gui.ScreenToClient(hwnd_tmp, (cx, cy))
                    lparam = win32api.MAKELONG(client_x, client_y)
                    win32gui.SendMessage(hwnd_tmp, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
                    time.sleep(2)
                    win32gui.SendMessage(hwnd_tmp, win32con.WM_LBUTTONUP, 0, lparam)
            time.sleep(1)
        else:
            # 默认发布：左键点击"发表"按钮
            input_wx.click(publish_tab)
            time.sleep(1)

        # 等待发布面板出现
        if not panel.Exists(maxSearchSeconds=5):
            raise RuntimeError("发布面板未打开")

        return panel

    def _find_publish_input(self, panel: auto.Control) -> auto.EditControl:
        """
        在发布面板中查找文本输入框。

        输入框: EditControl, ClassName="mmui::XValidatorTextEdit"
        """
        edit = panel.EditControl(
            ClassName=self.PUBLISH_INPUT_CLASS,
            searchDepth=10,
        )
        if not edit.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到朋友圈文本输入框")
        return edit

    def _find_publish_button(self, panel: auto.Control) -> auto.ButtonControl:
        """
        在发布面板中查找"发表"按钮。

        按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="发表"
        """
        btn = panel.ButtonControl(
            ClassName=self.PUBLISH_BTN_CLASS,
            Name=self.PUBLISH_BTN_NAME,
            searchDepth=3,
        )
        if not btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到'发表'按钮")
        return btn

    def _find_cancel_button(self, panel: auto.Control) -> auto.ButtonControl:
        """
        在发布面板中查找"取消"按钮。

        按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="取消"
        """
        btn = panel.ButtonControl(
            ClassName=self.PUBLISH_BTN_CLASS,
            Name=self.CANCEL_BTN_NAME,
            searchDepth=10,
        )
        if not btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到'取消'按钮")
        return btn

    def _select_file_in_dialog(self, file_path: str) -> None:
        """
        在系统文件选择对话框中选择文件。

        等待 #32770 对话框出现，输入文件路径，按 Alt+O 打开。
        """
        file_dlg = self._win.WindowControl(ClassName="#32770")
        if not file_dlg.Exists(maxSearchSeconds=5):
            raise RuntimeError("文件选择对话框未弹出")

        # 激活文件名输入框
        input_wx.send_keys(file_dlg, "{Alt}N")
        time.sleep(0.3)

        # 输入文件路径
        file_edit = file_dlg.PaneControl(AutomationId="1148").EditControl()
        if not file_edit.Exists(maxSearchSeconds=3):
            file_edit = file_dlg.EditControl(AutomationId="1148")
        if not file_edit.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到文件名输入框")

        vp = file_edit.GetValuePattern()
        if vp:
            vp.SetValue(file_path)
        else:
            input_wx.paste(file_path)
        time.sleep(0.3)

        # Alt+O 打开
        input_wx.send_keys(file_dlg, "{Alt}O")
        time.sleep(1)

    def _set_remind_contacts(self, panel: auto.Control,
                             contacts: list[str]) -> None:
        """
        在发布面板中设置"提醒谁看"的联系人。

        流程:
        1. 点击发布面板中的"提醒谁看"按钮
        2. 等待 SessionPickerWindow（"微信提醒谁看"）弹出
        3. 通过 _select_in_session_picker 搜索并勾选联系人
        4. 点击"完成"关闭弹窗

        Args:
            panel:    发布面板控件
            contacts: 联系人昵称列表
        """
        # 点击"提醒谁看"
        remind_btn = panel.GroupControl(
            ClassName="mmui::PublishComponent",
            Name="提醒谁看",
        )
        if not remind_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'提醒谁看'按钮")
        input_wx.click(remind_btn)
        time.sleep(0.5)

        # 复用 SessionPickerWindow 选择逻辑
        self._select_in_session_picker("微信提醒谁看", contacts=contacts)

    # ---- 隐私设置相关常量 ----
    # 隐私按钮: ButtonControl, ClassName="mmui::PublishPrivacyView"
    PRIVACY_BTN_CLASS = "mmui::PublishPrivacyView"
    # 隐私选项: RadioButtonControl, ClassName="mmui::PublishPrivacySelection"
    PRIVACY_SELECTION_CLASS = "mmui::PublishPrivacySelection"
    # 隐私确定按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="确定"
    PRIVACY_CONFIRM_NAME = "确定"
    # 有效的隐私选项
    PRIVACY_OPTIONS = ("公开", "私密", "谁可以看", "不给谁看")

    def _set_privacy(self, panel: auto.Control, permission: str,
                     permission_contacts: list[str] | None = None,
                     permission_labels: list[str] | None = None) -> None:
        """
        在发布面板中设置"谁可以看"隐私权限。

        流程:
        1. 点击发布面板中的 mmui::PublishPrivacyView 按钮
        2. 弹出隐私选择面板，包含 4 个 RadioButton:
           "公开"、"私密"、"谁可以看"、"不给谁看"
        3. 选择对应的 RadioButton
        4. 若选择"谁可以看"或"不给谁看"，会弹出 SessionPickerWindow
           （Name="微信谁可以看" 或 "微信不给谁看"），
           包含"标签"和"朋友"两个 tab，可分别选择标签和联系人
        5. 选完后点击"完成"关闭 SessionPickerWindow
        6. 点击"确定"关闭隐私选择面板

        控件结构:
        - 隐私按钮: ButtonControl, ClassName="mmui::PublishPrivacyView"
        - 隐私选项: RadioButtonControl, ClassName="mmui::PublishPrivacySelection"
        - 确定按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="确定"
        - SessionPickerWindow 内部结构同 _set_remind_contacts，
          额外有"标签"/"朋友"两个 tab (mmui::XButton)

        Args:
            panel:               发布面板控件
            permission:          隐私选项，"公开"/"私密"/"谁可以看"/"不给谁看"
            permission_contacts: 联系人昵称列表（"谁可以看"/"不给谁看"时使用）
            permission_labels:   标签名称列表（"谁可以看"/"不给谁看"时使用）
        """
        if permission not in self.PRIVACY_OPTIONS:
            raise ValueError(
                f"无效的隐私选项 '{permission}'，"
                f"有效值: {self.PRIVACY_OPTIONS}"
            )

        # 点击隐私按钮打开隐私选择面板
        privacy_btn = panel.ButtonControl(
            ClassName=self.PRIVACY_BTN_CLASS,
            searchDepth=5,
        )
        if not privacy_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'谁可以看'隐私按钮")
        input_wx.click(privacy_btn)
        time.sleep(0.5)

        # 隐私选项面板覆盖在发布面板上方，但不在 panel 子树中，
        # 需要在 SNSWindow 上搜索
        # 选择对应的隐私选项 RadioButton
        radio = self._win.RadioButtonControl(
            ClassName=self.PRIVACY_SELECTION_CLASS,
            Name=permission,
            searchDepth=10,
        )
        if not radio.Exists(maxSearchSeconds=2):
            raise RuntimeError(f"未找到隐私选项 '{permission}'")
        input_wx.click(radio)
        time.sleep(0.5)

        # "谁可以看"和"不给谁看"需要选择联系人/标签
        if permission in ("谁可以看", "不给谁看"):
            picker_name = f"微信{permission}"
            self._select_in_session_picker(
                picker_name, permission_contacts, permission_labels,
            )

        # 点击"确定"关闭隐私选择面板（同样在 SNSWindow 上搜索）
        confirm_btn = self._win.ButtonControl(
            ClassName=self.PUBLISH_BTN_CLASS,
            Name=self.PRIVACY_CONFIRM_NAME,
            searchDepth=10,
        )
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到隐私设置'确定'按钮")
        input_wx.click(confirm_btn)
        time.sleep(0.5)

    def _select_in_session_picker(
        self,
        picker_name: str,
        contacts: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> None:
        """
        在 SessionPickerWindow 中选择联系人和/或标签。

        "谁可以看"/"不给谁看"/"提醒谁看"共用此方法。
        SessionPickerWindow 内部结构:
        - 搜索框: EditControl, Name="搜索", ClassName="mmui::XValidatorTextEdit"
        - 搜索结果: CheckBoxControl, ClassName="mmui::SearchContactCellView"
        - "标签" tab: ButtonControl, Name="标签", ClassName="mmui::XButton"
        - "朋友" tab: ButtonControl, Name="朋友", ClassName="mmui::XButton"
        - 标签列表项: CheckBoxControl, ClassName="mmui::SPSelectionContactRow"
        - 完成按钮: ButtonControl, AutomationId="confirm_btn"

        注意：picker 内部存在自引用控件，所有子控件查找必须限制 searchDepth。

        Args:
            picker_name: SessionPickerWindow 的 Name（如 "微信谁可以看"）
            contacts:    联系人昵称列表
            labels:      标签名称列表
        """
        picker = self._win.WindowControl(
            ClassName="mmui::SessionPickerWindow",
            Name=picker_name,
        )
        if not picker.Exists(maxSearchSeconds=3):
            raise RuntimeError(f"'{picker_name}'弹窗未打开")

        # 选择标签
        if labels:
            # 点击"标签" tab
            label_tab = picker.ButtonControl(
                ClassName="mmui::XButton",
                Name="标签",
                searchDepth=5,
            )
            if label_tab.Exists(maxSearchSeconds=2):
                input_wx.click(label_tab)
                time.sleep(0.5)

                # 标签列表中直接勾选（标签数量通常不多，无需搜索）
                contact_list = picker.ListControl(
                    AutomationId="sp_to_select_contact_list",
                    searchDepth=5,
                )
                if contact_list.Exists(maxSearchSeconds=2):
                    for label_name in labels:
                        label_item = contact_list.CheckBoxControl(
                            Name=label_name,
                            searchDepth=2,
                        )
                        if label_item.Exists(maxSearchSeconds=2):
                            input_wx.click(label_item)
                            time.sleep(0.3)
                        else:
                            logger.warning("未找到标签 '%s'", label_name)

        # 选择联系人
        if contacts:
            # 点击"朋友" tab（如果有标签 tab 说明需要切换）
            friend_tab = picker.ButtonControl(
                ClassName="mmui::XButton",
                Name="朋友",
                searchDepth=5,
            )
            if friend_tab.Exists(maxSearchSeconds=2):
                input_wx.click(friend_tab)
                time.sleep(0.5)

            # 通过搜索逐个选择联系人
            search_edit = picker.EditControl(
                ClassName="mmui::XValidatorTextEdit",
                Name="搜索",
                searchDepth=5,
            )
            if not search_edit.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到搜索框")

            not_found: list[str] = []

            for contact in contacts:
                input_wx.click(search_edit)
                time.sleep(0.2)
                input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
                time.sleep(0.2)
                input_wx.paste(contact)
                time.sleep(1)

                result_list = picker.ListControl(
                    AutomationId="sp_search_result_list",
                    searchDepth=5,
                )
                if not result_list.Exists(maxSearchSeconds=2):
                    logger.warning("搜索 '%s' 时未出现结果列表", contact)
                    not_found.append(contact)
                    continue

                matched = result_list.CheckBoxControl(
                    ClassName="mmui::SearchContactCellView",
                    Name=contact,
                    searchDepth=2,
                )
                if matched.Exists(maxSearchSeconds=2):
                    input_wx.click(matched)
                    time.sleep(0.3)
                else:
                    first_result = result_list.CheckBoxControl(
                        ClassName="mmui::SearchContactCellView",
                        searchDepth=2,
                    )
                    if first_result.Exists(maxSearchSeconds=1):
                        logger.warning(
                            "未精确匹配 '%s'，选择第一个结果: '%s'",
                            contact, first_result.Name,
                        )
                        input_wx.click(first_result)
                        time.sleep(0.3)
                    else:
                        logger.warning("搜索 '%s' 无结果", contact)
                        not_found.append(contact)

            if not_found:
                logger.warning("以下联系人未找到: %s", not_found)

        # 点击"完成"按钮
        confirm_btn = picker.ButtonControl(
            AutomationId="confirm_btn",
            searchDepth=5,
        )
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'完成'按钮")
        input_wx.click(confirm_btn)
        time.sleep(0.5)

    @PIM.guard
    def publish(self, text: Optional[str] = None, images: list[str] = None,
                video: str = None, remind_contacts: list[str] = None,
                permission: str = None,
                permission_contacts: list[str] = None,
                permission_labels: list[str] = None) -> bool:
        """
        发布朋友圈。

        支持纯文字、图文、视频三种模式（图片和视频互斥）。

        Args:
            text:                 文本内容（纯文字模式必填，图文/视频模式可选）
            images:               图片路径列表（与 video 互斥）
            video:                视频路径（与 images 互斥）
            remind_contacts:      提醒谁看的联系人昵称列表
            permission:           隐私设置，可选值:
                                  "公开"（默认）/ "私密" / "谁可以看" / "不给谁看"
            permission_contacts:  隐私联系人列表（"谁可以看"/"不给谁看"时使用）
            permission_labels:    隐私标签列表（"谁可以看"/"不给谁看"时使用）

        Returns:
            True 发布成功
        """
        # 参数校验
        if images and video:
            raise ValueError("images 和 video 只能指定其中一个参数")
        if images and len(images) > 9:
            raise ValueError("朋友圈最多发 9 张图片")
        has_media = bool(images) or bool(video)
        if not text and not has_media:
            raise ValueError("text 和 images/video 至少指定一个")

        self._open_sns_window()

        # 右键"发表"按钮弹出菜单
        publish_tab = self._find_toolbar_button(self.PUBLISH_TAB_NAME)
        input_wx.click(publish_tab, button="right")
        time.sleep(0.5)

        if has_media:
            # 点击"选照片或视频"
            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView",
                Name="选照片或视频",
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'选照片或视频'菜单项")
            input_wx.click(menu_item)
            time.sleep(1)

            # 选择第一个文件
            first_file = images[0] if images else video
            self._select_file_in_dialog(first_file)

            # 等待发布面板出现
            panel = self._win.GroupControl(
                ClassName=self.PUBLISH_PANEL_CLASS,
                AutomationId=self.PUBLISH_PANEL_ID,
            )
            if not panel.Exists(maxSearchSeconds=5):
                raise RuntimeError("发布面板未打开")

            # 多张图片：逐个点击"添加图片"格子添加
            if images and len(images) > 1:
                for img_path in images[1:]:
                    # "添加图片"是 ListItemControl，ClassName="mmui::PublishImageAddGridCell"
                    add_cell = panel.ListItemControl(
                        ClassName="mmui::PublishImageAddGridCell",
                        Name="添加图片",
                        searchDepth=10,
                    )
                    if not add_cell.Exists(maxSearchSeconds=3):
                        raise RuntimeError("未找到'添加图片'按钮")

                    input_wx.click(add_cell)
                    time.sleep(1)

                    self._select_file_in_dialog(img_path)
        else:
            # 纯文字：点击"发表文字"
            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView",
                Name="发表文字",
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'发表文字'菜单项")
            input_wx.click(menu_item)
            time.sleep(1)

            panel = self._win.GroupControl(
                ClassName=self.PUBLISH_PANEL_CLASS,
                AutomationId=self.PUBLISH_PANEL_ID,
            )
            if not panel.Exists(maxSearchSeconds=5):
                raise RuntimeError("发布面板未打开")

        # 输入文字内容
        if text:
            edit = self._find_publish_input(panel)
            edit.GetValuePattern().SetValue(text)

        # 设置提醒谁看
        if remind_contacts:
            self._set_remind_contacts(panel, remind_contacts)

        # 设置隐私权限
        if permission:
            self._set_privacy(
                panel, permission, permission_contacts, permission_labels,
            )

        # 点击"发表"
        publish_btn = self._find_publish_button(panel)
        input_wx.click(publish_btn)

        # 等待发布面板消失
        for _ in range(30):
            if not panel.Exists(maxSearchSeconds=1):
                logger.info("朋友圈发布成功")
                return True
            time.sleep(1)

        raise RuntimeError("发布超时，发布面板未关闭")

    def _find_toolbar_button(self, name: str) -> auto.ButtonControl:
        """
        在朋友圈工具栏中查找指定名称的按钮。

        工具栏: ToolBarControl, ClassName="mmui::SNSWindowToolBar",
                AutomationId="sns_window_tool_bar"
        按钮:   ButtonControl, ClassName="mmui::XTabBarItem"

        Args:
            name: 按钮名称（如 "刷新"、"发表"）

        Returns:
            ButtonControl 控件

        Raises:
            RuntimeError: 未找到工具栏或按钮时抛出
        """
        toolbar = self._win.ToolBarControl(
            ClassName=self.TOOLBAR_CLASS,
            AutomationId=self.TOOLBAR_ID,
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到朋友圈工具栏")

        btn = toolbar.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name=name,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError(f"未找到工具栏'{name}'按钮")
        return btn

    @PIM.guard
    def refresh(self) -> None:
        """
        刷新朋友圈。

        点击工具栏"刷新"按钮，回到列表顶部并加载最新动态。
        """
        self._open_sns_window()
        btn = self._find_toolbar_button("刷新")
        input_wx.click(btn)
        time.sleep(2)

    def __str__(self) -> str:
        return "FriendCircle(朋友圈)"


# ======================================================================
# 模块: file_manager
# ======================================================================

"""
pywxauto 文件管理器模块。

包含 FileManager 和 ChatFile 类。
"""


logger = logging.getLogger(__name__)


@dataclass
class ChatFile:
    """聊天文件信息（来自"聊天文件"管理器窗口）"""
    file_name: str = ""           # 文件名
    sender_name: str = ""         # 发送人
    source_name: str = ""         # 来源（群名或个人昵称）
    source_type: str = ""         # 来源类型: "contact"(联系人私聊) 或 "room"(群聊)
    file_date: str = ""           # 日期文本
    file_status: str = ""         # 状态（如"将在X天后无法下载"、空=已下载）
    file_size: str = ""           # 文件大小
    raw_text: str = ""            # 原始文本
    _cell: object = field(default=None, repr=False)  # UI 控件引用（内部使用）

    def __str__(self):
        status = self.file_status if self.file_status else "已下载"
        type_label = "联系人" if self.source_type == "contact" else "群聊"
        return (f"[{self.file_date}] [{type_label}] {self.file_name} | "
                f"发送人: {self.sender_name} | 来源: {self.source_name} | "
                f"大小: {self.file_size} | 状态: {status}")


class FileManager(WeixinWindow):
    """
    微信"聊天文件"管理器窗口操作类。

    通过微信主窗口的"更多 → 聊天文件"打开独立的 mmui::FileManagerWindow 窗口，
    支持按文件类型筛选、获取文件列表、另存为等操作。

    关键控件:
    - 文件列表项: mmui::FileListCell
    - 文件类型筛选: mmui::XTableCell (ListItemControl)
    - 右键菜单: mmui::XMenu（浮动于桌面层级）
    """

    WINDOW_NAME = "聊天文件"
    FILE_LIST_CELL_CLASS = "mmui::FileListCell"
    MORE_BTN_AUTOMATION_ID = "main_tabbar.tabbar_setting"
    FILE_TYPE_FILTER_CLASS = "mmui::XTableCell"
    CONTEXT_MENU_WIN_CLASS = "mmui::XMenu"
    # 确认对话框的类名（微信 v4 使用 mmui::XDialog，浮动于桌面层级）
    CONFIRM_DIALOG_WIN_CLASS = "mmui::XDialog"
    SAVE_AS_MENU_ITEM_NAME = "另存为..."
    DOWNLOAD_TO_MENU_ITEM_NAME = "下载到..."
    DOWNLOAD_MENU_ITEM_NAME = "下载"
    DELETE_MENU_ITEM_NAME = "删除"

    def __init__(self, wx: "Weixin"):
        self.wx = wx
        self._win = auto.WindowControl(
            Name=self.WINDOW_NAME, searchDepth=1,
        )

    def _find_window(self) -> Optional[auto.WindowControl]:
        """查找并激活聊天文件窗口（独立窗口）"""
        self._win = auto.WindowControl(
            Name=self.WINDOW_NAME, searchDepth=1
        )
        if self._win.Exists(maxSearchSeconds=3):
            if not background:
                self._win.SetActive()
            return self._win
        return None

    @PIM.guard
    def open(self, filter_type: str = "") -> bool:
        """
        打开聊天文件管理器窗口。

        Args:
            filter_type: 文件类型筛选，可选值:
                - "全部"、"文档"、"表格"、"图片"、"视频"等
                - "": 不筛选（默认）
        """
        self.wx.activate()

        # 先关闭已有的文件管理器窗口
        self.close()

        # 通过导航栏 TabBar 缩小搜索范围，点击"更多"按钮
        self.wx.navigator.switch_to("更多")

        # 点击"聊天文件"按钮
        chat_file_btn = self.wx._win.ButtonControl(
            Name="聊天文件", searchDepth=10
        )
        if not chat_file_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到'聊天文件'按钮")

        input_wx.click(chat_file_btn)
        time.sleep(1)

        # 验证文件管理器窗口已打开
        fm_win = self._find_window()
        if not fm_win:
            raise RuntimeError("聊天文件窗口未能打开")

        # 如果指定了筛选类型，点击对应的筛选按钮
        if filter_type:
            self._click_filter(fm_win, filter_type)

        return True

    def _click_filter(self, fm_win, filter_name: str) -> bool:
        """
        点击聊天文件窗口中的文件类型筛选按钮。

        已知的筛选选项: "全部"、"文档"、"表格"、"图片"、"视频"等。
        """
        filter_btn = fm_win.ListItemControl(
            Name=filter_name,
            ClassName=self.FILE_TYPE_FILTER_CLASS,
            searchDepth=10,
        )
        if not filter_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError(f"未找到'{filter_name}'筛选按钮")

        input_wx.click(filter_btn)
        time.sleep(0.5)
        return True

    @PIM.guard
    def close(self, method: str = "event") -> None:
        """
        关闭聊天文件管理器窗口。

        Args:
            method: 关闭方式
                - "click": 点击窗口上的"关闭"按钮
                - "event": 通过 WM_CLOSE 消息关闭（默认）
        """
        fm_win = self._find_window()
        if not fm_win:
            return

        if method == "click":
            self._close_by_click(fm_win)
        elif method == "event":
            self._close_by_event(fm_win)

    def _close_by_click(self, fm_win) -> bool:
        """通过点击"关闭"按钮关闭窗口"""
        try:
            close_btn = fm_win.ButtonControl(Name="关闭")
            if close_btn.Exists(maxSearchSeconds=1):
                input_wx.click(close_btn)
                time.sleep(0.5)
                if not fm_win.Exists(maxSearchSeconds=1):
                    return True
        except Exception:
            pass
        return False

    def _close_by_event(self, fm_win) -> bool:
        """通过 WM_CLOSE 消息关闭窗口"""
        WM_CLOSE = 0x0010
        try:
            hwnd = fm_win.NativeWindowHandle
            if hwnd:
                ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                time.sleep(0.5)
                if not fm_win.Exists(maxSearchSeconds=1):
                    return True
        except Exception:
            pass
        return False

    def _find_context_menu_by_point(self) -> Optional[auto.Control]:
        """
        通过 ControlFromPoint 定位右键菜单。

        右键点击后鼠标指针停在菜单左上角，直接用当前鼠标坐标命中菜单，
        然后沿 GetParentControl() 向上查找 mmui::XMenu 容器。
        """
        for _ in range(10):
            x, y = auto.GetCursorPos()
            ctrl = auto.ControlFromPoint(x, y)
            if ctrl:
                current = ctrl
                for _ in range(10):
                    if current.ClassName == self.CONTEXT_MENU_WIN_CLASS:
                        return current
                    parent = current.GetParentControl()
                    if not parent:
                        break
                    current = parent
            time.sleep(0.3)
        return None

    def _find_confirm_dialog(self, max_attempts: int = 10) -> Optional[auto.Control]:
        """
        通过 ControlFromPoint 定位确认对话框。

        微信 v4 的确认对话框（mmui::XDialog）与右键菜单类似，
        浮动于桌面层级，不是文件管理器窗口的子控件。
        点击菜单项后鼠标指针停留在弹窗区域，
        用当前鼠标坐标命中弹窗，然后沿父级向上查找。
        """
        for _ in range(max_attempts):
            x, y = auto.GetCursorPos()
            ctrl = auto.ControlFromPoint(x, y)
            if ctrl:
                current = ctrl
                for _ in range(10):
                    if current.ClassName == self.CONFIRM_DIALOG_WIN_CLASS:
                        return current
                    parent = current.GetParentControl()
                    if not parent:
                        break
                    current = parent
            time.sleep(0.3)
        return None

    @PIM.guard
    def save_file_as(self, file_cell, file_path: str) -> bool:
        """
        对文件列表中的某个文件执行"另存为"操作。

        流程:
        1. 右键点击文件项 → 弹出微信右键菜单
        2. 点击"另存为..."菜单项 → 弹出 Windows 文件保存对话框
        3. 设置保存路径 → 按 Alt+S 保存

        Args:
            file_cell: mmui::FileListCell 控件对象（从 get_all_files 返回的 ChatFile._cell）
            file_path: 完整的保存路径（含文件名），如 "C:\\download\\test.xlsx"
        """
        fm_win = self._find_window()
        if not fm_win:
            raise RuntimeError("聊天文件窗口未打开")

        # 确保目标目录存在
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # 1. 右键点击文件项
        input_wx.click(file_cell, button="right")
        time.sleep(0.5)

        # 2. 定位右键菜单
        menu = self._find_context_menu_by_point()
        if not menu:
            raise RuntimeError("未找到右键菜单")

        # 查找"另存为..."菜单项
        save_as_item = None
        for child in menu.GetChildren():
            if child.Name == self.SAVE_AS_MENU_ITEM_NAME:
                save_as_item = child
                break

        if not save_as_item:
            raise RuntimeError("未找到'另存为'菜单项")

        input_wx.click(save_as_item)
        time.sleep(1)

        # 3. 查找 Windows 文件保存对话框（聊天文件窗口的子窗口）
        save_dialog = fm_win.WindowControl(ClassName="#32770", searchDepth=3)
        if not save_dialog.Exists(maxSearchSeconds=5):
            raise RuntimeError("未找到 Windows 文件保存对话框")

        # 定位文件名输入框
        file_name_edit = save_dialog.EditControl(
            AutomationId="1001", searchDepth=10
        )
        if not file_name_edit.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到文件名输入框")

        file_name_edit.GetValuePattern().SetValue(file_path)

        # 如果目标文件已存在，先删除（避免覆盖确认弹窗）
        if os.path.exists(file_path):
            os.remove(file_path)

        # 快捷键保存
        input_wx.send_keys(None, "{Alt}s")
        if not save_dialog.Exists(maxSearchSeconds=2):
            return True
        else:
            input_wx.send_keys(None, "{Esc}")
            return False

    @PIM.guard
    def download_to(self, file_cell, file_path: str) -> bool:
        """
        对文件列表中的某个文件执行"下载到"操作。

        流程与 save_file_as 一致，只是点击的菜单项为"下载到..."。

        Args:
            file_cell: mmui::FileListCell 控件对象（从 get_all_files 返回的 ChatFile._cell）
            file_path: 完整的保存路径（含文件名），如 "C:\\download\\test.xlsx"
        """
        fm_win = self._find_window()
        if not fm_win:
            raise RuntimeError("聊天文件窗口未打开")

        # 确保目标目录存在
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # 1. 右键点击文件项
        input_wx.click(file_cell, button="right")
        time.sleep(0.5)

        # 2. 定位右键菜单
        menu = self._find_context_menu_by_point()
        if not menu:
            raise RuntimeError("未找到右键菜单")

        # 查找"下载到..."菜单项
        download_to_item = None
        for child in menu.GetChildren():
            if child.Name == self.DOWNLOAD_TO_MENU_ITEM_NAME:
                download_to_item = child
                break

        if not download_to_item:
            raise RuntimeError("未找到'下载到'菜单项")

        input_wx.click(download_to_item)
        time.sleep(1)

        # 3. 查找 Windows 文件保存对话框（聊天文件窗口的子窗口）
        save_dialog = fm_win.WindowControl(ClassName="#32770", searchDepth=3)
        if not save_dialog.Exists(maxSearchSeconds=5):
            raise RuntimeError("未找到 Windows 文件保存对话框")

        # 定位文件名输入框
        file_name_edit = save_dialog.EditControl(
            AutomationId="1001", searchDepth=10
        )
        if not file_name_edit.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到文件名输入框")

        file_name_edit.GetValuePattern().SetValue(file_path)

        # 如果目标文件已存在，先删除（避免覆盖确认弹窗）
        if os.path.exists(file_path):
            os.remove(file_path)

        # 快捷键保存
        input_wx.send_keys(None, "{Alt}s")
        if not save_dialog.Exists(maxSearchSeconds=2):
            return True
        else:
            input_wx.send_keys(None, "{Esc}")
            return False

    @PIM.guard
    def delete_file(self, file_cell) -> bool:
        """
        删除文件列表中的某个文件。

        流程:
        1. 右键点击文件项 → 弹出微信右键菜单
        2. 点击"删除"菜单项 → 弹出确认对话框
        3. 点击确认按钮完成删除

        Args:
            file_cell: mmui::FileListCell 控件对象（从 get_all_files 返回的 ChatFile._cell）

        Returns:
            True 删除成功，False 删除失败
        """
        fm_win = self._find_window()
        if not fm_win:
            raise RuntimeError("聊天文件窗口未打开")

        # 1. 右键点击文件项
        input_wx.click(file_cell, button="right")
        time.sleep(0.5)

        # 2. 定位右键菜单
        menu = self._find_context_menu_by_point()
        if not menu:
            raise RuntimeError("未找到右键菜单")

        # 查找"删除"菜单项
        delete_item = None
        for child in menu.GetChildren():
            if child.Name == self.DELETE_MENU_ITEM_NAME:
                delete_item = child
                break

        if not delete_item:
            raise RuntimeError("未找到'删除'菜单项")

        input_wx.click(delete_item)
        time.sleep(0.5)

        # 在确认对话框中查找"删除"或"确定"按钮并点击
        # 微信 v4 的删除确认弹窗使用 mmui::XOutlineButton，Name="删除"
        confirm_btn = None

        # 优先查找 mmui::XOutlineButton 的"删除"按钮
        delete_btn = self._win.ButtonControl(
            ClassName="mmui::XOutlineButton", Name="删除",
        )
        if delete_btn.Exists(maxSearchSeconds=2):
            input_wx.click(delete_btn)
            time.sleep(0.5)
            return True
        return False

    @PIM.guard
    def download_file(self, file_cell, timeout: int = 60) -> bool:
        """
        下载文件列表中的某个文件。

        流程:
        1. 右键点击文件项 → 弹出微信右键菜单
        2. 点击"下载"菜单项 → 开始下载
        3. 轮询文件状态，等待 file_status 变为空（即已下载）

        Args:
            file_cell: mmui::FileListCell 控件对象（从 get_all_files 返回的 ChatFile._cell）
            timeout:   等待下载完成的超时时间（秒），默认 60 秒

        Returns:
            True 下载成功（状态变为已下载），False 下载超时

        Raises:
            RuntimeError: 聊天文件窗口未打开、右键菜单未弹出或未找到"下载"菜单项时抛出
        """
        fm_win = self._find_window()
        if not fm_win:
            raise RuntimeError("聊天文件窗口未打开")

        # 1. 右键点击文件项
        input_wx.click(file_cell, button="right")
        time.sleep(0.5)

        # 2. 定位右键菜单
        menu = self._find_context_menu_by_point()
        if not menu:
            raise RuntimeError("未找到右键菜单")

        # 查找"下载"菜单项
        download_item = None
        for child in menu.GetChildren():
            if child.Name == self.DOWNLOAD_MENU_ITEM_NAME:
                download_item = child
                break

        if not download_item:
            raise RuntimeError("未找到'下载'菜单项，文件可能已下载")

        input_wx.click(download_item)
        time.sleep(0.5)

        # 3. 轮询文件状态，等待下载完成
        # 下载完成后，文件的 Name 属性中不再包含"将在X天后无法下载"等状态文本，
        # 即 parse_file_cell_text 解析出的 file_status 为空字符串。
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # 重新读取文件项的 Name 属性（下载过程中会实时更新）
            cell_text = file_cell.Name
            if not cell_text:
                time.sleep(1)
                continue

            chat_file = self.parse_file_cell_text(cell_text)
            if chat_file and not chat_file.file_status:
                # file_status 为空表示已下载
                return True

            time.sleep(1)

        return False

    @staticmethod
    def parse_file_cell_text(cell_text: str) -> Optional[ChatFile]:
        """
        解析 mmui::FileListCell 的 Name 属性文本，提取文件信息。

        文本格式: "文件名 发送人 | 来源 日期 状态 大小"
        """
        if not cell_text:
            return None

        separator = " | "
        sep_idx = cell_text.rfind(separator)
        if sep_idx <= 0:
            return None

        left_part = cell_text[:sep_idx].strip()
        right_part = cell_text[sep_idx + len(separator):].strip()

        # 解析右侧: 来源 日期 [状态] 大小
        size_pattern = r'[\d.]+[BKMGT]'
        right_tokens = right_part.split()

        if len(right_tokens) < 2:
            return None

        file_size = right_tokens[-1] if re.match(size_pattern, right_tokens[-1]) else ""

        # 日期格式:
        #   - 今天: 只显示时间 "10:53"
        #   - 昨天: "昨天"
        #   - 本周: "星期X"
        #   - 更早: "YYYY年M月D日"
        date_str = ""
        date_idx = -1
        time_pattern = r'^\d{1,2}:\d{2}$'
        for i, token in enumerate(right_tokens):
            if re.match(time_pattern, token):
                date_str = "今天"
                date_idx = i
                break
            if token in ("今天", "昨天") or "星期" in token:
                date_str = token
                date_idx = i
                break
            if "年" in token and "月" in token:
                date_str = token
                date_idx = i
                break

        source_name = " ".join(right_tokens[:date_idx]) if date_idx > 0 else ""

        if file_size and date_idx >= 0:
            status_tokens = right_tokens[date_idx + 1:-1]
            file_status = " ".join(status_tokens)
        else:
            file_status = ""

        # 处理 source_name 以 " 未下载" 结尾的情况：
        # 微信文件列表中未下载的文件，"未下载"会紧跟在来源名称后面，
        # 被错误地解析为 source_name 的一部分。
        # 例如: "泡泡马特发货群 未下载 18:20 ..." 中 source_name 会被解析为
        # "泡泡马特发货群 未下载"，需要将 "未下载" 拆分到 file_status 中。
        if source_name.endswith(" 未下载"):
            source_name = source_name.rstrip(" 未下载")
            file_status = "未下载"

        left_tokens = left_part.rsplit(" ", 1)
        if len(left_tokens) == 2:
            file_name = left_tokens[0].strip()
            sender_name = left_tokens[1].strip()
        else:
            file_name = left_part
            sender_name = ""

        source_type = "contact" if sender_name and sender_name == source_name else "room"

        return ChatFile(
            file_name=file_name,
            sender_name=sender_name,
            source_name=source_name,
            source_type=source_type,
            file_date=date_str,
            file_status=file_status,
            file_size=file_size,
            raw_text=cell_text,
        )

    def _find_all_file_cells(self, parent) -> list:
        """递归查找所有 mmui::FileListCell 控件"""
        results = []
        try:
            children = parent.GetChildren()
            for child in children:
                if child.ClassName == self.FILE_LIST_CELL_CLASS:
                    results.append(child)
                else:
                    results.extend(self._find_all_file_cells(child))
        except Exception:
            pass
        return results

    def get_all_files(self) -> list[ChatFile]:
        """获取聊天文件窗口中所有可见的文件列表"""
        fm_win = self._find_window()
        if not fm_win:
            raise RuntimeError("聊天文件窗口未打开")

        files = []
        for cell in self._find_all_file_cells(fm_win):
            chat_file = self.parse_file_cell_text(cell.Name)
            if chat_file:
                chat_file._cell = cell
                files.append(chat_file)
        return files

    def get_today_files(self) -> list[ChatFile]:
        """获取今天的文件列表"""
        all_files = self.get_all_files()
        today_str = "今天"
        today_date = date.today()
        today_formatted = f"{today_date.year}年{today_date.month}月{today_date.day}日"
        return [f for f in all_files
                if f.file_date == today_str or f.file_date == today_formatted]

    @property
    def exists(self) -> bool:
        """聊天文件窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=1)

    def __str__(self) -> str:
        if self._win.Exists(0, 0):
            return "FileManager(open)"
        return "FileManager(closed)"


# ======================================================================
# 模块: chat
# ======================================================================

"""
pywxauto 聊天模块。

包含 Chat（主窗口聊天区域）和 SeparateChat（独立窗口聊天）类。
"""


logger = logging.getLogger(__name__)


class Chat:
    """
    聊天区域，包含标题栏、消息列表、输入框。

    关键控件：
    - 标题栏名称: TextControl,
        AutomationId="content_view...current_chat_name_label"
    - 消息列表: ListControl, Name="消息",
        ClassName="mmui::RecyclerListView", AutomationId="chat_message_list"
    - 输入框: EditControl, ClassName="mmui::ChatInputField",
              AutomationId="chat_input_field"
    - 发送按钮: ButtonControl, Name="发送", ClassName="mmui::XOutlineButton"
    - 工具栏: ToolBarControl, AutomationId="tool_bar_accessible"
      - 发送表情(Alt+E), 发送收藏, 发送文件, 截图(Alt+A), 语音输入
    """

    TITLE_LABEL_IDS = [
        # 4.1.2.17
        "title_h_view.title_left_v_view_.title_left_info_v_view_.big_title_line_h_view.current_chat_name_label",
        # 4.1.2.17+
        "content_view.top_content_view.title_h_view.title_left_v_view_.title_left_info_v_view_.big_title_line_h_view.current_chat_name_label",
        # 4.1.8.28
        "content_view.top_content_view.title_h_view.left_v_view.left_content_v_view.left_ui_.big_title_line_h_view.current_chat_name_label",
    ]
    MEMBER_COUNT_LABEL_IDS = [
        # 4.1.2.17
        "title_h_view.title_left_v_view_.title_left_info_v_view_.big_title_line_h_view.current_chat_count_label",
        # 4.1.2.17+
        "content_view.top_content_view.title_h_view.title_left_v_view_.title_left_info_v_view_.big_title_line_h_view.current_chat_count_label",
        # 4.1.8.28
        "content_view.top_content_view.title_h_view.left_v_view.left_content_v_view.left_ui_.big_title_line_h_view.current_chat_count_label",
    ]

    def __init__(self, wx: "Weixin"):
        self.wx = wx
        self._win = wx._win

    def _get_image_text(self, image: bytes) -> dict:
        """
        识别图片中的文本内容。
        """
        if self.wx is None:
            raise RuntimeError("未关联 Weixin 实例，无法执行 OCR")
        return self.wx.get_image_text(image)

    def _activate_window(self) -> None:
        """
        激活当前聊天所在的窗口。

        Chat: 激活微信主窗口
        SeparateChat: 子类覆盖此方法，激活独立窗口
        """
        if self.wx:
            self.wx.activate()

    def __str__(self) -> str:
        try:
            name = self.current_name
            chat_type = self.chat_type
            return f"Chat(type={chat_type!r}, name={name!r})"
        except Exception as e:
            return f"Chat(error={e!r})"

    # -- 标题栏 --

    def _find_title_label(self) -> Optional[auto.TextControl]:
        """查找标题栏名称控件（兼容多版本 AutomationId）"""
        for aid in self.TITLE_LABEL_IDS:
            ctrl = self._win.TextControl(AutomationId=aid)
            if ctrl.Exists(0, 0):
                return ctrl
        return None

    def _find_member_count_label(self) -> Optional[auto.TextControl]:
        """查找成员数量控件（兼容多版本 AutomationId）"""
        for aid in self.MEMBER_COUNT_LABEL_IDS:
            ctrl = self._win.TextControl(AutomationId=aid)
            if ctrl.Exists(0, 0):
                return ctrl
        return None

    @property
    def current_name(self) -> str:
        """获取当前聊天对象名称"""
        label = self._find_title_label()
        return label.Name if label else ""

    @property
    def chat_type(self) -> str:
        """
        获取当前聊天类型。

        通过标题栏是否存在成员数量标签判断：
        - 存在 -> "群聊"
        - 不存在且有聊天名称 -> "私聊"
        - 无聊天名称 -> "未知"
        """
        if not self._find_title_label():
            return "未知"
        return "群聊" if self._find_member_count_label() else "私聊"

    # -- 输入框 --

    @property
    def _input_field(self) -> auto.EditControl:
        return self._win.EditControl(
            ClassName="mmui::ChatInputField",
            AutomationId="chat_input_field",
        )

    def clear_input(self) -> None:
        """清空输入框"""
        field = self._input_field
        if field.Exists(maxSearchSeconds=2):
            input_wx.send_keys(field, "{Ctrl}a{Del}")
            time.sleep(0.1)

    # -- 发送消息 --

    # ClassName -> 消息类型映射（供状态检测使用）
    _TEXT_CLASS_NAMES = {"mmui::ChatTextItemView"}
    _FILE_CLASS_NAMES = {"mmui::ChatFileItemView"}
    _IMAGE_CLASS_NAMES = {"mmui::ChatImageItemView"}
    _VIDEO_CLASS_NAMES = {"mmui::ChatVideoItemView"}
    _EMOTION_CLASS_NAMES = {"mmui::ChatEmojiItemView", "mmui::ChatBubbleReferItemView"}
    # 文件消息在传输中/失败时 ClassName 为 ChatBubbleItemView，
    # 需要通过 Name 以 "文件\n" 开头来区分
    _FILE_BUBBLE_CLASS_NAMES = {"mmui::ChatFileItemView", "mmui::ChatBubbleItemView"}

    def _find_last_self_message_ctrl(
        self, class_names: set[str],
    ) -> Optional[auto.Control]:
        """
        从消息列表中倒序查找最后一条自己发的、且 ClassName 匹配的消息控件。

        通过头像控件位置判断是否为自己发的消息（头像在右侧）。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return None

        # 获取窗口句柄，用于 PrintWindow 截图
        hwnd = self._win.NativeWindowHandle or 0

        # 收集所有消息控件
        candidates: list[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            if (ctrl.ClassName or "") in class_names:
                candidates.append(ctrl)

        # 倒序查找自己发的
        for ctrl in reversed(candidates):
            sender, sender_type, _ = self._detect_sender(
                hwnd, ctrl, self.current_name or "对方",
            )
            if sender_type == SenderType.SELF:
                return ctrl
        return None

    @staticmethod
    def _check_status_by_prefix(
        name: str,
        space_sep: bool = True,
    ) -> MessageStatus:
        """
        通过 Name 前缀判断消息发送状态。

        space_sep=True:  前缀用空格分隔（文本/图片/视频等）
        space_sep=False: 前缀用换行分隔（文件消息）
        """
        sep = " " if space_sep else "\n"
        if name.startswith(f"发送失败{sep}"):
            return MessageStatus.FAILED
        if name.startswith(f"发送中{sep}"):
            return MessageStatus.SENDING
        return MessageStatus.SENT

    def _check_last_message_status(self, timeout: float = 5) -> MessageStatus:
        """
        检测最后一条自己发的消息的发送状态（自动识别消息类型）。

        从消息列表中倒序查找最后一条自己发的消息，根据其 ClassName 和 Name
        判断消息类型，然后调用对应的状态检测方法。

        适用于发送收藏等无法预知消息类型的场景。

        Args:
            timeout: 轮询超时时间（秒），默认 5 秒

        Returns:
            MessageStatus 发送状态
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return MessageStatus.UNKNOWN

        hwnd = self._win.NativeWindowHandle or 0

        # 收集所有消息控件
        candidates: list[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            candidates.append(ctrl)

        # 倒序查找最后一条自己发的消息
        for ctrl in reversed(candidates):
            sender, sender_type, _ = self._detect_sender(
                hwnd, ctrl, self.current_name or "对方",
            )
            if sender_type != SenderType.SELF:
                continue

            cls = ctrl.ClassName or ""
            name = ctrl.Name

            # 根据 ClassName 和 Name 判断类型并调用对应检测
            if cls == "mmui::ChatTextItemView":
                return self.check_text_message_status(timeout=timeout)
            if cls == "mmui::ChatImageItemView":
                return self.check_image_message_status(timeout=timeout)
            if cls == "mmui::ChatVideoItemView":
                return self.check_video_message_status(timeout=timeout)
            if cls == "mmui::ChatFileItemView":
                return self.check_file_message_status(timeout=timeout)
            if cls == "mmui::ChatEmojiItemView":
                return self.check_emotion_message_status(timeout=timeout)

            # ChatBubbleItemView — 通用气泡
            if cls == "mmui::ChatBubbleItemView":
                if name.startswith("文件\n"):
                    return self.check_file_message_status(timeout=timeout)
                # 其他气泡类型（链接、位置等）无传输状态，直接返回 SENT
                return MessageStatus.SENT

            # ChatBubbleReferItemView — 图片/视频/表情
            if cls == "mmui::ChatBubbleReferItemView":
                if self._IMAGE_NAME_RE.match(name):
                    return self.check_image_message_status(timeout=timeout)
                if self._VIDEO_NAME_RE.match(name):
                    return self.check_video_message_status(timeout=timeout)
                if self._EMOTION_NAME_RE.match(name):
                    return self.check_emotion_message_status(timeout=timeout)
                # 其他 refer 类型
                return self._check_status_by_prefix(name, space_sep=True)

            # 未知类型，用通用前缀检测
            return self._check_status_by_prefix(name, space_sep=True)

        return MessageStatus.UNKNOWN

    def check_text_message_status(
        self, content: str = "", timeout: float = 0, interval: float = 0.5,
    ) -> MessageStatus:
        """
        检测最后一条自己发的文本消息的发送状态。

        content:  发送的消息内容，用于精确匹配。
                  会同时匹配纯内容、"发送失败 "+内容、"发送中 "+内容。
        timeout:  超时时间（秒）。大于 0 时，若状态为 SENDING 会轮询等待，
                  直到状态变为 SENT/FAILED 或超时（超时仍返回当时的状态）。
                  默认 0 表示不等待，立即返回。
        interval: 轮询间隔（秒），默认 0.5。
        """
        deadline = time.monotonic() + timeout if timeout > 0 else 0

        while True:
            ctrl = self._find_last_self_message_ctrl(self._TEXT_CLASS_NAMES)
            if not ctrl:
                status = MessageStatus.UNKNOWN
            else:
                name = ctrl.Name
                if content:
                    expected = {content, f"发送失败 {content}", f"发送中 {content}"}
                    if name not in expected:
                        status = MessageStatus.UNKNOWN
                    else:
                        status = self._check_status_by_prefix(name, space_sep=True)
                else:
                    status = self._check_status_by_prefix(name, space_sep=True)

            # 不需要等待 或 已经有最终状态 → 直接返回
            if not deadline or status != MessageStatus.SENDING:
                return status
            # 超时 → 返回当前状态（SENDING）
            if time.monotonic() >= deadline:
                return status
            time.sleep(interval)

    def check_file_message_status(self, timeout: float = 0, interval: float = 1.0) -> MessageStatus:
        """
        检测最后一条自己发的文件消息的发送状态。

        文件消息的 Name 格式（换行分隔）：
        - 发送中:   "文件\\n进度: 25%\\n{文件名}\\n{来源}"
        - 发送失败: "文件\\n进度: 0%\\n{文件名}\\n发送中断\\n{来源}"
        - 发送成功: "文件\\n{文件名}\\n{来源}" （无"进度"行）

        Args:
            timeout:  超时时间（秒）。大于 0 时，若状态为 SENDING 会轮询等待，
                      直到状态变为 SENT/FAILED 或超时。默认 0 不等待。
            interval: 轮询间隔（秒），默认 1.0。
        """
        deadline = time.monotonic() + timeout if timeout > 0 else 0

        while True:
            ctrl = self._find_last_self_file_ctrl()
            if not ctrl:
                status = MessageStatus.UNKNOWN
            else:
                status = self._check_file_status_by_content(ctrl.Name)

            if not deadline or status != MessageStatus.SENDING:
                return status
            if time.monotonic() >= deadline:
                return status
            time.sleep(interval)

    def _find_last_self_file_ctrl(self) -> Optional[auto.Control]:
        """
        从消息列表中倒序查找最后一条自己发的文件消息控件。

        文件消息可能是 ChatFileItemView（发送完成后）或
        ChatBubbleItemView（传输中/失败时），通过 Name 以 "文件\\n" 开头来区分。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return None

        hwnd = self._win.NativeWindowHandle or 0

        candidates: list[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            cls = ctrl.ClassName or ""
            if cls not in self._FILE_BUBBLE_CLASS_NAMES:
                continue
            # ChatBubbleItemView 是通用气泡，需要通过 Name 过滤文件消息
            if cls == "mmui::ChatBubbleItemView" and not ctrl.Name.startswith("文件\n"):
                continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, sender_type, _ = self._detect_sender(
                hwnd, ctrl, self.current_name or "对方",
            )
            if sender_type == SenderType.SELF:
                return ctrl
        return None

    # 文件消息 Name 正则匹配
    # 发送中:   "文件\n进度: 25%\n{文件名}\n{来源}"
    # 发送失败: "文件\n进度: 0%\n{文件名}\n发送中断\n{来源}"
    # 发送成功: "文件\n{文件名}\n{来源}"
    _FILE_SENDING_RE = re.compile(r"^文件\n进度[:：]\s*\d+%\n.+\n(?!.*发送中断)", re.DOTALL)
    _FILE_FAILED_RE = re.compile(r"^文件\n进度[:：]\s*\d+%\n.+\n发送中断\n", re.DOTALL)
    _FILE_SENT_RE = re.compile(r"^文件\n(?!进度[:：])")

    @staticmethod
    def _check_file_status_by_content(name: str) -> MessageStatus:
        """
        通过正则匹配文件消息 Name 判断发送状态。

        格式：
        - 发送中:   "文件\\n进度: {N}%\\n{文件名}\\n{来源}"
        - 发送失败: "文件\\n进度: 0%\\n{文件名}\\n发送中断\\n{来源}"
        - 发送成功: "文件\\n{文件名}\\n{来源}" （无"进度"行）
        """
        if not name:
            return MessageStatus.UNKNOWN
        if Chat._FILE_FAILED_RE.match(name):
            return MessageStatus.FAILED
        if Chat._FILE_SENDING_RE.match(name):
            return MessageStatus.SENDING
        if Chat._FILE_SENT_RE.match(name):
            return MessageStatus.SENT
        return MessageStatus.UNKNOWN

    def check_image_message_status(self, timeout: float = 0, interval: float = 0.5) -> MessageStatus:
        """
        检测最后一条自己发的图片消息的发送状态。

        图片消息的 Name 格式（空格分隔前缀）：
        - 发送中:   "发送中 图片"
        - 发送失败: "发送失败 图片"
        - 发送成功: "图片"

        ClassName 为 mmui::ChatImageItemView 或 mmui::ChatBubbleReferItemView。

        Args:
            timeout:  超时时间（秒）。大于 0 时，若状态为 SENDING 会轮询等待，
                      直到状态变为 SENT/FAILED 或超时。默认 0 不等待。
            interval: 轮询间隔（秒），默认 0.5。
        """
        deadline = time.monotonic() + timeout if timeout > 0 else 0

        while True:
            ctrl = self._find_last_self_image_ctrl()
            if not ctrl:
                status = MessageStatus.UNKNOWN
            else:
                status = self._check_status_by_prefix(ctrl.Name, space_sep=True)

            if not deadline or status != MessageStatus.SENDING:
                return status
            if time.monotonic() >= deadline:
                return status
            time.sleep(interval)

    # 图片消息 Name 匹配正则（用于从 ChatBubbleReferItemView 中过滤图片消息）
    _IMAGE_NAME_RE = re.compile(r"^(?:发送失败\s+|发送中\s+)?图片$")

    def _find_last_self_image_ctrl(self) -> Optional[auto.Control]:
        """
        从消息列表中倒序查找最后一条自己发的图片消息控件。

        图片消息可能是 ChatImageItemView 或 ChatBubbleReferItemView，
        通过 Name 匹配 "图片" / "发送中 图片" / "发送失败 图片" 来区分。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return None

        hwnd = self._win.NativeWindowHandle or 0

        target_classes = {"mmui::ChatImageItemView", "mmui::ChatBubbleReferItemView"}
        candidates: list[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            cls = ctrl.ClassName or ""
            if cls not in target_classes:
                continue
            # ChatBubbleReferItemView 是通用类型，需要通过 Name 过滤图片消息
            if cls == "mmui::ChatBubbleReferItemView":
                if not self._IMAGE_NAME_RE.match(ctrl.Name):
                    continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, sender_type, _ = self._detect_sender(
                hwnd, ctrl, self.current_name or "对方",
            )
            if sender_type == SenderType.SELF:
                return ctrl
        return None

    def check_emotion_message_status(self, timeout: float = 0, interval: float = 0.5) -> MessageStatus:
        """
        检测最后一条自己发的表情消息的发送状态。

        表情消息的 Name 格式（空格分隔前缀）：
        - 发送中:   "发送中 动画表情" 或 "发送中 动画表情 [xxx]"
        - 发送失败: "发送失败 动画表情" 或 "发送失败 动画表情 [xxx]"
        - 发送成功: "动画表情" 或 "动画表情 [xxx]"

        ClassName 为 mmui::ChatEmojiItemView 或 mmui::ChatBubbleReferItemView。

        Args:
            timeout:  超时时间（秒）。大于 0 时，若状态为 SENDING 会轮询等待，
                      直到状态变为 SENT/FAILED 或超时。默认 0 不等待。
            interval: 轮询间隔（秒），默认 0.5。
        """
        deadline = time.monotonic() + timeout if timeout > 0 else 0

        while True:
            ctrl = self._find_last_self_emotion_ctrl()
            if not ctrl:
                status = MessageStatus.UNKNOWN
            else:
                status = self._check_status_by_prefix(ctrl.Name, space_sep=True)

            if not deadline or status != MessageStatus.SENDING:
                return status
            if time.monotonic() >= deadline:
                return status
            time.sleep(interval)

    # 表情消息 Name 匹配正则（用于从 ChatBubbleReferItemView 中过滤表情消息）
    _EMOTION_NAME_RE = re.compile(r"^(?:发送失败\s+|发送中\s+)?动画表情")

    def _find_last_self_emotion_ctrl(self) -> Optional[auto.Control]:
        """
        从消息列表中倒序查找最后一条自己发的表情消息控件。

        表情消息可能是 ChatEmojiItemView 或 ChatBubbleReferItemView，
        通过 Name 包含 "动画表情" 来区分。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return None

        hwnd = self._win.NativeWindowHandle or 0

        candidates: list[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            cls = ctrl.ClassName or ""
            if cls not in self._EMOTION_CLASS_NAMES:
                continue
            # ChatBubbleReferItemView 是通用类型，需要通过 Name 过滤表情消息
            if cls == "mmui::ChatBubbleReferItemView":
                if not self._EMOTION_NAME_RE.match(ctrl.Name):
                    continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, sender_type, _ = self._detect_sender(
                hwnd, ctrl, self.current_name or "对方",
            )
            if sender_type == SenderType.SELF:
                return ctrl
        return None

    def check_video_message_status(self, timeout: float = 0, interval: float = 1.0) -> MessageStatus:
        """
        检测最后一条自己发的视频消息的发送状态。

        视频消息的 Name 格式（空格分隔）：
        - 发送中:   "视频 进度: {N}%{时长}" 如 "视频 进度: 0%0:02"
        - 发送失败: "视频 上传 暂停{时长}" 如 "视频 上传 暂停0:02"
        - 发送成功: "视频" 或 "视频{时长}" 如 "视频0:02"

        ClassName 为 mmui::ChatBubbleReferItemView。

        Args:
            timeout:  超时时间（秒）。大于 0 时，若状态为 SENDING 会轮询等待，
                      直到状态变为 SENT/FAILED 或超时。默认 0 不等待。
            interval: 轮询间隔（秒），默认 1.0。
        """
        deadline = time.monotonic() + timeout if timeout > 0 else 0

        while True:
            ctrl = self._find_last_self_video_ctrl()
            if not ctrl:
                status = MessageStatus.UNKNOWN
            else:
                status = self._check_video_status_by_content(ctrl.Name)

            if not deadline or status != MessageStatus.SENDING:
                return status
            if time.monotonic() >= deadline:
                return status
            time.sleep(interval)

    def _find_last_self_video_ctrl(self) -> Optional[auto.Control]:
        """
        从消息列表中倒序查找最后一条自己发的视频消息控件。

        视频消息可能是 ChatVideoItemView（发送完成后）或
        ChatBubbleReferItemView（传输中/失败时），通过 Name 以 "视频" 开头来区分。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return None

        hwnd = self._win.NativeWindowHandle or 0

        target_classes = {"mmui::ChatVideoItemView", "mmui::ChatBubbleReferItemView"}
        candidates: list[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            cls = ctrl.ClassName or ""
            if cls not in target_classes:
                continue
            # ChatBubbleReferItemView 是通用类型，需要通过 Name 过滤视频消息
            if cls == "mmui::ChatBubbleReferItemView":
                if not self._VIDEO_NAME_RE.match(ctrl.Name):
                    continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, sender_type, _ = self._detect_sender(
                hwnd, ctrl, self.current_name or "对方",
            )
            if sender_type == SenderType.SELF:
                return ctrl
        return None

    # 视频消息 Name 正则匹配
    # 发送中:   "视频 进度: 0%0:02"
    # 发送失败: "视频 上传 暂停0:02"
    # 发送成功: "视频 0:02" 或 "视频"
    _VIDEO_NAME_RE = re.compile(r"^视频(?:\s|$)")
    _VIDEO_SENDING_RE = re.compile(r"^视频\s+进度[:：]\s*\d+%")
    _VIDEO_FAILED_RE = re.compile(r"^视频\s+上传\s*暂停")
    _VIDEO_SENT_RE = re.compile(r"^视频(?:\s+\d+:\d+)?$")

    @staticmethod
    def _check_video_status_by_content(name: str) -> MessageStatus:
        """
        通过正则匹配视频消息 Name 判断发送状态。

        格式：
        - 发送中:   "视频 进度: {N}%{时长}"
        - 发送失败: "视频 上传 暂停{时长}"
        - 发送成功: "视频" 或 "视频{时长}"
        """
        if not name:
            return MessageStatus.UNKNOWN
        if Chat._VIDEO_FAILED_RE.match(name):
            return MessageStatus.FAILED
        if Chat._VIDEO_SENDING_RE.match(name):
            return MessageStatus.SENDING
        if Chat._VIDEO_SENT_RE.match(name):
            return MessageStatus.SENT
        return MessageStatus.UNKNOWN

    def _get_input_value(self) -> str:
        """读取输入框当前的 Value"""
        field = self._input_field
        if not field.Exists(0, 0):
            return ""
        vp = field.GetValuePattern()
        return vp.Value if vp else ""

    def _get_input_doc_length(self) -> int:
        """通过 TextPattern.DocumentRange.GetText 获取输入框文档长度"""
        field = self._input_field
        if not field.Exists(0, 0):
            return 0
        tp = field.GetTextPattern()
        if not tp:
            return 0
        doc_range = tp.DocumentRange
        if not doc_range:
            return 0
        text = doc_range.GetText(-1)
        return len(text) if text else 0

    @PIM.guard
    def send_text(self, content: str, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送文本消息，返回发送状态。

        Args:
            content: 文本内容
            timeout: 状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待

        前台模式：ValuePattern 设置文本 + 点击发送按钮
        后台模式：ValuePattern 设置文本 + send_keys 回车发送
        """
        self._activate_window()

        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天输入框")

        input_wx.send_keys(field, content)

        send_btn = self._win.ButtonControl(Name="发送")
        input_wx.click(send_btn)

        # 发送后校验：输入框应已清空
        remaining = self._get_input_value()
        if remaining:
            raise SendError(
                f"发送后输入框未清空: Value={remaining!r}，消息可能未发出"
            )

        return self.check_text_message_status(content, timeout=timeout)

    @PIM.guard
    def send_file(self, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送文件，返回最后一个文件的发送状态。

        Args:
            file_path: 文件路径或路径列表，支持本地路径和网络 URL
            timeout:   状态检测超时时间（秒），大于 0 时轮询等待传输完成，默认 0 不等待

        Returns:
            最后一个文件的发送状态
        """
        return self._send_media(file_path, "文件", self.check_file_message_status, timeout)

    @PIM.guard
    def send_image(self, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送图片，返回最后一张图片的发送状态。

        Args:
            file_path: 图片路径或路径列表，支持本地路径和网络 URL
            timeout:   状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待

        Returns:
            最后一张图片的发送状态
        """
        return self._send_media(file_path, "图片", self.check_image_message_status, timeout)

    @PIM.guard
    def send_video(self, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送视频，返回最后一个视频的发送状态。

        Args:
            file_path: 视频路径或路径列表，支持本地路径和网络 URL
            timeout:   状态检测超时时间（秒），大于 0 时轮询等待上传完成，默认 0 不等待

        Returns:
            最后一个视频的发送状态
        """
        return self._send_media(file_path, "视频", self.check_video_message_status, timeout)

    def _send_media(self, file_path: "str | list[str]", label: str,
                    check_status: callable, timeout: float = 0) -> MessageStatus:
        """
        发送文件/图片/视频的通用实现。

        前台模式：通过剪贴板粘贴文件后点击发送按钮。
        后台模式：通过工具栏"发送文件"按钮打开文件选择对话框，
                  逐个填入路径发送，全程不抢焦点。

        Args:
            file_path:    单个路径或路径列表
            label:        类型标签（"文件"/"图片"/"视频"），用于错误提示
            check_status: 发送后的状态检测方法

        Returns:
            发送状态
        """
        self._activate_window()

        paths = [file_path] if isinstance(file_path, str) else list(file_path)
        if not paths:
            raise ValueError(f"{label}路径不能为空")

        # 预处理：下载网络 URL 到临时文件，并转为绝对路径
        local_paths: list[str] = []
        tmp_files: list[str] = []
        for p in paths:
            if _is_url(p):
                tmp = _download_to_temp(p)
                local_paths.append(os.path.abspath(tmp))
                tmp_files.append(tmp)
            else:
                local_paths.append(os.path.abspath(p))

        try:
            self.clear_input()
            field = self._input_field
            if not field.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到聊天输入框")

            if background:
                # 后台模式：复制粘贴文件，失败时重试最多 3 次
                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    self.clear_input()
                    self._win.SetActive()
                    input_wx.paste(local_paths)
                    time.sleep(0.3)

                    doc_len = self._get_input_doc_length()
                    if doc_len > 0:
                        break

                    logger.warning(
                        f"{label}粘贴第 {attempt} 次失败，"
                        f"输入框文档长度为 0"
                    )
                    if attempt < max_retries:
                        time.sleep(0.5)
                else:
                    raise SendError(
                        f"{label}粘贴校验失败: 重试 {max_retries} 次后"
                        f"输入框文档长度仍为 0，{label}可能未粘贴成功"
                    )

                send_btn = self._win.ButtonControl(Name="发送")
                input_wx.click(send_btn)

                remaining_len = self._get_input_doc_length()
                if remaining_len > 0:
                    raise SendError(
                        f"发送后输入框未清空: 文档长度={remaining_len}，{label}可能未发出"
                    )
            else:
                input_wx.paste(local_paths)

                doc_len = self._get_input_doc_length()
                if doc_len == 0:
                    raise SendError(
                        f"{label}粘贴校验失败: 输入框文档长度为 0，{label}可能未粘贴成功"
                    )

                send_btn = self._win.ButtonControl(Name="发送")
                input_wx.click(send_btn)

                remaining_len = self._get_input_doc_length()
                if remaining_len > 0:
                    raise SendError(
                        f"发送后输入框未清空: 文档长度={remaining_len}，{label}可能未发出"
                    )

            return check_status(timeout=timeout)
        finally:
            # 清理临时文件
            for tmp in tmp_files:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

    def _send_file_via_dialog(self, file_path: str) -> None:
        """
        通过工具栏"发送文件"按钮打开文件选择对话框，填入路径并发送。

        全程使用 SendMessage / SetValue，不抢焦点。

        Args:
            file_path: 文件绝对路径
        """
        # 点击工具栏"发送文件"按钮
        toolbar = self._win.ToolBarControl(
            AutomationId="tool_bar_accessible",
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天工具栏")

        file_btn = toolbar.ButtonControl(Name="发送文件")
        if not file_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'发送文件'按钮")
        input_wx.click(file_btn)
        time.sleep(0.5)

        # 等待文件选择对话框弹出（系统 #32770 对话框）
        dlg = auto.WindowControl(ClassName="#32770")
        if not dlg.Exists(maxSearchSeconds=5):
            raise RuntimeError("文件选择对话框未弹出")

        # 填入文件路径
        edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
        if not edit.Exists(0, 0):
            edit = dlg.EditControl(AutomationId="1148")
        if not edit.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到文件名输入框")
        # edit.GetValuePattern().SetValue(file_path)
        input_wx.focus(edit)
        input_wx.send_keys(edit, file_path)
        time.sleep(0.2)

        # 点击"打开"按钮
        open_btn = dlg.ButtonControl(Name="打开(&O)")
        if not open_btn.Exists(maxSearchSeconds=2):
            open_btn = dlg.ButtonControl(Name="Open(&O)")
        if not open_btn.Exists(0, 0):
            open_btn = dlg.ButtonControl(AutomationId="1")
        if not open_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'打开'按钮")
        input_wx.click(open_btn)
        time.sleep(0.5)

    @PIM.guard
    def send_at(self, content: str, at_members: list[str], timeout: float = 0) -> MessageStatus:
        """
        在当前群聊会话中 @指定成员并发送消息，返回发送状态。

        Args:
            content:    消息正文（追加在 @成员 之后）
            at_members: 要 @ 的成员昵称列表，传 ["所有人"] 可 @所有人
            timeout:    状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待
        """
        self.clear_input()
        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天输入框")

        self._add_at_members(field, at_members)

        if content:
            input_wx.send_keys(content)
            time.sleep(0.2)

        send_btn = self._win.ButtonControl(Name="发送")
        input_wx.click(send_btn)

        # 发送后校验：输入框应已清空
        remaining = self._get_input_value()
        if remaining:
            raise SendError(
                f"发送后输入框未清空: Value={remaining!r}，文件可能未发出"
            )

        return self.check_text_message_status(timeout=timeout)

    # ---- 发送收藏相关控件信息 ----
    # 工具栏: ToolBarControl, AutomationId="tool_bar_accessible"
    # 发送收藏按钮: ButtonControl, Name="发送收藏", ClassName="mmui::XButton"
    #   注意: 该按钮嵌套在 GroupControl(mmui::XView) 内
    # 收藏选择面板:
    #   标题: TextControl, ClassName="mmui::XTextView", Name="发送收藏给"{联系人名}""
    #   分类列表: ListControl, ClassName="mmui::StickyHeaderRecyclerListView",
    #             AutomationId="fav_category_list"
    #   收藏详情列表: ListControl, ClassName="mmui::XRecyclerTableView",
    #                 AutomationId="fav_detail_list"
    #     搜索前 Name="全部收藏"，搜索后 Name=搜索关键词
    #     收藏项: ListItemControl, ClassName="mmui::XTableCell"
    #       第一个 ListItem 为空（表头），后续为实际收藏项
    #       Name 格式: "{内容摘要}{日期}" 如 "小程序写诗喂狗2024年5月3日"
    #   搜索框: EditControl, ClassName="mmui::XValidatorTextEdit", Name="搜索"
    #     位于分类列表上方，注意主窗口中可能有多个搜索框，
    #     需通过位置（在收藏面板区域内）区分
    #   发送按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="发送"
    #     选中收藏项后才可用（初始为 disabled）
    #   取消按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="取消"

    FAV_SEND_BTN_NAME = "发送收藏"
    FAV_SEND_BTN_CLASS = "mmui::XButton"
    FAV_DETAIL_LIST_ID = "fav_detail_list"
    FAV_DETAIL_LIST_CLASS = "mmui::XRecyclerTableView"
    FAV_ITEM_CLASS = "mmui::XTableCell"
    FAV_SEARCH_CLASS = "mmui::XValidatorTextEdit"
    FAV_SEARCH_NAME = "搜索"
    FAV_SEND_CONFIRM_NAME = "发送"
    FAV_SEND_CONFIRM_CLASS = "mmui::XOutlineButton"
    FAV_CANCEL_NAME = "取消"
    FAV_CANCEL_CLASS = "mmui::XOutlineButton"

    def _open_collection_panel(self) -> auto.ListControl:
        """
        打开收藏选择面板。

        点击工具栏中的"发送收藏"按钮，弹出收藏选择面板。
        如果面板已打开则直接返回。

        Returns:
            收藏详情列表控件 (fav_detail_list)

        Raises:
            RuntimeError: 未找到工具栏或按钮时抛出
        """
        # 检查面板是否已打开
        detail_list = self._win.ListControl(
            ClassName=self.FAV_DETAIL_LIST_CLASS,
            AutomationId=self.FAV_DETAIL_LIST_ID,
        )
        if detail_list.Exists(maxSearchSeconds=0.5):
            return detail_list

        # 查找工具栏
        toolbar = self._win.ToolBarControl(
            AutomationId="tool_bar_accessible",
            searchDepth=16,
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天工具栏")

        # 查找"发送收藏"按钮（嵌套在 GroupControl 内）
        fav_btn = toolbar.ButtonControl(
            ClassName=self.FAV_SEND_BTN_CLASS,
            Name=self.FAV_SEND_BTN_NAME,
            searchDepth=5,
        )
        if not fav_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'发送收藏'按钮")

        input_wx.click(fav_btn)

        # 等待收藏面板出现
        if not detail_list.Exists(maxSearchSeconds=5):
            raise RuntimeError("收藏选择面板未打开")

        return detail_list

    def _close_collection_panel(self) -> None:
        """
        关闭收藏选择面板。

        点击面板中的"取消"按钮关闭面板。
        """
        cancel_btn = self._win.ButtonControl(
            ClassName=self.FAV_CANCEL_CLASS,
            Name=self.FAV_CANCEL_NAME,
        )
        if cancel_btn.Exists(maxSearchSeconds=1):
            input_wx.click(cancel_btn)
            time.sleep(0.3)

    def _find_fav_search_edit(self) -> auto.EditControl:
        """
        在收藏面板中查找搜索框。

        注意: 主窗口中可能存在多个 Name="搜索" 的 EditControl，
        需要通过收藏面板区域来定位正确的搜索框。
        收藏面板的搜索框位于分类列表上方区域。

        搜索框: EditControl, ClassName="mmui::XValidatorTextEdit", Name="搜索"
        """
        # 遍历所有搜索框，找到位于收藏面板区域内的那个
        # 收藏面板的搜索框通常是第一个匹配的（位于面板标题下方）
        detail_list = self._win.ListControl(
            ClassName=self.FAV_DETAIL_LIST_CLASS,
            AutomationId=self.FAV_DETAIL_LIST_ID,
        )
        if not detail_list.Exists(0, 0):
            raise RuntimeError("收藏面板未打开，无法查找搜索框")

        detail_rect = detail_list.BoundingRectangle

        # 查找所有搜索框
        edit = self._win.EditControl(
            ClassName=self.FAV_SEARCH_CLASS,
            Name=self.FAV_SEARCH_NAME,
        )
        # 第一个搜索框通常就是收藏面板内的
        # 通过检查其位置是否在收藏面板区域附近来确认
        if edit.Exists(maxSearchSeconds=2):
            edit_rect = edit.BoundingRectangle
            # 搜索框应该在详情列表的左侧或上方区域
            if edit_rect.top >= detail_rect.top - 100 and edit_rect.left < detail_rect.left:
                return edit

        raise RuntimeError("未找到收藏面板搜索框")

    def _find_collection_item(self, detail_list, keyword) -> Optional[auto.ListItemControl]:
        """
        在收藏详情列表中查找第一个有效的搜索结果项。

        遍历 fav_detail_list 中的 ListItemControl，
        跳过第一个空的表头项，返回第一个有 Name 的结果项。

        Args:
            detail_list: 收藏详情列表控件

        Returns:
            匹配的 ListItemControl，未找到返回 None
        """
        for ctrl, _ in auto.WalkControl(detail_list):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            cls_name = ctrl.ClassName or ""
            if cls_name != self.FAV_ITEM_CLASS:
                continue
            # 返回第一个有 Name 的搜索结果
            return ctrl
        return None

    @PIM.guard
    def send_collection(self, keyword: str, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送收藏内容。

        流程:
        1. 点击工具栏"发送收藏"按钮，打开收藏选择面板
        2. 在收藏面板的搜索框中输入 keyword
        3. 等待搜索结果出现在右侧详情列表中
        4. 选中第一个搜索结果
        5. 点击"发送"按钮发送

        Args:
            keyword: 搜索关键词，输入到收藏面板的搜索框中。
            timeout: 状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待

        Returns:
            MessageStatus 发送状态

        Raises:
            ValueError: keyword 为空时抛出
            RuntimeError: 未找到匹配的收藏项或发送失败时抛出
        """
        if not keyword:
            raise ValueError("keyword 不能为空")

        self._activate_window()

        # 1. 打开收藏选择面板
        self._open_collection_panel()

        # 2. 在搜索框中输入关键词
        search_edit = self._find_fav_search_edit()
        input_wx.click(search_edit)
        input_wx.send_keys(search_edit, keyword)

        # 3. 获取搜索后的详情列表
        detail_list = self._win.ListControl(
            ClassName=self.FAV_DETAIL_LIST_CLASS,
            AutomationId=self.FAV_DETAIL_LIST_ID,
        )
        if not detail_list.Exists(maxSearchSeconds=3):
            self._close_collection_panel()
            raise RuntimeError("搜索后未找到收藏详情列表")

        # 4. 选中第一个搜索结果
        matched_item = self._find_collection_item(detail_list, keyword)
        if not matched_item:
            self._close_collection_panel()
            raise RuntimeError(f"未找到匹配的收藏项: {keyword}")
        input_wx.click(matched_item)

        # 5. 点击"发送"按钮
        send_btn = self._win.ButtonControl(
            ClassName=self.FAV_SEND_CONFIRM_CLASS,
            Name=self.FAV_SEND_CONFIRM_NAME,
        )
        if not send_btn.Exists(maxSearchSeconds=2):
            self._close_collection_panel()
            raise RuntimeError("未找到'发送'按钮")

        # 等待按钮变为可用
        for _ in range(10):
            if send_btn.IsEnabled:
                break
            time.sleep(0.3)
        else:
            self._close_collection_panel()
            raise RuntimeError("'发送'按钮未启用，可能收藏项未正确选中")

        input_wx.click(send_btn)

        time.sleep(0.1)

        # 6. 验证面板已关闭（表示发送成功）
        check_list = self._win.ListControl(
            ClassName=self.FAV_DETAIL_LIST_CLASS,
            AutomationId=self.FAV_DETAIL_LIST_ID,
        )
        if check_list.Exists(maxSearchSeconds=1):
            raise SendError("发送收藏失败，选择面板未关闭")

        logger.info("收藏发送成功")
        return self._check_last_message_status(timeout=timeout)

    # -- 发送表情 --
    # 表情按钮: ButtonControl, Name="发送表情(Alt+E)", ClassName="mmui::XButton"
    #   位于工具栏 tool_bar_accessible 内
    # 表情面板: 独立弹窗 WindowControl, ClassName="mmui::XPopover",
    #           AutomationId="EmoticonPopover"
    #   面板工具栏: TabControl, AutomationId="emoticon_panel_tool_bar"
    #     搜索表情: TabItemControl, Name="搜索表情", ClassName="mmui::EmoticonToolbarItem"
    #     默认表情: TabItemControl, Name="默认表情", ClassName="mmui::EmoticonToolbarItem"
    #     自定义表情: TabItemControl, Name="自定义表情", ClassName="mmui::EmoticonToolbarItem"
    #   搜索页面: GroupControl, ClassName="mmui::SearchPageView"
    #     搜索框容器: GroupControl, ClassName="mmui::XSearchField"
    #     搜索输入框: EditControl, Name="搜索", ClassName="mmui::XValidatorTextEdit"
    #   搜索结果区: DocumentControl, Name="表情搜索",
    #               ClassName="Chrome_RenderWidgetHostHWND"
    #     搜索结果为 Chromium 内嵌网页渲染，表情项为 ListItemControl，
    #     Name 格式: "{关键词}表情，来自{来源}"，支持 InvokePattern 直接点击发送。

    EMOJI_BTN_NAME = "发送表情(Alt+E)"
    EMOJI_BTN_CLASS = "mmui::XButton"
    EMOJI_POPOVER_CLASS = "mmui::XPopover"
    EMOJI_POPOVER_ID = "EmoticonPopover"
    EMOJI_PANEL_TOOLBAR_ID = "emoticon_panel_tool_bar"
    EMOJI_SEARCH_TAB_NAME = "搜索表情"
    EMOJI_SEARCH_TAB_CLASS = "mmui::EmoticonToolbarItem"
    EMOJI_SEARCH_INPUT_NAME = "搜索"
    EMOJI_SEARCH_INPUT_CLASS = "mmui::XValidatorTextEdit"
    EMOJI_SEARCH_FIELD_CLASS = "mmui::XSearchField"
    EMOJI_SEARCH_RESULT_CLASS = "Chrome_RenderWidgetHostHWND"
    EMOJI_SEARCH_RESULT_NAME = "表情搜索"
    EMOJI_CUSTOM_TAB_NAME = "自定义表情"
    EMOJI_CUSTOM_TAB_CLASS = "mmui::EmoticonToolbarItem"
    EMOJI_CUSTOM_GRID_CLASS = "mmui::EmoticonGridView"
    EMOJI_CUSTOM_ITEM_CLASS = "mmui::FavEmoticonItemView"

    @PIM.guard
    def send_emotion(self, keyword: str = None, index: int = 1, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送表情。

        当 keyword 不为 None 时，通过搜索关键词发送表情；
        当 keyword 为 None 时，发送自定义表情列表中第 index 个表情。

        Args:
            keyword: 表情搜索关键词，如 "哈喽"、"开心" 等。
                为 None 时发送自定义表情。
            index:   选择第几个表情，从 1 开始，默认为 1。
            timeout: 状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待

        Returns:
            MessageStatus 发送状态

        Raises:
            ValueError: index < 1 时抛出
            RuntimeError: 未找到控件或发送失败时抛出
        """
        if index < 1:
            raise ValueError("index 必须 >= 1")

        self._activate_window()

        try:
            # 1. 打开表情面板
            self._open_emoji_panel()

            popover = self._get_emoji_popover()

            if keyword is not None:
                # 搜索表情模式
                # 2. 点击"搜索表情"标签
                self._click_emoji_search_tab(popover)

                # 3. 在搜索框中输入关键词
                search_edit = self._find_emoji_search_edit(popover)
                input_wx.click(search_edit)

                # 清空已有内容后键盘输入，确保触发搜索
                input_wx.send_keys(search_edit, "{Ctrl}a")
                input_wx.send_keys(search_edit, keyword)
                time.sleep(1.5)  # 等待搜索结果加载（Chromium 渲染）

                # 4. 在搜索结果中点击第 index 个表情
                popover = self._get_emoji_popover()
                self._click_emoji_search_result(popover, index)
            else:
                # 自定义表情模式
                # 2. 点击"自定义表情"标签
                self._click_custom_emoji_tab(popover)

                # 3. 在自定义表情列表中点击第 index 个表情
                popover = self._get_emoji_popover()
                self._click_custom_emoji_item(popover, index)

            # 验证表情面板已关闭（表示发送成功）
            emoji_popover = auto.WindowControl(
                ClassName=self.EMOJI_POPOVER_CLASS,
                AutomationId=self.EMOJI_POPOVER_ID,
                searchDepth=1
            )
            if emoji_popover.Exists(maxSearchSeconds=1):
                self._close_emoji_panel()
                label = "自定义表情" if keyword is None else "表情"
                raise SendError(f"发送{label}失败，表情面板未关闭")

            logger.info("表情发送成功")
            return self.check_emotion_message_status(timeout=timeout)

        except Exception:
            self._close_emoji_panel()
            raise

    def _get_emoji_popover(self) -> auto.WindowControl:
        """
        获取表情弹窗（独立窗口 mmui::XPopover）。
        """
        popover = auto.WindowControl(
            ClassName=self.EMOJI_POPOVER_CLASS,
            AutomationId=self.EMOJI_POPOVER_ID,
            searchDepth=1
        )
        if not popover.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到表情弹窗")
        return popover

    def _open_emoji_panel(self) -> None:
        """
        打开表情选择面板。

        点击工具栏中的"发送表情"按钮。
        如果面板已打开则直接返回。
        """
        # 检查面板是否已打开（表情弹窗是独立窗口）
        emoji_popover = auto.WindowControl(
            ClassName=self.EMOJI_POPOVER_CLASS,
            AutomationId=self.EMOJI_POPOVER_ID,
            searchDepth=1
        )
        if emoji_popover.Exists(maxSearchSeconds=0.5):
            return

        # 查找工具栏
        toolbar = self._win.ToolBarControl(
            AutomationId="tool_bar_accessible",
            searchDepth=16
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天工具栏")

        # 查找"发送表情"按钮
        emoji_btn = toolbar.ButtonControl(
            ClassName=self.EMOJI_BTN_CLASS,
            Name=self.EMOJI_BTN_NAME,
            searchDepth=5,
        )
        if not emoji_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'发送表情'按钮")

        input_wx.click(emoji_btn)

        # 等待表情弹窗出现
        if not emoji_popover.Exists(maxSearchSeconds=5):
            raise RuntimeError("表情选择面板未打开")

    def _close_emoji_panel(self) -> None:
        """
        关闭表情面板。

        通过按 Escape 键关闭面板。
        """
        try:
            emoji_popover = auto.WindowControl(
                ClassName=self.EMOJI_POPOVER_CLASS,
                AutomationId=self.EMOJI_POPOVER_ID,
            )
            if emoji_popover.Exists(maxSearchSeconds=0.5):
                input_wx.send_keys(emoji_popover, "{Esc}")
                time.sleep(0.3)
        except Exception:
            # 兜底：向主窗口发送 Esc
            input_wx.send_keys(self._win, "{Esc}")
            time.sleep(0.3)

    def _click_emoji_search_tab(self, popover: auto.WindowControl) -> None:
        """
        在表情面板工具栏中点击"搜索表情"标签。
        """
        panel_toolbar = popover.TabControl(
            AutomationId=self.EMOJI_PANEL_TOOLBAR_ID,
        )
        if not panel_toolbar.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到表情面板工具栏")

        search_tab = panel_toolbar.TabItemControl(
            ClassName=self.EMOJI_SEARCH_TAB_CLASS,
            Name=self.EMOJI_SEARCH_TAB_NAME,
        )
        if not search_tab.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'搜索表情'标签")

        input_wx.click(search_tab)

    def _find_emoji_search_edit(
        self, popover: auto.WindowControl,
    ) -> auto.EditControl:
        """
        在表情搜索面板中查找搜索输入框。

        搜索输入框位于 mmui::XSearchField 容器内。
        """
        search_field = popover.GroupControl(
            ClassName=self.EMOJI_SEARCH_FIELD_CLASS,
        )
        if search_field.Exists(maxSearchSeconds=3):
            edit = search_field.EditControl(
                ClassName=self.EMOJI_SEARCH_INPUT_CLASS,
                Name=self.EMOJI_SEARCH_INPUT_NAME,
            )
            if edit.Exists(maxSearchSeconds=2):
                return edit

        raise RuntimeError("未找到表情搜索输入框")

    def _click_emoji_search_result(
        self, popover: auto.WindowControl, index: int,
    ) -> None:
        """
        在表情搜索结果中点击第 index 个表情（从 1 开始）。

        搜索结果在 Chrome_RenderWidgetHostHWND 内渲染，
        表情项为 ListItemControl，Name 格式: "{关键词}表情，来自{来源}"，
        支持 InvokePattern 直接点击发送。
        """
        result_doc = popover.DocumentControl(
            ClassName=self.EMOJI_SEARCH_RESULT_CLASS,
            Name=self.EMOJI_SEARCH_RESULT_NAME,
        )
        if not result_doc.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到表情搜索结果区域")

        # 收集所有 ListItemControl（即表情项）
        items = result_doc.GetChildren()
        emotion_items = []
        for i, child in enumerate(items):
            if i == 0:
                if not child.Exists(maxSearchSeconds=10):
                    raise RuntimeError("未找到任何表情")
            self._collect_emotion_items(child, emotion_items)

        if not emotion_items:
            raise RuntimeError("搜索结果为空，未找到任何表情")

        if index > len(emotion_items):
            raise RuntimeError(
                f"第 {index} 个表情不存在，"
                f"搜索结果共 {len(emotion_items)} 个表情"
            )

        target = emotion_items[index - 1]
        try:
            target.GetInvokePattern().Invoke()
        except Exception:
            # InvokePattern 失败时回退到坐标点击
            rect = target.BoundingRectangle
            if rect.width() > 0 and rect.height() > 0:
                auto.Click(
                    int(rect.left + rect.width() / 2),
                    int(rect.top + rect.height() / 2),
                )
            else:
                raise RuntimeError(
                    f"第 {index} 个表情不可见（offscreen），无法点击"
                )

    def _collect_emotion_items(self, control, result: list) -> None:
        """递归收集 ListItemControl 表情项。"""
        if control.ControlType == auto.ControlType.ListItemControl:
            name = control.Name or ""
            if "表情" in name:
                result.append(control)
                return
        for child in control.GetChildren():
            self._collect_emotion_items(child, result)

    def _click_custom_emoji_tab(self, popover: auto.WindowControl) -> None:
        """
        在表情面板工具栏中点击"自定义表情"标签。
        """
        panel_toolbar = popover.TabControl(
            AutomationId=self.EMOJI_PANEL_TOOLBAR_ID,
        )
        if not panel_toolbar.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到表情面板工具栏")

        custom_tab = panel_toolbar.TabItemControl(
            ClassName=self.EMOJI_CUSTOM_TAB_CLASS,
            Name=self.EMOJI_CUSTOM_TAB_NAME,
        )
        if not custom_tab.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'自定义表情'标签")
        input_wx.click(custom_tab)

    def _click_custom_emoji_item(
        self, popover: auto.WindowControl, index: int,
    ) -> None:
        """
        在自定义表情列表中点击第 index 个表情（从 1 开始）。

        自定义表情项为 mmui::FavEmoticonItemView（TextControl），
        位于 mmui::EmoticonGridView（ListControl）内，
        支持 InvokePattern 直接点击发送。
        """
        grid = popover.ListControl(
            ClassName=self.EMOJI_CUSTOM_GRID_CLASS,
        )
        if not grid.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到自定义表情列表")

        items = grid.GetChildren()
        emoji_items = [
            item for item in items
            if item.ClassName == self.EMOJI_CUSTOM_ITEM_CLASS
        ]

        if not emoji_items:
            raise RuntimeError("自定义表情列表为空")

        if index > len(emoji_items):
            raise RuntimeError(
                f"第 {index} 个自定义表情不存在，"
                f"共 {len(emoji_items)} 个自定义表情"
            )
        input_wx.click(emoji_items[index - 1])

    # -- 发送名片 --
    # 聊天信息按钮: ButtonControl, Name="聊天信息", ClassName="mmui::XButton",
    #   AutomationId 末尾为 "more_button"
    # 联系人头像: ButtonControl, ClassName="mmui::ChatMemberCell",
    #   AutomationId="single_chat_member_cell"
    # 资料面板更多: ButtonControl, Name="更多", ClassName="mmui::XButton"
    # 推荐菜单项: MenuItemControl, Name="把他推荐给朋友",
    #   ClassName="mmui::XMenuView", AutomationId="XMenuItem"
    # 发送给弹窗: WindowControl, Name="微信发送给",
    #   ClassName="mmui::SessionPickerWindow"
    # 弹窗搜索框: EditControl, Name="搜索",
    #   ClassName="mmui::XValidatorTextEdit"
    # 搜索结果列表: ListControl, AutomationId="sp_search_result_list"
    # 搜索结果项: CheckBoxControl, ClassName="mmui::SearchContactCellView"
    # 发送按钮: ButtonControl, AutomationId="confirm_btn", Name="发送"
    # 取消按钮: ButtonControl, AutomationId="cancel_btn", Name="取消"

    @PIM.guard
    def send_card(self, receiver_nickname: str) -> bool:
        """
        将当前私聊联系人的名片发送给指定接收者。

        流程:
        1. 点击聊天标题栏右上角"聊天信息"按钮，打开聊天信息面板
        2. 点击联系人头像，打开资料面板
        3. 点击资料面板右上角"更多"按钮
        4. 在弹出菜单中点击"把他推荐给朋友"
        5. 在"微信发送给"弹窗中搜索并勾选接收者
        6. 点击"发送"按钮

        Args:
            receiver_nickname: 接收名片的联系人昵称

        Returns:
            True 发送成功

        Raises:
            ValueError: receiver_nickname 为空时抛出
            RuntimeError: 当前非私聊、控件未找到或发送失败时抛出
        """
        if not receiver_nickname:
            raise ValueError("receiver_nickname 不能为空")

        if self.chat_type != "私聊":
            raise RuntimeError("发送名片仅支持私聊会话")

        contact_name = self.current_name
        if not contact_name:
            raise RuntimeError("无法获取当前聊天联系人名称")

        self._activate_window()

        try:
            # 1. 点击"聊天信息"按钮
            self._click_chat_info_button()
            time.sleep(0.5)

            # 2. 点击联系人头像
            self._click_contact_avatar()
            time.sleep(0.5)

            # 3. 点击资料面板"更多"按钮
            self._click_profile_more_button()
            time.sleep(0.3)

            # 4. 点击"把他推荐给朋友"
            self._click_recommend_contact()
            time.sleep(0.5)

            # 5. 在弹窗中搜索、勾选接收者并点击发送
            self._search_and_select_receiver(receiver_nickname)

            logger.info(f"名片发送成功: {contact_name} -> {receiver_nickname}")
            return True
        except Exception:
            # 出错时尝试关闭可能残留的弹窗
            self._cleanup_send_card()
            raise

    def _click_chat_info_button(self) -> None:
        """点击聊天标题栏右上角的"聊天信息"按钮"""
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name="聊天信息",
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'聊天信息'按钮")
        input_wx.click(btn)

    def _click_contact_avatar(self) -> None:
        """点击聊天信息面板中的联系人头像"""
        avatar = self._win.ButtonControl(
            ClassName="mmui::ChatMemberCell",
            AutomationId="single_chat_member_cell",
        )
        if not avatar.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到联系人头像")
        input_wx.click(avatar)

    def _click_profile_more_button(self) -> None:
        """点击资料面板右上角的"更多"按钮（排除导航栏的同名按钮）"""
        # 资料面板的"更多"按钮 ClassName 为 mmui::XButton，
        # 位于窗口右侧区域；导航栏的同名按钮位于左下角。
        # 通过坐标位置区分。
        win_rect = self._win.BoundingRectangle
        win_center_x = (win_rect.left + win_rect.right) // 2

        for child, _ in auto.WalkControl(self._win, maxDepth=20):
            if (child.ControlType == auto.ControlType.ButtonControl
                    and child.ClassName == "mmui::XButton"
                    and child.Name == "更多"):
                child_rect = child.BoundingRectangle
                if child_rect.left > win_center_x:
                    input_wx.click(child)
                    return

        raise RuntimeError("未找到资料面板'更多'按钮")

    def _click_recommend_contact(self) -> None:
        """点击弹出菜单中的"把他推荐给朋友" """
        menu_item = self._win.MenuItemControl(
            ClassName="mmui::XMenuView",
            Name="把他推荐给朋友",
        )
        if not menu_item.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'把他推荐给朋友'菜单项")
        input_wx.click(menu_item)

    def _search_and_select_receiver(self, receiver_nickname: str) -> None:
        """在"微信发送给"弹窗中搜索并勾选接收者"""
        # SessionPickerWindow 是微信主窗口的子控件，从 self._win 查找
        picker_win = self._win.WindowControl(
            ClassName="mmui::SessionPickerWindow",
        )
        if not picker_win.Exists(maxSearchSeconds=3):
            raise RuntimeError("'微信发送给'弹窗未打开")

        # 定位搜索框
        search_field = picker_win.GroupControl(
            ClassName="mmui::XSearchField",
        )
        if not search_field.Exists(maxSearchSeconds=2):
            raise RuntimeError("弹窗中未找到搜索区域")

        search_edit = search_field.EditControl(
            ClassName="mmui::XValidatorTextEdit", Name="搜索",
        )
        if not search_edit.Exists(maxSearchSeconds=2):
            raise RuntimeError("弹窗中未找到搜索框")

        # 输入接收者昵称（通过剪贴板粘贴，确保触发搜索）
        input_wx.click(search_edit)
        time.sleep(0.3)
        input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
        time.sleep(0.2)
        input_wx.paste(receiver_nickname)
        time.sleep(1.5)

        # 重新获取 picker_win，避免控件缓存问题
        fresh_picker = auto.WindowControl(
            ClassName="mmui::SessionPickerWindow",
        )
        if not fresh_picker.Exists(maxSearchSeconds=3):
            raise RuntimeError("'微信发送给'弹窗已关闭")

        # 在搜索结果列表中查找并勾选接收者
        result_list = fresh_picker.ListControl(
            ClassName="mmui::XTableView",
            AutomationId="sp_search_result_list",
        )
        if not result_list.Exists(maxSearchSeconds=5):
            raise RuntimeError(f"搜索 '{receiver_nickname}' 后未出现结果列表")

        contact_row = result_list.CheckBoxControl(
            ClassName="mmui::SearchContactCellView",
        )
        if not contact_row.Exists(maxSearchSeconds=3):
            raise RuntimeError(f"搜索结果中未找到联系人: {receiver_nickname}")

        # 关键：在选中联系人之前先获取发送按钮引用，
        # 因为选中后 SPDetailView 面板会刷新重建，旧控件引用会失效，
        # 此时面板尚未刷新，控件树是稳定的，可以可靠地找到按钮。
        send_btn = fresh_picker.ButtonControl(
            AutomationId="confirm_btn",
        )
        if not send_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'发送'按钮")

        # 移动鼠标到搜索结果上，再按空格键选中
        input_wx.click(contact_row)

        # 选中后等待面板刷新完成，再点击之前预获取的发送按钮
        # 等待按钮变为可用
        for _ in range(10):
            try:
                if send_btn.IsEnabled:
                    break
            except Exception:
                pass
            time.sleep(0.3)
        else:
            raise RuntimeError("'发送'按钮未启用，可能接收者未正确选中")

        input_wx.click(send_btn)
        time.sleep(0.5)

    def _cleanup_send_card(self) -> None:
        """清理 send_card 过程中可能残留的弹窗和面板"""
        try:
            picker_win = self._win.WindowControl(
                ClassName="mmui::SessionPickerWindow",
            )
            if picker_win.Exists(maxSearchSeconds=0.5):
                cancel_btn = picker_win.ButtonControl(
                    AutomationId="cancel_btn",
                )
                if cancel_btn.Exists(maxSearchSeconds=0.5):
                    input_wx.click(cancel_btn)
                    time.sleep(0.3)
        except Exception:
            pass

        try:
            input_wx.send_keys(self._win, "{Esc}")
            time.sleep(0.2)
            input_wx.send_keys(self._win, "{Esc}")
            time.sleep(0.2)
        except Exception:
            pass

    def _add_at_members(self, chat_input: auto.EditControl,
                        at_members: list[str]) -> None:
        """
        在输入框中 @指定群成员。

        @菜单控件:
        - ListControl, AutomationId="chat_mention_list", searchDepth=4
        - 菜单项: ListItemControl, Name 为成员昵称

        支持完全匹配和模糊匹配，包含 "所有人" 时只 @所有人。
        """
        if not at_members:
            return
        if "所有人" in at_members:
            at_members = ["所有人"]

        for member in at_members:
            if not member:
                continue
            if not chat_input.HasKeyboardFocus:
                input_wx.click(chat_input)

            if member == "所有人":
                input_wx.send_keys(chat_input, "@")
            else:
                input_wx.send_keys(chat_input, f"@{member}")

            menu = self._win.ListControl(
                AutomationId="chat_mention_list", searchDepth=4,
            )
            if not menu.Exists(maxSearchSeconds=2):
                raise RuntimeError(f"@群成员失败，未找到: {member}")

            controls = []
            for ctrl, _ in auto.WalkControl(menu):
                if (ctrl.ControlType == auto.ControlType.ListItemControl
                        and ctrl.Name):
                    controls.append(ctrl)

            full = [c for c in controls if c.Name == member]
            fuzzy = [c for c in controls if member in c.Name]

            if full or len(fuzzy) == 1:
                input_wx.send_keys(None, "{Enter}")
            elif len(fuzzy) > 1:
                names = [c.Name for c in fuzzy]
                raise RuntimeError(f"@群成员模糊匹配到多个: {names}")
            else:
                raise RuntimeError(f"@群成员失败，未找到: {member}")

    def _click_voip_menu(self, menu_name: str) -> None:
        """
        点击通话按钮弹出菜单，再选择指定项。

        通话按钮: ButtonControl, AutomationId="voip_button"
        弹出菜单: WindowControl, ClassName="mmui::XMenu"
        菜单项:   MenuItemControl, ClassName="mmui::XMenuView",
                  AutomationId="XMenuItem", Name="语音通话"/"视频通话"
        """
        btn = self._win.ButtonControl(AutomationId="voip_button")
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到通话按钮")
        input_wx.click(btn)
        time.sleep(0.3)

        menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
        if not menu_win.Exists(maxSearchSeconds=2):
            raise RuntimeError("通话菜单未弹出")
        item = menu_win.MenuItemControl(
            ClassName="mmui::XMenuView",
            AutomationId="XMenuItem",
            Name=menu_name,
        )
        if not item.Exists(maxSearchSeconds=1):
            input_wx.send_keys(self._win, "{Esc}")
            raise RuntimeError(f"通话菜单中未找到: {menu_name}")
        input_wx.click(item)
        time.sleep(0.3)

    @PIM.guard
    def voice_call(self) -> "VoipCallWindow":
        self._click_voip_menu("语音通话")
        return VoipCallWindow()

    @PIM.guard
    def video_call(self) -> "VoipCallWindow":
        self._click_voip_menu("视频通话")
        return VoipCallWindow()

    @PIM.guard
    def separate(self) -> "SeparateChat":
        """
        将当前聊天会话打开为独立窗口，返回 SeparateChat 实例。

        通过双击会话列表中的对应 SessionItem 打开独立窗口。
        等待独立窗口出现后返回 SeparateChat 对象。
        """
        self._activate_window()
        
        contact_name = self.current_name
        if not contact_name:
            raise RuntimeError("无法获取当前聊天对象名称")

        # 在会话列表中找到对应的 SessionItem 并双击
        item = self._win.ListItemControl(
            ClassName="mmui::ChatSessionCell",
            AutomationId=f"session_item_{contact_name}",
        )
        
        if not item.Exists(maxSearchSeconds=2):
            raise RuntimeError(f"会话列表中未找到: {contact_name}")
        
        input_wx.click(item, click="double")
        time.sleep(0.5)

        # 等待独立窗口出现并返回
        try:
            return SeparateChat(self.wx, contact_name)
        except RuntimeError:
            raise RuntimeError(f"独立窗口未成功打开: {contact_name}")

    @property
    def _message_list(self) -> auto.ListControl:
        return self._win.ListControl(
            ClassName="mmui::RecyclerListView",
            AutomationId="chat_message_list",
        )

    def get_visible_messages(self, sender_cache: dict[tuple, tuple] = None) -> list[Message]:
        """
        获取当前可见的消息列表，返回具体消息子类实例。

        消息项为 ListItemControl，通过 ClassName 区分类型，
        通过头像控件位置判断 SenderType。
        每条消息携带 runtime_id（UI Automation RuntimeId），
        作为控件的唯一标识，用于消息监听时的精确去重。

        Args:
            sender_cache: 可选的发送者缓存字典，格式为
                {runtime_id: (sender, sender_type)}。
                传入后，已缓存的消息跳过截图检测直接使用缓存结果，
                新消息检测后自动写入缓存。
                用于监听场景下避免对已知消息重复截图导致窗口闪烁。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return []

        # 获取窗口句柄，用于 PrintWindow 截图
        hwnd = self._win.NativeWindowHandle or 0

        # ClassName -> 消息子类映射
        cls_map: dict[str, type[Message]] = {
            "mmui::ChatTextItemView": TextMessage,
            "mmui::ChatImageItemView": ImageMessage,
            "mmui::ChatFileItemView": FileMessage,
            "mmui::ChatVoiceItemView": VoiceMessage,
            "mmui::ChatVideoItemView": VideoMessage,
            "mmui::ChatPersonalCardItemView": PersonalCardMessage,
            "mmui::ChatBubbleReferItemView": QuoteMessage,
            "mmui::ChatEmojiItemView": EmotionMessage,
            "mmui::ChatMusicItemView": MusicMessage,
            "mmui::ChatMiniProgramItemView": LinkMessage,
            "mmui::ChatItemView": SystemMessage,
        }

        chat_name = self.current_name or "对方"

        messages: list[Message] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue

            ui_cls = ctrl.ClassName or ""
            raw_name = ctrl.Name or ""

            # Name 为空时，仅允许已知的非文本类型通过（如图片、视频等 Name 可能为空）
            if not raw_name and ui_cls not in cls_map:
                continue

            # 提取 RuntimeId 作为控件唯一标识
            try:
                rid = tuple(ctrl.GetRuntimeId())
            except Exception:
                rid = ()

            msg_cls = cls_map.get(ui_cls)

            # 引用消息优先级最高：任何类型的 Name 包含"引用 xxx 的消息"都识别为引用消息
            if QuoteMessage.match(raw_name):
                msg_cls = QuoteMessage
            # ChatBubbleItemView 是通用气泡，需要二次分类
            elif ui_cls == "mmui::ChatBubbleItemView":
                msg_cls = self._classify_bubble(raw_name)
            # ChatBubbleReferItemView 复用于引用消息、图片、视频、动画表情
            elif ui_cls == "mmui::ChatBubbleReferItemView":
                msg_cls = self._classify_bubble_refer(raw_name)

            if msg_cls is None:
                msg_cls = OtherMessage

            # 系统消息
            if msg_cls is SystemMessage:
                sys_msg = SystemMessage(
                    content=raw_name,
                    timestamp=raw_name,
                    raw_name=raw_name,
                    runtime_id=rid,
                )
                sys_msg.chat = self
                messages.append(sys_msg)
                continue

            # 判断发送者：优先从缓存读取，避免重复截图
            if sender_cache is not None and rid and rid in sender_cache:
                sender, sender_type, bubble_rect = sender_cache[rid]
            else:
                sender, sender_type, bubble_rect = self._detect_sender(
                    hwnd, ctrl, chat_name,
                )
                # 写入缓存
                if sender_cache is not None and rid:
                    sender_cache[rid] = (sender, sender_type, bubble_rect)

            # 构造具体消息对象
            msg = self._build_message(msg_cls, raw_name, sender, sender_type,
                                      runtime_id=rid)
            msg.bubble_rect = bubble_rect
            msg.chat = self
            messages.append(msg)
        return messages

    @staticmethod
    def _classify_bubble(name: str) -> type[Message]:
        """
        对 mmui::ChatBubbleItemView 通用气泡做二次分类。
        """
        if name.startswith("位置"):
            return LocationMessage
        if name.startswith("文件\n") or name.startswith("文件\r"):
            return FileMessage
        if name.startswith("链接\n") or name.startswith("链接\r"):
            return LinkMessage
        if name.startswith("[链接]"):
            return LinkMessage
        if re.search(r"https?://", name):
            return LinkMessage
        if name.startswith("语音通话") or name.startswith("视频通话"):
            return VoipMessage
        if "聊天记录" in name or name.startswith("合并"):
            return MergeMessage
        if "笔记" in name:
            return NoteMessage
        if name.endswith("微信红包") and "  " in name:
            return RedPacketMessage
        if name.endswith("微信转账") and name.startswith("￥"):
            return TransferMessage
        if MusicMessage.match(name):
            return MusicMessage
        # ChatBubbleItemView 中未匹配的通常是卡片消息
        # （公众号文章、小程序卡片等）
        return CardMessage

    # 动画表情 Name 格式: "动画表情" 或 "动画表情 [xxx]"
    _ANIMATED_EMOJI_RE = re.compile(r"^动画表情(\s+\[.+\])?$")

    @staticmethod
    def _classify_bubble_refer(name: str) -> type[Message]:
        """
        对 mmui::ChatBubbleReferItemView 做二次分类。

        该 ClassName 复用于多种消息类型：
        - 图片: Name == "图片"
        - 视频: Name == "视频"
        - 动画表情: Name 匹配 "动画表情 [xxx]"，如 "动画表情 [嗅嗅]"
        - 引用消息: 其他情况
        """
        if name == "图片":
            return ImageMessage
        if name.startswith("视频"):
            return VideoMessage
        if Chat._ANIMATED_EMOJI_RE.match(name):
            return EmotionMessage
        return QuoteMessage

    @staticmethod
    def _detect_sender(
        hwnd: int, ctrl, chat_name: str,
    ) -> tuple[str, SenderType, tuple]:
        """
        判断消息发送者、来源类型，并检测气泡区域坐标。

        通过截图后从左右两侧向内扫描非白色像素，判断头像在哪侧。

        Args:
            hwnd:      窗口句柄，用于 PrintWindow 截图
            ctrl:      消息 ListItemControl 控件
            chat_name: 当前聊天对象名称（用于标记对方消息的 sender）

        Returns:
            (sender, sender_type, bubble_rect)
            bubble_rect 为气泡区域屏幕坐标 (left, top, right, bottom)，空元组表示未检测到
        """
        return Chat._detect_sender_by_pixel(ctrl, chat_name, hwnd)

    @staticmethod
    def _detect_sender_by_pixel(
        ctrl, chat_name: str, hwnd: int = 0,
    ) -> tuple[str, SenderType, tuple]:
        """
        通过截图像素分析判断消息发送者，并检测气泡区域。

        Returns:
            (sender, sender_type, bubble_rect)
            bubble_rect 为气泡区域屏幕坐标 (left, top, right, bottom)，空元组表示未检测到
        """
        try:
            if hwnd:
                png_bytes = capture_control(hwnd, ctrl, offset_right=15, mode="print_window")
                img = Image.open(io.BytesIO(png_bytes))
            else:
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="_wxuia_msg_")
                os.close(tmp_fd)
                try:
                    ctrl.CaptureToImage(tmp_path)
                    img = Image.open(tmp_path)
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        except Exception:
            return "", SenderType.UNKNOWN, ()

        w, h = img.size

        # ---- 边缘扫描 ----
        edge_result = Chat._detect_sender_by_edge_scan(img, w, h, chat_name)
        edge_scan_y, edge_left_x, edge_right_x = -1, -1, -1
        if edge_result is not None:
            sender, sender_type, edge_scan_y, edge_left_x, edge_right_x = edge_result
        else:
            sender, sender_type = "", SenderType.UNKNOWN

        # ---- 检测气泡区域 ----
        bubble_left, bubble_right = Chat._detect_bubble_rect(img, w, h, sender_type)

        # 转换为屏幕坐标
        bubble_rect = ()
        if bubble_left > 0 or bubble_right > 0:
            try:
                ctrl_rect = ctrl.BoundingRectangle
                bubble_rect = (
                    bubble_left + ctrl_rect.left,
                    ctrl_rect.top,
                    bubble_right + ctrl_rect.left,
                    ctrl_rect.bottom,
                )
            except Exception:
                pass

        return sender, sender_type, bubble_rect

    @staticmethod
    def _detect_bubble_rect(
        img: "Image.Image", w: int, h: int,
        sender_type: "SenderType",
    ) -> tuple[int, int]:
        """
        检测气泡的左边缘和右边缘 x 坐标（相对于控件截图）。

        在 y=38 高度处扫描：
        - 对方消息（FRIEND）：先从左侧扫描找气泡左边缘，再从右侧扫描找气泡右边缘
        - 自己消息（SELF）：先从右侧扫描找气泡右边缘，再从左侧扫描找气泡左边缘

        Returns:
            (bubble_left, bubble_right) 相对于控件的 x 坐标，(0, 0) 表示未检测到
        """
        scan_y = 38
        if scan_y >= h:
            return 0, 0

        threshold = 3  # 连续非白色像素数
        skip_px = 75   # 跳过头像区域的像素

        def _scan_left_to_right(start: int, end: int) -> int:
            count = 0
            for x in range(start, end):
                r, g, b = img.getpixel((x, scan_y))[:3]
                if Chat._is_non_white(r, g, b):
                    count += 1
                    if count >= threshold:
                        return x - threshold + 1
                else:
                    count = 0
            return 0

        def _scan_right_to_left(start: int, end: int) -> int:
            count = 0
            for x in range(start, end, -1):
                r, g, b = img.getpixel((x, scan_y))[:3]
                if Chat._is_non_white(r, g, b):
                    count += 1
                    if count >= threshold:
                        return x + threshold - 1
                else:
                    count = 0
            return 0

        if sender_type == SenderType.FRIEND:
            bubble_left = _scan_left_to_right(skip_px, w)
            bubble_right = _scan_right_to_left(w - 1 - skip_px, -1)
        elif sender_type == SenderType.SELF:
            bubble_right = _scan_right_to_left(w - 1 - skip_px, -1)
            bubble_left = _scan_left_to_right(skip_px, w)
        else:
            return 0, 0

        return bubble_left, bubble_right

    @staticmethod
    def _is_non_white(r: int, g: int, b: int) -> bool:
        """判断像素是否为非白色背景（排除纯白和接近纯白的背景色）"""
        return not (r > 245 and g > 245 and b > 245)

    @staticmethod
    def _detect_sender_by_edge_scan(
        img: "Image.Image", w: int, h: int, chat_name: str,
    ) -> tuple[str, SenderType, int, int, int] | None:
        """
        从左右两侧同时向中间扫描，先找到非白色像素的一侧即为头像侧。

        Returns:
            (sender, sender_type, scan_y, left_x, right_x) 或 None
            left_x/right_x 为扫描到的 x 坐标，-1 表示未找到
        """
        scan_y = 38
        if scan_y >= h:
            return None

        left = 0
        right = w - 1
        found_left = False
        found_right = False

        while left <= right:
            if not found_left:
                r, g, b = img.getpixel((left, scan_y))[:3]
                if Chat._is_non_white(r, g, b):
                    found_left = True
            if not found_right:
                r, g, b = img.getpixel((right, scan_y))[:3]
                if Chat._is_non_white(r, g, b):
                    found_right = True

            if found_left or found_right:
                break

            left += 1
            right -= 1

        if not found_left and not found_right:
            return None

        left_x = left if found_left else -1
        right_x = right if found_right else -1

        if found_left and found_right:
            if left < (w - 1 - right):
                return chat_name, SenderType.FRIEND, scan_y, left_x, right_x
            elif (w - 1 - right) < left:
                return "我", SenderType.SELF, scan_y, left_x, right_x
            else:
                return None

        if found_left:
            return chat_name, SenderType.FRIEND, scan_y, left_x, right_x
        return "我", SenderType.SELF, scan_y, left_x, right_x

    # -- 消息状态检测 --

    # 不同消息类型的状态前缀映射
    # 文本/引用/表情等气泡类消息：Name 以 "发送失败 " / "发送中 " 开头
    # 文件消息：Name 以 "发送失败\n" / "发送中\n" 开头
    # 图片/视频消息：Name 以 "发送失败 " / "发送中 " 开头
    _STATUS_PREFIXES = {
        "发送失败 ": MessageStatus.FAILED,
        "发送中 ": MessageStatus.SENDING,
        "发送失败\n": MessageStatus.FAILED,
        "发送中\n": MessageStatus.SENDING,
    }

    @staticmethod
    def _detect_message_status(
        msg_cls: type[Message],
        raw_name: str,
        sender_type: SenderType,
    ) -> tuple[MessageStatus, str]:
        """
        检测消息发送状态，返回 (状态, 去掉前缀后的实际内容)。

        不同消息类型的检测策略：
        - 文本/引用/表情等: Name 前缀 "发送失败 " / "发送中 "
        - 文件消息: Name 前缀 "发送失败\\n" / "发送中\\n"（文件名在换行后）
        - 图片/视频: Name 前缀 "发送失败 " / "发送中 "
        - 系统消息: 不检测状态
        - 收到的消息: 状态为 RECEIVED
        - 自己发的无前缀: 状态为 SENT
        """
        if msg_cls is SystemMessage:
            return MessageStatus.UNKNOWN, raw_name

        # 文件消息优先检测换行分隔的前缀
        if msg_cls is FileMessage:
            for prefix, status in [
                ("发送失败\n", MessageStatus.FAILED),
                ("发送中\n", MessageStatus.SENDING),
            ]:
                if raw_name.startswith(prefix):
                    return status, raw_name[len(prefix):]

        # 通用前缀检测（空格分隔）
        for prefix, status in [
            ("发送失败 ", MessageStatus.FAILED),
            ("发送中 ", MessageStatus.SENDING),
        ]:
            if raw_name.startswith(prefix):
                return status, raw_name[len(prefix):]

        # 无前缀，根据发送者推断
        if sender_type == SenderType.SELF:
            return MessageStatus.SENT, raw_name
        if sender_type == SenderType.FRIEND:
            return MessageStatus.RECEIVED, raw_name
        return MessageStatus.UNKNOWN, raw_name

    @staticmethod
    def _build_message(
        msg_cls: type[Message],
        raw_name: str,
        sender: str,
        sender_type: SenderType,
        runtime_id: tuple = (),
    ) -> Message:
        """根据消息子类构造具体消息对象，调用各子类的 parse 方法提取字段"""
        msg_status, actual_name = Chat._detect_message_status(
            msg_cls, raw_name, sender_type,
        )

        base = dict(sender=sender, sender_type=sender_type,
                    raw_name=raw_name, status=msg_status,
                    runtime_id=runtime_id)

        if msg_cls is VoiceMessage:
            content, duration, played = VoiceMessage.parse(actual_name)
            return VoiceMessage(**base, content=content, duration=duration, played=played)

        if msg_cls is FileMessage:
            content, file_name = FileMessage.parse(actual_name)
            return FileMessage(**base, content=content, file_name=file_name)

        if msg_cls is LocationMessage:
            content, address = LocationMessage.parse(actual_name)
            return LocationMessage(**base, content=content, address=address)

        if msg_cls is LinkMessage:
            content, title, source = LinkMessage.parse(actual_name)
            return LinkMessage(**base, content=content, title=title, source=source)

        if msg_cls is PersonalCardMessage:
            content, card_name = PersonalCardMessage.parse(actual_name)
            return PersonalCardMessage(**base, content=content, card_name=card_name)

        if msg_cls is VoipMessage:
            content, call_type, call_status = VoipMessage.parse(actual_name)
            return VoipMessage(**base, content=content, call_type=call_type, call_status=call_status)

        if msg_cls is CardMessage:
            content, title, description = CardMessage.parse(actual_name)
            return CardMessage(**base, content=content, title=title, description=description)

        if msg_cls is MusicMessage:
            content, source, song_name, artist = MusicMessage.parse(actual_name)
            return MusicMessage(**base, content=content, source=source,
                                song_name=song_name, artist=artist)

        if msg_cls is RedPacketMessage:
            content, greeting = RedPacketMessage.parse(actual_name)
            return RedPacketMessage(**base, content=content, greeting=greeting)

        if msg_cls is TransferMessage:
            content, amount, remark = TransferMessage.parse(actual_name)
            return TransferMessage(**base, content=content, amount=amount, remark=remark)

        if msg_cls is EmotionMessage:
            content, emoji_name = EmotionMessage.parse(actual_name)
            return EmotionMessage(**base, content=content, emoji_name=emoji_name)

        if msg_cls is QuoteMessage:
            content, reply_content, quote_sender, quote_content = QuoteMessage.parse(actual_name)
            return QuoteMessage(**base, content=content, reply_content=reply_content,
                                quote_sender=quote_sender, quote_content=quote_content)

        # TextMessage, ImageMessage, VideoMessage,
        # MergeMessage, NoteMessage, OtherMessage
        return msg_cls(**base, content=actual_name)

    # ---- 聊天信息面板操作 ----

    @PIM.guard
    def clear_chat_history(self) -> None:
        """
        清空当前会话的聊天记录（私聊）。

        流程：
        1. 点击标题栏右上角"聊天信息"按钮，展开聊天信息面板
        2. 在面板中找到"清空聊天记录"按钮并点击
        3. 在确认弹窗中点击"清空"按钮
        4. 收回聊天信息面板
        """
        self._activate_window()

        # 1. 展开聊天信息面板
        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 2. 点击"清空聊天记录"按钮
            clear_btn = self._win.ButtonControl(
                Name="清空聊天记录",
            )
            if not clear_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'清空聊天记录'按钮")
            input_wx.click(clear_btn)
            time.sleep(0.5)

            # 3. 确认弹窗中点击"清空"
            confirm_btn = self._win.ButtonControl(
                Name="清空",
                ClassName="mmui::XOutlineButton",
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'清空'确认按钮")
            input_wx.click(confirm_btn)
            time.sleep(0.3)

            logger.info(f"清空聊天记录成功: {self.current_name}")

        finally:
            # 4. 收回聊天信息面板
            self._close_chat_info_panel()

    @PIM.guard
    def clear_room_chat_history(self) -> None:
        """
        清空当前群聊会话的聊天记录。

        群聊的聊天信息面板中，"清空聊天记录"按钮位于
        mmui::ChatRoomMemberInfoView 区域的底部，需要先滚动到底部
        才能看到该按钮。由于该按钮不暴露为独立的 UI Automation 控件，
        需要通过 OCR 图像识别定位并点击。

        流程：
        1. 点击标题栏右上角"聊天信息"按钮，展开聊天信息面板
        2. 定位 mmui::ChatRoomMemberInfoView 区域
        3. 将该区域滚动到底部
        4. 使用 OCR 图像识别定位"清空聊天记录"文本并点击
        5. 在确认弹窗中点击"清空"按钮
        6. 收回聊天信息面板

        Raises:
            RuntimeError: 当前非群聊、控件未找到或操作失败时抛出
        """
        self._ensure_room_chat()
        self._activate_window()

        # 1. 展开聊天信息面板
        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 2. 定位 mmui::ChatRoomMemberInfoView 区域
            member_info_view = self._win.GroupControl(
                ClassName="mmui::ChatRoomMemberInfoView",
            )
            if not member_info_view.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到群聊信息面板 (mmui::ChatRoomMemberInfoView)")

            # 3. 将该区域滚动到底部
            rect = member_info_view.BoundingRectangle
            cx = rect.left + rect.width() // 2
            cy = rect.top + rect.height() // 2
            # 多次滚动确保到达底部
            for _ in range(10):
                input_wx.scroll_at(cx, cy, -120 * 5)
                time.sleep(0.3)

            time.sleep(0.5)

            # 4. 使用 OCR 图像识别定位"清空聊天记录"
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if "清空聊天记录" not in ocr_data:
                raise RuntimeError(
                    "OCR 未识别到'清空聊天记录'文本，"
                    "请确认聊天信息面板已展开且已滚动到底部"
                )

            info = ocr_data["清空聊天记录"]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1])
            auto.Click(click_x, click_y)
            time.sleep(0.5)

            # 5. 确认弹窗中点击"清空"
            confirm_btn = self._win.ButtonControl(
                Name="清空",
                ClassName="mmui::XOutlineButton",
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'清空'确认按钮")
            input_wx.click(confirm_btn)
            time.sleep(0.3)

            logger.info(f"清空群聊聊天记录成功: {self.current_name}")

        finally:
            # 6. 收回聊天信息面板
            self._close_chat_info_panel()

    @PIM.guard
    def exit_room(self) -> None:
        """
        退出当前群聊。

        群聊的聊天信息面板中，"退出群聊"按钮位于
        mmui::ChatRoomMemberInfoView 区域的底部，需要先滚动到底部
        才能看到该按钮。由于该按钮不暴露为独立的 UI Automation 控件，
        需要通过 OCR 图像识别定位并点击。

        流程：
        1. 点击标题栏右上角"聊天信息"按钮，展开聊天信息面板
        2. 定位 mmui::ChatRoomMemberInfoView 区域
        3. 将该区域滚动到底部
        4. 使用 OCR 图像识别定位"退出群聊"文本并点击
        5. 在确认弹窗中点击"确定"按钮

        Raises:
            RuntimeError: 当前非群聊、控件未找到或操作失败时抛出
        """
        self._ensure_room_chat()
        self._activate_window()

        # 1. 展开聊天信息面板
        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 2. 定位 mmui::ChatRoomMemberInfoView 区域
            member_info_view = self._win.GroupControl(
                ClassName="mmui::ChatRoomMemberInfoView",
            )
            if not member_info_view.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到群聊信息面板 (mmui::ChatRoomMemberInfoView)")

            # 3. 将该区域滚动到底部
            rect = member_info_view.BoundingRectangle
            cx = rect.left + rect.width() // 2
            cy = rect.top + rect.height() // 2
            for _ in range(10):
                input_wx.scroll_at(cx, cy, -120 * 5)
                time.sleep(0.3)

            # 4. 使用 OCR 图像识别定位"退出群聊"
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if "退出群聊" not in ocr_data:
                raise RuntimeError(
                    "OCR 未识别到'退出群聊'文本，"
                    "请确认聊天信息面板已展开且已滚动到底部"
                )

            info = ocr_data["退出群聊"]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1])
            auto.Click(click_x, click_y)

            # 5. 确认弹窗中点击"确定"
            confirm_btn = self._win.ButtonControl(
                Name="确定",
                ClassName="mmui::XOutlineButton",
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'确定'确认按钮")
            input_wx.click(confirm_btn)
            logger.info(f"退出群聊成功: {self.current_name}")

        finally:
            # 退出群聊后面板可能已自动关闭，尝试收回
            self._close_chat_info_panel()

    @PIM.guard
    def add_room_members(self, members: list[str]) -> None:
        """
        添加群成员。

        仅群聊可用。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 使用 OCR 识别"添加"文本，点击其下方一个文本高度处（"+"图标位置）
        3. 在弹出的 SessionPickerWindow 中逐个搜索并勾选成员
        4. 点击"完成"按钮

        Args:
            members: 要添加的成员昵称列表

        Raises:
            ValueError: members 为空时抛出
            RuntimeError: 操作失败时抛出
        """
        if not members:
            raise ValueError("members 不能为空")

        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()

        try:
            # 使用 OCR 识别"添加"文本并点击其下方（"+"图标位置）
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if "添加" not in ocr_data:
                raise OCRError("OCR 未识别到'添加'文本")

            info = ocr_data["添加"]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            # 点击"添加"文本中心 X，Y 偏移一个文本高度（即"+"图标所在位置）
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1] - 2 * info["height"])
            auto.Click(click_x, click_y)
            time.sleep(0.5)

            # 等待 SessionPickerWindow 出现
            picker_win = self._win.WindowControl(
                ClassName="mmui::SessionPickerWindow",
                searchDepth=1,
            )
            if not picker_win.Exists(maxSearchSeconds=3):
                raise RuntimeError("添加群成员窗口未打开")

            # 逐个搜索并勾选成员
            for nickname in members:
                fresh_picker = self._win.WindowControl(
                    ClassName="mmui::SessionPickerWindow",
                    searchDepth=1,
                )
                if not fresh_picker.Exists(maxSearchSeconds=3):
                    raise RuntimeError("添加群成员窗口已关闭")
                if not background:
                    fresh_picker.SetActive()
                input_wx.focus(fresh_picker)
                time.sleep(0.3)

                search_field = fresh_picker.GroupControl(
                    ClassName="mmui::XSearchField",
                    searchDepth=3,
                )
                if not search_field.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到搜索区域")
                search_edit = search_field.EditControl(
                    ClassName="mmui::XValidatorTextEdit", Name="搜索",
                    searchDepth=1,
                )
                if not search_edit.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到搜索框")

                input_wx.click(search_edit)
                time.sleep(0.3)
                input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
                time.sleep(0.3)
                input_wx.send_keys(search_edit, nickname)
                time.sleep(1.5)

                # 添加群成员窗口搜索后使用 SearchContactView
                search_view = fresh_picker.GroupControl(
                    ClassName="mmui::SearchContactView",
                    searchDepth=3,
                )
                if not search_view.Exists(maxSearchSeconds=3):
                    raise RuntimeError(f"搜索联系人 '{nickname}' 后未出现搜索视图")

                result_list = search_view.ListControl(
                    ClassName="mmui::XTableView",
                    AutomationId="sp_search_result_list",
                    searchDepth=1,
                )
                if not result_list.Exists(maxSearchSeconds=5):
                    raise RuntimeError(f"搜索联系人 '{nickname}' 后未出现结果列表")

                contact_row = result_list.CheckBoxControl(
                    ClassName="mmui::SearchContactCellView",
                    searchDepth=1,
                )
                if not contact_row.Exists(maxSearchSeconds=3):
                    raise RuntimeError(f"未找到联系人: {nickname}")

                input_wx.click(contact_row)
                time.sleep(0.5)

            # 点击完成按钮
            final_picker = self._win.WindowControl(
                ClassName="mmui::SessionPickerWindow",
                searchDepth=1,
            )
            if not final_picker.Exists(maxSearchSeconds=3):
                raise RuntimeError("添加群成员窗口已关闭")
            detail_view = final_picker.GroupControl(
                ClassName="mmui::SPDetailView",
                searchDepth=3,
            )
            if not detail_view.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到详情面板")
            confirm_btn = detail_view.ButtonControl(
                ClassName="mmui::XOutlineButton",
                AutomationId="confirm_btn",
                Name="添加",
                searchDepth=2,
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'添加'按钮")
            input_wx.click(confirm_btn)

            time.sleep(0.5)

            # 非好友会邀请失败
            if self._win.TextControl(Name="未能邀请").Exists(0, 0):
                input_wx.click(self._win.ButtonControl(Name="我知道了"))

            # 等待操作窗口消失后再收起聊天信息面板
            for _ in range(30):
                check_picker = self._win.WindowControl(
                    ClassName="mmui::SessionPickerWindow",
                    searchDepth=1,
                )
                if not check_picker.Exists(maxSearchSeconds=1):
                    break
                time.sleep(1)

            logger.info(f"添加群成员成功: {self.current_name} -> {members}")

        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def remove_room_members(self, members: list[str]) -> None:
        """
        移除群成员。

        仅群聊可用。

        移除群成员窗口与添加群成员窗口的控件结构不同：
        - 搜索结果视图: mmui::SearchGroupMemberView（非 SearchContactNewChatView）
        - 搜索结果列表: mmui::XTableView, AutomationId="sp_search_list"
        - 搜索结果项: mmui::XTableCell (ListItemControl)
        - 确认按钮: Name="移出"（非"完成"）

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 使用 OCR 识别"移出"文本，点击其下方一个文本高度处（"-"图标位置）
        3. 在弹出的 SessionPickerWindow 中逐个搜索并勾选要移除的成员
        4. 点击"移出"按钮
        5. 确认弹窗中点击"确定"

        Args:
            members: 要移除的成员昵称列表

        Raises:
            ValueError: members 为空时抛出
            RuntimeError: 操作失败时抛出
        """
        if not members:
            raise ValueError("members 不能为空")

        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 使用 OCR 识别"移出"文本并点击其下方（"-"图标位置）
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if "移出" not in ocr_data:
                raise OCRError("OCR 未识别到'移出'文本")

            info = ocr_data["移出"]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1] - 2 * info["height"])
            auto.Click(click_x, click_y)
            time.sleep(0.5)

            # 等待 SessionPickerWindow 出现
            picker_win = self._win.WindowControl(
                ClassName="mmui::SessionPickerWindow",
                searchDepth=1,
            )
            if not picker_win.Exists(maxSearchSeconds=3):
                raise RuntimeError("移除群成员窗口未打开")

            # 逐个搜索并勾选要移除的成员
            for nickname in members:
                fresh_picker = self._win.WindowControl(
                    ClassName="mmui::SessionPickerWindow",
                    searchDepth=1,
                )
                if not fresh_picker.Exists(maxSearchSeconds=3):
                    raise RuntimeError("移除群成员窗口已关闭")
                if not background:
                    fresh_picker.SetActive()
                input_wx.focus(fresh_picker)
                time.sleep(0.3)

                search_field = fresh_picker.GroupControl(
                    ClassName="mmui::XSearchField",
                    searchDepth=3,
                )
                if not search_field.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到搜索区域")
                search_edit = search_field.EditControl(
                    ClassName="mmui::XValidatorTextEdit", Name="搜索",
                    searchDepth=1,
                )
                if not search_edit.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到搜索框")

                input_wx.click(search_edit)
                time.sleep(0.3)
                input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
                time.sleep(0.3)
                input_wx.send_keys(search_edit, nickname)
                time.sleep(1.5)

                # 移除群成员窗口使用 SearchGroupMemberView 而非 SearchContactNewChatView
                search_view = fresh_picker.GroupControl(
                    ClassName="mmui::SearchGroupMemberView",
                    searchDepth=3,
                )
                if not search_view.Exists(maxSearchSeconds=3):
                    raise RuntimeError(f"搜索成员 '{nickname}' 后未出现搜索视图")

                # 搜索结果列表 AutomationId 为 sp_search_list
                result_list = search_view.ListControl(
                    ClassName="mmui::XTableView",
                    AutomationId="sp_search_list",
                    searchDepth=1,
                )
                if not result_list.Exists(maxSearchSeconds=5):
                    raise RuntimeError(f"搜索成员 '{nickname}' 后未出现结果列表")

                # 搜索结果项为 mmui::XTableCell (ListItemControl)
                contact_row = result_list.ListItemControl(
                    ClassName="mmui::XTableCell",
                    searchDepth=1,
                )
                if not contact_row.Exists(maxSearchSeconds=3):
                    raise RuntimeError(f"未找到成员: {nickname}")

                input_wx.click(contact_row)
                time.sleep(0.5)

            # 点击"移出"按钮（非"完成"）
            final_picker = self._win.WindowControl(
                ClassName="mmui::SessionPickerWindow",
                searchDepth=1,
            )
            if not final_picker.Exists(maxSearchSeconds=3):
                raise RuntimeError("移除群成员窗口已关闭")
            detail_view = final_picker.GroupControl(
                ClassName="mmui::SPDetailView",
                searchDepth=3,
            )
            if not detail_view.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到详情面板")
            confirm_btn = detail_view.ButtonControl(
                ClassName="mmui::XOutlineButton",
                AutomationId="confirm_btn",
                Name="移出",
                searchDepth=2,
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'移出'按钮")
            input_wx.click(confirm_btn)
            time.sleep(0.5)

            # 确认弹窗中点击"确定"
            ok_btn = self._win.ButtonControl(
                Name="确定",
                ClassName="mmui::XOutlineButton",
            )
            if ok_btn.Exists(maxSearchSeconds=3):
                input_wx.click(ok_btn)
                time.sleep(0.3)

            # 等待操作窗口消失后再收起聊天信息面板
            for _ in range(30):
                check_picker = self._win.WindowControl(
                    ClassName="mmui::SessionPickerWindow",
                    searchDepth=1,
                )
                if not check_picker.Exists(maxSearchSeconds=1):
                    break
                time.sleep(1)

            logger.info(f"移除群成员成功: {self.current_name} -> {members}")

        finally:
            self._close_chat_info_panel()

    def _scroll_room_info_to_bottom(self) -> auto.GroupControl:
        """
        在已展开的聊天信息面板中，定位 mmui::ChatRoomMemberInfoView
        区域并滚动到底部。

        Returns:
            member_info_view 控件

        Raises:
            RuntimeError: 未找到控件时抛出
        """
        member_info_view = self._win.GroupControl(
            ClassName="mmui::ChatRoomMemberInfoView",
        )
        if not member_info_view.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到群聊信息面板 (mmui::ChatRoomMemberInfoView)")

        rect = member_info_view.BoundingRectangle
        cx = rect.left + rect.width() // 2
        cy = rect.top + rect.height() // 2
        for _ in range(10):
            input_wx.scroll_at(cx, cy, -120 * 5)
            time.sleep(0.3)
        time.sleep(0.5)
        return member_info_view

    def _ocr_window(self) -> dict:
        """
        对微信主窗口截图并执行 OCR，返回识别结果字典。

        Returns:
            {text: {center, left_top, right_bottom, width, height}} 字典

        Raises:
            RuntimeError: 无法获取窗口句柄时抛出
        """
        hwnd = self._win.NativeWindowHandle
        if not hwnd:
            raise RuntimeError("无法获取微信窗口句柄")
        png_bytes = capture_window(hwnd, mode="print_window")
        return self._get_image_text(png_bytes), hwnd

    def _ocr_click(self, text: str) -> None:
        """
        对微信主窗口截图 OCR 识别，点击指定文本的中心位置。

        Args:
            text: 要点击的 OCR 文本

        Raises:
            RuntimeError: OCR 未识别到指定文本时抛出
        """
        ocr_data, hwnd = self._ocr_window()
        if text not in ocr_data:
            raise OCRError(f"OCR 未识别到'{text}'文本")
        info = ocr_data[text]
        win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
        click_x = int(win_left + info["center"][0])
        click_y = int(win_top + info["center"][1])
        auto.Click(click_x, click_y)

    def _set_room_ocr_switch(self, switch_name: str, enable: bool) -> None:
        """
        通过 OCR 识别设置群聊信息面板中的开关。

        Args:
            switch_name: 开关名称（如 "消息免打扰"、"置顶聊天"）
            enable: True 开启，False 关闭
        """
        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            self._scroll_room_info_to_bottom()

            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if switch_name not in ocr_data:
                raise RuntimeError(
                    f"OCR 未识别到'{switch_name}'文本，"
                    "请确认聊天信息面板已展开且已滚动到底部"
                )

            img = Image.open(io.BytesIO(png_bytes))
            self._toggle_ocr_switch(img, ocr_data, hwnd, switch_name, enable)

            action = "开启" if enable else "关闭"
            logger.info(f"{action}{switch_name}成功: {self.current_name}")

        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def pin_room_chat(self) -> None:
        """置顶当前群聊会话（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("置顶聊天", True)

    @PIM.guard
    def unpin_room_chat(self) -> None:
        """取消置顶当前群聊会话（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("置顶聊天", False)

    @PIM.guard
    def mute_room_chat(self) -> None:
        """开启当前群聊的消息免打扰（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("消息免打扰", True)

    @PIM.guard
    def unmute_room_chat(self) -> None:
        """关闭当前群聊的消息免打扰（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("消息免打扰", False)

    @PIM.guard
    def add_room_address_book(self) -> None:
        """将当前群聊保存到通讯录（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("保存到通讯录", True)

    @PIM.guard
    def remove_room_address_book(self) -> None:
        """将当前群聊从通讯录移除（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("保存到通讯录", False)

    @PIM.guard
    def display_room_member_nickname(self) -> None:
        """显示群成员昵称（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("显示群成员昵称", True)

    @PIM.guard
    def hidden_room_member_nickname(self) -> None:
        """隐藏群成员昵称（通过 OCR 识别开关）"""
        self._set_room_ocr_switch("显示群成员昵称", False)

    @PIM.guard
    def fold_room_chat(self) -> None:
        """
        折叠当前群聊会话（通过 OCR 识别开关）。

        "折叠该聊天"是"消息免打扰"的子选项，
        只有在消息免打扰开启时才会出现。
        如果消息免打扰未开启，会先自动开启。
        """
        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            self._scroll_room_info_to_bottom()

            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            # 先确保消息免打扰已开启
            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)
            img = Image.open(io.BytesIO(png_bytes))
            self._toggle_ocr_switch(img, ocr_data, hwnd, "消息免打扰", True)

            # 开启消息免打扰后，"折叠该聊天"选项才会出现，重新截图
            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)
            img = Image.open(io.BytesIO(png_bytes))
            self._toggle_ocr_switch(img, ocr_data, hwnd, "折叠该聊天", True)

            logger.info(f"折叠群聊成功: {self.current_name}")

        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def unfold_room_chat(self) -> None:
        """
        取消折叠当前群聊会话（通过 OCR 识别开关）。

        "折叠该聊天"是"消息免打扰"的子选项，
        只有在消息免打扰开启时才会出现。
        """
        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            self._scroll_room_info_to_bottom()

            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)
            img = Image.open(io.BytesIO(png_bytes))

            # 折叠该聊天只在消息免打扰开启时存在
            if "折叠该聊天" in ocr_data:
                self._toggle_ocr_switch(img, ocr_data, hwnd, "折叠该聊天", False)

            logger.info(f"取消折叠群聊成功: {self.current_name}")

        finally:
            self._close_chat_info_panel()

    @staticmethod
    def _detect_ocr_switch_state(img: Image.Image, info: dict) -> bool:
        """
        通过像素扫描判断 OCR 识别到的开关当前状态。

        从文本中心 Y 坐标出发，从文本右边界向右扫描像素，
        发现绿色像素说明开关处于开启状态。

        Args:
            img:  窗口截图 PIL Image
            info: OCR 识别结果中某个文本的坐标信息

        Returns:
            True 开启，False 关闭
        """
        sw_img_y = int(info["center"][1])
        min_x = int(info["right_bottom"][0]) + 5
        # 从图片右边界向左扫描，开关控件总是靠右对齐
        for x in range(img.width - 1, min_x, -1):
            r, g, b = img.getpixel((x, sw_img_y))[:3]
            if g > 150 and g - r > 40 and g - b > 40:
                return True
        return False

    @staticmethod
    def _find_switch_center_x(img: Image.Image, info: dict) -> int:
        """
        通过像素扫描定位开关控件的水平中心坐标（图片坐标系）。

        从图片右边界向左扫描（开关控件总是靠右对齐），
        查找开关的彩色区域（绿色=开启，灰色=关闭），
        返回该区域的水平中心 X 坐标。

        开关像素特征：
        - 开启状态（绿色）: G > 150, G-R > 40, G-B > 40
        - 关闭状态（灰色）: R,G,B 接近且在 180~230 范围，排除纯白背景

        Returns:
            开关中心的 X 坐标（图片坐标系），未找到时回退到图片右侧 - 40px
        """
        sw_img_y = int(info["center"][1])
        # 开关不会超出文本右边界的左侧，设为扫描下限
        min_x = int(info["right_bottom"][0]) + 5

        switch_left = -1
        switch_right = -1

        gap = 0  # 连续非开关像素计数，允许小间隙（圆形滑块中间有白色区域）
        max_gap = 15  # 开关滑块直径约 20px，允许 15px 间隙

        # 从图片右边界向左扫描，先找到开关的右边缘
        for x in range(img.width - 1, min_x, -1):
            r, g, b = img.getpixel((x, sw_img_y))[:3]
            # 绿色（开启）
            is_green = g > 150 and g - r > 40 and g - b > 40
            # 灰色（关闭）: 三通道接近，亮度适中，排除纯白背景
            is_gray = (180 < r < 230 and 180 < g < 230 and 180 < b < 230
                       and abs(r - g) < 15 and abs(r - b) < 15)
            if is_green or is_gray:
                if switch_right < 0:
                    switch_right = x
                switch_left = x
                gap = 0
            else:
                if switch_right >= 0:
                    gap += 1
                    if gap > max_gap:
                        break

        if switch_left >= 0 and switch_right > switch_left:
            return (switch_left + switch_right) // 2

        # 回退：图片右边界 - 40px（开关通常在最右侧）
        return img.width - 40

    def _toggle_ocr_switch(self, img, ocr_data, hwnd,
                           switch_name: str, enable: bool) -> None:
        """
        根据已有的 OCR 数据和截图，切换指定开关。

        如果 switch_name 不在 ocr_data 中则跳过（不报错）。
        检测当前状态，状态不符时点击切换。

        通过像素扫描定位开关控件的实际位置（而非固定偏移），
        确保在不同窗口大小和面板布局下都能准确点击。

        Args:
            img:         窗口截图 PIL Image
            ocr_data:    OCR 识别结果字典
            hwnd:        窗口句柄
            switch_name: 开关名称
            enable:      目标状态
        """
        if switch_name not in ocr_data:
            logger.warning(f"OCR 未识别到'{switch_name}'，跳过")
            return

        info = ocr_data[switch_name]
        is_on = self._detect_ocr_switch_state(img, info)

        if is_on != enable:
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            switch_img_x = self._find_switch_center_x(img, info)
            switch_x = int(win_left + switch_img_x)
            switch_y = int(win_top + info["center"][1])
            auto.Click(switch_x, switch_y)
            time.sleep(0.5)

    @PIM.guard
    def set_room_info(self, name: str = None, announcement: str = None,
                      remark: str = None, my_nickname: str = None,
                      mute: bool = None, pin: bool = None,
                      save_address_book: bool = None,
                      display_member_nickname: bool = None,
                      fold: bool = None) -> None:
        """
        一次性设置群聊的多项信息。

        只打开一次聊天信息面板，按顺序完成所有操作后关闭。
        参数为 None 时跳过对应项，不做修改。

        name、announcement、remark、my_nickname 每个操作前独立截图 OCR。
        开关类参数滚动到底部后每个独立截图 OCR。

        Args:
            name:                    群聊名称
            announcement:            群公告内容
            remark:                  群聊备注
            my_nickname:             我在本群的昵称
            mute:                    消息免打扰（True 开启 / False 关闭）
            pin:                     置顶聊天（True 开启 / False 关闭）
            save_address_book:        保存到通讯录（True 开启 / False 关闭）
            display_member_nickname: 显示群成员昵称（True 开启 / False 关闭）
            fold:                    折叠该聊天（True 开启 / False 关闭），
                                     开启时会自动先开启消息免打扰

        Raises:
            RuntimeError: 当前非群聊或操作失败时抛出
        """
        # 全部为 None 则不操作
        if all(v is None for v in (name, announcement, remark, my_nickname,
                                   mute, pin, save_address_book,
                                   display_member_nickname, fold)):
            return

        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            def _fresh_ocr() -> tuple[bytes, dict, int, int]:
                """每次操作前重新截图 + OCR，确保坐标准确"""
                _png = capture_window(hwnd, mode="print_window")
                _ocr = self._get_image_text(_png)
                _left, _top, _, _ = win32gui.GetWindowRect(hwnd)
                return _png, _ocr, _left, _top

            # ---- 第一组：文本字段（每个字段操作前独立截图 OCR） ----

            # -- 群聊名称 --
            if name is not None:
                png_bytes, ocr_data, win_left, win_top = _fresh_ocr()
                if "群聊名称" not in ocr_data:
                    raise OCRError("OCR 未识别到'群聊名称'文本")
                info = ocr_data["群聊名称"]
                click_x = int(win_left + info["center"][0])
                click_y = int(win_top + info["center"][1] + 1.5 * info["height"])
                auto.Click(click_x, click_y)
                time.sleep(0.2)
                input_wx.send_keys(self._win, "{Ctrl}a{Del}")
                time.sleep(0.1)
                input_wx.paste(name)
                input_wx.send_keys(self._win, "{Enter}")
                update_btn = self._win.ButtonControl(Name="修改")
                if update_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(update_btn)
                time.sleep(0.5)

            # -- 群公告 --
            if announcement is not None:
                png_bytes, ocr_data, win_left, win_top = _fresh_ocr()
                if "群公告" not in ocr_data:
                    raise OCRError("OCR 未识别到'群公告'文本")
                info = ocr_data["群公告"]
                click_x = int(win_left + info["center"][0])
                click_y = int(win_top + info["center"][1] + 1.5 * info["height"])
                auto.Click(click_x, click_y)

                # 等待群公告窗口出现
                pane_title = f"“{self.current_name}”的群公告"
                announcement_pane = auto.PaneControl(Name=pane_title)
                if not announcement_pane.Exists(maxSearchSeconds=3):
                    raise RuntimeError("未找到群公告编辑窗口")

                pane_hwnd = announcement_pane.NativeWindowHandle
                if not pane_hwnd:
                    raise RuntimeError("无法获取群公告窗口句柄")
                pane_png = capture_window(pane_hwnd, mode="print_window")
                pane_ocr = self._get_image_text(pane_png)

                # 如果之前发布过群公告，需要先点击"编辑群公告"
                if "编辑群公告" in pane_ocr:
                    ei = pane_ocr["编辑群公告"]
                    pane_left, pane_top, _, _ = win32gui.GetWindowRect(pane_hwnd)
                    auto.Click(int(pane_left + ei["center"][0]),
                               int(pane_top + ei["center"][1]))
                    time.sleep(0.5)
                    pane_png = capture_window(pane_hwnd, mode="print_window")
                    pane_ocr = self._get_image_text(pane_png)

                input_wx.send_keys(announcement_pane, "{Ctrl}a{Del}")
                input_wx.paste(announcement)

                time.sleep(0.5)

                pane_png = capture_window(pane_hwnd, mode="print_window")
                pane_ocr = self._get_image_text(pane_png)
                if "完成" not in pane_ocr:
                    raise OCRError("OCR 未识别到'完成'按钮")
                fi = pane_ocr["完成"]
                pane_left, pane_top, _, _ = win32gui.GetWindowRect(pane_hwnd)
                auto.Click(int(pane_left + fi["center"][0]),
                           int(pane_top + fi["center"][1]))
                time.sleep(0.5)

                publish_btn = announcement_pane.ButtonControl(Name="发布")
                if publish_btn.Exists(maxSearchSeconds=3):
                    publish_btn.GetInvokePattern().Invoke()
                time.sleep(1)

                # 等待群公告窗口关闭
                for _ in range(10):
                    if not get_hwnd(pane_title):
                        break
                    time.sleep(3)

                time.sleep(0.5)

            # -- 备注 --
            if remark is not None:
                png_bytes, ocr_data, win_left, win_top = _fresh_ocr()
                if "备注" not in ocr_data:
                    raise OCRError("OCR 未识别到'备注'文本")
                info = ocr_data["备注"]
                click_x = int(win_left + info["center"][0])
                click_y = int(win_top + info["center"][1] + 1.5 * info["height"])
                auto.Click(click_x, click_y)
                time.sleep(0.2)
                input_wx.send_keys(self._win, "{Ctrl}a{Del}")
                time.sleep(0.1)
                input_wx.paste(remark)
                input_wx.send_keys(self._win, "{Enter}")
                time.sleep(0.5)

            # -- 我在本群的昵称 --
            if my_nickname is not None:
                png_bytes, ocr_data, win_left, win_top = _fresh_ocr()
                ocr_key = None
                for candidate in ("我在本群的昵称", "我在本群的呢称"):
                    if candidate in ocr_data:
                        ocr_key = candidate
                        break
                if not ocr_key:
                    for key in ocr_data:
                        if "本群" in key and ("昵称" in key or "呢称" in key):
                            ocr_key = key
                            break
                if not ocr_key:
                    raise OCRError("OCR 未识别到'我在本群的昵称'文本")
                info = ocr_data[ocr_key]
                click_x = int(win_left + info["center"][0])
                click_y = int(win_top + info["center"][1] + 1.5 * info["height"])
                auto.Click(click_x, click_y)
                time.sleep(0.2)
                input_wx.send_keys(self._win, "{Ctrl}a{Del}")
                time.sleep(0.1)
                input_wx.paste(my_nickname)
                input_wx.send_keys(self._win, "{Enter}")
                update_btn = self._win.ButtonControl(Name="修改")
                if update_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(update_btn)
                time.sleep(0.5)

            # ---- 第二组：开关（滚动到底部，每个开关独立截图 OCR） ----
            has_switches = any(v is not None for v in
                              (mute, pin, save_address_book,
                               display_member_nickname, fold))

            if has_switches:
                self._scroll_room_info_to_bottom()

                # fold=True 需要先开启消息免打扰
                if fold is True and mute is not True:
                    png_bytes, ocr_data, _, _ = _fresh_ocr()
                    img = Image.open(io.BytesIO(png_bytes))
                    self._toggle_ocr_switch(
                        img, ocr_data, hwnd, "消息免打扰", True)
                    # mute 已处理，跳过后续重复操作
                    mute = None

                # 每个开关独立截图+OCR，因为点击后界面状态会变化
                # 折叠该聊天紧跟在消息免打扰之后操作
                for switch_name, switch_val in [
                    ("消息免打扰", mute),
                    ("折叠该聊天", fold),
                    ("置顶聊天", pin),
                    ("保存到通讯录", save_address_book),
                    ("显示群成员昵称", display_member_nickname),
                ]:
                    if switch_val is None:
                        continue
                    png_bytes, ocr_data, _, _ = _fresh_ocr()
                    img = Image.open(io.BytesIO(png_bytes))
                    self._toggle_ocr_switch(
                        img, ocr_data, hwnd, switch_name, switch_val)

            logger.info(f"设置群聊信息成功: {self.current_name}")

        finally:
            self._close_chat_info_panel()

    def _get_chat_info_switch(self, name: str) -> tuple:
        """
        获取聊天信息面板中指定开关的当前状态。

        先展开聊天信息面板，查找 mmui::XSwitchButton 开关控件，
        通过 TogglePattern 读取状态。

        Args:
            name: 开关名称（"消息免打扰" 或 "置顶聊天"）

        Returns:
            (switch_control, is_on: bool) 元组
        """
        sw = self._win.CheckBoxControl(
            ClassName="mmui::XSwitchButton",
            Name=name,
        )
        if not sw.Exists(maxSearchSeconds=3):
            raise RuntimeError(f"未找到'{name}'开关")
        toggle = sw.GetTogglePattern()
        is_on = toggle.ToggleState == 1 if toggle else False
        return sw, is_on

    def _set_chat_info_switch(self, name: str, enable: bool) -> None:
        """
        设置聊天信息面板中指定开关的状态。

        Args:
            name: 开关名称（"消息免打扰" 或 "置顶聊天"）
            enable: True 开启，False 关闭
        """
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            sw, is_on = self._get_chat_info_switch(name)
            if is_on != enable:
                input_wx.click(sw)
                time.sleep(0.3)
                action = "开启" if enable else "关闭"
                logger.info(f"{action}{name}成功: {self.current_name}")
        finally:
            self._close_chat_info_panel()

    @property
    def is_pinned(self) -> bool:
        """当前会话是否已置顶"""
        self._activate_window()
        self._click_chat_info_button()
        time.sleep(0.5)
        try:
            _, is_on = self._get_chat_info_switch("置顶聊天")
            return is_on
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def pin_contact_chat(self) -> None:
        """置顶当前私聊会话（通过 UI Automation 开关）"""
        self._set_chat_info_switch("置顶聊天", True)

    @PIM.guard
    def unpin_contact_chat(self) -> None:
        """取消置顶当前私聊会话（通过 UI Automation 开关）"""
        self._set_chat_info_switch("置顶聊天", False)

    def pin_chat(self) -> None:
        """置顶当前会话（自动区分私聊/群聊）"""
        if self.chat_type == "群聊":
            self.pin_room_chat()
        else:
            self.pin_contact_chat()

    def unpin_chat(self) -> None:
        """取消置顶当前会话（自动区分私聊/群聊）"""
        if self.chat_type == "群聊":
            self.unpin_room_chat()
        else:
            self.unpin_contact_chat()

    @property
    def is_muted(self) -> bool:
        """当前会话是否已开启消息免打扰"""
        self._activate_window()
        self._click_chat_info_button()
        time.sleep(0.5)
        try:
            _, is_on = self._get_chat_info_switch("消息免打扰")
            return is_on
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def mute_contact_chat(self) -> None:
        """开启当前私聊的消息免打扰（通过 UI Automation 开关）"""
        self._set_chat_info_switch("消息免打扰", True)

    @PIM.guard
    def unmute_contact_chat(self) -> None:
        """关闭当前私聊的消息免打扰（通过 UI Automation 开关）"""
        self._set_chat_info_switch("消息免打扰", False)

    def mute_chat(self) -> None:
        """开启消息免打扰（自动区分私聊/群聊）"""
        if self.chat_type == "群聊":
            self.mute_room_chat()
        else:
            self.mute_contact_chat()

    def unmute_chat(self) -> None:
        """关闭消息免打扰（自动区分私聊/群聊）"""
        if self.chat_type == "群聊":
            self.unmute_room_chat()
        else:
            self.unmute_contact_chat()

    @PIM.guard
    def fold_contact_chat(self) -> None:
        """
        折叠当前私聊会话（通过 UI Automation 开关）。

        "折叠该聊天"是"消息免打扰"的子选项，
        只有在消息免打扰开启时才会出现。
        如果消息免打扰未开启，会先自动开启。
        """
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 检查消息免打扰是否开启，未开启则先开启
            mute_sw, mute_on = self._get_chat_info_switch("消息免打扰")
            if not mute_on:
                input_wx.click(mute_sw)
                time.sleep(0.5)

            # 设置折叠该聊天
            fold_sw, fold_on = self._get_chat_info_switch("折叠该聊天")
            if not fold_on:
                input_wx.click(fold_sw)
                time.sleep(0.3)
                logger.info(f"折叠聊天成功: {self.current_name}")
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def unfold_contact_chat(self) -> None:
        """
        取消折叠当前私聊会话（通过 UI Automation 开关）。

        "折叠该聊天"是"消息免打扰"的子选项，
        只有在消息免打扰开启时才会出现。
        """
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 折叠该聊天只在消息免打扰开启时存在
            fold_sw = self._win.CheckBoxControl(
                ClassName="mmui::XSwitchButton",
                Name="折叠该聊天",
            )
            if fold_sw.Exists(maxSearchSeconds=2):
                toggle = fold_sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 1:
                    input_wx.click(fold_sw)
                    time.sleep(0.3)
                    logger.info(f"取消折叠聊天成功: {self.current_name}")
        finally:
            self._close_chat_info_panel()

    def fold_chat(self) -> None:
        """折叠当前会话（自动区分私聊/群聊）"""
        if self.chat_type == "群聊":
            self.fold_room_chat()
        else:
            self.fold_contact_chat()

    def unfold_chat(self) -> None:
        """取消折叠当前会话（自动区分私聊/群聊）"""
        if self.chat_type == "群聊":
            self.unfold_room_chat()
        else:
            self.unfold_contact_chat()

    # ---- 群聊信息面板操作（仅群聊可用） ----

    def _ensure_room_chat(self) -> None:
        """确保当前是群聊会话，否则抛出异常"""
        if self.chat_type != "群聊":
            raise RuntimeError("群聊信息操作仅支持群聊会话")

    def _click_room_info_item(self, item_name: str) -> None:
        """
        在群聊信息面板中点击指定的信息项按钮。

        群聊信息面板中的"群聊名称"、"群公告"、"备注"、"我在本群的昵称"
        等条目均为 ButtonControl，ClassName="mmui::XMouseEventView"。

        Args:
            item_name: 按钮名称（如 "群聊名称"、"群公告"、"备注"、"我在本群的昵称"）

        Returns:
            ButtonControl 控件

        Raises:
            RuntimeError: 未找到按钮时抛出
        """
        btn = self._win.ButtonControl(
            Name=item_name,
        )
        if not btn.Exists(maxSearchSeconds=3):
            raise RuntimeError(f"未找到'{item_name}'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

    @PIM.guard
    def set_room_name(self, name: str) -> None:
        """
        设置群聊名称。

        仅群聊可用。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 在面板中找到"群聊名称"按钮并点击
        3. 在弹出的编辑弹窗中修改群聊名称
        4. 点击"完成"按钮保存
        5. 收回聊天信息面板

        Args:
            name: 新的群聊名称

        Raises:
            ValueError: name 为空时抛出
            RuntimeError: 操作失败时抛出
        """
        if not name:
            raise ValueError("群聊名称不能为空")

        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()

        try:
            # 使用图片识别定位"群聊名称"
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if "群聊名称" not in ocr_data:
                raise OCRError("OCR 未识别到'群聊名称'文本，请确认聊天信息面板已展开")

            info = ocr_data["群聊名称"]
            # 窗口左上角屏幕坐标
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            # 点击"群聊名称"文本中心 X，Y 偏移一个文本高度（即名称值所在行）
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1] + info["height"])

            auto.Click(click_x, click_y)

            time.sleep(0.2)
            input_wx.send_keys(self._win, "{Ctrl}a{Del}")
            time.sleep(0.1)

            # 通过剪贴板粘贴名称
            input_wx.paste(name)
            input_wx.send_keys(self._win, "{Enter}")

            # 点击搜索框 完成保存
            update_bth = self._win.ButtonControl(Name="修改")
            input_wx.click(update_bth)
            logger.info(f"设置群聊名称成功: {name}")

        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_room_announcement(self, content: str) -> None:
        """
        设置群公告。

        仅群聊可用。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 使用图片识别定位"群公告"文本坐标并点击其下方区域
        3. 在弹出的编辑弹窗中修改群公告内容
        4. 点击"发布"按钮保存
        5. 收回聊天信息面板

        Args:
            content: 群公告内容

        Raises:
            ValueError: content 为空时抛出
            RuntimeError: 操作失败时抛出
        """
        if not content:
            raise ValueError("群公告内容不能为空")

        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()

        try:
            # 使用图片识别定位"群公告"
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")
            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            # 点击"群公告"文本下方区域
            if "群公告" not in ocr_data:
                raise OCRError("OCR 未识别到'群公告'文本，请确认聊天信息面板已展开")
            info = ocr_data["群公告"]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1] + info["height"])
            auto.Click(click_x, click_y)

            # 判断群公告窗口是否出现
            pane_title = f"“{self.current_name}”的群公告"
            announcement_pane = auto.PaneControl(Name=pane_title)
            if not announcement_pane.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到群公告编辑窗口")

            # 识别群公告编辑窗口
            pane_hwnd = announcement_pane.NativeWindowHandle
            if not pane_hwnd:
                raise RuntimeError("无法获取群公告窗口句柄")
            png_bytes = capture_window(pane_hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)
            if not ocr_data:
                raise OCRError("群公告窗口 OCR 未识别到任何文本")

            # 如果之前发布过群公告，需要先点击"编辑群公告"
            if "编辑群公告" in ocr_data:
                info = ocr_data["编辑群公告"]
                pane_left, pane_top, _, _ = win32gui.GetWindowRect(pane_hwnd)
                click_x = int(pane_left + info["center"][0])
                click_y = int(pane_top + info["center"][1])
                auto.Click(click_x, click_y)
                time.sleep(0.5)

                # 再次识别窗口更新识别信息
                png_bytes = capture_window(pane_hwnd, mode="print_window")
                ocr_data = self._get_image_text(png_bytes)
                if not ocr_data:
                    raise OCRError("群公告窗口 OCR 未识别到任何文本")

            # 清空输入框并粘贴内容
            input_wx.send_keys(announcement_pane, "{Ctrl}a{Del}")
            input_wx.paste(content)
            time.sleep(0.5)

            # 点击"完成"按钮（OCR 定位）
            if "完成" not in ocr_data:
                raise OCRError(f"OCR 未识别到'完成'按钮，识别到的文本: {list(ocr_data.keys())}")
            info = ocr_data["完成"]
            pane_left, pane_top, _, _ = win32gui.GetWindowRect(pane_hwnd)
            click_x = int(pane_left + info["center"][0])
            click_y = int(pane_top + info["center"][1])
            auto.Click(click_x, click_y)
            time.sleep(0.5)

            # 点击"发布"按钮（WebView 内的按钮，支持 InvokePattern）
            publish_btn = announcement_pane.ButtonControl(Name="发布")
            if not publish_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'发布'按钮")
            publish_btn.GetInvokePattern().Invoke()

            time.sleep(1)

            for i in range(10):
                if not get_hwnd(pane_title):
                    logger.info(f"设置群公告成功: {self.current_name}")
                    return
                time.sleep(3)

            logger.info(f"设置群公告失败: {self.current_name}")
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_room_remark(self, remark: str) -> None:
        """
        设置群聊备注。

        仅群聊可用。群聊的备注仅自己可见。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 使用图片识别定位"备注"文本坐标并点击其下方区域
        3. 在弹出的编辑弹窗中修改备注
        4. 点击"完成"按钮保存
        5. 收回聊天信息面板

        Args:
            remark: 备注内容

        Raises:
            ValueError: remark 为空时抛出
            RuntimeError: 操作失败时抛出
        """
        if not remark:
            raise ValueError("备注不能为空")

        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()

        try:
            # 使用图片识别定位"备注"
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if "备注" not in ocr_data:
                raise OCRError("OCR 未识别到'备注'文本，请确认聊天信息面板已展开")

            info = ocr_data["备注"]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1] + info["height"])

            auto.Click(click_x, click_y)

            time.sleep(0.2)
            input_wx.send_keys(self._win, "{Ctrl}a{Del}")
            time.sleep(0.1)

            # 通过剪贴板粘贴文本
            input_wx.paste(remark)
            input_wx.send_keys(self._win, "{Enter}")

            logger.info(f"设置群聊备注成功: {self.current_name} -> {remark}")

        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_room_nickname(self, nickname: str) -> None:
        """
        设置我在本群的昵称。

        仅群聊可用。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 使用图片识别定位"我在本群的昵称"文本坐标并点击其下方区域
        3. 在弹出的编辑弹窗中修改昵称
        4. 点击"完成"按钮保存
        5. 收回聊天信息面板

        Args:
            nickname: 新的群内昵称

        Raises:
            ValueError: nickname 为空时抛出
            RuntimeError: 操作失败时抛出
        """
        if not nickname:
            raise ValueError("群内昵称不能为空")

        self._ensure_room_chat()
        self._activate_window()

        self._click_chat_info_button()

        try:
            # 使用图片识别定位"我在本群的昵称"
            hwnd = self._win.NativeWindowHandle
            if not hwnd:
                raise RuntimeError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            # OCR 可能识别为完整文本或拆分文本，按优先级匹配
            ocr_key = None
            for candidate in ("我在本群的昵称", "我在本群的呢称"):
                if candidate in ocr_data:
                    ocr_key = candidate
                    break
            if not ocr_key:
                # 模糊匹配：查找包含"本群"和"昵称"的 key
                for key in ocr_data:
                    if "本群" in key and ("昵称" in key or "呢称" in key):
                        ocr_key = key
                        break
            if not ocr_key:
                raise OCRError("OCR 未识别到'我在本群的昵称'文本，请确认聊天信息面板已展开")

            info = ocr_data[ocr_key]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1] + info["height"])

            auto.Click(click_x, click_y)

            time.sleep(0.2)
            input_wx.send_keys(self._win, "{Ctrl}a{Del}")
            time.sleep(0.1)

            # 通过剪贴板粘贴文本
            input_wx.paste(nickname)
            input_wx.send_keys(self._win, "{Enter}")

            # 点击"修改"按钮完成保存
            update_btn = self._win.ButtonControl(Name="修改")
            input_wx.click(update_btn)

            logger.info(f"设置群内昵称成功: {self.current_name} -> {nickname}")

        finally:
            self._close_chat_info_panel()

    # ---- 联系人资料面板操作（仅私聊可用） ----

    def _ensure_contact_chat(self) -> None:
        """确保当前是私聊会话，否则抛出异常"""
        if self.chat_type != "私聊":
            raise RuntimeError("联系人资料操作仅支持私聊会话")

    def _open_contact_profile(self) -> None:
        """
        打开当前私聊联系人的资料面板。

        流程：
        1. 点击"聊天信息"按钮
        2. 点击联系人头像，打开资料面板
        """
        self._ensure_contact_chat()
        self._activate_window()

        self._click_chat_info_button()
        time.sleep(0.5)

        self._click_contact_avatar()
        time.sleep(0.5)

    def _click_profile_menu_item(self, menu_name: str) -> None:
        """
        点击资料面板"更多"菜单中的指定菜单项。

        Args:
            menu_name: 菜单项名称
        """
        self._click_profile_more_button()
        time.sleep(0.3)

        menu_item = self._win.MenuItemControl(
            ClassName="mmui::XMenuView",
            Name=menu_name,
        )
        if not menu_item.Exists(maxSearchSeconds=2):
            input_wx.send_keys(self._win, "{Esc}")
            raise RuntimeError(f"未找到'{menu_name}'菜单项")
        input_wx.click(menu_item)

    def _cleanup_profile(self) -> None:
        """关闭可能残留的弹窗和面板，并收回聊天信息面板"""
        try:
            input_wx.send_keys(self._win, "{Esc}")
            time.sleep(0.2)
            input_wx.send_keys(self._win, "{Esc}")
            time.sleep(0.2)
            input_wx.send_keys(self._win, "{Esc}")
            time.sleep(0.2)
        except Exception:
            pass
        self._close_chat_info_panel()

    def _close_chat_info_panel(self) -> None:
        """点击"聊天信息"按钮收回展开的面板"""
        try:
            btn = self._win.ButtonControl(
                ClassName="mmui::XButton",
                Name="聊天信息",
            )
            if btn.Exists(0, 0):
                input_wx.click(btn)
                time.sleep(0.2)
        except Exception:
            pass

    @PIM.guard
    def get_contact_profile(self) -> dict:
        """
        获取当前私聊联系人的资料信息。

        打开联系人资料面板（mmui::ContactProfileView），
        从面板中提取各字段信息，然后关闭面板。

        Returns:
            dict: {
                "display_name": str,
                "nickname": str,
                "account": str,
                "region": str,
                "remark": str,
                "tags": list[str],
                "description": str,
                "permission": str,
                "common_groups": str,
                "source": str,
                "signature": str,
                "finder_name": str,
            }
        """
        self._activate_window()
        try:
            self._open_contact_profile()
            time.sleep(0.5)

            profile = self._win.GroupControl(
                ClassName="mmui::ContactProfileView",
            )
            if not profile.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到联系人资料面板")

            result = {
                "display_name": None,
                "nickname": None,
                "account": None,
                "region": None,
                "remark": None,
                "tags": [],
                "description": None,
                "permission": None,
                "common_groups": None,
                "source": None,
                "signature": None,
                "finder_name": None,
            }

            # 顶部：显示名
            display_name = profile.TextControl(
                AutomationId="right_v_view.nickname_button_view.display_name_text",
            )
            if display_name.Exists(0, 0):
                val = (display_name.Name or "").strip()
                if val:
                    result["display_name"] = val

            # 顶部：基本信息行（昵称、微信号、地区）
            key_map = {
                "昵称：": "nickname",
                "微信号：": "account",
                "地区：": "region",
            }
            info_center = profile.GroupControl(
                AutomationId="right_v_view.user_info_center_view",
            )
            if info_center.Exists(0, 0):
                for child in info_center.GetChildren():
                    key_ctrl = child.TextControl(
                        AutomationId="right_v_view.user_info_center_view.basic_line_view.basic_line.key_text",
                    )
                    if not key_ctrl.Exists(0, 0):
                        continue
                    key_name = key_ctrl.Name or ""
                    field = key_map.get(key_name)
                    if not field:
                        continue
                    val_ctrl = child.TextControl(
                        ClassName="mmui::ContactProfileTextView",
                    )
                    if val_ctrl.Exists(0, 0):
                        val = (val_ctrl.Name or "").strip()
                        if val:
                            result[field] = val

            # 中间：备注、标签、描述、朋友权限
            line_map = {
                "remark_line": "remark",
                "tag_line": "tags",
                "desc_line": "description",
                "friend_per_line": "permission",
            }
            for line_id, field in line_map.items():
                full_id = f"qt_scrollarea_viewport.mid_ui_.main_part_v_view.line_v_view.{line_id}"
                line = profile.GroupControl(AutomationId=full_id)
                if not line.Exists(0, 0):
                    continue
                val_btn = line.ButtonControl(
                    ClassName="mmui::XMouseEventView",
                )
                if not val_btn.Exists(0, 0):
                    continue
                val = (val_btn.Name or "").strip()
                if field == "tags":
                    result[field] = [t.strip() for t in val.split(",") if t.strip()] if val else []
                elif val:
                    result[field] = val

            # 中间：共同群聊、来源、个性签名
            friend_line_map = {
                "chatroom_intersection": "common_groups",
                "source": "source",
                "sign": "signature",
            }
            for line_id, field in friend_line_map.items():
                full_id = f"qt_scrollarea_viewport.mid_ui_.wx_friend_v_view.line_v_view.{line_id}"
                line = profile.GroupControl(AutomationId=full_id)
                if not line.Exists(0, 0):
                    continue
                val_btn = line.ButtonControl(
                    ClassName="mmui::XMouseEventView",
                )
                if val_btn.Exists(0, 0) and (val_btn.Name or "").strip():
                    result[field] = val_btn.Name.strip()
                    continue
                val_text = line.TextControl(
                    ClassName="mmui::ContactProfileTextView",
                    searchDepth=8,
                )
                if val_text.Exists(0, 0) and (val_text.Name or "").strip():
                    result[field] = val_text.Name.strip()

            # 视频号名称
            finder_view = profile.GroupControl(
                ClassName="mmui::ProfileFinderView",
                AutomationId="qt_scrollarea_viewport.mid_ui_.wx_friend_finder_",
            )
            if finder_view.Exists(0, 0):
                finder_nick = finder_view.TextControl(
                    AutomationId="ProfileFinderUi.nick_name_",
                )
                if finder_nick.Exists(0, 0):
                    val = (finder_nick.Name or "").strip()
                    if val:
                        result["finder_name"] = val

            logger.info(f"获取联系人资料成功: {self.current_name}")
            return result

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_contact_info(self, *,
                         remark: str = None,
                         labels: list = None,
                         phones: list = None,
                         description: str = None,
                         images: list = None) -> None:
        """
        一次性设置当前私聊联系人的备注、标签、电话、描述、图片。

        只打开一次"设置备注和标签"弹窗，按顺序完成所有操作后点击"完成"保存。
        参数为 None 时跳过对应项，不做修改。

        Args:
            remark: 备注名，None 不修改
            labels: 标签列表（覆盖式：先清空再添加），None 不修改，[] 清空所有标签
            phones: 电话列表（覆盖式：先清空再添加），None 不修改，[] 清空所有电话
            description: 描述信息（最大200字符），None 不修改
            images: 图片路径列表（覆盖式：先清空再添加），None 不修改，[] 清空所有图片
        """
        if all(v is None for v in (remark, labels, phones, description, images)):
            return

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            # ---- 1. 备注 ----
            if remark is not None:
                remark_edit = remark_pop.EditControl(
                    ClassName="mmui::XLineEdit",
                    Name="修改备注名",
                )
                if remark_edit.Exists(maxSearchSeconds=2):
                    input_wx.click(remark_edit)
                    input_wx.send_keys(remark_edit, "{Ctrl}a{Del}")
                    if remark:
                        input_wx.paste(remark)

            # 辅助函数：将弹窗滚动区域滚动到底部
            def _scroll_to_bottom() -> None:
                scroll_area = remark_pop.GroupControl(ClassName="QFScrollArea")
                if not scroll_area.Exists(0, 0):
                    return
                rect = scroll_area.BoundingRectangle
                cx = rect.left + rect.width() // 2
                cy = rect.top + rect.height() // 2
                lines = max(rect.height() // 40, 10)
                input_wx.scroll_at(cx, cy, -120 * lines)
                time.sleep(0.3)

            # ---- 2. 标签（覆盖式） ----
            if labels is not None:
                tag_btn = remark_pop.ButtonControl(
                    Name="修改标签", AutomationId="button",
                )
                if tag_btn.Exists(maxSearchSeconds=2):
                    existing_labels = set()
                    tag_text = tag_btn.TextControl(ClassName="mmui::XTextView")
                    if tag_text.Exists(0, 0):
                        name = tag_text.Name
                        if name and name != "搜索或创建标签...":
                            existing_labels = {t.strip() for t in name.split(",") if t.strip()}

                    target_set = set(labels)
                    to_add = [l for l in labels if l not in existing_labels]
                    to_remove = [l for l in existing_labels if l not in target_set]

                    if to_add or to_remove:
                        input_wx.click(tag_btn)

                        for label in to_remove:
                            label_item = remark_pop.ListItemControl(
                                Name=label, searchDepth=8,
                            )
                            if label_item.Exists(maxSearchSeconds=1):
                                input_wx.click(label_item)

                        for label in to_add:
                            tag_edit = remark_pop.EditControl(
                                ClassName="mmui::XValidatorTextEdit", Name="搜索",
                            )
                            if tag_edit.Exists(maxSearchSeconds=2):
                                input_wx.click(tag_edit)
                                input_wx.send_keys(tag_edit, "{Ctrl}a{Del}")
                                input_wx.paste(label)
                                label_item = remark_pop.ListItemControl(
                                    Name=label, searchDepth=8,
                                )
                                if label_item.Exists(maxSearchSeconds=1):
                                    input_wx.click(label_item)
                                input_wx.send_keys(tag_edit, "{Ctrl}a{Del}")

                        title_text = remark_pop.TextControl(
                            ClassName="mmui::XTextView",
                            Name="设置备注和标签",
                        )
                        if title_text.Exists(0, 0):
                            input_wx.click(title_text)

            # ---- 3. 电话（覆盖式） ----
            if phones is not None:
                phone_area = remark_pop.GroupControl(
                    ClassName="mmui::ProfileFormPhoneView",
                )
                if phone_area.Exists(maxSearchSeconds=2):
                    for _ in range(20):
                        phone_field = phone_area.TextControl(
                            ClassName="mmui::XLineField",
                        )
                        if not phone_field.Exists(0, 0):
                            break
                        name = phone_field.Name
                        if not name or name == "填写电话":
                            break
                        separator_view = phone_field.GetParentControl()
                        if separator_view:
                            num_view = separator_view.GetParentControl()
                            if num_view:
                                del_btn = num_view.ButtonControl(Name="删除电话")
                                if del_btn.Exists(0, 0):
                                    input_wx.click(del_btn)
                                    continue
                        break

                    for phone in phones:
                        empty_field = phone_area.TextControl(
                            ClassName="mmui::XLineField", Name="填写电话",
                        )
                        if not empty_field.Exists(0, 0):
                            add_btn = phone_area.ButtonControl(
                                Name="添加电话", AutomationId="button",
                            )
                            if add_btn.Exists(maxSearchSeconds=1):
                                input_wx.click(add_btn)

                        empty_field = phone_area.TextControl(
                            ClassName="mmui::XLineField", Name="填写电话",
                        )
                        if empty_field.Exists(maxSearchSeconds=2):
                            phone_edit = empty_field.EditControl(
                                ClassName="mmui::XLineEdit",
                            )
                            if phone_edit.Exists(0, 0):
                                input_wx.click(phone_edit)
                                vp = phone_edit.GetValuePattern()
                                if vp:
                                    vp.SetValue(phone)
                                else:
                                    input_wx.paste(phone)
                                input_wx.send_keys(phone_edit, "{Tab}")

            # ---- 4. 描述 ----
            if description is not None:
                desc_edit = remark_pop.EditControl(
                    ClassName="mmui::XValidatorTextEdit", Name="修改描述",
                )
                if desc_edit.Exists(maxSearchSeconds=2):
                    _scroll_to_bottom()
                    input_wx.click(desc_edit)
                    input_wx.send_keys(desc_edit, "{Ctrl}a{Del}")
                    if description:
                        input_wx.paste(description[:200])

            # ---- 5. 图片（覆盖式） ----
            if images is not None:
                img_list = remark_pop.GroupControl(
                    AutomationId="desc_img_list_view_",
                )
                _scroll_to_bottom()
                if img_list.Exists(0, 0):
                    for _ in range(20):
                        img_item = img_list.GroupControl(
                            Name="描述图片",
                            AutomationId="desc_img_list_view_.desc_img_button_view",
                        )
                        if not img_item.Exists(0, 0):
                            break
                        img_btn = img_item.ButtonControl(
                            ClassName="mmui::UrlImageView",
                        )
                        if not img_btn.Exists(0, 0):
                            break
                        input_wx.click(img_btn, button="right")
                        menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                        if not menu_win.Exists(maxSearchSeconds=2):
                            break
                        del_item = menu_win.MenuItemControl(
                            ClassName="mmui::XMenuView", Name="删除",
                        )
                        if not del_item.Exists(maxSearchSeconds=1):
                            input_wx.send_keys(self._win, "{Esc}")
                            break
                        input_wx.click(del_item)

                for img_path in images:
                    add_img_btn = remark_pop.GroupControl(
                        Name="添加图片",
                        AutomationId="desc_img_list_view_.add_button_view",
                    )
                    if not add_img_btn.Exists(maxSearchSeconds=2):
                        break
                    input_wx.click(add_img_btn)
                    dlg = auto.WindowControl(ClassName="#32770")
                    if not dlg.Exists(maxSearchSeconds=5):
                        break
                    input_wx.send_keys(dlg, "{Alt}N")
                    edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
                    if not edit.Exists(0, 0):
                        edit = dlg.EditControl(AutomationId="1148")
                    if edit.Exists(maxSearchSeconds=2):
                        edit.GetValuePattern().SetValue(os.path.abspath(img_path))
                        input_wx.send_keys(dlg, "{Alt}O")
                        time.sleep(0.5)

            # ---- 点击"完成"保存 ----
            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton", Name="完成",
            )
            if ok_btn.Exists(maxSearchSeconds=2):
                input_wx.click(ok_btn)

            logger.info(f"设置联系人信息成功: {self.current_name}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_contact_remark(self, remark: str) -> None:
        """
        设置当前私聊联系人的备注名。

        Args:
            remark: 备注名

        Raises:
            ValueError: remark 为空时抛出
            RuntimeError: 操作失败时抛出
        """
        if not remark:
            raise ValueError("remark 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            remark_edit = remark_pop.EditControl(
                ClassName="mmui::XLineEdit",
                Name="修改备注名",
            )
            if not remark_edit.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'修改备注名'编辑框")

            input_wx.click(remark_edit)
            time.sleep(0.2)
            input_wx.send_keys(remark_edit, "{Ctrl}a{Del}")
            time.sleep(0.1)

            input_wx.paste(remark)
            time.sleep(0.3)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'完成'按钮")
            input_wx.click(ok_btn)
            time.sleep(0.3)

            logger.info(f"设置备注成功: {self.current_name} -> {remark}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def add_contact_label(self, labels: list) -> None:
        """
        为当前私聊联系人添加标签。

        Args:
            labels: 标签名列表，如 ["朋友", "同事"]
        """
        if not labels:
            raise ValueError("labels 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            existing_labels = set()
            tag_btn = remark_pop.ButtonControl(
                Name="修改标签",
                AutomationId="button",
            )
            if not tag_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'修改标签'按钮")

            tag_text = tag_btn.TextControl(
                ClassName="mmui::XTextView",
            )
            if tag_text.Exists(maxSearchSeconds=1):
                name = tag_text.Name
                if name and name != "搜索或创建标签...":
                    existing_labels = {t.strip() for t in name.split(",") if t.strip()}

            new_labels = [l for l in labels if l not in existing_labels]
            if not new_labels:
                logger.info(f"所有标签已存在，跳过: {self.current_name} -> {labels}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            input_wx.click(tag_btn)
            time.sleep(0.3)

            for label in new_labels:
                tag_edit = remark_pop.EditControl(
                    ClassName="mmui::XValidatorTextEdit",
                    Name="搜索",
                )
                if not tag_edit.Exists(maxSearchSeconds=3):
                    raise RuntimeError("未找到标签搜索输入框")

                input_wx.click(tag_edit)
                time.sleep(0.2)
                input_wx.send_keys(tag_edit, "{Ctrl}a{Del}")
                time.sleep(0.1)

                input_wx.paste(label)
                time.sleep(0.5)

                label_item = remark_pop.ListItemControl(
                    Name=label,
                    searchDepth=8,
                )
                if label_item.Exists(maxSearchSeconds=1):
                    input_wx.click(label_item)
                    time.sleep(0.3)
                else:
                    logger.info(f"搜索结果中未找到标签，跳过: {label}")

                input_wx.send_keys(tag_edit, "{Ctrl}a{Del}")
                time.sleep(0.2)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.info(f"添加标签成功: {self.current_name} -> {labels}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def remove_contact_label(self, labels: list) -> None:
        """
        移除当前私聊联系人的标签。

        Args:
            labels: 要移除的标签名列表
        """
        if not labels:
            raise ValueError("labels 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            existing_labels = set()
            tag_btn = remark_pop.ButtonControl(
                Name="修改标签",
                AutomationId="button",
            )
            if not tag_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'修改标签'按钮")

            tag_text = tag_btn.TextControl(
                ClassName="mmui::XTextView",
            )
            if tag_text.Exists(maxSearchSeconds=1):
                name = tag_text.Name
                if name and name != "搜索或创建标签...":
                    existing_labels = {t.strip() for t in name.split(",") if t.strip()}

            to_remove = [l for l in labels if l in existing_labels]
            if not to_remove:
                logger.info(f"标签均不存在，跳过: {self.current_name} -> {labels}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            input_wx.click(tag_btn)
            time.sleep(0.3)

            for label in to_remove:
                label_item = remark_pop.ListItemControl(
                    Name=label,
                    searchDepth=8,
                )
                if label_item.Exists(maxSearchSeconds=2):
                    input_wx.click(label_item)
                    time.sleep(0.3)
                else:
                    logger.warning(f"列表中未找到标签项: {label}")

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.info(f"移除标签成功: {self.current_name} -> {labels}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def add_contact_phone(self, phones: list) -> None:
        """
        为当前私聊联系人添加电话号码（增量添加，不删除已有号码）。

        Args:
            phones: 电话号码列表，如 ["13800138000", "13900139000"]
        """
        if not phones:
            raise ValueError("phones 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            # 读取已有电话号码
            existing_phones = set()
            phone_area = remark_pop.GroupControl(
                ClassName="mmui::ProfileFormPhoneView",
            )
            if phone_area.Exists(maxSearchSeconds=2):
                idx = 0
                while True:
                    field = phone_area.TextControl(
                        ClassName="mmui::XLineField",
                        foundIndex=idx + 1,
                    )
                    if not field.Exists(0, 0):
                        break
                    name = field.Name
                    if name and name != "填写电话":
                        existing_phones.add(name.strip())
                    idx += 1

            # 过滤掉已存在的号码
            new_phones = [p for p in phones if p not in existing_phones]
            if not new_phones:
                logger.info(f"所有电话号码已存在，跳过: {self.current_name} -> {phones}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            for phone in new_phones:
                empty_field = phone_area.TextControl(
                    ClassName="mmui::XLineField",
                    Name="填写电话",
                )
                if not empty_field.Exists(0, 0):
                    add_btn = phone_area.ButtonControl(
                        Name="添加电话",
                        AutomationId="button",
                    )
                    if not add_btn.Exists(maxSearchSeconds=2):
                        raise RuntimeError("未找到'添加电话'按钮")
                    input_wx.click(add_btn)
                    time.sleep(0.3)

                empty_field = phone_area.TextControl(
                    ClassName="mmui::XLineField",
                    Name="填写电话",
                )
                if not empty_field.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到空的电话号码输入框")

                phone_edit = empty_field.EditControl(
                    ClassName="mmui::XLineEdit",
                )
                if not phone_edit.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到电话号码编辑框")

                input_wx.click(phone_edit)
                time.sleep(0.2)

                vp = phone_edit.GetValuePattern()
                if vp:
                    vp.SetValue(phone)
                else:
                    input_wx.paste(phone)
                time.sleep(0.3)
                input_wx.send_keys(phone_edit, "{Tab}")
                time.sleep(0.3)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.info(f"添加电话号码成功: {self.current_name} -> {phones}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def add_contact_image(self, images: list) -> None:
        """
        为当前私聊联系人添加备注图片（增量添加，不删除已有图片）。

        Args:
            images: 图片文件路径列表，如 ["C:/a.jpg", "C:/b.png"]
        """
        if not images:
            raise ValueError("images 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            # 滚动到底部，确保"添加图片"按钮可见
            scroll_area = remark_pop.GroupControl(ClassName="QFScrollArea")
            if scroll_area.Exists(0, 0):
                rect = scroll_area.BoundingRectangle
                cx = rect.left + rect.width() // 2
                cy = rect.top + rect.height() // 2
                lines = max(rect.height() // 40, 10)
                input_wx.scroll_at(cx, cy, -120 * lines)
                time.sleep(0.3)

            for img_path in images:
                add_img_btn = remark_pop.GroupControl(
                    Name="添加图片",
                    AutomationId="desc_img_list_view_.add_button_view",
                )
                if not add_img_btn.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到'添加图片'按钮")

                input_wx.click(add_img_btn)
                time.sleep(1)

                dlg = auto.WindowControl(ClassName="#32770")
                if not dlg.Exists(maxSearchSeconds=5):
                    raise RuntimeError("文件选择对话框未弹出")

                input_wx.send_keys(dlg, "{Alt}N")
                time.sleep(0.3)
                edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
                if not edit.Exists(0, 0):
                    edit = dlg.EditControl(AutomationId="1148")
                if not edit.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到文件名输入框")

                abs_path = os.path.abspath(img_path)
                edit.GetValuePattern().SetValue(abs_path)
                time.sleep(0.3)

                input_wx.send_keys(dlg, "{Alt}O")
                time.sleep(1)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'完成'按钮")
            input_wx.click(ok_btn)
            time.sleep(0.3)

            logger.info(f"添加备注图片成功: {self.current_name} -> {images}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def remove_contact_phone(self, phones: list[str]) -> None:
        """
        移除当前私聊联系人的电话号码。

        Args:
            phones: 要移除的电话号码列表，如 ["13800138000"]
        """
        if not phones:
            raise ValueError("phones 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            phone_area = remark_pop.GroupControl(
                ClassName="mmui::ProfileFormPhoneView",
            )
            if not phone_area.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到电话区域")

            # 读取已有电话号码
            existing_phones = set()
            idx = 0
            while True:
                field = phone_area.TextControl(
                    ClassName="mmui::XLineField",
                    foundIndex=idx + 1,
                )
                if not field.Exists(0, 0):
                    break
                name = field.Name
                if name and name != "填写电话":
                    existing_phones.add(name.strip())
                idx += 1

            to_remove = [p for p in phones if p in existing_phones]
            if not to_remove:
                logger.info(f"电话号码均不存在，跳过: {self.current_name} -> {phones}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            for phone in to_remove:
                phone_field = phone_area.TextControl(
                    ClassName="mmui::XLineField",
                    Name=phone,
                )
                if phone_field.Exists(maxSearchSeconds=1):
                    separator_view = phone_field.GetParentControl()
                    if separator_view:
                        num_view = separator_view.GetParentControl()
                        if num_view:
                            del_btn = num_view.ButtonControl(Name="删除电话")
                            if del_btn.Exists(maxSearchSeconds=1):
                                input_wx.click(del_btn)
                                time.sleep(0.3)
                            else:
                                logger.warning(f"未找到删除按钮: {phone}")
                else:
                    logger.warning(f"未找到电话号码项: {phone}")

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.info(f"移除电话号码成功: {self.current_name} -> {phones}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def remove_contact_image(self, indexes: list[int]) -> None:
        """
        删除当前私聊联系人的备注图片（按序号）。

        Args:
            indexes: 要删除的图片序号列表（从 1 开始），如 [1, 3]。
                     按从大到小的顺序删除，避免序号偏移。
        """
        if not indexes:
            raise ValueError("indexes 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            # 滚动到底部，确保图片区域可见
            scroll_area = remark_pop.GroupControl(ClassName="QFScrollArea")
            if scroll_area.Exists(0, 0):
                rect = scroll_area.BoundingRectangle
                cx = rect.left + rect.width() // 2
                cy = rect.top + rect.height() // 2
                lines = max(rect.height() // 40, 10)
                input_wx.scroll_at(cx, cy, -120 * lines)
                time.sleep(0.3)

            img_list = remark_pop.GroupControl(
                AutomationId="desc_img_list_view_",
            )
            if not img_list.Exists(maxSearchSeconds=2):
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == "描述图片":
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            # 按从大到小排序删除，避免删除后序号偏移
            deleted = 0
            for idx in sorted(indexes, reverse=True):
                if idx < 1 or idx > len(img_items):
                    logger.warning(f"图片序号超出范围，跳过: {idx} (共{len(img_items)}张)")
                    continue

                target = img_items[idx - 1]
                img_btn = target.ButtonControl(
                    ClassName="mmui::UrlImageView",
                )
                if not img_btn.Exists(0, 0):
                    continue

                input_wx.click(img_btn, button="right")
                time.sleep(0.5)

                menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                if not menu_win.Exists(maxSearchSeconds=2):
                    continue

                del_item = menu_win.MenuItemControl(
                    ClassName="mmui::XMenuView",
                    Name="删除",
                )
                if not del_item.Exists(maxSearchSeconds=1):
                    input_wx.send_keys(self._win, "{Esc}")
                    continue

                input_wx.click(del_item)
                time.sleep(0.3)
                deleted += 1

            if deleted > 0:
                ok_btn = remark_pop.ButtonControl(
                    ClassName="mmui::XOutlineButton",
                    Name="完成",
                )
                if ok_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(ok_btn)
                    time.sleep(0.3)
                logger.info(f"删除备注图片成功: {self.current_name} -> 删除{deleted}张")
            else:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_contact_star(self) -> None:
        """将当前私聊联系人设为星标朋友"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设为星标朋友")
            time.sleep(0.3)
            logger.info(f"设为星标朋友操作完成: {self.current_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def cancel_contact_star(self) -> None:
        """取消当前私聊联系人的星标朋友"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("不再设为星标朋友")
            time.sleep(0.3)
            logger.info(f"取消星标朋友操作完成: {self.current_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def black_contact(self) -> None:
        """将当前私聊联系人加入黑名单"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("加入黑名单")
            time.sleep(0.5)

            confirm_btn = self._win.ButtonControl(Name="确定")
            if confirm_btn.Exists(maxSearchSeconds=3):
                input_wx.click(confirm_btn)
                time.sleep(0.3)
                logger.info(f"加入黑名单成功: {self.current_name}")
            else:
                logger.warning(f"未找到确认按钮，加入黑名单可能未完成: {self.current_name}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def unblack_contact(self) -> None:
        """将当前私聊联系人移出黑名单"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("移出黑名单")
            time.sleep(0.3)
            logger.info(f"移出黑名单成功: {self.current_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def delete_contact(self) -> None:
        """删除当前私聊联系人（不可逆）"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("删除联系人")
            time.sleep(0.5)

            confirm_btn = self._win.ButtonControl(Name="删除")
            if confirm_btn.Exists(maxSearchSeconds=3):
                input_wx.click(confirm_btn)
                time.sleep(0.3)
                logger.info(f"删除联系人成功: {self.current_name}")
            else:
                logger.warning(f"未找到'删除'确认按钮，删除联系人可能未完成: {self.current_name}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def get_friend_permission(self) -> dict:
        """
        获取当前私聊联系人的朋友权限设置。

        Returns:
            dict: {
                "permission": "chatonly" | "all",
                "hide_my_posts": bool,
                "hide_their_posts": bool,
            }
        """
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置朋友权限")
            time.sleep(0.5)

            perm_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="朋友权限",
            )
            if not perm_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'朋友权限'弹窗")

            result = {
                "permission": "all",
                "hide_my_posts": False,
                "hide_their_posts": False,
            }

            chatonly_item = perm_pop.GroupControl(
                ClassName="mmui::ProfileFormPermissionItemUi",
                Name="仅聊天",
            )
            if chatonly_item.Exists(maxSearchSeconds=1):
                text_icon = chatonly_item.GroupControl(
                    AutomationId="text_separator_v_view.text_icon_h_view",
                )
                if text_icon.Exists(0, 0):
                    children = text_icon.GetChildren()
                    if len(children) >= 2:
                        result["permission"] = "chatonly"

            if result["permission"] == "all":
                hide_my = perm_pop.CheckBoxControl(
                    ClassName="mmui::XSwitchButton",
                    Name="不让他（她）看",
                )
                if hide_my.Exists(maxSearchSeconds=1):
                    toggle = hide_my.GetTogglePattern()
                    if toggle:
                        result["hide_my_posts"] = toggle.ToggleState == 1

                hide_their = perm_pop.CheckBoxControl(
                    ClassName="mmui::XSwitchButton",
                    Name="不看他（她）",
                )
                if hide_their.Exists(maxSearchSeconds=1):
                    toggle = hide_their.GetTogglePattern()
                    if toggle:
                        result["hide_their_posts"] = toggle.ToggleState == 1

            cancel_btn = perm_pop.ButtonControl(Name="取消")
            if cancel_btn.Exists(maxSearchSeconds=1):
                input_wx.click(cancel_btn)
            time.sleep(0.3)

            logger.info(f"获取朋友权限成功: {self.current_name} -> {result}")
            return result

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_friend_permission(self, permission: str = "all",
                              hide_my_posts: bool = False,
                              hide_their_posts: bool = False) -> None:
        """
        设置当前私聊联系人的朋友权限。

        Args:
            permission: "all" 或 "chatonly"
            hide_my_posts: 不让他（她）看我的朋友圈和状态
            hide_their_posts: 不看他（她）的朋友圈和状态
        """
        if permission not in ("all", "chatonly"):
            raise ValueError(f"permission 必须为 'all' 或 'chatonly'，当前: {permission}")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置朋友权限")
            time.sleep(0.5)

            perm_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="朋友权限",
            )
            if not perm_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'朋友权限'弹窗")

            changed = False

            target_name = "仅聊天" if permission == "chatonly" else "聊天、朋友圈、微信运动等"
            target_item = perm_pop.GroupControl(
                ClassName="mmui::ProfileFormPermissionItemUi",
                Name=target_name,
            )
            if not target_item.Exists(maxSearchSeconds=1):
                raise RuntimeError(f"未找到权限选项: {target_name}")

            text_icon = target_item.GroupControl(
                AutomationId="text_separator_v_view.text_icon_h_view",
            )
            already_selected = False
            if text_icon.Exists(0, 0):
                children = text_icon.GetChildren()
                if len(children) >= 2:
                    already_selected = True

            if not already_selected:
                input_wx.click(target_item)
                time.sleep(0.3)
                changed = True

            if permission == "all":
                hide_my_sw = perm_pop.CheckBoxControl(
                    ClassName="mmui::XSwitchButton",
                    Name="不让他（她）看",
                )
                if hide_my_sw.Exists(maxSearchSeconds=1):
                    toggle = hide_my_sw.GetTogglePattern()
                    if toggle:
                        current = toggle.ToggleState == 1
                        if current != hide_my_posts:
                            input_wx.click(hide_my_sw)
                            time.sleep(0.2)
                            changed = True

                hide_their_sw = perm_pop.CheckBoxControl(
                    ClassName="mmui::XSwitchButton",
                    Name="不看他（她）",
                )
                if hide_their_sw.Exists(maxSearchSeconds=1):
                    toggle = hide_their_sw.GetTogglePattern()
                    if toggle:
                        current = toggle.ToggleState == 1
                        if current != hide_their_posts:
                            input_wx.click(hide_their_sw)
                            time.sleep(0.2)
                            changed = True

            if changed:
                ok_btn = perm_pop.ButtonControl(
                    ClassName="mmui::XOutlineButton",
                    Name="完成",
                )
                if ok_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(ok_btn)
                    time.sleep(0.3)
            else:
                cancel_btn = perm_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                    time.sleep(0.2)

            logger.info(f"设置朋友权限成功: {self.current_name} -> permission={permission}, "
                        f"hide_my={hide_my_posts}, hide_their={hide_their_posts}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def collect_contact_image(self, indexes: list[int]) -> int:
        """
        收藏当前私聊联系人的指定备注图片。

        在"设置备注和标签"弹窗中，对指定序号的图片右键点击"收藏"。

        Args:
            indexes: 要收藏的图片序号列表（从 1 开始），如 [1, 3]

        Returns:
            成功收藏的图片数量
        """
        if not indexes:
            raise ValueError("indexes 不能为空")

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            # 滚动到底部，确保图片区域可见
            scroll_area = remark_pop.GroupControl(ClassName="QFScrollArea")
            if scroll_area.Exists(0, 0):
                rect = scroll_area.BoundingRectangle
                cx = rect.left + rect.width() // 2
                cy = rect.top + rect.height() // 2
                lines = max(rect.height() // 40, 10)
                input_wx.scroll_at(cx, cy, -120 * lines)
                time.sleep(0.3)

            img_list = remark_pop.GroupControl(
                AutomationId="desc_img_list_view_",
            )
            if not img_list.Exists(maxSearchSeconds=2):
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return 0

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == "描述图片":
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return 0

            collected = 0
            for idx in indexes:
                if idx < 1 or idx > len(img_items):
                    logger.warning(f"图片序号超出范围，跳过: {idx} (共{len(img_items)}张)")
                    continue

                target = img_items[idx - 1]
                img_btn = target.ButtonControl(
                    ClassName="mmui::UrlImageView",
                )
                if not img_btn.Exists(0, 0):
                    continue

                input_wx.click(img_btn, button="right")
                time.sleep(0.5)

                menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                if not menu_win.Exists(maxSearchSeconds=2):
                    continue

                collect_item = menu_win.MenuItemControl(
                    ClassName="mmui::XMenuView",
                    Name="收藏",
                )
                if not collect_item.Exists(maxSearchSeconds=1):
                    input_wx.send_keys(self._win, "{Esc}")
                    logger.warning(f"右键菜单中未找到'收藏'，跳过第{idx}张")
                    continue

                input_wx.click(collect_item)
                time.sleep(0.5)
                collected += 1

            # 收藏不修改数据，点"取消"关闭弹窗
            cancel_btn = remark_pop.ButtonControl(Name="取消")
            if cancel_btn.Exists(maxSearchSeconds=1):
                input_wx.click(cancel_btn)

            logger.info(f"收藏备注图片成功: {self.current_name} -> 收藏{collected}张")
            return collected

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def save_contact_image(self, indexes: list[int], save_path: str) -> int:
        """
        保存当前私聊联系人的指定备注图片到指定目录。

        在"设置备注和标签"弹窗中，对指定序号的图片右键点击"另存为..."，
        在弹出的系统文件保存对话框中设置保存路径，然后 Alt+S 保存。

        Args:
            indexes: 要保存的图片序号列表（从 1 开始），如 [1, 3]
            save_path: 保存目录路径，如 "C:/download/images"

        Returns:
            保存的图片数量，无图片时返回 0
        """
        if not indexes:
            raise ValueError("indexes 不能为空")

        save_dir = os.path.abspath(save_path)
        os.makedirs(save_dir, exist_ok=True)

        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设置备注和标签")
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name="设置备注和标签",
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'设置备注和标签'弹窗")

            # 滚动到底部，确保图片区域可见
            scroll_area = remark_pop.GroupControl(ClassName="QFScrollArea")
            if scroll_area.Exists(0, 0):
                rect = scroll_area.BoundingRectangle
                cx = rect.left + rect.width() // 2
                cy = rect.top + rect.height() // 2
                lines = max(rect.height() // 40, 10)
                input_wx.scroll_at(cx, cy, -120 * lines)
                time.sleep(0.3)

            img_list = remark_pop.GroupControl(
                AutomationId="desc_img_list_view_",
            )
            if not img_list.Exists(maxSearchSeconds=2):
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return 0

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == "描述图片":
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return 0

            saved = 0

            for idx in indexes:
                if idx < 1 or idx > len(img_items):
                    logger.warning(f"图片序号超出范围，跳过: {idx} (共{len(img_items)}张)")
                    continue

                target = img_items[idx - 1]
                img_btn = target.ButtonControl(
                    ClassName="mmui::UrlImageView",
                )
                if not img_btn.Exists(0, 0):
                    continue

                input_wx.click(img_btn, button="right")
                time.sleep(0.5)

                menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                if not menu_win.Exists(maxSearchSeconds=2):
                    continue

                save_item = menu_win.MenuItemControl(
                    ClassName="mmui::XMenuView",
                    Name="另存为...",
                )
                if not save_item.Exists(maxSearchSeconds=1):
                    input_wx.send_keys(self._win, "{Esc}")
                    continue

                input_wx.click(save_item)
                time.sleep(1)

                # 等待系统文件保存对话框
                dlg = remark_pop.WindowControl(ClassName="#32770")
                if not dlg.Exists(maxSearchSeconds=5):
                    dlg = auto.WindowControl(ClassName="#32770")
                    if not dlg.Exists(maxSearchSeconds=3):
                        continue

                edit = dlg.EditControl(AutomationId="1001")
                if not edit.Exists(maxSearchSeconds=2):
                    input_wx.send_keys(dlg, "{Esc}")
                    continue

                vp = edit.GetValuePattern()
                original_name = vp.Value if vp else ""
                if not original_name:
                    input_wx.send_keys(dlg, "{Esc}")
                    continue
                full_path = os.path.join(save_dir, original_name)
                vp.SetValue(full_path)
                time.sleep(0.3)

                input_wx.send_keys(dlg, "{Alt}S")
                time.sleep(1)

                # 如果弹出覆盖确认，按 Y 确认
                if dlg.Exists(maxSearchSeconds=0.5):
                    input_wx.send_keys(dlg, "{Alt}Y")
                    time.sleep(0.5)

                saved += 1

            # 点击"取消"关闭弹窗（保存图片不需要点完成）
            cancel_btn = remark_pop.ButtonControl(Name="取消")
            if cancel_btn.Exists(maxSearchSeconds=1):
                input_wx.click(cancel_btn)

            logger.info(f"保存备注图片成功: {self.current_name} -> {save_dir} ({saved}张)")
            return saved

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def recommend_contact(self, receiver_nickname: str) -> bool:
        """将当前私聊联系人推荐给另一个朋友（发送名片）"""
        return self.send_card(receiver_nickname)


class SeparateChat(Chat, WeixinWindow):
    """
    独立窗口显示的聊天会话控制。

    继承自 Chat 类，复用所有消息发送和读取逻辑。
    继承自 WeixinWindow 类，复用通用窗口操作（pin/unpin/minimize/maximize/restore/close/activate）。
    独立窗口与主窗口的聊天区域控件结构完全一致
    （chat_message_list、chat_input_field、current_chat_name_label 等），
    但窗口类名不同：
    - 窗口: mmui::ChatSingleWindow, AutomationId="ChatSingleWindow{contact_id}"
    - 标题栏: mmui::TitleBar (置顶/最小化/最大化/关闭)
    """

    WINDOW_CLASS = "mmui::ChatSingleWindow"

    def __init__(self, wx: "Weixin | None", contact_name: str):
        if not contact_name:
            raise ValueError("contact_name 不能为空")
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            Name=contact_name,
            searchDepth=1
        )
        if not self._win.Exists(0, 0):
            raise RuntimeError(f"独立聊天窗口未找到: {contact_name}")
        self.wx = wx

    @property
    def exists(self) -> bool:
        """独立窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=2)

    @property
    def is_pinned(self) -> bool:
        """窗口是否已置顶"""
        return self.is_topmost

    def _activate_window(self) -> None:
        """激活独立聊天窗口（覆盖 Chat 的主窗口激活）"""
        self.activate()

    @PIM.guard
    def send_text(self, content: str, timeout: float = 0) -> MessageStatus:
        self.activate()
        return super().send_text(content, timeout)

    @PIM.guard
    def send_file(self, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        self.activate()
        return super().send_file(file_path, timeout)

    @PIM.guard
    def send_image(self, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        self.activate()
        return super().send_image(file_path, timeout)

    @PIM.guard
    def send_video(self, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        self.activate()
        return super().send_video(file_path, timeout)

    @PIM.guard
    def send_at(self, content: str, at_members: list[str], timeout: float = 0) -> MessageStatus:
        self.activate()
        return super().send_at(content, at_members, timeout)

    @PIM.guard
    def send_collection(self, keyword: str, timeout: float = 0) -> MessageStatus:
        self.activate()
        return super().send_collection(keyword, timeout)

    @PIM.guard
    def send_emotion(self, keyword: str = None, index: int = 1, timeout: float = 0) -> MessageStatus:
        self.activate()
        return super().send_emotion(keyword, index, timeout)

    @PIM.guard
    def send_card(self, nickname: str) -> bool:
        self.activate()
        return super().send_card(nickname)

    @PIM.guard
    def voice_call(self) -> "VoipCallWindow":
        self.activate()
        return super().voice_call()

    @PIM.guard
    def video_call(self) -> "VoipCallWindow":
        self.activate()
        return super().video_call()

    def move_offscreen(self) -> None:
        """将窗口移到屏幕外（不可见但仍处于正常状态）。"""
        hwnd = self._win.NativeWindowHandle
        rect = self._win.BoundingRectangle
        self._offscreen_rect = (rect.left, rect.top,
                                rect.width(), rect.height())
        ctypes.windll.user32.MoveWindow(hwnd, -9999, -9999,
                                        rect.width(), rect.height(), True)

    def move_back(self) -> None:
        """将窗口从屏幕外移回原始位置"""
        if not hasattr(self, '_offscreen_rect') or not self._offscreen_rect:
            return
        hwnd = self._win.NativeWindowHandle
        x, y, w, h = self._offscreen_rect
        ctypes.windll.user32.MoveWindow(hwnd, x, y, w, h, True)
        self._offscreen_rect = None

    @property
    def is_offscreen(self) -> bool:
        """窗口是否在屏幕外"""
        rect = self._win.BoundingRectangle
        return rect.right <= 0

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "SeparateChat(closed)"
        return (f"SeparateChat(chat_type={self.chat_type!r}, "
                f"name={self.current_name!r})")

    def __repr__(self) -> str:
        return self.__str__()


# ======================================================================
# 模块: core
# ======================================================================

"""
┌─────────────────────────────────────────────────────────────────────────────┐
│  mmui::MainWindow (微信主窗口)                              _ □ × (置顶)   │
├────────┬──────────────────┬─────────────────────────────────────────────────┤
│        │  搜索 🔍         │  聊天标题栏                                     │
│        │ XValidatorText   │  current_chat_name_label  (群成员数)  [聊天信息]│
│  N     │  Edit "搜索"     ├─────────────────────────────────────────────────┤
│  a     ├──────────────────┤                                                 │
│  v     │                  │  消息列表 (chat_message_list)                    │
│  i     │  会话列表         │  mmui::RecyclerListView                         │
│  g     │  (session_list)  │                                                 │
│  a     │  mmui::XTableView│  ┌─────────────────────────────────┐            │
│  t     │                  │  │ [头像] 系统消息 (ChatItemView)   │            │
│  o     │ ┌──────────────┐ │  ├─────────────────────────────────┤            │
│  r     │ │ 会话1 [激活]  │ │  │ [头像]  文本气泡 (灰/白=对方)   │            │
│        │ │ 最后一条消息   │ │  │         ChatTextItemView       │            │
│ ┌────┐ │ │ 17:15         │ │  ├─────────────────────────────────┤            │
│ │微信│ │ ├──────────────┤ │  │   文本气泡 (绿=自己)    [头像]  │            │
│ ├────┤ │ │ 会话2         │ │  │   ChatTextItemView              │            │
│ │通讯│ │ │ [图片消息]    │ │  ├─────────────────────────────────┤            │
│ │ 录 │ │ │ 16:30 🔇     │ │  │ [头像]  图片/文件/语音/视频...  │            │
│ ├────┤ │ ├──────────────┤ │  │         ChatImageItemView       │            │
│ │收藏│ │ │ 会话3         │ │  │         ChatFileItemView        │            │
│ ├────┤ │ │ ...           │ │  │         ChatVoiceItemView       │            │
│ │朋友│ │ │               │ │  │         ChatVideoItemView       │            │
│ │ 圈 │ │ ├──────────────┤ │  │         ChatBubbleItemView      │            │
│ ├────┤ │ │ 会话N         │ │  │         ...                     │            │
│ │视频│ │ │               │ │  └─────────────────────────────────┘            │
│ │ 号 │ │ └──────────────┘ │                                                 │
│ ├────┤ │                  ├─────────────────────────────────────────────────┤
│ │搜一│ │                  │  工具栏 (tool_bar_accessible)                    │
│ │ 搜 │ │                  │  [表情Alt+E] [收藏] [文件] [截图Alt+A] [语音]   │
│ ├────┤ │                  ├─────────────────────────────────────────────────┤
│ │手机│ │                  │  输入框 (chat_input_field)                       │
│ ├────┤ │                  │  mmui::ChatInputField                           │
│ │更多│ │                  │                                                 │
│ │    │ │  [快捷操作]      │                                                 │
│ └────┘ │                  │                                    [发送]        │
├────────┴──────────────────┴─────────────────────────────────────────────────┤
│ MainTabBar              Session                    Chat                     │
│ mmui::XTabBarItem       mmui::ChatSessionCell      mmui::XOutlineButton     │
└─────────────────────────────────────────────────────────────────────────────┘

独立窗口:
┌──────────────────────────────┐  ┌──────────────────────┐  ┌────────────────┐
│ mmui::ChatSingleWindow       │  │ mmui::SNSWindow      │  │ mmui::VOIPWindow│
│ (SeparateChat 独立聊天)       │  │ (Moment 朋友圈)      │  │ (VoipCall 通话) │
│ 控件结构与主窗口 Chat 一致     │  │                      │  │                │
│ ┌──────────────────────────┐ │  │ ┌──────────────────┐ │  │ 呼叫者信息      │
│ │ 标题栏 + 消息列表         │ │  │ │ TimeLineListView │ │  │ 通话状态        │
│ │ + 输入框 + 发送           │ │  │ │ (sns_list)       │ │  │ ┌────────────┐ │
│ └──────────────────────────┘ │  │ │ TimelineCell...   │ │  │ │麦克风│挂断 │ │
│                              │  │ └──────────────────┘ │  │ │扬声器│摄像头│ │
│                              │  │ [刷新] [发表]        │  │ └────────────┘ │
└──────────────────────────────┘  └──────────────────────┘  └────────────────┘

┌──────────────────────────┐  ┌──────────────────────────────┐
│ mmui::LoginWindow        │  │ Chrome_WidgetWin_0 "笔记"     │
│ (Login 登录窗口)          │  │ (NoteEditorWindow 笔记编辑)   │
│                          │  │                              │
│ [头像]                   │  │ ┌──────────────────────────┐ │
│ 当前登录用户{昵称}        │  │ │ xeditorInputId           │ │
│                          │  │ │ (富文本编辑器 WebView)     │ │
│ [进入微信]               │  │ │ Ctrl+B/I/U 格式快捷键     │ │
│ [切换账号] [仅传输文件]   │  │ └──────────────────────────┘ │
│         [网络代理设置]    │  │ [标签Ctrl+T] [文件Ctrl+O]    │
└──────────────────────────┘  └──────────────────────────────┘
"""


# ---- 从子模块导入 ----


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---- 从拆分模块导入业务类 ----


class Weixin(WeixinWindow):

    WINDOW_CLASS = "mmui::MainWindow"
    WINDOW_REGEX = "微信|Weixin"
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 1000
    SHORTCUTS = {
        "发送消息": "Enter",
        "语音输入文字": "Ctrl+Win",
        "截图": "Alt+A",
        "锁定": "Ctrl+L",
        "显示窗口": "Ctrl+Alt+W",
    }

    def __init__(
        self, 
        auto_login: bool = False, 
        login_timeout: float = 0,
        background: bool = False, 
        idle_wait: float = 0, 
        lock_input: bool = False, 
        resize: bool = True,
        install_path: Optional[str] = None,
        ocr_engine: str = "wcocr",
        wxocr_weixin_install_path: Optional[str] = None, 
        wxocr_plugin_path: Optional[str] = None
    ):
        """
        Args:
            background:   True 时使用后台模式（通过 SendMessage 发送虚拟鼠标/键盘消息，
                          不需要窗口在前台），默认 False。
            idle_wait:   人类操作等待时间（秒），大于 0 时自动启动物理输入监控，
                          所有 UI 操作方法执行前会等待用户停止物理键盘/鼠标操作达到该秒数。
                          默认 0 表示不等待。
            lock_input:   True 时在自动化操作期间锁定物理键盘鼠标（需管理员权限），
                          默认 False。
            resize:       True 时将微信窗口设置为固定大小（1000x700），
                          False 时保持原窗口大小。默认 True。
            ocr_engine:   OCR 引擎选择
                - "wcocr":    使用微信自带 OCR（默认）
                - "rapidocr": 使用 RapidOCR
            install_path: 微信安装路径，None 时自动检测
            wxocr_weixin_install_path: 微信 OCR 插件带版本号微信安装路径，None 时自动检测
            wxocr_plugin_path:   微信 OCR 插件路径，None 时自动检测
        """
        self.background = background
        globals()['background'] = background # 设置全局后台模式标志
        self.idle_wait = idle_wait
        self.lock_input = lock_input
        if self.idle_wait > 0:
            PIM(idle_wait=self.idle_wait, lock_input=self.lock_input)
            PIM.start()

        if ocr_engine not in ("wcocr", "rapidocr"):
            raise ValueError(f"ocr_engine 参数必须为 'wcocr' 或 'rapidocr'，当前: {ocr_engine!r}")

        self._ocr_engine = ocr_engine
        if self._ocr_engine == "wcocr":
            self.wxocr_weixin_install_path = wxocr_weixin_install_path or get_wechat_install_path(4)
            self.wxocr_plugin_path = wxocr_plugin_path or get_wechat_wxocr_path()
            wcocr.init(self.wxocr_plugin_path, self.wxocr_weixin_install_path)
        else:
            self._rapid_ocr = RapidOCR()

        self.auto_login = auto_login
        self.login_timeout = login_timeout
        self.version = get_wechat_version(4)
        self.install_path = install_path or get_wechat_install_path()
        self._ee = EventEmitter()

        ensure_narrator_registry()
        self._ensure_running()
        self._win: auto.WindowControl = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            RegexName=self.WINDOW_REGEX,
            searchDepth=1
        )
        self.resize = resize
        hwnd = self._win.NativeWindowHandle
        if resize and hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            x, y = rect[0], rect[1]
            ctypes.windll.user32.MoveWindow(hwnd, x, y,
                                            self.WINDOW_WIDTH, self.WINDOW_HEIGHT, True)
        self._main_offscreen_rect = None
        if background and hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            self._main_offscreen_rect = (rect[0], rect[1],
                                         rect[2] - rect[0], rect[3] - rect[1])
            ctypes.windll.user32.MoveWindow(hwnd, -9999, -9999,
                                            rect[2] - rect[0], rect[3] - rect[1], True)

        self.navigator = Navigator(self)
        self.session = Session(self)
        self.file_manager = FileManager(self)
        self.friend_circle = FriendCircle(self)
        logger.info(f"微信客户端({self.version}) - 已连接")

    def __del__(self):
        self.move_back()
        logger.info(f"微信客户端({self.version}) - 已断开")

    def move_back(self) -> None:
        """将主窗口从屏幕外移回原始位置（仅后台模式下有效）"""
        if not self._main_offscreen_rect:
            return
        hwnd = self._win.NativeWindowHandle
        if hwnd:
            x, y, w, h = self._main_offscreen_rect
            ctypes.windll.user32.MoveWindow(hwnd, x, y, w, h, True)
        self._main_offscreen_rect = None

    @staticmethod
    def find_wechat_window() -> list[int]:
        result = []

        def callback(hwnd, _) -> None:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                # 关键：微信窗口标题通常包含“微信”
                if title.lower() in ["微信", "wechat", "weixin"]:
                    result.append(hwnd)

        win32gui.EnumWindows(callback, None)
        return result

    @staticmethod
    def _is_process_running(name: str) -> bool:
        output = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
            text=True, creationflags=0x08000000,
        )
        return name.lower() in output.lower()

    @staticmethod
    def is_exists_window(timeout: float = 30, interval: float = 0.1) -> bool:
        # 检测微信窗口是否存在
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if Weixin.find_wechat_window():
                return True
            time.sleep(interval)
        return False

    def _ensure_running(self) -> None:
        if self.find_wechat_window():
            return

        self.shortcut("显示窗口")
        if self.is_exists_window(timeout=3, interval=0.1):
            return 

        subprocess.Popen([f"{self.install_path}\\Weixin.exe"])
        if self.is_exists_window(timeout=self.login_timeout, interval=0.1):
            return 

        raise LoginError("微信启动超时，请手动登录后重试")

    @property
    def is_online(self) -> bool:
        """微信是否在线（主窗口是否存在）"""
        return self._win.Exists(0, 0)

    @property
    def is_locked(self) -> bool:
        txt = self._win.TextControl(ClassName="mmui::XTextView", Name="Windows 微信已被锁定")
        return txt.Exists(0, 0)

    @property
    def has_session(self) -> bool:
        """会话列表是否可见（即当前是否在微信标签页）"""
        return self.session.is_visible

    @property
    def chat(self) -> Optional[Chat]:
        for aid in Chat.TITLE_LABEL_IDS:
            title = self._win.TextControl(AutomationId=aid)
            if title.Exists(0, 0) and title.Name:
                return Chat(self)
        return None

    @property
    def chats(self) -> list[Chat | SeparateChat]:
        """
        获取所有已打开的聊天窗口对象。

        包括主窗口中的当前聊天（Chat）和所有独立聊天窗口（SeparateChat）。
        通过桌面顶层窗口一次性过滤，避免逐个搜索。
        """
        result: list[Chat | SeparateChat] = []

        # 主窗口中的当前聊天
        main_chat = self.chat
        if main_chat is not None:
            result.append(main_chat)

        # 从桌面一次性获取所有顶层窗口，按类名过滤独立聊天窗口
        for ctrl in auto.GetRootControl().GetChildren():
            if ctrl.ClassName == SeparateChat.WINDOW_CLASS and ctrl.Name:
                try:
                    result.append(SeparateChat(self, ctrl.Name))
                except (RuntimeError, ValueError):
                    pass

        return result

    @PIM.guard
    def open_session(self, nickname: str) -> Chat:
        """通过在会话列表中查找并点击来打开指定会话，返回 Chat 对象"""
        self.activate()
        if not self.has_session:
            self.navigator.switch_to("微信")
        self.session.open(nickname)
        for _ in range(10):
            chat = self.chat
            if chat is not None:
                return chat
            time.sleep(0.3)
        raise RuntimeError(f"打开会话失败: {nickname}")

    @PIM.guard
    def open_session_by_search(self, nickname: str, chat_type: Optional[list[str]] = None, force_search: bool = False) -> Chat:
        """通过搜索打开指定会话，返回 Chat 对象"""
        self.activate()
        if not self.has_session:
            self.navigator.switch_to("微信")
        self.session.open_by_search(nickname, chat_type, force_search)
        # 等待聊天界面加载完成（搜索点击后界面切换需要时间）
        for _ in range(10):
            chat = self.chat
            if chat is not None:
                return chat
            time.sleep(0.3)
        raise RuntimeError(f"打开会话失败: {nickname}")

    def close_session(self, nickname: str) -> None:
        self.session.close(nickname)

    def send_text(self, nickname: str, content: str, timeout: float = 0) -> MessageStatus:
        """发送文本消息"""
        return self.chat_with(nickname).send_text(content, timeout)

    def send_file(self, nickname: str, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        """发送文件，支持单个或多个路径，支持网络 URL"""
        return self.chat_with(nickname).send_file(file_path, timeout)

    def send_image(self, nickname: str, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        """发送图片，支持单个或多个路径，支持网络 URL"""
        return self.chat_with(nickname).send_image(file_path, timeout)

    def send_video(self, nickname: str, file_path: "str | list[str]", timeout: float = 0) -> MessageStatus:
        """发送视频，支持单个或多个路径，支持网络 URL"""
        return self.chat_with(nickname).send_video(file_path, timeout)

    def send_at(self, nickname: str, content: str, at_members: list[str], timeout: float = 0) -> MessageStatus:
        """在群聊中 @指定成员发送消息"""
        return self.chat_with(nickname).send_at(content, at_members, timeout)

    def send_collection(self, nickname: str, keyword: str, timeout: float = 0) -> MessageStatus:
        """发送收藏内容"""
        return self.chat_with(nickname).send_collection(keyword, timeout)

    def send_emotion(self, nickname: str, keyword: str = None, index: int = 1, timeout: float = 0) -> MessageStatus:
        """发送表情，keyword 为 None 时发送自定义表情"""
        return self.chat_with(nickname).send_emotion(keyword, index, timeout)

    def send_card(self, nickname: str, share: str) -> bool:
        """
        将指定联系人的名片发送给接收者。

        Args:
            nickname: 接收名片的联系人昵称
            share: 要分享名片的联系人昵称

        Returns:
            True 发送成功
        """
        return self.chat_with(share).send_card(nickname)

    @PIM.guard
    def create_note(self, content: str) -> None:
        """
        创建笔记并写入内容，完成后关闭笔记窗口。

        content: 笔记内容
        """
        self.activate()
        self.navigator.switch_to("微信")
        note = self.session.new_note()
        note.set_content(content)
        note.save()
        note.close()

    @PIM.guard
    def create_room(self, nickname_list: list[str]) -> None:
        """
        发起群聊。

        nickname_list: 好友昵称列表，至少需要两个好友才能创建群聊。
        """
        self.activate()
        if not self.has_session:
            self.navigator.switch_to("微信")
        self.session.create_room(nickname_list)

    def get_separate_chat(self, contact_name: str) -> Optional[SeparateChat]:
        """
        获取独立窗口的聊天会话。

        contact_name: 联系人名称
        返回 SeparateChat 实例，若窗口不存在则返回 None
        """
        try:
            return SeparateChat(self, contact_name)
        except (RuntimeError, ValueError):
            return None

    def get_separate_chats(self) -> list[SeparateChat]:
        """
        获取所有已打开的独立聊天窗口。

        遍历桌面顶层窗口，返回所有 mmui::ChatSingleWindow 的 SeparateChat 实例。
        """
        result: list[SeparateChat] = []
        skip_names = {"微信", "Weixin"}
        for ctrl in auto.GetRootControl().GetChildren():
            try:
                if ctrl.ClassName == SeparateChat.WINDOW_CLASS and ctrl.Name and ctrl.Name not in skip_names:
                    result.append(SeparateChat(self, ctrl.Name))
            except (RuntimeError, ValueError, Exception):
                pass
        return result

    def chat_with(self, nickname: str, chat_type: Optional[list[str]] = None,
                  force_search: bool = False) -> "Chat | SeparateChat":
        """
        获取与指定联系人/群聊的聊天窗口对象。

        优先查找已打开的独立聊天窗口（SeparateChat），
        找不到则通过主窗口搜索打开会话。

        Args:
            nickname:     联系人或群聊名称
            chat_type:    搜索时优先匹配的分类，如 ["联系人", "群聊"]
            force_search: 是否强制走搜索流程

        Returns:
            Chat 或 SeparateChat 实例
        """
        separate = self.get_separate_chat(nickname)
        if separate is not None:
            return separate
        return self.open_session_by_search(nickname, chat_type, force_search)

    def get_contact_profile(self, nickname: str) -> dict:
        """获取联系人的资料信息"""
        chat = self.chat_with(nickname)
        return chat.get_contact_profile()

    def set_contact_info(self, nickname: str, *,
                         remark: str = None,
                         labels: list = None,
                         phones: list = None,
                         description: str = None,
                         images: list = None) -> None:
        """一次性设置联系人的备注、标签、电话、描述、图片"""
        chat = self.chat_with(nickname)
        chat.set_contact_info(remark=remark, labels=labels, phones=phones,
                              description=description, images=images)

    def set_contact_remark(self, nickname: str, remark: str) -> None:
        """设置联系人的备注名"""
        chat = self.chat_with(nickname)
        chat.set_contact_remark(remark)

    def set_contact_label(self, nickname: str, labels: list[str]) -> None:
        """为联系人设置标签"""
        chat = self.chat_with(nickname)
        chat.set_contact_info(labels=labels)

    def set_contact_phone(self, nickname: str, phones: list[str]) -> None:
        """为联系人设置电话号码"""
        chat = self.chat_with(nickname)
        chat.set_contact_info(phones=phones)

    def set_contact_description(self, nickname: str, description: str) -> None:
        """设置联系人的描述信息"""
        chat = self.chat_with(nickname)
        chat.set_contact_info(description=description)

    def set_contact_image(self, nickname: str, images: list[str]) -> None:
        """设置联系人的备注图片（覆盖式）"""
        chat = self.chat_with(nickname)
        chat.set_contact_info(images=images)

    def add_contact_label(self, nickname: str, labels: list[str]) -> None:
        """为联系人添加标签"""
        chat = self.chat_with(nickname)
        chat.add_contact_label(labels)

    def add_contact_phone(self, nickname: str, phones: list[str]) -> None:
        """为联系人添加电话号码"""
        chat = self.chat_with(nickname)
        chat.add_contact_phone(phones)

    def add_contact_image(self, nickname: str, images: list[str]) -> None:
        """为联系人添加备注图片"""
        chat = self.chat_with(nickname)
        chat.add_contact_image(images)

    def remove_contact_label(self, nickname: str, labels: list[str]) -> None:
        """移除联系人的标签"""
        chat = self.chat_with(nickname)
        chat.remove_contact_label(labels)

    def remove_contact_phone(self, nickname: str, phones: list[str]) -> None:
        """移除联系人的电话号码"""
        chat = self.chat_with(nickname)
        chat.remove_contact_phone(phones)

    def remove_contact_image(self, nickname: str, images: list[int]) -> None:
        """删除联系人的备注图片（按序号）"""
        chat = self.chat_with(nickname)
        chat.remove_contact_image(images)

    def collect_contact_image(self, nickname: str, images: list[int]) -> int:
        """收藏联系人的指定备注图片"""
        chat = self.chat_with(nickname)
        return chat.collect_contact_image(images)

    def save_contact_image(self, nickname: str, images: list[int], save_path: str) -> int:
        """保存联系人的指定备注图片到指定目录"""
        chat = self.chat_with(nickname)
        return chat.save_contact_image(images, save_path)

    def set_contact_star(self, nickname: str) -> None:
        """将联系人设为星标朋友"""
        chat = self.chat_with(nickname)
        chat.set_contact_star()

    def cancel_contact_star(self, nickname: str) -> None:
        """取消联系人的星标朋友"""
        chat = self.chat_with(nickname)
        chat.cancel_contact_star()

    def get_friend_permission(self, nickname: str) -> dict:
        """获取联系人的朋友权限设置"""
        chat = self.chat_with(nickname)
        return chat.get_friend_permission()

    def set_friend_permission(self, nickname: str, permission: str = "all",
                              hide_my_posts: bool = False,
                              hide_their_posts: bool = False) -> None:
        """设置联系人的朋友权限"""
        chat = self.chat_with(nickname)
        chat.set_friend_permission(permission, hide_my_posts, hide_their_posts)

    def black_contact(self, nickname: str) -> None:
        """将联系人加入黑名单"""
        chat = self.chat_with(nickname)
        chat.black_contact()

    def unblack_contact(self, nickname: str) -> None:
        """将联系人移出黑名单"""
        chat = self.chat_with(nickname)
        chat.unblack_contact()

    def delete_contact(self, nickname: str) -> None:
        """删除联系人"""
        chat = self.chat_with(nickname)
        chat.delete_contact()

    def recommend_contact(self, nickname: str, receiver_nickname: str) -> bool:
        """将指定联系人推荐给另一个朋友（发送名片）"""
        chat = self.chat_with(nickname)
        return chat.recommend_contact(receiver_nickname)

    def clear_chat_history(self, nickname: str) -> None:
        """清空指定会话的聊天记录"""
        chat = self.chat_with(nickname)
        chat.clear_chat_history()

    def clear_room_chat_history(self, nickname: str) -> None:
        """清空指定群聊会话的聊天记录"""
        chat = self.chat_with(nickname)
        chat.clear_room_chat_history()

    def exit_room(self, nickname: str) -> None:
        """退出指定群聊"""
        chat = self.chat_with(nickname)
        chat.exit_room()

    def add_room_members(self, nickname: str, members: list[str]) -> None:
        """添加指定群聊的成员"""
        chat = self.chat_with(nickname)
        chat.add_room_members(members)

    def remove_room_members(self, nickname: str, members: list[str]) -> None:
        """移除指定群聊的成员"""
        chat = self.chat_with(nickname)
        chat.remove_room_members(members)

    def pin_room_chat(self, nickname: str) -> None:
        """置顶指定群聊会话"""
        chat = self.chat_with(nickname)
        chat.pin_room_chat()

    def unpin_room_chat(self, nickname: str) -> None:
        """取消置顶指定群聊会话"""
        chat = self.chat_with(nickname)
        chat.unpin_room_chat()

    def mute_room_chat(self, nickname: str) -> None:
        """开启指定群聊的消息免打扰"""
        chat = self.chat_with(nickname)
        chat.mute_room_chat()

    def unmute_room_chat(self, nickname: str) -> None:
        """关闭指定群聊的消息免打扰"""
        chat = self.chat_with(nickname)
        chat.unmute_room_chat()

    def add_room_address_book(self, nickname: str) -> None:
        """将指定群聊保存到通讯录"""
        chat = self.chat_with(nickname)
        chat.add_room_address_book()

    def remove_room_address_book(self, nickname: str) -> None:
        """将指定群聊从通讯录移除"""
        chat = self.chat_with(nickname)
        chat.remove_room_address_book()

    def display_room_member_nickname(self, nickname: str) -> None:
        """显示指定群聊的群成员昵称"""
        chat = self.chat_with(nickname)
        chat.display_room_member_nickname()

    def hidden_room_member_nickname(self, nickname: str) -> None:
        """隐藏指定群聊的群成员昵称"""
        chat = self.chat_with(nickname)
        chat.hidden_room_member_nickname()

    def set_room_info(self, nickname: str, name: str = None,
                      announcement: str = None, remark: str = None,
                      my_nickname: str = None, mute: bool = None,
                      pin: bool = None, save_address_book: bool = None,
                      display_member_nickname: bool = None,
                      fold: bool = None) -> None:
        """一次性设置指定群聊的多项信息"""
        chat = self.chat_with(nickname)
        chat.set_room_info(
            name=name, announcement=announcement, remark=remark,
            my_nickname=my_nickname, mute=mute, pin=pin,
            save_address_book=save_address_book,
            display_member_nickname=display_member_nickname,
            fold=fold,
        )

    def fold_room_chat(self, nickname: str) -> None:
        """折叠指定群聊会话"""
        chat = self.chat_with(nickname)
        chat.fold_room_chat()

    def unfold_room_chat(self, nickname: str) -> None:
        """取消折叠指定群聊会话"""
        chat = self.chat_with(nickname)
        chat.unfold_room_chat()

    def pin_chat(self, nickname: str) -> None:
        """置顶指定会话"""
        chat = self.chat_with(nickname)
        chat.pin_chat()

    def unpin_chat(self, nickname: str) -> None:
        """取消置顶指定会话"""
        chat = self.chat_with(nickname)
        chat.unpin_chat()

    def mute_chat(self, nickname: str) -> None:
        """开启指定会话的消息免打扰"""
        chat = self.chat_with(nickname)
        chat.mute_chat()

    def unmute_chat(self, nickname: str) -> None:
        """关闭指定会话的消息免打扰"""
        chat = self.chat_with(nickname)
        chat.unmute_chat()

    def fold_chat(self, nickname: str) -> None:
        """折叠指定会话"""
        chat = self.chat_with(nickname)
        chat.fold_chat()

    def unfold_chat(self, nickname: str) -> None:
        """取消折叠指定会话"""
        chat = self.chat_with(nickname)
        chat.unfold_chat()

    def set_room_name(self, nickname: str, name: str) -> None:
        """设置指定群聊的名称"""
        chat = self.chat_with(nickname)
        chat.set_room_name(name)

    def set_room_announcement(self, nickname: str, content: str) -> None:
        """设置指定群聊的群公告"""
        chat = self.chat_with(nickname)
        chat.set_room_announcement(content)

    def set_room_remark(self, nickname: str, remark: str) -> None:
        """设置指定群聊的备注"""
        chat = self.chat_with(nickname)
        chat.set_room_remark(remark)

    def set_room_nickname(self, nickname: str, my_nickname: str) -> None:
        """设置我在指定群聊中的昵称"""
        chat = self.chat_with(nickname)
        chat.set_room_nickname(my_nickname)

    def get_screenshot(self) -> bytes:
        """
        对微信主窗口截图，返回 PNG 格式的字节数据。

        前台模式使用 BitBlt，后台模式使用 PrintWindow。
        """
        hwnd = self._win.NativeWindowHandle
        if not hwnd:
            raise RuntimeError("无法获取微信窗口句柄")
        mode = "print_window" if background else "bitblt"
        return capture_window(hwnd, mode=mode)

    def screenshot(self, save_path: str) -> None:
        """
        对微信主窗口截图并保存到指定路径。

        前台模式使用 BitBlt，后台模式使用 PrintWindow。
        前台模式下截图前会自动恢复最小化窗口并激活，确保截图内容完整。

        Args:
            save_path: 保存路径（含文件名），如 "C:\\screenshots\\wx.png"
        """
        hwnd = self._win.NativeWindowHandle
        if not hwnd:
            raise RuntimeError("无法获取微信窗口句柄")
        if not background:
            if self.is_minimized:
                self.restore()
                time.sleep(0.3)
            self.activate()
        dir_path = os.path.dirname(save_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        mode = "print_window" if background else "bitblt"
        png_bytes = capture_window(hwnd, mode=mode)
        with open(save_path, "wb") as f:
            f.write(png_bytes)

    def check_new_msg(self) -> int:
        """
        通过对导航栏微信图标截图 OCR 识别未读消息数量。

        对导航栏的"微信"按钮进行截图，识别红色角标上的数字。
        截图保存为 _debug_check_new_msg.png 方便调试。

        Returns:
            未读消息数量，0 表示无新消息
        """
        hwnd = self._win.NativeWindowHandle
        if not hwnd:
            return 0

        # 获取导航栏微信按钮控件
        tabbar = self.navigator._tabbar
        wx_btn = tabbar.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name="微信",
            searchDepth=5,
        )
        if not wx_btn.Exists(0, 0):
            return 0

        # 截图微信按钮区域
        try:
            png_bytes = capture_control(hwnd, wx_btn, mode="print_window")
            # with open("_debug_check_new_msg.png", "wb") as f:
            #     f.write(png_bytes)
        except Exception:
            return 0

        # OCR 识别角标数字
        try:
            ocr_result = self.get_image_text(png_bytes)
        except Exception:
            return 0

        # 从 OCR 结果中提取数字
        for text in ocr_result:
            text = text.strip()
            if text.isdigit():
                return int(text)
            # 处理 "99+" 等格式
            if text.rstrip("+").isdigit():
                return int(text.rstrip("+"))

        return 0

    # @PIM.guard
    # def lock(self) -> None:
    #     """通过点击菜单锁定微信（已弃用，改用快捷键）"""
    #     self.activate()
    #     more_btn = self.navigator._win.ButtonControl(Name="更多")
    #     if not more_btn.Exists(maxSearchSeconds=2):
    #         raise RuntimeError("未找到更多按钮")
    #     more_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
    #     time.sleep(0.1)
    #
    #     lock_btn = self._win.ButtonControl(ClassName="mmui::XButton", Name="锁定")
    #     if not lock_btn.Exists(maxSearchSeconds=2):
    #         self._win.SendKeys("{Esc}")
    #         raise RuntimeError("弹出菜单中未找到锁定按钮")
    #     lock_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    @PIM.guard
    def lock(self) -> None:
        """锁定微信（Ctrl+L）"""
        self.shortcut("锁定")

    @staticmethod
    def shortcut(name: str) -> None:
        """
        通过快捷键名称执行对应的键盘快捷键。

        支持的快捷键名称（见 Weixin.SHORTCUTS）：
        - "发送消息":     Enter
        - "语音输入文字": Ctrl+Win
        - "截图":         Alt+A
        - "锁定":         Ctrl+L
        - "显示窗口":     Ctrl+Alt+W

        也可以直接传入按键组合字符串，如 "Ctrl+Shift+A"。

        Args:
            name: 快捷键名称或按键组合字符串

        Raises:
            ValueError: 名称未注册且无法解析为按键组合时抛出
        """
        combo = Weixin.SHORTCUTS.get(name, name)
        # 将 "Ctrl+Alt+W" 格式转为 SendKeys 格式 "{Ctrl}{Alt}w"
        _MOD_KEYS = {"ctrl", "alt", "shift", "win"}
        _SPECIAL_KEYS = {
            "enter": "Enter", "tab": "Tab", "esc": "Escape",
            "escape": "Escape", "delete": "Delete", "del": "Delete",
            "backspace": "Backspace", "home": "Home", "end": "End",
        }
        keys = [k.strip().lower() for k in combo.split("+")]
        sendkeys_str = ""
        for key in keys:
            if key in _MOD_KEYS:
                sendkeys_str += "{" + key.capitalize() + "}"
            elif key in _SPECIAL_KEYS:
                sendkeys_str += "{" + _SPECIAL_KEYS[key] + "}"
            elif len(key) == 1:
                sendkeys_str += key
            else:
                raise ValueError(f"无法识别的按键: {key!r}")
        input_wx.send_keys(None, sendkeys_str)

    def wakeup(self) -> None:
        """唤醒微信窗口（Ctrl+Alt+W）"""
        self.shortcut("显示窗口")

    def capture(self) -> None:
        """截图（Alt+A）"""
        self.shortcut("截图")

    def voice_input(self) -> None:
        """语音输入文字（Ctrl+Win）"""
        self.shortcut("语音输入文字")

    def enter(self) -> None:
        """发送消息（Enter）"""
        self.shortcut("发送消息")

    def click(self, control, button: str = "left",
              click: str = "once") -> None:
        """
        点击 uiautomation 控件。

        根据 self.background 属性选择点击方式：
        - background=False: 使用 uiautomation 的 Click（需要窗口在前台）
        - background=True:  使用 SendMessage 发送虚拟鼠标消息（不需要窗口在前台）

        Args:
            control: uiautomation 控件对象
            button:  鼠标键 - "left"(默认) / "right" / "middle"
            click:   点击方式 - "once"(默认) / "double"
        """
        input_wx.click(control, button=button, click=click)

    # ---- 朋友圈快捷方法 ----

    def get_moments(self, count: int = 10, position: str = "top") -> list:
        """获取朋友圈动态列表，委托给 friend_circle"""
        return self.friend_circle.get_moments(count, position)

    def iter_moments(self, count: int = 10, position: str = "top"):
        """逐条获取朋友圈动态（生成器），委托给 friend_circle"""
        yield from self.friend_circle.iter_moments(count, position)

    def like_moment(self, moment: "Moment") -> bool:
        """对指定动态点赞"""
        return self.friend_circle.like(moment)

    def unlike_moment(self, moment: "Moment") -> bool:
        """取消指定动态的点赞"""
        return self.friend_circle.unlike(moment)

    def comment_moment(self, moment: "Moment", content: str) -> bool:
        """对指定动态评论"""
        return self.friend_circle.comment(moment, content)

    def refresh_friend_circle(self) -> None:
        """刷新朋友圈，回到列表顶部并加载最新动态"""
        self.friend_circle.refresh()

    def close_friend_circle(self) -> None:
        """关闭朋友圈窗口"""
        self.friend_circle.close()

    def ocr(self, image: bytes | str) -> dict:
        """
        识别图片中的文本内容。

        ocr 是 get_image_text 的别名，根据初始化时的 ocr 参数自动选择引擎。

        Args:
            image: 图片数据，支持两种类型：
                - str:   图片文件路径
                - bytes: 图片字节数据

        Returns:
            {text: {center, left_top, right_bottom, width, height}} 字典
        """
        return self.get_image_text(image)

    def get_image_text(self, image: bytes | str) -> dict:
        """
        识别图片中的文本内容。

        根据 ocr 参数选择引擎：
        - "wcocr":    使用微信自带 OCR（通过 wcocr 库）
        - "rapidocr": 使用 RapidOCR

        Args:
            image: 图片数据，支持两种类型：
                - str:   图片文件路径
                - bytes: 图片字节数据

        Returns:
            {text: {center, left_top, right_bottom, width, height}} 字典
        """
        if self._ocr_engine == "rapidocr":
            return self._get_image_text_rapidocr(image)
        return self._get_image_text_wcocr(image)

    def _get_image_text_rapidocr(self, image: bytes | str) -> dict:
        """使用 RapidOCR 识别图片"""
        if isinstance(image, str):
            with open(image, "rb") as f:
                image = f.read()
        result = self._rapid_ocr(image)
        data = {}
        if result.boxes is None or result.txts is None:
            return data
        for box, txt in zip(result.boxes, result.txts):
            point = box.tolist()
            data[txt] = {
                "center": (point[0][0] + (point[2][0] - point[0][0]) / 2,
                           point[0][1] + (point[2][1] - point[0][1]) / 2),
                "left_top": (point[0][0], point[0][1]),
                "right_bottom": (point[2][0], point[2][1]),
                "width": point[2][0] - point[0][0],
                "height": point[2][1] - point[0][1],
            }
        return data

    def _get_image_text_wcocr(self, image: bytes | str) -> dict:
        """使用微信 OCR 识别图片"""
        if isinstance(image, str):
            result = wcocr.ocr(image)
        else:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="_pywxauto_ocr_")
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    f.write(image)
                result = wcocr.ocr(tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        data = {}
        if not result or "ocr_response" not in result:
            return data
        for item in result["ocr_response"]:
            txt = item.get("text", "")
            if not txt:
                continue
            left = item["left"]
            top = item["top"]
            right = item["right"]
            bottom = item["bottom"]
            width = right - left
            height = bottom - top
            data[txt] = {
                "center": (left + width / 2, top + height / 2),
                "left_top": (left, top),
                "right_bottom": (right, bottom),
                "width": width,
                "height": height,
            }
        return data

    def _register_handler(self, events: "Event | list[Event] | None",
                         func: callable, once: bool = False) -> callable:
        """内部方法：注册事件处理器到 pyee EventEmitter"""
        if not events:
            event_list = [Event.ALL]
        elif isinstance(events, list):
            event_list = events
        else:
            event_list = [events]

        listen = self._ee.once if once else self._ee.on
        for event in event_list:
            listen(event, func)
        return func

    def on(self, events: "Event | list[Event] | None" = None) -> "callable":
        """
        注册消息事件处理器（装饰器）。

        用法::

            @wx.on(Event.TEXT)
            def on_text(wx, message):
                print(message.content)

            @wx.on([Event.TEXT, Event.IMAGE])
            def on_text_or_image(wx, message):
                print(message.type_label)

            @wx.on()  # 监听所有消息
            def on_all(wx, message):
                print(message)
        """
        def decorator(func):
            return self._register_handler(events, func, once=False)
        return decorator

    def once(self, events: "Event | list[Event] | None" = None) -> "callable":
        """
        注册一次性消息事件处理器（装饰器）。

        回调触发一次后自动移除。

        用法::

            @wx.once(Event.TEXT)
            def on_first_text(wx, message):
                print("第一条文本消息:", message.content)
        """
        def decorator(func):
            return self._register_handler(events, func, once=True)
        return decorator

    def off(self, events: "Event | list[Event] | None" = None, func: "callable | None" = None) -> None:
        """
        移除事件处理器。

        Args:
            events: Event 枚举值或列表，None 表示移除所有事件的处理器
            func:   要移除的回调函数，None 表示移除该事件的所有处理器
        """
        if events is None:
            if func is None:
                self._ee.remove_all_listeners()
            else:
                for event in list(self._ee.event_names()):
                    self._ee.remove_listener(event, func)
            return

        event_list = events if isinstance(events, list) else [events]
        for event in event_list:
            if func is None:
                self._ee.remove_all_listeners(event)
            else:
                self._ee.remove_listener(event, func)

    def _emit(self, message: "Message") -> None:
        """
        触发消息事件，通过 pyee EventEmitter 分发到所有匹配的处理器。

        分发逻辑：
        1. 根据消息类型查找对应的事件类型常量
        2. emit 该事件类型（触发具体类型的处理器）
        3. emit Event.ALL（触发全局处理器）

        回调签名: callback(wx: Weixin, message: Message)
        消息关联的聊天窗口通过 message.chat 获取。
        """
        event_type = _MSG_CLASS_TO_EVENT.get(type(message), Event.OTHER)
        self._ee.emit(event_type, self, message)
        self._ee.emit(Event.ALL, self, message)

    @property
    def has_handlers(self) -> bool:
        """是否注册了任何事件处理器"""
        return bool(self._ee.event_names())

    def add_chat_listen(self, names: "str | list[str] | None" = None) -> list[SeparateChat]:
        """
        注册要监听的聊天窗口。

        Args:
            names: 联系人/群聊名称，支持单个字符串或列表。
                   为 None 时自动发现所有已打开的独立聊天窗口并注册监听。

        Returns:
            成功注册的 SeparateChat 实例列表

        Note:
            后台模式下窗口会自动移到屏幕外，前台模式下保持原位。
        """
        if not hasattr(self, '_listeners'):
            self._chat_listeners: dict[str, SeparateChat] = {}
        self._offscreen = background

        # names 为 None 时，自动发现所有已打开的独立聊天窗口
        if names is None:
            skip_names = {"微信", "Weixin"}
            for ctrl in auto.GetRootControl().GetChildren():
                try:
                    cls_name = ctrl.ClassName
                    name = ctrl.Name
                except Exception:
                    continue
                if cls_name == SeparateChat.WINDOW_CLASS and name and name not in skip_names:
                    if name not in self._chat_listeners or not self._chat_listeners[name].exists:
                        try:
                            chat = SeparateChat(self, name)
                            self._chat_listeners[name] = chat
                            logger.info("已注册监听: [%s] %s", chat.chat_type, name)
                        except (RuntimeError, ValueError):
                            pass
            return list(self._chat_listeners.values())

        if isinstance(names, str):
            names = [names]
        elif isinstance(names, Iterable):
            result: list[SeparateChat] = []
            for name in names:
                if not name:
                    continue

                # 跳过已监听的聊天窗口
                if name in self._chat_listeners and self._chat_listeners[name].exists:
                    result.append(self._chat_listeners[name])
                    continue

                # 尝试获取已打开的独立窗口
                chat = self.get_separate_chat(name)
                if chat is None:
                    # 未打开，通过主窗口搜索并打开独立窗口
                    try:
                        main_chat = self.open_session_by_search(name)
                        chat = main_chat.separate()
                    except Exception as e:
                        logger.error("打开独立窗口失败 [%s]: %s", name, e)
                        continue

                self._chat_listeners[name] = chat
                result.append(chat)
                logger.info("已注册监听: [%s] %s", chat.chat_type, name)

            return result

    def remove_chat_listen(self, names: "str | list[str] | None" = None) -> None:
        """
        移除聊天监听。

        Args:
            names: 要移除的联系人/群聊名称。
                - None: 移除所有监听
                - str: 移除单个监听
                - list[str]: 移除列表中的监听

        移除后如果窗口在屏幕外（offscreen），会自动移回原位。
        """
        if not hasattr(self, '_listeners'):
            return

        if names is None:
            for name, chat in list(self._chat_listeners.items()):
                if chat.exists and chat.is_offscreen:
                    try:
                        chat.move_back()
                    except Exception:
                        pass
                logger.info("已移除监听: %s", name)
            self._chat_listeners.clear()
            return

        if isinstance(names, str):
            names = [names]

        for name in names:
            chat = self._chat_listeners.pop(name, None)
            if chat is not None:
                if chat.exists and chat.is_offscreen:
                    try:
                        chat.move_back()
                    except Exception:
                        pass
                logger.info("已移除监听: %s", name)

    def stop(self) -> None:
        """
        停止消息监听（run/listen）。

        可从其他线程调用，触发 stop_event 使监听循环退出。
        同时将主窗口移回原位。
        """
        if hasattr(self, '_stop_event') and self._stop_event is not None:
            self._stop_event.set()
        self.move_back()

    def run(self, interval: float = 0.1, idle_interval: float = 0.1) -> None:
        """
        启动消息监听（阻塞运行，Ctrl+C 退出）。

        仅监听通过 add_chat_listen 注册的聊天窗口。
        消息通过 on/once 装饰器注册的事件处理器分发。

        通过 RuntimeId（UI Automation 为每个控件分配的唯一标识）进行差异比对，
        精确识别新增消息。

        Args:
            interval:      有新消息时的轮询间隔（秒）
            idle_interval: 无新消息时的轮询间隔（秒）
        """
        if not self.has_handlers:
            raise ValueError(
                "未注册任何事件处理器，请使用 @wx.on(Event) 装饰器注册"
            )
        if not hasattr(self, '_chat_listeners') or not self._chat_listeners:
            raise RuntimeError("未注册任何监听，请先调用 add_chat_listen")

        self._stop_event = threading.Event()
        stop_event = self._stop_event
        msg_queue: Queue[tuple[SeparateChat, Message]] = Queue()
        threads: dict[str, threading.Thread] = {}

        def _watch_chat(chat: SeparateChat, name: str) -> None:
            # 已知消息的 RuntimeId 集合（仅保留当前可见的）
            known_rids: set[tuple] = set()
            # 发送者缓存：{runtime_id: (sender, sender_type, bubble_rect)}
            sender_cache: dict[tuple, tuple] = {}
            first_scan = True

            if self._offscreen:
                chat.move_offscreen()

            while not stop_event.is_set():
                if not chat.exists:
                    break

                try:
                    visible = chat.get_visible_messages(sender_cache=sender_cache)
                except Exception:
                    if stop_event.wait(interval):
                        break
                    continue

                # 当前可见消息的 RuntimeId 集合
                curr_rids = {msg.runtime_id for msg in visible if msg.runtime_id}

                if first_scan:
                    known_rids = curr_rids
                    first_scan = False
                    if stop_event.wait(interval):
                        break
                    continue

                # 新增的 RuntimeId
                new_rids = curr_rids - known_rids

                if not new_rids:
                    # 移除已滚出可见区域的，只保留当前可见的
                    known_rids = curr_rids
                    # sender_cache 同步清理
                    for rid in list(sender_cache):
                        if rid not in curr_rids:
                            del sender_cache[rid]
                    if stop_event.wait(idle_interval):
                        break
                    continue

                # 按消息在列表中的原始顺序推送新消息
                for msg in visible:
                    if msg.runtime_id and msg.runtime_id in new_rids:
                        msg_queue.put((chat, msg))

                # 只保留当前可见的 + 新增的
                known_rids = curr_rids

                if stop_event.wait(interval):
                    break

            if chat.exists and self._offscreen:
                try:
                    chat.move_back()
                except Exception:
                    pass

        # 为每个已注册的监听启动线程
        for name, chat in self._chat_listeners.items():
            if not chat.exists:
                logger.warning("窗口已关闭，跳过: %s", name)
                continue
            t = threading.Thread(
                target=_watch_chat,
                args=(chat, name),
                daemon=True,
                name=f"listen-{name}",
            )
            threads[name] = t
            t.start()
            logger.info("开始监听: [%s] %s", chat.chat_type, name)

        if not threads:
            raise RuntimeError("没有可监听的窗口")

        # 以 ASCII 树形式输出监听列表
        contacts = []
        rooms = []
        for name, chat in self._chat_listeners.items():
            if name not in threads:
                continue
            if chat.chat_type == "群聊":
                rooms.append(name)
            else:
                contacts.append(name)

        tree_lines = ["*监听列表"]
        sections = []
        if contacts:
            sections.append(("私聊", contacts))
        if rooms:
            sections.append(("群聊", rooms))

        for si, (section_name, names) in enumerate(sections):
            is_last_section = si == len(sections) - 1
            branch = "└── " if is_last_section else "├── "
            tree_lines.append(f"{branch}{section_name}")
            prefix = "    " if is_last_section else "│   "
            for ni, name in enumerate(names):
                is_last_name = ni == len(names) - 1
                node = "└── " if is_last_name else "├── "
                tree_lines.append(f"{prefix}{node}{name}")

        logger.info("\n" + "\n".join(tree_lines))
        logger.info("消息监听已启动 (Ctrl+C 退出)...")

        try:
            while not stop_event.is_set():
                # 检查是否所有线程都已退出
                alive = [n for n, t in threads.items() if t.is_alive()]
                if not alive:
                    logger.info("所有监听线程已退出")
                    break

                try:
                    chat, msg = msg_queue.get(timeout=0.1)
                except Empty:
                    continue
                try:
                    self._emit(msg)
                except Exception:
                    logger.exception("事件分发异常 [%s]", chat.current_name)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("正在停止监听线程...")
            stop_event.set()
            for t in threads.values():
                t.join(timeout=3)
            self._stop_event = None
            logger.info("监听已停止")
