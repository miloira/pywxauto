"""
pywxauto 工具函数模块。

包含注册表查询、微信路径检测、剪贴板操作、窗口查找等底层工具。
"""

from __future__ import annotations

import fnmatch
import glob
import os
import random
import struct
import urllib
import tempfile
from enum import Enum
from typing import Optional

import requests
import win32clipboard
import win32con
import win32gui
import winreg

from .exceptions import RegistryError

try:
    from . import wcocr
except ImportError:
    wcocr = None

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
