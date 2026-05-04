"""
PIM (Physical Input Monitor) - 物理键盘/鼠标输入监控器。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import functools
import threading
import time
from typing import Optional


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
