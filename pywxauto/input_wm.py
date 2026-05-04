import re
import fnmatch
import win32gui
import win32con
import win32api

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
