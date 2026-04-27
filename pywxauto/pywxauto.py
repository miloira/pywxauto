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

from __future__ import annotations

import ctypes
from ctypes import Structure, c_uint, c_long, c_int, c_bool, sizeof
import hashlib
import logging
import os
import random
import re
import struct
import subprocess
import tempfile
import threading
import time
import requests
import urllib.parse
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from queue import Queue, Empty
from typing import Optional

import win32api
import win32clipboard
import win32con
import win32gui
import win32ui
import winreg

import numpy as np
import uiautomation as auto

from PIL import Image


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# DROPFILES struct: pFiles(uint), x(long), y(long), fNC(int), fWide(bool)
_DROPFILES_FORMAT = "Illii"
_DROPFILES_SIZE = struct.calcsize(_DROPFILES_FORMAT)


def select_all():
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("A"), 0, 0, 0)
    win32api.keybd_event(ord("A"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def copy():
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("C"), 0, 0, 0)
    win32api.keybd_event(ord("C"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def get_clipboard():
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return data
        return ""
    finally:
        win32clipboard.CloseClipboard()


def set_clipboard(fmt, data):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(fmt, data)
    finally:
        win32clipboard.CloseClipboard()


def simulate_paste():
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("V"), 0, 0, 0)
    win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def copy_text(text):
    if text.isdigit():
        text += "\0"
    set_clipboard(win32con.CF_UNICODETEXT, text)


def copy_files(file_paths):
    header = struct.pack(_DROPFILES_FORMAT, _DROPFILES_SIZE, 0, 0, 0, True)
    files = "\0".join(p.replace("/", "\\") for p in file_paths)
    payload = files.encode("utf-16-le") + b"\0\0\0\0"
    set_clipboard(win32con.CF_HDROP, header + payload)


def paste(content, interval=0):
    if isinstance(content, str):
        copy_text(content)
    elif isinstance(content, list):
        copy_files(content)
    else:
        raise TypeError(f"Not support type: {type(content)}")

    time.sleep(interval)
    simulate_paste()


def recognize_qrcode(image_bytes):
    image_matrix = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(image_matrix, cv2.IMREAD_COLOR)
    detector = cv2.QRCodeDetector()
    content, box, _ = detector.detectAndDecode(image)
    return content


def capture_window(hwnd):
    """获取窗口截图"""
    # 获取窗口的屏幕坐标
    window_rect = win32gui.GetWindowRect(hwnd)
    win_left, win_top, win_right, win_bottom = window_rect
    win_width = win_right - win_left
    win_height = win_bottom - win_top

    # 获取窗口的设备上下文
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    # 创建位图对象保存整个窗口截图
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, win_width, win_height)
    saveDC.SelectObject(saveBitMap)

    # 使用PrintWindow捕获整个窗口（包括被遮挡或最小化的窗口）
    ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

    # 转换为PIL图像
    bmp_info = saveBitMap.GetInfo()
    bmp_str = saveBitMap.GetBitmapBits(True)
    im = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]), bmp_str, "raw", "BGRX", 0, 1)

    # 释放资源
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    return im


class RegistryError(Exception):
    """注册表操作异常"""
    pass


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
        # CreateKeyEx 在键不存在时自动创建，存在时直接打开
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
                # RunningState 值不存在，创建它
                winreg.SetValueEx(key, key_name, 0, winreg.REG_DWORD, 1)
                return True
        finally:
            winreg.CloseKey(key)
    except PermissionError as e:
        raise RegistryError(f"注册表访问被拒绝: {e}")
    except Exception as e:
        raise RegistryError(f"注册表访问失败: {e}")


class SenderType(Enum):
    """消息来源类型"""
    SYSTEM = "system"    # 系统消息（时间戳、拍一拍、撤回等）
    SELF = "self"        # 自己发送的消息
    FRIEND = "friend"    # 好友/对方发送的消息
    OTHER = "other"      # 无法判断来源


class MessageStatus(Enum):
    """消息发送状态"""
    SENT = "sent"            # 已发送（正常状态）
    SENDING = "sending"      # 发送中
    FAILED = "failed"        # 发送失败
    RECEIVED = "received"    # 收到的消息
    UNKNOWN = "unknown"      # 未知状态


class Message:
    """聊天消息基类"""

    def __init__(self, *, sender="", sender_type=SenderType.OTHER,
                 content="", raw_name="",
                 status=MessageStatus.UNKNOWN):
        self.sender = sender
        self.sender_type = sender_type
        self.content = content
        self.raw_name = raw_name
        self.status = status

    @property
    def type_label(self) -> str:
        return "消息"

    def __repr__(self):
        cls = self.__class__.__name__
        status_tag = f", status={self.status.value}" if self.status != MessageStatus.UNKNOWN else ""
        return (f"{cls}(sender_type={self.sender_type.value}, "
                f"sender={self.sender!r}, content={self.content!r}{status_tag})")


class TextMessage(Message):
    """文本消息"""
    @property
    def type_label(self) -> str:
        return "文本消息"


class QuoteMessage(Message):
    """引用消息"""
    @property
    def type_label(self) -> str:
        return "引用消息"


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
        """解析语音 Name -> (content, duration, played)"""
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
        """解析文件 Name -> (content, file_name)"""
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
        """解析位置 Name -> (content, address)"""
        addr = raw_name[2:] if raw_name.startswith("位置") else raw_name
        return addr, addr


class LinkMessage(Message):
    """链接消息"""

    def __init__(self, *, title="", **kw):
        super().__init__(**kw)
        self.title: str = title

    @property
    def type_label(self) -> str:
        return "链接消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str]:
        """解析链接 Name -> (content, title)"""
        parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
        title = parts[1] if len(parts) > 1 else raw_name
        return title, title


class EmotionMessage(Message):
    """表情消息"""
    @property
    def type_label(self) -> str:
        return "表情消息"


class MergeMessage(Message):
    """合并消息（合并转发的聊天记录）"""
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
        """解析名片 Name -> (content, card_name)"""
        name = raw_name[:-5] if raw_name.endswith("_个人名片") else raw_name
        return name, name


class NoteMessage(Message):
    """笔记消息"""
    @property
    def type_label(self) -> str:
        return "笔记消息"


class CardMessage(Message):
    """卡片消息（音乐分享、公众号文章、小程序卡片等）"""

    def __init__(self, *, title="", description="", **kw):
        super().__init__(**kw)
        self.title: str = title
        self.description: str = description

    @property
    def type_label(self) -> str:
        return "卡片消息"

    @staticmethod
    def parse(raw_name: str) -> tuple[str, str, str]:
        """解析卡片 Name -> (content, title, description)"""
        parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
        title = parts[0] if parts else raw_name
        description = parts[1] if len(parts) > 1 else ""
        content = title
        return content, title, description


class SystemMessage(Message):
    """系统消息（时间戳、拍一拍、撤回提示等）"""

    def __init__(self, *, timestamp="", **kw):
        kw.setdefault("sender_type", SenderType.SYSTEM)
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
        """解析通话 Name -> (content, call_type, call_status)"""
        for prefix in ("语音通话", "视频通话"):
            if raw_name.startswith(prefix):
                call_status = raw_name[len(prefix):]
                return raw_name, prefix, call_status
        return raw_name, "", raw_name


class OtherMessage(Message):
    """其他/未识别消息"""
    @property
    def type_label(self) -> str:
        return "其他消息"


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



def _rand_ratio() -> float:
    """返回 0.2~0.6 之间的随机比例，用于模拟人类点击偏移"""
    return random.uniform(0.2, 0.6)


class WeixinWindow:
    """
    微信窗口基类，封装通用的窗口操作。

    子类需要设置 self._win 为 uiautomation 的 WindowControl 实例。
    提供 activate、pin、unpin、minimize、maximize、restore、close 等通用操作，
    支持两种模式：
    - use_message=True（默认）: 通过 Windows 消息 API 操作，不需要窗口可见
    - use_message=False: 通过点击标题栏按钮操作，模拟用户行为
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

    def activate(self):
        """激活窗口（置前并聚焦）"""
        self._window.SetActive()
        self._window.SetFocus()
        time.sleep(0.2)

    def pin(self, use_message: bool = True, simulate_move: bool = True):
        """置顶窗口"""
        if use_message:
            self._window.SetTopmost(True)
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._PIN_BTN_CLASS, Name="置顶",
            )
            if btn.Exists(0, 0):
                btn.Click(simulateMove=simulate_move)

    def unpin(self, use_message: bool = True, simulate_move: bool = True):
        """取消置顶窗口"""
        if use_message:
            self._window.SetTopmost(False)
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._PIN_BTN_CLASS, Name="取消置顶",
            )
            if btn.Exists(0, 0):
                btn.Click(simulateMove=simulate_move)

    def minimize(self, use_message: bool = True, simulate_move: bool = True):
        """最小化窗口"""
        if use_message:
            self._window.Minimize()
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._BTN_CLASS, Name="最小化",
            )
            if not btn.Exists(maxSearchSeconds=1):
                raise RuntimeError("未找到最小化按钮")
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio(),
                      simulateMove=simulate_move)

    def maximize(self, use_message: bool = True, simulate_move: bool = True):
        """最大化/还原窗口"""
        if use_message:
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
                    btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio(),
                              simulateMove=simulate_move)
                    return
            raise RuntimeError("未找到最大化/还原按钮")

    def restore(self):
        """还原窗口"""
        self._window.Restore()

    def close(self, use_message: bool = True, simulate_move: bool = True):
        """关闭窗口"""
        if use_message:
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
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio(),
                      simulateMove=simulate_move)


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

    def _ensure_exists(self):
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError("微信登录窗口未找到")

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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

        # 等待登录窗口消失
        for _ in range(timeout):
            if not self._win.Exists(maxSearchSeconds=1):
                logger.debug("已进入微信")
                return True
            time.sleep(1)

        raise RuntimeError("登录超时，登录窗口未关闭")

    def switch_account(self):
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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    def transfer_only(self):
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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

    def _ensure_proxy_page(self):
        """确保当前在代理设置页面，如果不在则打开"""
        if not self._is_proxy_page_open():
            self.open_proxy_settings()

    def open_proxy_settings(self):
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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

        # 等待代理设置页面出现
        back_btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.PROXY_BACK_BTN_NAME,
        )
        if not back_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("代理设置页面未打开")

    def close_proxy_settings(self):
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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

    def enable_proxy(self):
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
        sw.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    def disable_proxy(self):
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
        sw.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

    def _set_proxy_field(self, name: str, value: str):
        """设置代理表单字段的值"""
        edit = self._find_proxy_edit(name)
        edit.Click(ratioX=0.5, ratioY=0.5)
        time.sleep(0.2)
        edit.SendKeys("{Ctrl}a{Del}")
        time.sleep(0.1)
        vp = edit.GetValuePattern()
        if vp:
            vp.SetValue(value)
        else:
            edit.SendKeys(value)
        time.sleep(0.2)

    def _get_proxy_field(self, name: str) -> str:
        """获取代理表单字段的值"""
        edit = self._find_proxy_edit(name)
        vp = edit.GetValuePattern()
        if vp:
            return vp.Value or ""
        return ""

    def set_proxy(self, address: str = "", port: str = "",
                  username: str = "", password: str = ""):
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

    def save_proxy(self):
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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    def close(self, use_message: bool = True, simulate_move: bool = True):
        """
        关闭登录窗口。

        Args:
            use_message: True — 通过 WindowPattern 关闭（默认）
                         False — 点击标题栏"关闭"按钮
            simulate_move: 是否模拟鼠标移动（仅 use_message=False 时有效）
        """
        self._ensure_exists()
        if use_message:
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
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio(),
                      simulateMove=simulate_move)
        time.sleep(0.3)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "Login(closed)"
        nick = self.nickname
        return f"Login(user={nick!r})"


class SessionItem:
    """会话列表中的一条会话"""

    def __init__(self, *, name="", last_msg="", msg_time="",
                 muted=False, unread="", active=False,
                 _session: "Session | None" = None):
        self.name = name
        self.last_msg = last_msg
        self.msg_time = msg_time
        self.muted = muted
        self.unread = unread       # 未读条数文本，如 "[9条]"
        self.active = active       # 是否为当前选中（激活）的会话
        self._session = _session   # 关联的 Session 实例（用于执行操作）

    def __repr__(self):
        muted_tag = " [免打扰]" if self.muted else ""
        active_tag = " [激活]" if self.active else ""
        return f"SessionItem({self.name!r}, {self.msg_time}{muted_tag}{active_tag})"

    def _require_session(self) -> "Session":
        if self._session is None:
            raise RuntimeError("此 SessionItem 未关联 Session，无法执行操作")
        return self._session

    def pin(self):
        """置顶会话"""
        self._require_session()._session_context_action(self.name, "置顶")

    def unpin(self):
        """取消置顶会话"""
        self._require_session()._session_context_action(self.name, "取消置顶")

    def mark_as_unread(self):
        """标为未读"""
        self._require_session()._session_context_action(self.name, "标为未读")

    def mark_as_read(self):
        """标为已读"""
        self._require_session()._session_context_action(self.name, "标为已读")

    def mute(self):
        """消息免打扰"""
        self._require_session()._session_context_action(self.name, "消息免打扰")

    def unmute(self):
        """允许消息通知"""
        self._require_session()._session_context_action(self.name, "允许消息通知")

    def separate(self):
        """独立窗口显示"""
        self._require_session()._session_context_action(self.name, "独立窗口显示")

    def separate(self) -> "SeparateChat":
        """双击打开独立窗口，返回 SeparateChat 实例"""
        session = self._require_session()
        if session._wx:
            session._wx.activate()
        item = session._ensure_session_visible(self.name)
        item.DoubleClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)
        return SeparateChat(self.name)

    def hide(self):
        """不显示该会话"""
        self._require_session()._session_context_action(self.name, "不显示")

    def delete(self):
        """删除会话（危险操作，会清除聊天记录）"""
        session = self._require_session()
        session._session_context_action(self.name, "删除")
        # 点击确认弹窗中的"删除"按钮
        confirm_btn = session._win.ButtonControl(Name="删除", ClassName="mmui::XOutlineButton")
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到删除确认弹窗")
        confirm_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def open(self):
        """打开该会话"""
        self._require_session().open(self.name)

    def close(self):
        """关闭该会话（如果处于激活状态则取消选中）"""
        self._require_session().close(self.name)


class MomentItem:
    """朋友圈动态条目"""

    def __init__(self, *, type="", sender="", content="",
                 raw_text="", timestamp="", image_count=0,
                 cell_type=""):
        self.type = type              # 动态类型（文本/图片/视频/分享/文本图片/文本视频/文本分享/其他）
        self.sender = sender          # 发送者昵称
        self.content = content        # 文本内容
        self.raw_text = raw_text      # 原始文本（控件 Name 属性）
        self.timestamp = timestamp    # 时间文本（如 "8小时前"）
        self.image_count = image_count  # 图片数量
        self.cell_type = cell_type    # 原始 Cell ClassName（用于调试）

    def __repr__(self):
        return (f"MomentItem(type={self.type!r}, sender={self.sender!r}, "
                f"content={self.content!r}, timestamp={self.timestamp!r})")

    def __str__(self):
        preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        return f"[{self.type}] [{self.timestamp}] {self.sender}: {preview}"


class Moment(WeixinWindow):
    """
    朋友圈（Moments）操作类。

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
        self._wx = wx
        self._win = auto.WindowControl(
            ClassName=self.SNS_WINDOW_CLASS,
            AutomationId=self.SNS_WINDOW_ID,
        )

    @property
    def exists(self) -> bool:
        """朋友圈窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=1)

    def _open_sns_window(self):
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
        self._wx.activate()
        self._wx.navigator.switch_to(self.MOMENT_TAB_NAME)
        time.sleep(1)

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

    @staticmethod
    def _parse_moment_name(raw_name: str, cls_name: str = "") -> MomentItem | None:
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

        return MomentItem(
            type=moment_type,
            sender=sender,
            content=content,
            raw_text=raw_name,
            timestamp=timestamp,
            image_count=image_count,
            cell_type=cls_name,
        )

    def _collect_moments(self, lc) -> list[tuple[str, str]]:
        """
        收集当前可见的动态条目的 (raw_name, cls_name) 列表。
        跳过评论区、辅助行等非动态 Cell。
        """
        items: list[tuple[str, str]] = []
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
                items.append((raw, cls_name))
        return items

    def get(self, count: int = 10, position="top") -> list[MomentItem]:
        """
        获取指定条数的朋友圈动态列表。

        打开朋友圈独立窗口，从 mmui::TimeLineListView (sns_list) 中
        遍历 ListItemControl 提取动态信息。
        当可见条目不足时，通过 PageDown 键滚动加载更多内容，
        直到收集到指定条数或连续多次滚动无新内容为止。

        Args:
            count:    要获取的动态条数，默认 10 条
            position: 起始位置
                - "current": 从当前滚动位置开始采集（默认）
                - "top":     先点击"刷新"回到顶部，再从头采集

        Returns:
            MomentItem 列表
        """
        self._open_sns_window()

        if position == "top":
            # 点击"刷新"按钮回到顶部
            refresh_btn = self._win.ButtonControl(
                ClassName="mmui::XTabBarItem",
                Name="刷新",
            )
            if refresh_btn.Exists(maxSearchSeconds=2):
                refresh_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(2)  # 等待刷新和回到顶部

        lc = self._find_sns_list()

        moments: list[MomentItem] = []
        seen_texts: set[str] = set()
        max_scrolls = count * 3
        no_new_count = 0

        for _ in range(max_scrolls):
            if len(moments) >= count:
                break

            # 收集当前可见的动态
            new_found = False
            for raw, cls_name in self._collect_moments(lc):
                if raw in seen_texts:
                    continue
                item = self._parse_moment_name(raw, cls_name)
                if item:
                    seen_texts.add(raw)
                    moments.append(item)
                    new_found = True
                if len(moments) >= count:
                    break

            if len(moments) >= count:
                break

            if not new_found:
                no_new_count += 1
                if no_new_count >= 5:
                    break
            else:
                no_new_count = 0

            # 滚动列表：先确保列表有焦点，再用 Down 键滚动
            lc.SetFocus()
            time.sleep(0.2)
            lc.SendKeys("{PageDown}")
            time.sleep(1)

        return moments[:count]

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
            win32api.SetCursorPos((cx, cy))
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
            time.sleep(2)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
            time.sleep(1)
        else:
            # 默认发布：左键点击"发表"按钮
            publish_tab.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

    def publish_text(self, content: str) -> bool:
        """
        发布纯文本朋友圈。

        流程:
        1. 打开朋友圈独立窗口
        2. 长按工具栏"发表"按钮 3 秒，进入纯文本发布模式
        3. 在文本输入框中输入内容
        4. 长按"发表"按钮 3 秒确认发布
        5. 等待发布完成

        Args:
            content: 要发布的文本内容，不能为空

        Returns:
            True 发布成功

        Raises:
            ValueError: content 为空时抛出
            RuntimeError: 发布过程中出现异常时抛出
        """
        if not content or not content.strip():
            raise ValueError("发布内容不能为空")

        # 1. 打开朋友圈窗口
        self._open_sns_window()

        # 2. 长按"发表"按钮 3 秒，进入纯文本发布模式
        panel = self._open_publish_panel(text_only=True)
        time.sleep(0.5)

        # 3. 找到文本输入框并输入内容
        edit = self._find_publish_input(panel)
        edit.Click(ratioX=0.5, ratioY=0.5)
        time.sleep(0.3)

        # 清空输入框（如果有残留内容）
        edit.SendKeys("{Ctrl}a{Del}")
        time.sleep(0.2)

        # 通过剪贴板粘贴文本，避免 SendKeys 丢字或特殊字符问题
        paste(content)
        time.sleep(0.5)

        # 4. 点击"发表"按钮
        publish_btn = self._find_publish_button(panel)
        publish_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

        # 5. 等待发布面板消失（表示发布成功）
        for _ in range(30):
            if not panel.Exists(maxSearchSeconds=1):
                logger.debug("朋友圈文本发布成功")
                return True
            time.sleep(1)

        raise RuntimeError("发布超时，发布面板未关闭")

    def cancel_publish(self):
        """
        取消当前发布操作。

        如果发布面板已打开，点击"取消"按钮关闭面板。
        """
        self._open_sns_window()
        panel = self._win.GroupControl(
            ClassName=self.PUBLISH_PANEL_CLASS,
            AutomationId=self.PUBLISH_PANEL_ID,
        )
        if not panel.Exists(maxSearchSeconds=1):
            return  # 面板未打开，无需取消

        cancel_btn = self._find_cancel_button(panel)
        cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    # ---- 工具栏按钮名称 ----
    REFRESH_BTN_NAME = "刷新"

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

    def refresh(self):
        """
        刷新朋友圈。

        点击工具栏"刷新"按钮，回到列表顶部并加载最新动态。
        """
        self._open_sns_window()
        btn = self._find_toolbar_button(self.REFRESH_BTN_NAME)
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(2)

    def __str__(self) -> str:
        return "Moment(朋友圈)"


def _is_url(path: str) -> bool:
    """判断路径是否为网络 URL"""
    return path.startswith("http://") or path.startswith("https://")


def _download_to_temp(url: str, timeout: int = 60) -> str:
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


def _parse_session_name(raw: str, session: "Session | None" = None) -> SessionItem:
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
    # 提取未读数
    m = re.search(r"\[(\d+)条\]", raw)
    if m:
        item.unread = m.group(0)
    return item


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

    def _ensure_exists(self):
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError("通话窗口未找到")

    @property
    def _toolbar(self):
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

    def toggle_mic(self):
        """切换麦克风开关"""
        btn = self._find_toolbar_button("麦克风已开", "麦克风已关")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def toggle_speaker(self):
        """切换扬声器开关"""
        btn = self._find_toolbar_button("扬声器已开", "扬声器已关")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def toggle_camera(self):
        """切换摄像头开关（仅视频通话）"""
        btn = self._find_toolbar_button("摄像头已开", "摄像头已关", "无摄像头")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def cancel(self):
        """取消通话（呼叫中未接通时）"""
        btn = self._find_toolbar_button("取消")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def hangup(self):
        """挂断通话（通话中）"""
        btn = self._find_toolbar_button("挂断")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def end_call(self):
        """结束通话（自动识别取消/挂断）"""
        try:
            btn = self._find_toolbar_button("取消", "挂断")
        except RuntimeError:
            raise RuntimeError("未找到取消或挂断按钮")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def switch_to_video(self):
        """切换到视频通话（通话中可用）"""
        btn = self._find_toolbar_button("切换到视频通话")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def pin(self):
        """置顶窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::PinnedButton", Name="置顶",
        )
        if btn.Exists(0, 0):
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.2)

    def minimize(self):
        """最小化通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="最小化",
        )
        if btn.Exists(0, 0):
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.2)

    def maximize(self):
        """最大化通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="最大化",
        )
        if btn.Exists(0, 0):
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.2)

    def close(self):
        """关闭通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="关闭",
        )
        if btn.Exists(0, 0):
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

    def _refresh_win(self):
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

    def _ensure_exists(self):
        self._refresh_win()
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError("笔记编辑窗口未找到")

    def activate(self):
        self._ensure_exists()
        super().activate()

    # -- 笔记窗口特有的 pin/unpin（Chrome WebView 按钮无 ClassName 区分） --

    def pin(self, **kwargs):
        """置顶窗口（通过标题栏按钮）"""
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="置顶")
        if btn.Exists(0, 0):
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.2)

    def unpin(self, **kwargs):
        """取消置顶窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="取消置顶")
        if btn.Exists(0, 0):
            btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.2)

    @property
    def is_pinned(self) -> bool:
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="取消置顶")
        return btn.Exists(0, 0)

    def minimize(self, **kwargs):
        """最小化窗口（Chrome WebView 优先用窗口 API）"""
        self._ensure_exists()
        self._win.Minimize()
        time.sleep(0.2)

    def maximize(self, **kwargs):
        """最大化/还原窗口"""
        self._ensure_exists()
        if self._win.IsMaximize():
            self._win.Restore()
        else:
            self._win.Maximize()
        time.sleep(0.2)

    def close(self, **kwargs):
        """关闭笔记窗口（窗口有两个关闭按钮，取可见的）"""
        self._ensure_exists()
        btns = self._win.GetChildren()
        for child in btns:
            btn = child.ButtonControl(Name="关闭")
            if btn.Exists(0, 0):
                rect = btn.BoundingRectangle
                if rect.width() > 0 and rect.height() > 0:
                    btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

    def focus_editor(self, force_click: bool = True):
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
                container.Click(ratioX=0.5, ratioY=0.3)
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

    def set_content(self, text: str):
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

    def type_text(self, text: str):
        """
        在编辑器中输入文本（追加到当前光标位置）。

        text: 要输入的文本
        """
        self.focus_editor()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到笔记编辑器输入控件")
        editor.SendKeys(text)
        time.sleep(0.2)

    def clear(self):
        """清空编辑器内容"""
        self.focus_editor()
        editor = self._editor
        if editor.Exists(maxSearchSeconds=2):
            editor.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.2)

    def select_all(self):
        """全选编辑器内容"""
        self.focus_editor()
        self._editor.SendKeys("{Ctrl}a")
        time.sleep(0.1)

    # -- 富文本格式快捷键 --
    # 底部工具栏渲染在 WebView 内部，不暴露为 UI Automation 控件，
    # 因此通过键盘快捷键操作格式。

    def begin_voice_input(self):
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

    def end_voice_input(self):
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

    def add_file(self, file_path: str):
        """
        通过 Ctrl+O 打开文件选择对话框，输入路径并确认添加文件。

        file_path: 文件绝对路径
        """
        self.focus_editor()
        self._editor.SendKeys("{Ctrl}O")
        time.sleep(1)

        # 系统文件选择对话框
        dlg = auto.WindowControl(ClassName="#32770")
        if not dlg.Exists(maxSearchSeconds=5):
            raise RuntimeError("文件选择对话框未弹出")

        # Alt+N 激活文件名输入框，通过 ValuePattern 直接设置路径
        dlg.SendKeys("{Alt}N")
        time.sleep(0.3)
        edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
        if not edit.Exists(0, 0):
            edit = dlg.EditControl(AutomationId="1148")
        edit.GetValuePattern().SetValue(file_path)
        time.sleep(0.3)
        # Alt+O 点击打开
        dlg.SendKeys("{Alt}O")
        time.sleep(0.5)

    def bold(self):
        """加粗（Ctrl+B）"""
        self.focus_editor(force_click=False)
        self._editor.SendKeys("{Ctrl}B")
        time.sleep(0.1)

    def italic(self):
        """斜体（Ctrl+I）"""
        self.focus_editor(force_click=False)
        self._editor.SendKeys("{Ctrl}I")
        time.sleep(0.1)

    def underline(self):
        """下划线（Ctrl+U）"""
        self.focus_editor(force_click=False)
        self._editor.SendKeys("{Ctrl}U")
        time.sleep(0.1)

    def highlight(self):
        """高亮（Ctrl+Shift+H）"""
        self.focus_editor(force_click=False)
        self._editor.SendKeys("{Ctrl}{Shift}H")
        time.sleep(0.1)

    def undo(self):
        """撤销（Ctrl+Z）"""
        self.focus_editor(force_click=False)
        self._editor.SendKeys("{Ctrl}z")
        time.sleep(0.1)

    def redo(self):
        """重做（Ctrl+Y）"""
        self.focus_editor(force_click=False)
        self._editor.SendKeys("{Ctrl}y")
        time.sleep(0.1)

    def new_line(self):
        """换行（Enter）"""
        self.focus_editor()
        self._editor.SendKeys("{Enter}")
        time.sleep(0.1)

    def save(self):
        """保存笔记（Ctrl+S）"""
        self.focus_editor(force_click=False)
        self._editor.SendKeys("{Ctrl}s")
        time.sleep(0.3)

    def add_tags(self, *tags: str):
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
            self._editor.SendKeys("{Ctrl}T")
            time.sleep(1)
            # 标签弹窗内的输入框不暴露为 UI Automation 控件，
            # 需要通过窗口级别 SendKeys 输入
            auto.SendKeys(tag)
            time.sleep(0.3)
            auto.SendKeys("{Down}")
            auto.SendKeys("{Enter}")
            time.sleep(0.3)
        # 按 Esc 关闭标签弹窗
        auto.SendKeys("{Esc}")
        time.sleep(0.2)

    def paste(self):
        """粘贴剪贴板内容（Ctrl+V）"""
        self.focus_editor()
        self._editor.SendKeys("{Ctrl}v")
        time.sleep(0.2)

    def paste_file(self, file_path: str):
        """
        通过剪贴板粘贴文件到笔记中。

        file_path: 文件路径
        """
        self.focus_editor()
        paste([file_path])
        time.sleep(0.5)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "NoteEditorWindow(closed)"
        content = self.content
        preview = content[:30] + "..." if len(content) > 30 else content
        return f"NoteEditorWindow(content={preview!r})"


class FileManager:
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
    DELETE_MENU_ITEM_NAME = "删除"

    def __init__(self, wx: "Weixin"):
        self._wx = wx
        self._file_manager_window: Optional[auto.WindowControl] = None

    def _find_window(self) -> Optional[auto.WindowControl]:
        """查找并激活聊天文件窗口（独立窗口）"""
        self._file_manager_window = auto.WindowControl(
            Name=self.WINDOW_NAME, searchDepth=1
        )
        if self._file_manager_window.Exists(maxSearchSeconds=3):
            self._file_manager_window.SetActive()
            return self._file_manager_window
        return None

    def open(self, filter_type: str = "") -> bool:
        """
        打开聊天文件管理器窗口。

        Args:
            filter_type: 文件类型筛选，可选值:
                - "全部"、"文档"、"表格"、"图片"、"视频"等
                - "": 不筛选（默认）
        """
        self._wx.activate()

        # 先关闭已有的文件管理器窗口
        self.close()

        # 通过导航栏 TabBar 缩小搜索范围，点击"更多"按钮
        self._wx.navigator.switch_to("更多")

        # 点击"聊天文件"按钮
        chat_file_btn = self._wx.window.ButtonControl(
            Name="聊天文件", searchDepth=10
        )
        if not chat_file_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到'聊天文件'按钮")

        chat_file_btn.Click(simulateMove=False)
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

        filter_btn.Click(simulateMove=False)
        time.sleep(0.5)
        return True

    def close(self, method: str = "event"):
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
                close_btn.Click(simulateMove=False)
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
        file_cell.RightClick(simulateMove=False, waitTime=0.3)
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

        save_as_item.Click(simulateMove=False, waitTime=0.3)
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
        auto.SendKeys("{Alt}s", waitTime=0.5)
        if not save_dialog.Exists(maxSearchSeconds=2):
            return True
        else:
            auto.SendKeys("{Esc}", waitTime=0.3)
            return False

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
        file_cell.RightClick(simulateMove=False, waitTime=0.3)
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

        delete_item.Click(simulateMove=False, waitTime=0.3)
        time.sleep(0.5)

        # 在确认对话框中查找"删除"或"确定"按钮并点击
        # 微信 v4 的删除确认弹窗使用 mmui::XOutlineButton，Name="删除"
        confirm_btn = None

        # 优先查找 mmui::XOutlineButton 的"删除"按钮
        delete_btn = self._file_manager_window.ButtonControl(
            ClassName="mmui::XOutlineButton", Name="删除",
        )
        if delete_btn.Exists(maxSearchSeconds=2):
            delete_btn.Click(simulateMove=False)
            time.sleep(0.5)
            return True
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

    def __str__(self) -> str:
        fm_win = auto.WindowControl(Name=self.WINDOW_NAME, searchDepth=1)
        if fm_win.Exists(0, 0):
            return "FileManager(open)"
        return "FileManager(closed)"


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
        self._wx = wx
        self._win = wx.window
        self._tabbar = self._win.ToolBarControl(ClassName="mmui::MainTabBar", searchDepth=5)

    def switch_to(self, tab_name: str):
        if tab_name not in self.TABS:
            raise ValueError(f"未知标签页: {tab_name}，可选: {list(self.TABS.keys())}")

        if tab_name not in ["手机", "更多"]:
            btn = self._tabbar.ButtonControl(ClassName="mmui::XTabBarItem", Name=self.TABS[tab_name], searchDepth=1)
        else:
            btn = self._tabbar.ButtonControl(ClassName="mmui::MainTabBarSettingView", Name=self.TABS[tab_name], searchDepth=1)

        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

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
        self._wx = wx
        self._win = wx.window

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

    def click(self, name: str):
        """通过 AutomationId 精确点击指定会话"""
        item = self._win.ListItemControl(
            ClassName="mmui::ChatSessionCell",
            AutomationId=f"session_item_{name}",
        )
        if not item.Exists(maxSearchSeconds=2):
            raise RuntimeError(f"会话列表中未找到: {name}")
        item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def _get_search_edit(self) -> auto.EditControl:
        return self._win.EditControl(
            ClassName="mmui::XValidatorTextEdit",
            Name="搜索",
        )

    def search(self, keyword: str, chat_type: Optional[list[str]] = None):
        """搜索并打开会话（search_and_select 的别名，失败时抛异常）"""
        if not self.search_and_select(keyword, chat_type):
            raise RuntimeError(f"搜索未找到结果: {keyword}")

    def open_by_search(self, name: str, chat_type: Optional[list[str]] = None):
        """
        打开指定名称的会话。
        如果当前聊天对象已经是目标会话，则不做任何操作。
        否则优先在会话列表中直接点击，找不到则通过搜索打开。
        """
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
            item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)
            return
        # 列表中没有，走搜索
        self.search(name, chat_type)

    def scroll(self, direction: str = "down", clicks: int = 3):
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

    @staticmethod
    def _session_key(s: SessionItem) -> tuple:
        """会话的唯一标识，用 (name, last_msg, msg_time) 组合"""
        return (s.name, s.last_msg, s.msg_time)

    def all(self, step: int = 5, max_scrolls: int = 500) -> list[SessionItem]:
        """
        通过滚动获取完整的会话列表（支持重名会话）。

        去重策略：通过相邻批次的重叠区域判断新会话。
        每次按固定次数 Down 键滚动，将新一屏的会话列表与上一批末尾对比，
        找到重叠位置后只追加重叠之后的新会话。
        使用 (name, last_msg, msg_time) 组合作为会话标识，
        以正确处理同名会话。

        step: 每次按 Down 键的次数（固定滚动幅度，不受窗口大小影响）
        max_scrolls: 最大滚动轮次

        Returns:
            按出现顺序排列的完整会话列表
        """
        self._wx.activate()
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到会话列表控件")

        time.sleep(0.1)
        lc.SetFocus()
        time.sleep(0.2)

        # 滚动到顶部
        scroll_pattern = lc.GetScrollPattern()
        if scroll_pattern:
            scroll_pattern.SetScrollPercent(-1, 0)
            time.sleep(0.3)
        else:
            lc.SendKeys("{Home}")
            time.sleep(0.3)

        # 收集第一屏
        all_sessions: list[SessionItem] = []
        prev_visible: list[SessionItem] = self.visible()
        all_sessions.extend(prev_visible)
        no_new_count = 0

        for _ in range(max_scrolls):
            # 检查是否已滚动到底部
            sp = lc.GetScrollPattern()
            if sp:
                v_percent = sp.VerticalScrollPercent
                if v_percent >= 100 or v_percent < 0:
                    break

            # 按固定次数 Down 键滚动
            lc.SendKeys("{Down}" * step)

            curr_visible = self.visible()
            if not curr_visible:
                no_new_count += 1
                if no_new_count >= 3:
                    break
                continue

            # 找重叠位置：在 curr_visible 中找到 prev_visible 最后一个会话的位置
            overlap_idx = -1
            if prev_visible:
                last_key = self._session_key(prev_visible[-1])
                for i, s in enumerate(curr_visible):
                    if self._session_key(s) == last_key:
                        overlap_idx = i

            if overlap_idx >= 0:
                new_sessions = curr_visible[overlap_idx + 1:]
            else:
                new_sessions = curr_visible

            if new_sessions:
                all_sessions.extend(new_sessions)
                no_new_count = 0
            else:
                no_new_count += 1
                if no_new_count >= 3:
                    break

            prev_visible = curr_visible

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

        lc.SetFocus()
        time.sleep(0.2)

        # 先滚动到顶部
        scroll_pattern = lc.GetScrollPattern()
        if scroll_pattern:
            scroll_pattern.SetScrollPercent(-1, 0)
        else:
            lc.SendKeys("{Home}")
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

            lc.SendKeys("{Down}" * step)

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

    def _right_click_session(self, name: str):
        """右键点击指定会话，弹出上下文菜单"""
        item = self._ensure_session_visible(name)
        item.RightClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def _click_context_menu_item(self, menu_name: str):
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
            self._win.SendKeys("{Esc}")
            raise RuntimeError(f"菜单中未找到: {menu_name}")
        menu_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def _session_context_action(self, name: str, menu_name: str):
        """对指定会话执行右键菜单操作"""
        self._wx.activate()
        self._right_click_session(name)
        self._click_context_menu_item(menu_name)

    def pin(self, name: str):
        """置顶会话"""
        self._session_context_action(name, "置顶")

    def unpin(self, name: str):
        """取消置顶会话"""
        self._session_context_action(name, "取消置顶")

    def mark_as_unread(self, name: str):
        """标为未读"""
        self._session_context_action(name, "标为未读")

    def mark_as_read(self, name: str):
        """标为已读"""
        self._session_context_action(name, "标为已读")

    def mute(self, name: str):
        """消息免打扰"""
        self._session_context_action(name, "消息免打扰")

    def unmute(self, name: str):
        """允许消息通知"""
        self._session_context_action(name, "允许消息通知")

    def separate(self, name: str):
        """独立窗口显示"""
        self._session_context_action(name, "独立窗口显示")

    def hide(self, name: str):
        """不显示该会话"""
        self._session_context_action(name, "不显示")

    def close(self, name: str):
        """关闭指定会话：如果该会话处于激活状态，点击一下取消选中"""
        self._wx.activate()
        item = self._ensure_session_visible(name)
        try:
            pattern = item.GetSelectionItemPattern()
            if not pattern or not pattern.IsSelected:
                return
        except Exception:
            return
        item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def open(self, name: str):
        """通过在会话列表中查找并点击来打开指定会话，如果已激活则不操作"""
        self._wx.activate()
        item = self._ensure_session_visible(name)
        try:
            pattern = item.GetSelectionItemPattern()
            if pattern and pattern.IsSelected:
                return
        except Exception:
            pass
        item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def delete(self, name: str):
        """删除会话（危险操作，会清除聊天记录）"""
        self._session_context_action(name, "删除")
        confirm_btn = self._win.ButtonControl(
            Name="删除", ClassName="mmui::XOutlineButton",
        )
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到删除确认弹窗")
        confirm_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def search_and_select(self, keyword: str, chat_type: Optional[list[str]] = None) -> bool:
        """
        在搜索框中输入关键词并点击第一个匹配结果。
        返回是否成功找到并点击了结果。

        keyword: 搜索关键词
        chat_type: 优先匹配的分类，如 ["联系人", "群聊", "功能"]
        """
        chat_type = chat_type or ["联系人", "群聊", "功能"]
        edit = self._get_search_edit()
        edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)
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
                    result_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.3)
                    return True
        return False

    def cancel_search(self):
        """取消搜索（按 Esc 退出搜索模式）"""
        self._win.SendKeys("{Esc}")
        time.sleep(0.2)

    def search_contact(self, keyword: str) -> bool:
        """搜索联系人并打开会话"""
        return self.search_and_select(keyword, chat_type=["联系人"])

    def search_group(self, keyword: str) -> bool:
        """搜索群聊并打开会话"""
        return self.search_and_select(keyword, chat_type=["群聊"])

    def _click_quick_action_button(self):
        """点击快捷操作按钮"""
        self._wx.activate()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name="快捷操作",
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到快捷操作按钮")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def _click_quick_action_item(self, item_name: str):
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
        item.Click()
        time.sleep(0.3)

    def _quick_action(self, item_name: str):
        """执行快捷操作"""
        self._click_quick_action_button()
        self._click_quick_action_item(item_name)

    def create_room(self, nickname_list: list[str]):
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
            fresh_picker.SetActive()
            fresh_picker.SetFocus()
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
            search_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)
            search_edit.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.3)
            search_edit.SendKeys(nickname, interval=0.05)
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

            contact_row.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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
        confirm_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    def add_friend(self, keyword: str, message: Optional[str] = None, remark: Optional[str] = None,
                   permission: Optional[str] = None, hide_my_posts: bool = False,
                   hide_their_posts: bool = False):
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
        search_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.2)
        search_edit.GetValuePattern().SetValue(keyword)
        time.sleep(0.3)
        search_btn = add_friend_win.ButtonControl(
            ClassName="mmui::XOutlineButton", Name="搜索",
        )
        if not search_btn.Exists(maxSearchSeconds=1):
            raise RuntimeError("未找到搜索按钮")
        search_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(1)

        # --- 第2步：点击"添加到通讯录" ---
        add_btn = add_friend_win.ButtonControl(Name="添加到通讯录")
        if not add_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到'添加到通讯录'按钮，可能搜索无结果")
        add_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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
                msg_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.1)
                msg_edit.SendKeys("{Ctrl}a{Del}")
                time.sleep(0.1)
                msg_edit.GetValuePattern().SetValue(message)
                time.sleep(0.2)

        # 填写备注
        if remark is not None:
            remark_edit = verify_win.EditControl(
                ClassName="mmui::XLineEdit", Name="修改备注",
            )
            if remark_edit.Exists(maxSearchSeconds=1):
                remark_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.1)
                remark_edit.SendKeys("{Ctrl}a{Del}")
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
                perm_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.2)

        # 设置朋友圈和状态开关
        if hide_my_posts:
            sw = verify_win.CheckBoxControl(
                ClassName="mmui::XSwitchButton", Name="不让他（她）看",
            )
            if sw.Exists(maxSearchSeconds=1):
                toggle = sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 0:
                    sw.Click(ratioX=0.5, ratioY=0.5)
                    time.sleep(0.2)

        if hide_their_posts:
            sw = verify_win.CheckBoxControl(
                ClassName="mmui::XSwitchButton", Name="不看他（她）",
            )
            if sw.Exists(maxSearchSeconds=1):
                toggle = sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 0:
                    sw.Click(ratioX=0.5, ratioY=0.5)
                    time.sleep(0.2)

        # --- 第4步：点击确定 ---
        confirm_btn = verify_win.ButtonControl(
            Name="确定", ClassName="mmui::XOutlineButton",
        )
        if not confirm_btn.Exists(maxSearchSeconds=1):
            raise RuntimeError("未找到确定按钮")
        confirm_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

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
        self._wx = wx
        self._win = wx.window

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

    def clear_input(self):
        """清空输入框"""
        field = self._input_field
        if field.Exists(maxSearchSeconds=2):
            field.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.1)

    # -- 发送消息 --

    # ClassName -> 消息类型映射（供状态检测使用）
    _TEXT_CLASS_NAMES = {"mmui::ChatTextItemView"}
    _FILE_CLASS_NAMES = {"mmui::ChatFileItemView"}
    _IMAGE_CLASS_NAMES = {"mmui::ChatImageItemView"}
    _VIDEO_CLASS_NAMES = {"mmui::ChatVideoItemView"}

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

        list_rect = lc.BoundingRectangle
        list_center_x = (list_rect.left + list_rect.right) // 2

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
            sender, sender_type = self._detect_sender(
                ctrl, list_center_x, self.current_name or "对方",
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

    def check_file_message_status(self) -> MessageStatus:
        """检测最后一条自己发的文件消息的发送状态。"""
        ctrl = self._find_last_self_message_ctrl(self._FILE_CLASS_NAMES)
        if not ctrl:
            return MessageStatus.UNKNOWN
        return self._check_status_by_prefix(ctrl.Name, space_sep=False)

    def check_image_message_status(self) -> MessageStatus:
        """检测最后一条自己发的图片消息的发送状态。"""
        ctrl = self._find_last_self_message_ctrl(self._IMAGE_CLASS_NAMES)
        if not ctrl:
            return MessageStatus.UNKNOWN
        return self._check_status_by_prefix(ctrl.Name, space_sep=True)

    def check_video_message_status(self) -> MessageStatus:
        """检测最后一条自己发的视频消息的发送状态。"""
        ctrl = self._find_last_self_message_ctrl(self._VIDEO_CLASS_NAMES)
        if not ctrl:
            return MessageStatus.UNKNOWN
        return self._check_status_by_prefix(ctrl.Name, space_sep=True)

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

    def send_text(self, content: str) -> MessageStatus:
        """
        在当前会话中发送文本消息，返回发送状态。

        通过剪贴板粘贴输入文本，避免 SendKeys 丢字或特殊字符问题。
        """

        if self._wx:
            self._wx.activate()
        self.clear_input()
        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天输入框")

        # 通过剪贴板粘贴文本
        paste(content)
        time.sleep(0.2)

        self._win.SendKeys("{Enter}")

        # 发送后校验：输入框应已清空
        remaining = self._get_input_value()
        if remaining:
            raise RuntimeError(
                f"发送后输入框未清空: Value={remaining!r}，消息可能未发出"
            )

        return self.check_text_message_status(content)

    def send_file(self, file_path: str) -> MessageStatus:
        """
        在当前会话中发送文件，返回发送状态。

        支持本地文件路径和网络 URL（http/https），
        网络资源会先下载到临时目录再发送。

        粘贴后通过 TextPattern.DocumentRange 的长度校验文件是否已粘贴，
        发送后校验文档长度是否已归零。
        """
        tmp_file = None
        if _is_url(file_path):
            tmp_file = _download_to_temp(file_path)
            file_path = tmp_file

        try:
            self.clear_input()
            paste([file_path])

            # 发送前校验：文档长度应大于 0（说明文件已粘贴）
            doc_len = self._get_input_doc_length()
            if doc_len == 0:
                raise RuntimeError("文件粘贴校验失败: 输入框文档长度为 0，文件可能未粘贴成功")

            self._win.SendKeys("{Enter}")

            # 发送后校验：文档长度应归零
            remaining_len = self._get_input_doc_length()
            if remaining_len > 0:
                raise RuntimeError(
                    f"发送后输入框未清空: 文档长度={remaining_len}，文件可能未发出"
                )

            return self.check_file_message_status()
        finally:
            # 清理临时文件
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass

    def send_at(self, content: str, at_members: list[str]) -> MessageStatus:
        """
        在当前群聊会话中 @指定成员并发送消息，返回发送状态。

        at_members: 要 @ 的成员昵称列表，传 ["所有人"] 可 @所有人
        content:    消息正文（追加在 @成员 之后）
        """
        self.clear_input()
        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天输入框")

        self._add_at_members(field, at_members)

        if content:
            paste(content)
            time.sleep(0.2)

        self._win.SendKeys("{Enter}")

        # 发送后校验：输入框应已清空
        remaining = self._get_input_value()
        if remaining:
            raise RuntimeError(
                f"发送后输入框未清空: Value={remaining!r}，文件可能未发出"
            )

        return self.check_text_message_status()

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

    def _open_collection_panel(self):
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
        if detail_list.Exists(maxSearchSeconds=1):
            return detail_list

        # 查找工具栏
        toolbar = self._win.ToolBarControl(
            AutomationId="tool_bar_accessible",
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

        fav_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

        # 等待收藏面板出现
        if not detail_list.Exists(maxSearchSeconds=5):
            raise RuntimeError("收藏选择面板未打开")

        return detail_list

    def _close_collection_panel(self):
        """
        关闭收藏选择面板。

        点击面板中的"取消"按钮关闭面板。
        """
        cancel_btn = self._win.ButtonControl(
            ClassName=self.FAV_CANCEL_CLASS,
            Name=self.FAV_CANCEL_NAME,
        )
        if cancel_btn.Exists(maxSearchSeconds=1):
            cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

    def _find_collection_item(self, detail_list, keywords) -> Optional[auto.ListItemControl]:
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

    def send_collection(self, keyword: str) -> bool:
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

        Returns:
            True 发送成功

        Raises:
            ValueError: keyword 为空时抛出
            RuntimeError: 未找到匹配的收藏项或发送失败时抛出
        """
        if not keyword:
            raise ValueError("keyword 不能为空")

        if self._wx:
            self._wx.activate()

        # 1. 打开收藏选择面板
        self._open_collection_panel()
        time.sleep(0.5)

        # 2. 在搜索框中输入关键词
        search_edit = self._find_fav_search_edit()
        search_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)
        search_edit.GetValuePattern().SetValue(keyword)
        time.sleep(1)  # 等待搜索结果加载

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

        matched_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

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

        send_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

        # 6. 验证面板已关闭（表示发送成功）
        check_list = self._win.ListControl(
            ClassName=self.FAV_DETAIL_LIST_CLASS,
            AutomationId=self.FAV_DETAIL_LIST_ID,
        )
        if check_list.Exists(maxSearchSeconds=1):
            raise RuntimeError("发送收藏失败，选择面板未关闭")

        logger.debug("收藏发送成功")
        return True

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

    def send_emotion(self, keyword: str = None, index: int = 1) -> bool:
        """
        在当前会话中发送表情。

        当 keyword 不为 None 时，通过搜索关键词发送表情；
        当 keyword 为 None 时，发送自定义表情列表中第 index 个表情。

        Args:
            keyword: 表情搜索关键词，如 "哈喽"、"开心" 等。
                为 None 时发送自定义表情。
            index: 选择第几个表情，从 1 开始，默认为 1。

        Returns:
            True 发送成功

        Raises:
            ValueError: index < 1 时抛出
            RuntimeError: 未找到控件或发送失败时抛出
        """
        if index < 1:
            raise ValueError("index 必须 >= 1")

        if self._wx:
            self._wx.activate()

        try:
            # 1. 打开表情面板
            self._open_emoji_panel()
            time.sleep(0.3)

            popover = self._get_emoji_popover()

            if keyword is not None:
                # 搜索表情模式
                # 2. 点击"搜索表情"标签
                self._click_emoji_search_tab(popover)
                time.sleep(0.3)

                # 3. 在搜索框中输入关键词
                search_edit = self._find_emoji_search_edit(popover)
                search_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.2)
                # 清空已有内容后键盘输入，确保触发搜索
                search_edit.SendKeys("{Ctrl}a", waitTime=0.1)
                search_edit.SendKeys(keyword, waitTime=0.1)
                time.sleep(1.5)  # 等待搜索结果加载（Chromium 渲染）

                # 4. 在搜索结果中点击第 index 个表情
                popover = self._get_emoji_popover()
                self._click_emoji_search_result(popover, index)
            else:
                # 自定义表情模式
                # 2. 点击"自定义表情"标签
                self._click_custom_emoji_tab(popover)
                time.sleep(0.3)

                # 3. 在自定义表情列表中点击第 index 个表情
                popover = self._get_emoji_popover()
                self._click_custom_emoji_item(popover, index)

            time.sleep(0.5)

            # 验证表情面板已关闭（表示发送成功）
            emoji_popover = auto.WindowControl(
                ClassName=self.EMOJI_POPOVER_CLASS,
                AutomationId=self.EMOJI_POPOVER_ID,
            )
            if emoji_popover.Exists(maxSearchSeconds=1):
                self._close_emoji_panel()
                label = "自定义表情" if keyword is None else "表情"
                raise RuntimeError(f"发送{label}失败，表情面板未关闭")

            logger.debug("表情发送成功")
            return True

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
        )
        if not popover.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到表情弹窗")
        return popover

    def _open_emoji_panel(self):
        """
        打开表情选择面板。

        点击工具栏中的"发送表情"按钮。
        如果面板已打开则直接返回。
        """
        # 检查面板是否已打开（表情弹窗是独立窗口）
        emoji_popover = auto.WindowControl(
            ClassName=self.EMOJI_POPOVER_CLASS,
            AutomationId=self.EMOJI_POPOVER_ID,
        )
        if emoji_popover.Exists(maxSearchSeconds=0.5):
            return

        # 查找工具栏
        toolbar = self._win.ToolBarControl(
            AutomationId="tool_bar_accessible",
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

        emoji_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

        # 等待表情弹窗出现
        if not emoji_popover.Exists(maxSearchSeconds=5):
            raise RuntimeError("表情选择面板未打开")

    def _close_emoji_panel(self):
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
                emoji_popover.SendKeys("{Esc}")
                time.sleep(0.3)
        except Exception:
            # 兜底：向主窗口发送 Esc
            self._win.SendKeys("{Esc}")
            time.sleep(0.3)

    def _click_emoji_search_tab(self, popover: auto.WindowControl):
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

        search_tab.Click()

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
    ):
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
        for child in items:
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

    def _collect_emotion_items(self, control, result: list):
        """递归收集 ListItemControl 表情项。"""
        if control.ControlType == auto.ControlType.ListItemControl:
            name = control.Name or ""
            if "表情" in name:
                result.append(control)
                return
        for child in control.GetChildren():
            self._collect_emotion_items(child, result)

    def _click_custom_emoji_tab(self, popover: auto.WindowControl):
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

        rect = custom_tab.BoundingRectangle
        auto.Click(
            int(rect.left + rect.width() / 2),
            int(rect.top + rect.height() / 2),
        )

    def _click_custom_emoji_item(
        self, popover: auto.WindowControl, index: int,
    ):
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

        target = emoji_items[index - 1]
        try:
            target.GetInvokePattern().Invoke()
        except Exception:
            rect = target.BoundingRectangle
            if rect.width() > 0 and rect.height() > 0:
                auto.Click(
                    int(rect.left + rect.width() / 2),
                    int(rect.top + rect.height() / 2),
                )
            else:
                raise RuntimeError(
                    f"第 {index} 个自定义表情不可见（offscreen），无法点击"
                )

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

        if self._wx:
            self._wx.activate()

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

            logger.debug(f"名片发送成功: {contact_name} -> {receiver_nickname}")
            return True

        except Exception:
            # 6. 点击"发送"按钮‘
            pass
        except Exception:
            # 出错时尝试关闭可能残留的弹窗
            self._cleanup_send_card()
            raise

    def _click_chat_info_button(self):
        """点击聊天标题栏右上角的"聊天信息"按钮"""
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name="聊天信息",
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'聊天信息'按钮")
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def _click_contact_avatar(self):
        """点击聊天信息面板中的联系人头像"""
        avatar = self._win.ButtonControl(
            ClassName="mmui::ChatMemberCell",
            AutomationId="single_chat_member_cell",
        )
        if not avatar.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到联系人头像")
        avatar.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def _click_profile_more_button(self):
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
                    child.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    return

        raise RuntimeError("未找到资料面板'更多'按钮")

    def _click_recommend_contact(self):
        """点击弹出菜单中的"把他推荐给朋友" """
        menu_item = self._win.MenuItemControl(
            ClassName="mmui::XMenuView",
            Name="把他推荐给朋友",
        )
        if not menu_item.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'把他推荐给朋友'菜单项")
        menu_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def _search_and_select_receiver(self, receiver_nickname: str):
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
        search_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)
        search_edit.SendKeys("{Ctrl}a{Del}")
        time.sleep(0.2)
        paste(receiver_nickname)
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
        contact_row.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

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

        send_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    def _click_picker_send_button(self):
        """点击"微信发送给"弹窗中的"发送"按钮"""
        # confirm_btn 位于 SPDetailView（右侧详情面板）下，
        # 选择联系人后面板会刷新重建，旧的控件引用会失效。
        # 关键：每次重试都必须从桌面根节点重新查找 SessionPickerWindow，
        # 彻底绕过 uiautomation 的控件缓存问题。
        send_btn = None
        for attempt in range(8):
            time.sleep(0.5)
            try:
                # 每次都从桌面根节点重新查找，获取全新的控件引用
                fresh_picker = auto.WindowControl(
                    ClassName="mmui::SessionPickerWindow",
                )
                if not fresh_picker.Exists(maxSearchSeconds=2):
                    continue
                fresh_picker.SetActive()
                fresh_picker.SetFocus()
                time.sleep(0.3)
                # 从全新的窗口引用中查找发送按钮
                btn = fresh_picker.ButtonControl(
                    AutomationId="confirm_btn",
                )
                if btn.Exists(maxSearchSeconds=1):
                    send_btn = btn
                    break
            except Exception:
                continue

        if send_btn is None:
            raise RuntimeError("未找到'发送'按钮")

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

        send_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    def _cleanup_send_card(self):
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
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.3)
        except Exception:
            pass

        try:
            self._win.SendKeys("{Esc}")
            time.sleep(0.2)
            self._win.SendKeys("{Esc}")
            time.sleep(0.2)
        except Exception:
            pass

    def _add_at_members(self, chat_input: auto.EditControl,
                        at_members: list[str]):
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
                chat_input.Click(
                    waitTime=0.1,
                    ratioX=_rand_ratio(), ratioY=_rand_ratio(),
                )

            if member == "所有人":
                chat_input.SendKeys("@", waitTime=0.3)
            else:
                chat_input.SendKeys(f"@{member}", waitTime=0.3)

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
                auto.SendKeys("{Enter}", waitTime=0.5)
            elif len(fuzzy) > 1:
                names = [c.Name for c in fuzzy]
                raise RuntimeError(f"@群成员模糊匹配到多个: {names}")
            else:
                raise RuntimeError(f"@群成员失败，未找到: {member}")

    def _click_voip_menu(self, menu_name: str):
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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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
            self._win.SendKeys("{Esc}")
            raise RuntimeError(f"通话菜单中未找到: {menu_name}")
        item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.3)

    def voice_call(self) -> "VoipCallWindow":
        self._click_voip_menu("语音通话")
        return VoipCallWindow()

    def video_call(self) -> "VoipCallWindow":
        self._click_voip_menu("视频通话")
        return VoipCallWindow()

    def separate(self) -> "SeparateChat":
        """
        将当前聊天会话打开为独立窗口，返回 SeparateChat 实例。

        通过双击会话列表中的对应 SessionItem 打开独立窗口。
        等待独立窗口出现后返回 SeparateChat 对象。
        """
        if self._wx:
            self._wx.activate()
        
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
        
        item.DoubleClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

        # 等待独立窗口出现并返回
        try:
            return SeparateChat(contact_name)
        except RuntimeError:
            raise RuntimeError(f"独立窗口未成功打开: {contact_name}")

    @property
    def _message_list(self) -> auto.ListControl:
        return self._win.ListControl(
            ClassName="mmui::RecyclerListView",
            AutomationId="chat_message_list",
        )

    def get_visible_messages(self) -> list[Message]:
        """
        获取当前可见的消息列表，返回具体消息子类实例。

        消息项为 ListItemControl，通过 ClassName 区分类型，
        通过头像控件位置判断 SenderType。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return []

        list_rect = lc.BoundingRectangle
        list_center_x = (list_rect.left + list_rect.right) // 2

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
            "mmui::ChatMusicItemView": LinkMessage,
            "mmui::ChatMiniProgramItemView": LinkMessage,
            "mmui::ChatItemView": SystemMessage,
        }

        chat_name = self.current_name or "对方"

        messages: list[Message] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue

            ui_cls = ctrl.ClassName or ""
            raw_name = ctrl.Name
            msg_cls = cls_map.get(ui_cls)

            # ChatBubbleItemView 是通用气泡，需要二次分类
            if ui_cls == "mmui::ChatBubbleItemView":
                msg_cls = self._classify_bubble(raw_name)

            if msg_cls is None:
                msg_cls = OtherMessage

            # 系统消息
            if msg_cls is SystemMessage:
                messages.append(SystemMessage(
                    content=raw_name,
                    timestamp=raw_name,
                    raw_name=raw_name,
                ))
                continue

            # 判断发送者
            sender, sender_type = self._detect_sender(
                ctrl, list_center_x, chat_name,
            )

            # 构造具体消息对象
            msg = self._build_message(msg_cls, raw_name, sender, sender_type)
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
        if re.search(r"https?://", name):
            return LinkMessage
        if name.startswith("语音通话") or name.startswith("视频通话"):
            return VoipMessage
        if "聊天记录" in name or name.startswith("合并"):
            return MergeMessage
        if "笔记" in name:
            return NoteMessage
        # ChatBubbleItemView 中未匹配的通常是卡片消息
        # （音乐分享、公众号文章、小程序卡片等）
        return CardMessage

    @staticmethod
    def _detect_sender(
        ctrl, list_center_x: int, chat_name: str,
    ) -> tuple[str, SenderType]:
        """
        判断消息发送者和来源类型。

        策略1: 通过头像控件 (mmui::ContactHeadView) 位置判断
        策略2: 若头像不可见（微信4.x虚拟化列表限制），
               则通过截图像素分析判断气泡在左侧还是右侧：
               - 自己发的消息气泡靠右
               - 对方发的消息气泡靠左
        """
        # 策略1: 头像控件检测
        head = ctrl.ButtonControl(
            ClassName="mmui::ContactHeadView",
            searchDepth=8,
        )
        if head.Exists(0, 0):
            head_rect = head.BoundingRectangle
            head_center_x = (head_rect.left + head_rect.right) // 2
            if head_center_x > list_center_x:
                return "我", SenderType.SELF
            return chat_name, SenderType.FRIEND

        # 策略2: 截图像素分析
        return Chat._detect_sender_by_pixel(ctrl, chat_name)

    @staticmethod
    def _detect_sender_by_pixel(
        ctrl, chat_name: str,
    ) -> tuple[str, SenderType]:
        """
        通过扫描气泡区域的颜色判断消息发送者。

        微信气泡颜色规则：
        - 绿色气泡：自己发的消息 (G > 180, G-R > 50, G-B > 80)
        - 灰色/白色气泡：对方发的消息 (R,G,B 接近且 > 200)
        采样中间几行像素，统计绿色和灰色像素数量来判断。
        """

        tmp_path = os.path.join(tempfile.gettempdir(), "_wxuia_msg.png")
        try:
            ctrl.CaptureToImage(tmp_path)
            img = Image.open(tmp_path)
        except Exception:
            return "", SenderType.OTHER
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        w, h = img.size
        green_count = 0
        gray_count = 0

        sample_rows = [h // 3, h // 2, h * 2 // 3]
        for y in sample_rows:
            for x in range(w):
                r, g, b = img.getpixel((x, y))[:3]
                # 绿色气泡：G 通道明显高于 R 和 B
                if g > 180 and g - r > 50 and g - b > 80:
                    green_count += 1
                # 灰色/白色气泡：三通道接近且偏亮，排除背景纯白
                elif r > 200 and g > 200 and b > 200 \
                        and abs(r - g) < 15 and abs(r - b) < 15 \
                        and not (r > 250 and g > 250 and b > 250):
                    gray_count += 1

        if green_count > 30:
            return "我", SenderType.SELF
        if gray_count > 30:
            return chat_name, SenderType.FRIEND

        return "", SenderType.OTHER

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
    ) -> Message:
        """根据消息子类构造具体消息对象，调用各子类的 parse 方法提取字段"""
        msg_status, actual_name = Chat._detect_message_status(
            msg_cls, raw_name, sender_type,
        )

        base = dict(sender=sender, sender_type=sender_type,
                    raw_name=raw_name, status=msg_status)

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
            content, title = LinkMessage.parse(actual_name)
            return LinkMessage(**base, content=content, title=title)

        if msg_cls is PersonalCardMessage:
            content, card_name = PersonalCardMessage.parse(actual_name)
            return PersonalCardMessage(**base, content=content, card_name=card_name)

        if msg_cls is VoipMessage:
            content, call_type, call_status = VoipMessage.parse(actual_name)
            return VoipMessage(**base, content=content, call_type=call_type, call_status=call_status)

        if msg_cls is CardMessage:
            content, title, description = CardMessage.parse(actual_name)
            return CardMessage(**base, content=content, title=title, description=description)

        # TextMessage, QuoteMessage, ImageMessage, VideoMessage,
        # EmotionMessage, MergeMessage, NoteMessage, OtherMessage
        return msg_cls(**base, content=actual_name)

    # ---- 聊天信息面板操作 ----

    def clear_chat_history(self):
        """
        清空当前会话的聊天记录。

        流程：
        1. 点击标题栏右上角"聊天信息"按钮，展开聊天信息面板
        2. 在面板中找到"清空聊天记录"按钮并点击
        3. 在确认弹窗中点击"清空"按钮
        4. 收回聊天信息面板
        """
        if self._wx:
            self._wx.activate()

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
            clear_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.5)

            # 3. 确认弹窗中点击"清空"
            confirm_btn = self._win.ButtonControl(
                Name="清空",
                ClassName="mmui::XOutlineButton",
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到'清空'确认按钮")
            confirm_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"清空聊天记录成功: {self.current_name}")

        finally:
            # 4. 收回聊天信息面板
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

    def _set_chat_info_switch(self, name: str, enable: bool):
        """
        设置聊天信息面板中指定开关的状态。

        Args:
            name: 开关名称（"消息免打扰" 或 "置顶聊天"）
            enable: True 开启，False 关闭
        """
        if self._wx:
            self._wx.activate()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            sw, is_on = self._get_chat_info_switch(name)
            if is_on != enable:
                sw.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.3)
                action = "开启" if enable else "关闭"
                logger.debug(f"{action}{name}成功: {self.current_name}")
        finally:
            self._close_chat_info_panel()

    @property
    def is_pinned(self) -> bool:
        """当前会话是否已置顶"""
        if self._wx:
            self._wx.activate()
        self._click_chat_info_button()
        time.sleep(0.5)
        try:
            _, is_on = self._get_chat_info_switch("置顶聊天")
            return is_on
        finally:
            self._close_chat_info_panel()

    def pin_chat(self):
        """置顶当前会话"""
        self._set_chat_info_switch("置顶聊天", True)

    def unpin_chat(self):
        """取消置顶当前会话"""
        self._set_chat_info_switch("置顶聊天", False)

    @property
    def is_muted(self) -> bool:
        """当前会话是否已开启消息免打扰"""
        if self._wx:
            self._wx.activate()
        self._click_chat_info_button()
        time.sleep(0.5)
        try:
            _, is_on = self._get_chat_info_switch("消息免打扰")
            return is_on
        finally:
            self._close_chat_info_panel()

    def mute(self):
        """开启消息免打扰"""
        self._set_chat_info_switch("消息免打扰", True)

    def unmute(self):
        """关闭消息免打扰"""
        self._set_chat_info_switch("消息免打扰", False)

    def fold_chat(self):
        """
        折叠当前会话。

        "折叠该聊天"是"消息免打扰"的子选项，
        只有在消息免打扰开启时才会出现。
        如果消息免打扰未开启，会先自动开启。
        """
        if self._wx:
            self._wx.activate()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 检查消息免打扰是否开启，未开启则先开启
            mute_sw, mute_on = self._get_chat_info_switch("消息免打扰")
            if not mute_on:
                mute_sw.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.5)

            # 设置折叠该聊天
            fold_sw, fold_on = self._get_chat_info_switch("折叠该聊天")
            if not fold_on:
                fold_sw.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.3)
                logger.debug(f"折叠聊天成功: {self.current_name}")
        finally:
            self._close_chat_info_panel()

    def unfold_chat(self):
        """
        取消折叠当前会话。

        "折叠该聊天"是"消息免打扰"的子选项，
        只有在消息免打扰开启时才会出现。
        """
        if self._wx:
            self._wx.activate()

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
                    fold_sw.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.3)
                    logger.debug(f"取消折叠聊天成功: {self.current_name}")
        finally:
            self._close_chat_info_panel()

    # ---- 群聊信息面板操作（仅群聊可用） ----

    def _ensure_room_chat(self):
        """确保当前是群聊会话，否则抛出异常"""
        if self.chat_type != "群聊":
            raise RuntimeError("群聊信息操作仅支持群聊会话")

    def _click_room_info_item(self, item_name: str):
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
        btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.5)

    def set_room_name(self, name: str):
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
        if self._wx:
            self._wx.activate()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 点击"群聊名称"按钮
            self._click_room_info_item("群聊名称")

            # 查找编辑弹窗中的输入框
            edit = self._win.EditControl(
                ClassName="mmui::XValidatorTextEdit",
            )
            if not edit.Exists(maxSearchSeconds=3):
                # 尝试查找 mmui::XLineEdit
                edit = self._win.EditControl(
                    ClassName="mmui::XLineEdit",
                )
            if not edit.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到群聊名称编辑框")

            edit.Click(ratioX=0.5, ratioY=0.5)
            time.sleep(0.2)
            edit.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.1)

            # 通过剪贴板粘贴文本
            paste(name)
            time.sleep(0.3)

            # 点击"完成"按钮
            ok_btn = self._win.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'完成'按钮")
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"设置群聊名称成功: {name}")

        finally:
            self._close_chat_info_panel()

    def set_room_announcement(self, content: str):
        """
        设置群公告。

        仅群聊可用。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 在面板中找到"群公告"按钮并点击
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
        if self._wx:
            self._wx.activate()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 点击"群公告"按钮
            self._click_room_info_item("群公告")

            # 查找编辑弹窗中的输入框
            edit = self._win.EditControl(
                ClassName="mmui::XValidatorTextEdit",
            )
            if not edit.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到群公告编辑框")

            edit.Click(ratioX=0.5, ratioY=0.5)
            time.sleep(0.2)
            edit.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.1)

            # 通过剪贴板粘贴文本
            paste(content)
            time.sleep(0.3)

            # 点击"发布"按钮
            ok_btn = self._win.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="发布",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                # 尝试查找"完成"按钮
                ok_btn = self._win.ButtonControl(
                    ClassName="mmui::XOutlineButton",
                    Name="完成",
                )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'发布'或'完成'按钮")
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"设置群公告成功: {self.current_name}")

        finally:
            self._close_chat_info_panel()

    def set_room_remark(self, remark: str):
        """
        设置群聊备注。

        仅群聊可用。群聊的备注仅自己可见。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 在面板中找到"备注"按钮并点击
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
        if self._wx:
            self._wx.activate()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 点击"备注"按钮
            self._click_room_info_item("备注")

            # 查找编辑弹窗中的输入框
            edit = self._win.EditControl(
                ClassName="mmui::XLineEdit",
            )
            if not edit.Exists(maxSearchSeconds=3):
                edit = self._win.EditControl(
                    ClassName="mmui::XValidatorTextEdit",
                )
            if not edit.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到备注编辑框")

            edit.Click(ratioX=0.5, ratioY=0.5)
            time.sleep(0.2)
            edit.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.1)

            # 通过剪贴板粘贴文本
            paste(remark)
            time.sleep(0.3)

            # 点击"完成"按钮
            ok_btn = self._win.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'完成'按钮")
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"设置群聊备注成功: {self.current_name} -> {remark}")

        finally:
            self._close_chat_info_panel()

    def set_room_nickname(self, nickname: str):
        """
        设置我在本群的昵称。

        仅群聊可用。

        流程：
        1. 点击"聊天信息"按钮，展开聊天信息面板
        2. 在面板中找到"我在本群的昵称"按钮并点击
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
        if self._wx:
            self._wx.activate()

        self._click_chat_info_button()
        time.sleep(0.5)

        try:
            # 点击"我在本群的昵称"按钮
            self._click_room_info_item("我在本群的昵称")

            # 查找编辑弹窗中的输入框
            edit = self._win.EditControl(
                ClassName="mmui::XLineEdit",
            )
            if not edit.Exists(maxSearchSeconds=3):
                edit = self._win.EditControl(
                    ClassName="mmui::XValidatorTextEdit",
                )
            if not edit.Exists(maxSearchSeconds=3):
                raise RuntimeError("未找到昵称编辑框")

            edit.Click(ratioX=0.5, ratioY=0.5)
            time.sleep(0.2)
            edit.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.1)

            # 通过剪贴板粘贴文本
            paste(nickname)
            time.sleep(0.3)

            # 点击"完成"按钮
            ok_btn = self._win.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'完成'按钮")
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"设置群内昵称成功: {self.current_name} -> {nickname}")

        finally:
            self._close_chat_info_panel()

    # ---- 联系人资料面板操作（仅私聊可用） ----

    def _ensure_contact_chat(self):
        """确保当前是私聊会话，否则抛出异常"""
        if self.chat_type != "私聊":
            raise RuntimeError("联系人资料操作仅支持私聊会话")

    def _open_contact_profile(self):
        """
        打开当前私聊联系人的资料面板。

        流程：
        1. 点击"聊天信息"按钮
        2. 点击联系人头像，打开资料面板
        """
        self._ensure_contact_chat()
        if self._wx:
            self._wx.activate()

        self._click_chat_info_button()
        time.sleep(0.5)

        self._click_contact_avatar()
        time.sleep(0.5)

    def _click_profile_menu_item(self, menu_name: str):
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
            self._win.SendKeys("{Esc}")
            raise RuntimeError(f"未找到'{menu_name}'菜单项")
        menu_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    def _cleanup_profile(self):
        """关闭可能残留的弹窗和面板，并收回聊天信息面板"""
        try:
            self._win.SendKeys("{Esc}")
            time.sleep(0.2)
            self._win.SendKeys("{Esc}")
            time.sleep(0.2)
            self._win.SendKeys("{Esc}")
            time.sleep(0.2)
        except Exception:
            pass
        self._close_chat_info_panel()

    def _close_chat_info_panel(self):
        """点击"聊天信息"按钮收回展开的面板"""
        try:
            btn = self._win.ButtonControl(
                ClassName="mmui::XButton",
                Name="聊天信息",
            )
            if btn.Exists(0, 0):
                btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.2)
        except Exception:
            pass

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
        if self._wx:
            self._wx.activate()
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

            logger.debug(f"获取联系人资料成功: {self.current_name}")
            return result

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def set_contact_info(self, *,
                         remark: str = None,
                         labels: list = None,
                         phones: list = None,
                         description: str = None,
                         images: list = None):
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

        if self._wx:
            self._wx.activate()
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
                    remark_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    remark_edit.SendKeys("{Ctrl}a{Del}")
                    if remark:
                        paste(remark)

            # 辅助函数：将弹窗滚动区域滚动到底部
            def _scroll_to_bottom():
                scroll_area = remark_pop.GroupControl(ClassName="QFScrollArea")
                if not scroll_area.Exists(0, 0):
                    return
                rect = scroll_area.BoundingRectangle
                cx = rect.left + rect.width() // 2
                cy = rect.top + rect.height() // 2
                lines = max(rect.height() // 40, 10)
                win32api.SetCursorPos((cx, cy))
                time.sleep(0.1)
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_WHEEL, cx, cy, -120 * lines, 0,
                )
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
                        tag_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

                        for label in to_remove:
                            label_item = remark_pop.ListItemControl(
                                Name=label, searchDepth=8,
                            )
                            if label_item.Exists(maxSearchSeconds=1):
                                label_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

                        for label in to_add:
                            tag_edit = remark_pop.EditControl(
                                ClassName="mmui::XValidatorTextEdit", Name="搜索",
                            )
                            if tag_edit.Exists(maxSearchSeconds=2):
                                tag_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                                tag_edit.SendKeys("{Ctrl}a{Del}")
                                paste(label)
                                label_item = remark_pop.ListItemControl(
                                    Name=label, searchDepth=8,
                                )
                                if label_item.Exists(maxSearchSeconds=1):
                                    label_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                                tag_edit.SendKeys("{Ctrl}a{Del}")

                        title_text = remark_pop.TextControl(
                            ClassName="mmui::XTextView",
                            Name="设置备注和标签",
                        )
                        if title_text.Exists(0, 0):
                            title_text.Click(ratioX=0.5, ratioY=0.5)

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
                                    del_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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
                                add_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

                        empty_field = phone_area.TextControl(
                            ClassName="mmui::XLineField", Name="填写电话",
                        )
                        if empty_field.Exists(maxSearchSeconds=2):
                            phone_edit = empty_field.EditControl(
                                ClassName="mmui::XLineEdit",
                            )
                            if phone_edit.Exists(0, 0):
                                phone_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                                vp = phone_edit.GetValuePattern()
                                if vp:
                                    vp.SetValue(phone)
                                else:
                                    paste(phone)
                                phone_edit.SendKeys("{Tab}")

            # ---- 4. 描述 ----
            if description is not None:
                desc_edit = remark_pop.EditControl(
                    ClassName="mmui::XValidatorTextEdit", Name="修改描述",
                )
                if desc_edit.Exists(maxSearchSeconds=2):
                    _scroll_to_bottom()
                    desc_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    desc_edit.SendKeys("{Ctrl}a{Del}")
                    if description:
                        paste(description[:200])

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
                        img_btn.RightClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                        menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                        if not menu_win.Exists(maxSearchSeconds=2):
                            break
                        del_item = menu_win.MenuItemControl(
                            ClassName="mmui::XMenuView", Name="删除",
                        )
                        if not del_item.Exists(maxSearchSeconds=1):
                            self._win.SendKeys("{Esc}")
                            break
                        del_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

                for img_path in images:
                    add_img_btn = remark_pop.GroupControl(
                        Name="添加图片",
                        AutomationId="desc_img_list_view_.add_button_view",
                    )
                    if not add_img_btn.Exists(maxSearchSeconds=2):
                        break
                    add_img_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    dlg = auto.WindowControl(ClassName="#32770")
                    if not dlg.Exists(maxSearchSeconds=5):
                        break
                    dlg.SendKeys("{Alt}N")
                    edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
                    if not edit.Exists(0, 0):
                        edit = dlg.EditControl(AutomationId="1148")
                    if edit.Exists(maxSearchSeconds=2):
                        edit.GetValuePattern().SetValue(os.path.abspath(img_path))
                        dlg.SendKeys("{Alt}O")
                        time.sleep(0.5)

            # ---- 点击"完成"保存 ----
            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton", Name="完成",
            )
            if ok_btn.Exists(maxSearchSeconds=2):
                ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

            logger.debug(f"设置联系人信息成功: {self.current_name}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def set_contact_remark(self, remark: str):
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

        if self._wx:
            self._wx.activate()
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

            remark_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.2)
            remark_edit.SendKeys("{Ctrl}a{Del}")
            time.sleep(0.1)

            paste(remark)
            time.sleep(0.3)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'完成'按钮")
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"设置备注成功: {self.current_name} -> {remark}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def add_contact_label(self, labels: list):
        """
        为当前私聊联系人添加标签。

        Args:
            labels: 标签名列表，如 ["朋友", "同事"]
        """
        if not labels:
            raise ValueError("labels 不能为空")

        if self._wx:
            self._wx.activate()
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
                logger.debug(f"所有标签已存在，跳过: {self.current_name} -> {labels}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                return

            tag_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            for label in new_labels:
                tag_edit = remark_pop.EditControl(
                    ClassName="mmui::XValidatorTextEdit",
                    Name="搜索",
                )
                if not tag_edit.Exists(maxSearchSeconds=3):
                    raise RuntimeError("未找到标签搜索输入框")

                tag_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.2)
                tag_edit.SendKeys("{Ctrl}a{Del}")
                time.sleep(0.1)

                paste(label)
                time.sleep(0.5)

                label_item = remark_pop.ListItemControl(
                    Name=label,
                    searchDepth=8,
                )
                if label_item.Exists(maxSearchSeconds=1):
                    label_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.3)
                else:
                    logger.debug(f"搜索结果中未找到标签，跳过: {label}")

                tag_edit.SendKeys("{Ctrl}a{Del}")
                time.sleep(0.2)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)
            logger.debug(f"添加标签成功: {self.current_name} -> {labels}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def remove_contact_label(self, labels: list):
        """
        移除当前私聊联系人的标签。

        Args:
            labels: 要移除的标签名列表
        """
        if not labels:
            raise ValueError("labels 不能为空")

        if self._wx:
            self._wx.activate()
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
                logger.debug(f"标签均不存在，跳过: {self.current_name} -> {labels}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                return

            tag_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            for label in to_remove:
                label_item = remark_pop.ListItemControl(
                    Name=label,
                    searchDepth=8,
                )
                if label_item.Exists(maxSearchSeconds=2):
                    label_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.3)
                else:
                    logger.warning(f"列表中未找到标签项: {label}")

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)
            logger.debug(f"移除标签成功: {self.current_name} -> {labels}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def add_contact_phone(self, phones: list):
        """
        为当前私聊联系人添加电话号码（增量添加，不删除已有号码）。

        Args:
            phones: 电话号码列表，如 ["13800138000", "13900139000"]
        """
        if not phones:
            raise ValueError("phones 不能为空")

        if self._wx:
            self._wx.activate()
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
                logger.debug(f"所有电话号码已存在，跳过: {self.current_name} -> {phones}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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
                    add_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

                phone_edit.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.2)

                vp = phone_edit.GetValuePattern()
                if vp:
                    vp.SetValue(phone)
                else:
                    paste(phone)
                time.sleep(0.3)
                phone_edit.SendKeys("{Tab}")
                time.sleep(0.3)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)
            logger.debug(f"添加电话号码成功: {self.current_name} -> {phones}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def add_contact_image(self, images: list):
        """
        为当前私聊联系人添加备注图片（增量添加，不删除已有图片）。

        Args:
            images: 图片文件路径列表，如 ["C:/a.jpg", "C:/b.png"]
        """
        if not images:
            raise ValueError("images 不能为空")

        if self._wx:
            self._wx.activate()
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
                win32api.SetCursorPos((cx, cy))
                time.sleep(0.1)
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_WHEEL, cx, cy, -120 * lines, 0,
                )
                time.sleep(0.3)

            for img_path in images:
                add_img_btn = remark_pop.GroupControl(
                    Name="添加图片",
                    AutomationId="desc_img_list_view_.add_button_view",
                )
                if not add_img_btn.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到'添加图片'按钮")

                add_img_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(1)

                dlg = auto.WindowControl(ClassName="#32770")
                if not dlg.Exists(maxSearchSeconds=5):
                    raise RuntimeError("文件选择对话框未弹出")

                dlg.SendKeys("{Alt}N")
                time.sleep(0.3)
                edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
                if not edit.Exists(0, 0):
                    edit = dlg.EditControl(AutomationId="1148")
                if not edit.Exists(maxSearchSeconds=2):
                    raise RuntimeError("未找到文件名输入框")

                abs_path = os.path.abspath(img_path)
                edit.GetValuePattern().SetValue(abs_path)
                time.sleep(0.3)

                dlg.SendKeys("{Alt}O")
                time.sleep(1)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise RuntimeError("未找到'完成'按钮")
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"添加备注图片成功: {self.current_name} -> {images}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def remove_contact_phone(self, phones: list[str]):
        """
        移除当前私聊联系人的电话号码。

        Args:
            phones: 要移除的电话号码列表，如 ["13800138000"]
        """
        if not phones:
            raise ValueError("phones 不能为空")

        if self._wx:
            self._wx.activate()
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
                logger.debug(f"电话号码均不存在，跳过: {self.current_name} -> {phones}")
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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
                                del_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                                time.sleep(0.3)
                            else:
                                logger.warning(f"未找到删除按钮: {phone}")
                else:
                    logger.warning(f"未找到电话号码项: {phone}")

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name="完成",
            )
            ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)
            logger.debug(f"移除电话号码成功: {self.current_name} -> {phones}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def remove_contact_image(self, indexes: list[int]):
        """
        删除当前私聊联系人的备注图片（按序号）。

        Args:
            indexes: 要删除的图片序号列表（从 1 开始），如 [1, 3]。
                     按从大到小的顺序删除，避免序号偏移。
        """
        if not indexes:
            raise ValueError("indexes 不能为空")

        if self._wx:
            self._wx.activate()
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
                win32api.SetCursorPos((cx, cy))
                time.sleep(0.1)
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_WHEEL, cx, cy, -120 * lines, 0,
                )
                time.sleep(0.3)

            img_list = remark_pop.GroupControl(
                AutomationId="desc_img_list_view_",
            )
            if not img_list.Exists(maxSearchSeconds=2):
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                return

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == "描述图片":
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

                img_btn.RightClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.5)

                menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                if not menu_win.Exists(maxSearchSeconds=2):
                    continue

                del_item = menu_win.MenuItemControl(
                    ClassName="mmui::XMenuView",
                    Name="删除",
                )
                if not del_item.Exists(maxSearchSeconds=1):
                    self._win.SendKeys("{Esc}")
                    continue

                del_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.3)
                deleted += 1

            if deleted > 0:
                ok_btn = remark_pop.ButtonControl(
                    ClassName="mmui::XOutlineButton",
                    Name="完成",
                )
                if ok_btn.Exists(maxSearchSeconds=2):
                    ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.3)
                logger.debug(f"删除备注图片成功: {self.current_name} -> 删除{deleted}张")
            else:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def set_contact_star(self):
        """将当前私聊联系人设为星标朋友"""
        if self._wx:
            self._wx.activate()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("设为星标朋友")
            time.sleep(0.3)
            logger.debug(f"设为星标朋友操作完成: {self.current_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def cancel_contact_star(self):
        """取消当前私聊联系人的星标朋友"""
        if self._wx:
            self._wx.activate()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("不再设为星标朋友")
            time.sleep(0.3)
            logger.debug(f"取消星标朋友操作完成: {self.current_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def black_contact(self):
        """将当前私聊联系人加入黑名单"""
        if self._wx:
            self._wx.activate()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("加入黑名单")
            time.sleep(0.5)

            confirm_btn = self._win.ButtonControl(Name="确定")
            if confirm_btn.Exists(maxSearchSeconds=3):
                confirm_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.3)
                logger.debug(f"加入黑名单成功: {self.current_name}")
            else:
                logger.warning(f"未找到确认按钮，加入黑名单可能未完成: {self.current_name}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def unblack_contact(self):
        """将当前私聊联系人移出黑名单"""
        if self._wx:
            self._wx.activate()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("移出黑名单")
            time.sleep(0.3)
            logger.debug(f"移出黑名单成功: {self.current_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def delete_contact(self):
        """删除当前私聊联系人（不可逆）"""
        if self._wx:
            self._wx.activate()
        try:
            self._open_contact_profile()
            self._click_profile_menu_item("删除联系人")
            time.sleep(0.5)

            confirm_btn = self._win.ButtonControl(Name="删除")
            if confirm_btn.Exists(maxSearchSeconds=3):
                confirm_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.3)
                logger.debug(f"删除联系人成功: {self.current_name}")
            else:
                logger.warning(f"未找到'删除'确认按钮，删除联系人可能未完成: {self.current_name}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

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
        if self._wx:
            self._wx.activate()
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
                cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
            time.sleep(0.3)

            logger.debug(f"获取朋友权限成功: {self.current_name} -> {result}")
            return result

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    def set_friend_permission(self, permission: str = "all",
                              hide_my_posts: bool = False,
                              hide_their_posts: bool = False):
        """
        设置当前私聊联系人的朋友权限。

        Args:
            permission: "all" 或 "chatonly"
            hide_my_posts: 不让他（她）看我的朋友圈和状态
            hide_their_posts: 不看他（她）的朋友圈和状态
        """
        if permission not in ("all", "chatonly"):
            raise ValueError(f"permission 必须为 'all' 或 'chatonly'，当前: {permission}")

        if self._wx:
            self._wx.activate()
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
                target_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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
                            hide_my_sw.Click(ratioX=0.5, ratioY=0.5)
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
                            hide_their_sw.Click(ratioX=0.5, ratioY=0.5)
                            time.sleep(0.2)
                            changed = True

            if changed:
                ok_btn = perm_pop.ButtonControl(
                    ClassName="mmui::XOutlineButton",
                    Name="完成",
                )
                if ok_btn.Exists(maxSearchSeconds=2):
                    ok_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.3)
            else:
                cancel_btn = perm_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                    time.sleep(0.2)

            logger.debug(f"设置朋友权限成功: {self.current_name} -> permission={permission}, "
                        f"hide_my={hide_my_posts}, hide_their={hide_their_posts}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

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

        if self._wx:
            self._wx.activate()
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
                win32api.SetCursorPos((cx, cy))
                time.sleep(0.1)
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_WHEEL, cx, cy, -120 * lines, 0,
                )
                time.sleep(0.3)

            img_list = remark_pop.GroupControl(
                AutomationId="desc_img_list_view_",
            )
            if not img_list.Exists(maxSearchSeconds=2):
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                return 0

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == "描述图片":
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

                img_btn.RightClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.5)

                menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                if not menu_win.Exists(maxSearchSeconds=2):
                    continue

                collect_item = menu_win.MenuItemControl(
                    ClassName="mmui::XMenuView",
                    Name="收藏",
                )
                if not collect_item.Exists(maxSearchSeconds=1):
                    self._win.SendKeys("{Esc}")
                    logger.warning(f"右键菜单中未找到'收藏'，跳过第{idx}张")
                    continue

                collect_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.5)
                collected += 1

            # 收藏不修改数据，点"取消"关闭弹窗
            cancel_btn = remark_pop.ButtonControl(Name="取消")
            if cancel_btn.Exists(maxSearchSeconds=1):
                cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

            logger.debug(f"收藏备注图片成功: {self.current_name} -> 收藏{collected}张")
            return collected

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

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

        if self._wx:
            self._wx.activate()
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
                win32api.SetCursorPos((cx, cy))
                time.sleep(0.1)
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_WHEEL, cx, cy, -120 * lines, 0,
                )
                time.sleep(0.3)

            img_list = remark_pop.GroupControl(
                AutomationId="desc_img_list_view_",
            )
            if not img_list.Exists(maxSearchSeconds=2):
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                return 0

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == "描述图片":
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name="取消")
                if cancel_btn.Exists(maxSearchSeconds=1):
                    cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
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

                img_btn.RightClick(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(0.5)

                menu_win = self._win.WindowControl(ClassName="mmui::XMenu")
                if not menu_win.Exists(maxSearchSeconds=2):
                    continue

                save_item = menu_win.MenuItemControl(
                    ClassName="mmui::XMenuView",
                    Name="另存为...",
                )
                if not save_item.Exists(maxSearchSeconds=1):
                    self._win.SendKeys("{Esc}")
                    continue

                save_item.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
                time.sleep(1)

                # 等待系统文件保存对话框
                dlg = remark_pop.WindowControl(ClassName="#32770")
                if not dlg.Exists(maxSearchSeconds=5):
                    dlg = auto.WindowControl(ClassName="#32770")
                    if not dlg.Exists(maxSearchSeconds=3):
                        continue

                edit = dlg.EditControl(AutomationId="1001")
                if not edit.Exists(maxSearchSeconds=2):
                    dlg.SendKeys("{Esc}")
                    continue

                vp = edit.GetValuePattern()
                original_name = vp.Value if vp else ""
                if not original_name:
                    dlg.SendKeys("{Esc}")
                    continue
                full_path = os.path.join(save_dir, original_name)
                vp.SetValue(full_path)
                time.sleep(0.3)

                dlg.SendKeys("{Alt}S")
                time.sleep(1)

                # 如果弹出覆盖确认，按 Y 确认
                if dlg.Exists(maxSearchSeconds=0.5):
                    dlg.SendKeys("{Alt}Y")
                    time.sleep(0.5)

                saved += 1

            # 点击"取消"关闭弹窗（保存图片不需要点完成）
            cancel_btn = remark_pop.ButtonControl(Name="取消")
            if cancel_btn.Exists(maxSearchSeconds=1):
                cancel_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

            logger.debug(f"保存备注图片成功: {self.current_name} -> {save_dir} ({saved}张)")
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

    def __init__(self, contact_name: str):
        if not contact_name:
            raise ValueError("contact_name 不能为空")
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            Name=contact_name,
            Depth=1
        )
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError(f"独立聊天窗口未找到: {contact_name}")
        self._wx = None

    @property
    def exists(self) -> bool:
        """独立窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=2)

    @property
    def is_pinned(self) -> bool:
        """窗口是否已置顶"""
        return self.is_topmost

    def send_text(self, content: str) -> MessageStatus:
        self.activate()
        return super().send_text(content)

    def send_file(self, file_path: str) -> MessageStatus:
        self.activate()
        return super().send_file(file_path)

    def send_at(self, content: str, at_members: list[str]) -> MessageStatus:
        self.activate()
        return super().send_at(content, at_members)

    def send_collection(self, keyword: str) -> bool:
        self.activate()
        return super().send_collection(keyword)

    def send_emotion(self, keyword: str = None, index: int = 1) -> bool:
        self.activate()
        return super().send_emotion(keyword, index)

    def send_card(self, nickname: str) -> bool:
        self.activate()
        return super().send_card(nickname)

    def voice_call(self) -> "VoipCallWindow":
        self.activate()
        return super().voice_call()

    def video_call(self) -> "VoipCallWindow":
        self.activate()
        return super().video_call()

    def move_offscreen(self):
        """将窗口移到屏幕外（不可见但仍处于正常状态）。"""
        hwnd = self._win.NativeWindowHandle
        rect = self._win.BoundingRectangle
        self._offscreen_rect = (rect.left, rect.top,
                                rect.width(), rect.height())
        ctypes.windll.user32.MoveWindow(hwnd, -9999, 0,
                                        rect.width(), rect.height(), True)

    def move_back(self):
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
        return (f"SeparateChat(type={self.chat_type!r}, "
                f"name={self.current_name!r})")


class Weixin(WeixinWindow):

    WINDOW_CLASS = "mmui::MainWindow"
    WINDOW_REGEX = "微信|Weixin"

    def __init__(self):
        ensure_narrator_registry()
        self._ensure_running()
        self.window: auto.WindowControl = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            RegexName=self.WINDOW_REGEX,
            Depth=1,
        )
        self.navigator = Navigator(self)
        self.session = Session(self)
        self.file_manager = FileManager(self)
        self.moment = Moment(self)

    @staticmethod
    def _is_process_running(name: str) -> bool:
        output = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
            text=True, creationflags=0x08000000,
        )
        return name.lower() in output.lower()

    @staticmethod
    def _ensure_running():
        wnd = auto.WindowControl(ClassName="mmui::MainWindow", RegexName="微信|Weixin", Depth=1)
        if wnd.Exists(maxSearchSeconds=3):
            return
        if Weixin._is_process_running("Weixin.exe"):
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Tencent\Weixin",
                )
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
            except FileNotFoundError:
                raise RuntimeError("未找到微信安装路径，请确认微信已安装")
            subprocess.Popen([f"{install_path}\\Weixin.exe"])
            if not wnd.Exists(maxSearchSeconds=15):
                raise RuntimeError("微信启动超时，请手动登录后重试")

    @property
    def is_locked(self) -> bool:
        txt = self.window.TextControl(ClassName="mmui::XTextView", Name="Windows 微信已被锁定")
        return txt.Exists(0, 0)

    @property
    def has_session(self) -> bool:
        """会话列表是否可见（即当前是否在微信标签页）"""
        return self.session.is_visible

    @property
    def chat(self) -> Optional[Chat]:
        for aid in Chat.TITLE_LABEL_IDS:
            title = self.window.TextControl(AutomationId=aid)
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
                    result.append(SeparateChat(ctrl.Name))
                except (RuntimeError, ValueError):
                    pass

        return result

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

    def open_session_by_search(self, nickname: str) -> Chat:
        """通过搜索打开指定会话，返回 Chat 对象"""
        self.activate()
        if not self.has_session:
            self.navigator.switch_to("微信")
        self.session.open_by_search(nickname)
        # 等待聊天界面加载完成（搜索点击后界面切换需要时间）
        for _ in range(10):
            chat = self.chat
            if chat is not None:
                return chat
            time.sleep(0.3)
        raise RuntimeError(f"打开会话失败: {nickname}")

    def close_session(self, nickname: str):
        self.session.close(nickname)

    def send_text(self, nickname: str, content: str) -> MessageStatus:
        """打开指定会话并发送文本消息"""
        chat = self.open_session_by_search(nickname)
        return chat.send_text(content)

    def send_file(self, nickname: str, file_path: str) -> MessageStatus:
        """打开指定会话并发送文件，支持本地路径和网络 URL"""
        chat = self.open_session_by_search(nickname)
        return chat.send_file(file_path)

    def send_at(self, nickname: str, content: str, at_members: list[str]) -> MessageStatus:
        """打开指定群聊会话并 @指定成员发送消息"""
        chat = self.open_session_by_search(nickname)
        return chat.send_at(content, at_members)

    def send_collection(self, nickname: str, keyword: str) -> bool:
        """打开指定会话并发送收藏内容"""
        chat = self.open_session_by_search(nickname)
        return chat.send_collection(keyword)

    def send_emotion(self, nickname: str, keyword: str = None, index: int = 1) -> bool:
        """打开指定会话并发送表情，keyword 为 None 时发送自定义表情"""
        chat = self.open_session_by_search(nickname)
        return chat.send_emotion(keyword, index)

    def send_card(self, nickname: str, share: str) -> bool:
        """
        将指定联系人的名片发送给接收者。

        Args:
            nickname: 接收名片的联系人昵称
            share: 要分享名片的联系人昵称

        Returns:
            True 发送成功
        """
        chat = self.open_session_by_search(share)
        return chat.send_card(nickname)

    def create_note(self, content: str):
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

    def create_room(self, nickname_list: list[str]):
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
            return SeparateChat(contact_name)
        except (RuntimeError, ValueError):
            return None

    def get_contact_profile(self, nickname: str) -> dict:
        """获取联系人的资料信息，委托给 Chat.get_contact_profile"""
        chat = self.open_session_by_search(nickname)
        return chat.get_contact_profile()

    def set_contact_info(self, nickname: str, *,
                         remark: str = None,
                         labels: list = None,
                         phones: list = None,
                         description: str = None,
                         images: list = None):
        """一次性设置联系人的备注、标签、电话、描述、图片，委托给 Chat.set_contact_info"""
        chat = self.open_session_by_search(nickname)
        chat.set_contact_info(remark=remark, labels=labels, phones=phones,
                              description=description, images=images)

    def set_contact_remark(self, nickname: str, remark: str):
        """设置联系人的备注名，委托给 Chat.set_contact_remark"""
        chat = self.open_session_by_search(nickname)
        chat.set_contact_remark(remark)

    def set_contact_label(self, nickname: str, labels: list[str]):
        """为联系人设置标签，委托给 Chat.set_contact_info"""
        chat = self.open_session_by_search(nickname)
        chat.set_contact_info(labels=phones)

    def set_contact_phone(self, nickname: str, phones: list[str]):
        """为联系人设置电话号码，委托给 Chat.set_contact_info"""
        chat = self.open_session_by_search(nickname)
        chat.set_contact_info(phones=phones)

    def set_contact_description(self, nickname: str, description: str):
        """设置联系人的描述信息，委托给 Chat.set_contact_info"""
        chat = self.open_session_by_search(nickname)
        chat.set_contact_info(description=description)

    def set_contact_image(self, nickname: str, images: list[str]):
        """设置联系人的备注图片（覆盖式），委托给 Chat.set_contact_info"""
        chat = self.open_session_by_search(nickname)
        chat.set_contact_info(images=images)

    def add_contact_label(self, nickname: str, labels: list[str]):
        """为联系人添加标签，委托给 Chat.add_contact_label"""
        chat = self.open_session_by_search(nickname)
        chat.add_contact_label(labels)

    def add_contact_phone(self, nickname: str, phones: list[str]):
        """为联系人添加电话号码，委托给 Chat.add_contact_phone"""
        chat = self.open_session_by_search(nickname)
        chat.add_contact_phone(phones)

    def add_contact_image(self, nickname: str, images: list[str]):
        """为联系人添加备注图片，委托给 Chat.add_contact_image"""
        chat = self.open_session_by_search(nickname)
        chat.add_contact_image(images)

    def remove_contact_label(self, nickname: str, labels: list[str]):
        """移除联系人的标签，委托给 Chat.remove_contact_label"""
        chat = self.open_session_by_search(nickname)
        chat.remove_contact_label(labels)

    def remove_contact_phone(self, nickname: str, phones: list[str]):
        """移除联系人的电话号码，委托给 Chat.remove_contact_phone"""
        chat = self.open_session_by_search(nickname)
        chat.remove_contact_phone(phones)

    def remove_contact_image(self, nickname: str, images: list[int]):
        """删除联系人的备注图片（按序号），委托给 Chat.remove_contact_image"""
        chat = self.open_session_by_search(nickname)
        chat.remove_contact_image(images)

    def collect_contact_image(self, nickname: str, images: list[int]) -> int:
        """收藏联系人的指定备注图片，委托给 Chat.collect_contact_image"""
        chat = self.open_session_by_search(nickname)
        return chat.collect_contact_image(images)

    def save_contact_image(self, nickname: str, images: list[int], save_path: str) -> int:
        """保存联系人的指定备注图片到指定目录，委托给 Chat.save_contact_image"""
        chat = self.open_session_by_search(nickname)
        return chat.save_contact_image(images, save_path)

    def set_contact_star(self, nickname: str):
        """将联系人设为星标朋友，委托给 Chat.set_contact_star"""
        chat = self.open_session_by_search(nickname)
        chat.set_contact_star()

    def cancel_contact_star(self, nickname: str):
        """取消联系人的星标朋友，委托给 Chat.cancel_contact_star"""
        chat = self.open_session_by_search(nickname)
        chat.cancel_contact_star()

    def get_friend_permission(self, nickname: str) -> dict:
        """获取联系人的朋友权限设置，委托给 Chat.get_friend_permission"""
        chat = self.open_session_by_search(nickname)
        return chat.get_friend_permission()

    def set_friend_permission(self, nickname: str, permission: str = "all",
                              hide_my_posts: bool = False,
                              hide_their_posts: bool = False):
        """设置联系人的朋友权限，委托给 Chat.set_friend_permission"""
        chat = self.open_session_by_search(nickname)
        chat.set_friend_permission(permission, hide_my_posts, hide_their_posts)

    def black_contact(self, nickname: str):
        """将联系人加入黑名单，委托给 Chat.black_contact"""
        chat = self.open_session_by_search(nickname)
        chat.black_contact()

    def unblack_contact(self, nickname: str):
        """将联系人移出黑名单，委托给 Chat.unblack_contact"""
        chat = self.open_session_by_search(nickname)
        chat.unblack_contact()

    def delete_contact(self, nickname: str):
        """删除联系人，委托给 Chat.delete_contact"""
        chat = self.open_session_by_search(nickname)
        chat.delete_contact()

    def recommend_contact(self, nickname: str, receiver_nickname: str) -> bool:
        """将指定联系人推荐给另一个朋友（发送名片），委托给 Chat.recommend_contact"""
        chat = self.open_session_by_search(nickname)
        return chat.recommend_contact(receiver_nickname)

    def clear_chat_history(self, nickname: str):
        """清空指定会话的聊天记录，委托给 Chat.clear_chat_history"""
        chat = self.open_session_by_search(nickname)
        chat.clear_chat_history()

    def pin_chat(self, nickname: str):
        """置顶指定会话，委托给 Chat.pin_chat"""
        chat = self.open_session_by_search(nickname)
        chat.pin_chat()

    def unpin_chat(self, nickname: str):
        """取消置顶指定会话，委托给 Chat.unpin_chat"""
        chat = self.open_session_by_search(nickname)
        chat.unpin_chat()

    def mute_chat(self, nickname: str):
        """开启指定会话的消息免打扰，委托给 Chat.mute"""
        chat = self.open_session_by_search(nickname)
        chat.mute()

    def unmute_chat(self, nickname: str):
        """关闭指定会话的消息免打扰，委托给 Chat.unmute"""
        chat = self.open_session_by_search(nickname)
        chat.unmute()

    def fold_chat(self, nickname: str):
        """折叠指定会话，委托给 Chat.fold_chat"""
        chat = self.open_session_by_search(nickname)
        chat.fold_chat()

    def unfold_chat(self, nickname: str):
        """取消折叠指定会话，委托给 Chat.unfold_chat"""
        chat = self.open_session_by_search(nickname)
        chat.unfold_chat()

    def set_room_name(self, nickname: str, name: str):
        """设置指定群聊的名称，委托给 Chat.set_room_name"""
        chat = self.open_session_by_search(nickname)
        chat.set_room_name(name)

    def set_room_announcement(self, nickname: str, content: str):
        """设置指定群聊的群公告，委托给 Chat.set_room_announcement"""
        chat = self.open_session_by_search(nickname)
        chat.set_room_announcement(content)

    def set_room_remark(self, nickname: str, remark: str):
        """设置指定群聊的备注，委托给 Chat.set_room_remark"""
        chat = self.open_session_by_search(nickname)
        chat.set_room_remark(remark)

    def set_room_nickname(self, nickname: str, my_nickname: str):
        """设置我在指定群聊中的昵称，委托给 Chat.set_room_nickname"""
        chat = self.open_session_by_search(nickname)
        chat.set_room_nickname(my_nickname)

    def lock(self):
        self.activate()
        more_btn = self.navigator._win.ButtonControl(Name="更多")
        if not more_btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到更多按钮")
        more_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())
        time.sleep(0.1)

        lock_btn = self.window.ButtonControl(ClassName="mmui::XButton", Name="锁定")
        if not lock_btn.Exists(maxSearchSeconds=2):
            self.window.SendKeys("{Esc}")
            raise RuntimeError("弹出菜单中未找到锁定按钮")
        lock_btn.Click(ratioX=_rand_ratio(), ratioY=_rand_ratio())

    @property
    def _window(self) -> auto.WindowControl:
        """覆盖基类属性，Weixin 使用 self.window 而非 self._win"""
        return self.window

    def listen(
        self,
        callback,
        interval: float = 0.1,
        idle_interval: float = 0.1,
        history: int = 5,
        scan_interval: float = 5.0,
    ):
        """
        多线程监听所有独立聊天窗口（SeparateChat）的新消息。

        每个独立窗口一个线程轮询消息，新消息逐条放入队列，
        主线程从队列中取出并逐条回调。

        callback: 回调函数，签名为 callback(chat: SeparateChat, message: Message)
                  每次回调传入一条新消息，在主线程中执行。
        interval:      有新消息时的轮询间隔（秒）
        idle_interval: 无新消息时的轮询间隔（秒），降低 CPU 占用
        history:       每个窗口初始记录的历史消息条数（用于去重基线，不触发回调）
        scan_interval: 扫描新窗口的间隔（秒）

        用法:
            wx = Weixin()
            def on_msg(chat, message):
                print(f"[{chat.current_name}] {message}")
            wx.listen(on_msg)  # 阻塞运行，Ctrl+C 退出
        """

        stop_event = threading.Event()
        # 消息队列：子线程生产，主线程消费
        msg_queue: Queue[tuple[SeparateChat, Message]] = Queue()
        # {窗口名: Thread}
        threads: dict[str, threading.Thread] = {}
        threads_lock = threading.Lock()

        def _msg_sig(msg: Message) -> str:
            """消息签名：类型+发送者类型+内容"""
            return f"{msg.__class__.__name__}|{msg.sender_type.value}|{msg.content}"

        def _snapshot_hash(sigs: list[str]) -> str:
            """对签名列表做 hash，用于快速判断是否有变化"""
            return hashlib.md5("\n".join(sigs).encode()).hexdigest()

        def _watch_chat(chat: SeparateChat, name: str):
            """
            单个窗口的监听线程。

            算法：
            1. 首次获取可见消息作为快照（不触发回调）
            2. 持续获取可见消息，先用 hash 快速判断是否有变化
            3. hash 变了则逐条对比快照，从第一条不一样的位置开始就是新消息
            4. 新消息逐条推送到队列，更新快照
            """
            # 快照：(签名列表, hash)
            snap_sigs: list[str] = []
            snap_hash: str = ""
            first_scan = True

            # 置顶并移到屏幕外，窗口仍处于正常状态，UI Automation 正常工作
            chat.pin()
            chat.move_offscreen()
            time.sleep(0.3)

            while not stop_event.is_set():
                if not chat.exists:
                    break

                try:
                    visible = chat.get_visible_messages()
                except Exception:
                    if stop_event.wait(interval):
                        break
                    continue

                curr_sigs = [_msg_sig(m) for m in visible]
                curr_hash = _snapshot_hash(curr_sigs)

                if first_scan:
                    snap_sigs = curr_sigs
                    snap_hash = curr_hash
                    first_scan = False
                    if stop_event.wait(interval):
                        break
                    continue

                # hash 相同，无变化
                if curr_hash == snap_hash:
                    if stop_event.wait(idle_interval):
                        break
                    continue

                # 锚定序列匹配：取快照后半部分作为锚定序列
                # 在当前列表中查找该序列，锚定序列之后的就是新消息
                # 锚定越长，重复消息导致误匹配的概率越低
                anchor_len = max(1, len(snap_sigs) // 2)
                anchor = snap_sigs[-anchor_len:]

                new_msgs: list[Message] = []
                # 在 curr_sigs 中从后往前找 anchor 序列
                found = -1
                for i in range(len(curr_sigs) - anchor_len, -1, -1):
                    if curr_sigs[i:i + anchor_len] == anchor:
                        found = i + anchor_len
                        break
                if found >= 0:
                    new_msgs = visible[found:]
                # 找不到说明快照消息已完全滚出可见区域，不推送避免重复

                # 更新快照
                snap_sigs = curr_sigs
                snap_hash = curr_hash

                for msg in new_msgs:
                    msg_queue.put((chat, msg))

                wait_time = interval if new_msgs else idle_interval
                if stop_event.wait(wait_time):
                    break

            # 线程退出，移回窗口并从跟踪表移除
            if chat.exists:
                try:
                    chat.move_back()
                except Exception:
                    pass
            with threads_lock:
                threads.pop(name, None)

        def _discover_chats() -> dict[str, SeparateChat]:
            found: dict[str, SeparateChat] = {}
            for ctrl in auto.GetRootControl().GetChildren():
                if ctrl.ClassName == SeparateChat.WINDOW_CLASS and ctrl.Name:
                    try:
                        found[ctrl.Name] = SeparateChat(ctrl.Name)
                    except (RuntimeError, ValueError):
                        pass
            return found

        def _scan_loop():
            """扫描线程：定期发现新窗口、清理已关闭窗口"""
            while not stop_event.is_set():
                current = _discover_chats()
                with threads_lock:
                    for name, chat in current.items():
                        if name not in threads:
                            t = threading.Thread(
                                target=_watch_chat,
                                args=(chat, name),
                                daemon=True,
                                name=f"listen-{name}",
                            )
                            threads[name] = t
                            t.start()
                            logger.debug("开始监听: %s", name)

                    for name in list(threads.keys()):
                        if not threads[name].is_alive():
                            threads.pop(name)
                            logger.debug("停止监听: %s", name)

                if stop_event.wait(scan_interval):
                    break

        logger.debug("开始多线程监听独立聊天窗口消息 (Ctrl+C 退出)...")
        # 启动扫描线程
        scanner = threading.Thread(target=_scan_loop, daemon=True, name="scanner")
        scanner.start()

        try:
            while True:
                try:
                    chat, msg = msg_queue.get(timeout=0.1)
                except Empty:
                    continue
                try:
                    callback(chat, msg)
                except Exception as e:
                    logger.exception("回调异常 [%s]", chat.current_name)
        except KeyboardInterrupt:
            logger.debug("正在停止监听线程...")
            stop_event.set()
            scanner.join(timeout=3)
            with threads_lock:
                for t in threads.values():
                    t.join(timeout=3)
            logger.debug("监听已停止")


if __name__ == "__main__":
    wx = Weixin()
    wx.set_room_name("test", "test2")
