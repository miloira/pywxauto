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
import ctypes.wintypes
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from queue import Empty, Queue
from typing import Optional, Iterable

import uiautomation as auto
import win32api
import win32con
import win32gui
import win32ui
import winreg
from PIL import Image
from pyee.base import EventEmitter
from rapidocr import RapidOCR

from .utils import (
    query_reg_install_path, get_wechat_install_path, get_wechat_wxocr_path,
    get_wechat_version, get_hwnd, ensure_narrator_registry,
    get_clipboard, save_clipboard, restore_clipboard, set_clipboard,
    copy_text, copy_files, is_url as _is_url, download_to_temp as _download_to_temp,
    rand_ratio as _rand_ratio,
    wcocr,
)

# ---- 从子模块导入 ----
from . import _state
from .exceptions import (
    WxAutoError, WindowNotFoundError, ControlTimeoutError,
    SendError, OCRError, LoginError, RegistryError,
)
from .capture import capture_window, capture_control
from . import input_wx, input_wm
from .pim import PIM
from .messages import (
    Event, SenderType, MessageStatus,
    Message, TextMessage, QuoteMessage, VoiceMessage, ImageMessage,
    VideoMessage, FileMessage, LocationMessage, LinkMessage,
    EmotionMessage, MergeMessage, PersonalCardMessage, NoteMessage,
    MusicMessage, CardMessage, SystemMessage, VoipMessage,
    TransferMessage, RedPacketMessage, OtherMessage,
    MSG_CLASS_TO_EVENT as _MSG_CLASS_TO_EVENT,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---- 从拆分模块导入业务类 ----
from .windows import WeixinWindow, Login, VoipCallWindow, NoteEditorWindow
from .friend_circle import Moment, FriendCircle
from .file_manager import ChatFile, FileManager
from .session import SessionItem, Navigator, Session
from .chat import Chat, SeparateChat


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

    def __init__(self, install_path: Optional[str] = None, wxocr_path: Optional[str] = None,
                 ocr_engine: str = "wcocr", idle_wait: float = 0, lock_input: bool = False,
                 background: bool = False, resize: bool = True):
        """
        Args:
            install_path: 微信安装路径，None 时自动检测
            wxocr_path:   微信 OCR 插件路径，None 时自动检测
            ocr_engine:   OCR 引擎选择
                - "wcocr":    使用微信自带 OCR（默认）
                - "rapidocr": 使用 RapidOCR
            idle_wait:   人类操作等待时间（秒），大于 0 时自动启动物理输入监控，
                          所有 UI 操作方法执行前会等待用户停止物理键盘/鼠标操作达到该秒数。
                          默认 0 表示不等待。
            lock_input:   True 时在自动化操作期间锁定物理键盘鼠标（需管理员权限），
                          默认 False。
            background:   True 时使用后台模式（通过 SendMessage 发送虚拟鼠标/键盘消息，
                          不需要窗口在前台），默认 False。
            resize:       True 时将微信窗口设置为固定大小（1000x700），
                          False 时保持原窗口大小。默认 True。
        """
        self.background: bool = background

        # 设置全局后台模式标志
        _state.background = background

        # 读取微信版本号
        self.version: str = get_wechat_version(4)

        # 物理输入监控
        if idle_wait > 0:
            PIM(idle_wait=idle_wait, lock_input=lock_input)
            PIM.start()

        # 事件处理器 (pyee EventEmitter)
        self._ee = EventEmitter()

        # 选择OCR引擎
        if ocr_engine not in ("wcocr", "rapidocr"):
            raise ValueError(f"ocr_engine 参数必须为 'wcocr' 或 'rapidocr'，当前: {ocr_engine!r}")
        self._ocr_engine = ocr_engine

        # 微信安装路径
        self.install_path = install_path or get_wechat_install_path(4)

        # 微信OCR插件路径
        self.wxocr_path = wxocr_path or get_wechat_wxocr_path()

        # 初始化 OCR 引擎
        if self._ocr_engine == "wcocr":
            wcocr.init(self.wxocr_path, self.install_path)
        else:
            self._rapid_ocr = RapidOCR()

        # 开启讲述人模式标识 激活微信控件通信
        ensure_narrator_registry()

        # 初始化微信窗口
        self._ensure_running()

        # 窗口定位
        self._win: auto.WindowControl = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            RegexName=self.WINDOW_REGEX,
            searchDepth=1
        )

        # 设置固定窗口大小
        self.resize = resize
        hwnd = self._win.NativeWindowHandle
        if resize and hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            x, y = rect[0], rect[1]
            ctypes.windll.user32.MoveWindow(hwnd, x, y,
                                            self.WINDOW_WIDTH, self.WINDOW_HEIGHT, True)

        # 后台模式下将主窗口移到屏幕外
        self._main_offscreen_rect = None
        if _state.background and hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            self._main_offscreen_rect = (rect[0], rect[1],
                                         rect[2] - rect[0], rect[3] - rect[1])
            ctypes.windll.user32.MoveWindow(hwnd, -9999, 0,
                                            rect[2] - rect[0], rect[3] - rect[1], True)

        # 窗口功能
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

    @staticmethod
    def _ensure_running() -> None:
        # 用 find_wechat_window 判断窗口是否存在
        if Weixin.find_wechat_window():
            return

        # 窗口不存在，尝试用快捷键唤醒
        Weixin.shortcut("显示窗口")

        # 检测微信窗口是否存在
        if Weixin.is_exists_window(timeout=3, interval=0.1):
            return 

        # 唤醒失败，尝试启动微信
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Tencent\Weixin",
            )
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
        except FileNotFoundError:
            raise LoginError("未找到微信安装路径，请确认微信已安装")
        subprocess.Popen([f"{install_path}\\Weixin.exe"])

        # 检测微信窗口是否存在
        if Weixin.is_exists_window(timeout=3, interval=0.1):
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

    def send_text(self, nickname: str, content: str) -> MessageStatus:
        """发送文本消息"""
        return self.chat_with(nickname).send_text(content)

    def send_file(self, nickname: str, file_path: "str | list[str]") -> MessageStatus:
        """发送文件，支持单个或多个路径，支持网络 URL"""
        return self.chat_with(nickname).send_file(file_path)

    def send_image(self, nickname: str, file_path: "str | list[str]") -> MessageStatus:
        """发送图片，支持单个或多个路径，支持网络 URL"""
        return self.chat_with(nickname).send_image(file_path)

    def send_video(self, nickname: str, file_path: "str | list[str]") -> MessageStatus:
        """发送视频，支持单个或多个路径，支持网络 URL"""
        return self.chat_with(nickname).send_video(file_path)

    def send_at(self, nickname: str, content: str, at_members: list[str]) -> MessageStatus:
        """在群聊中 @指定成员发送消息"""
        return self.chat_with(nickname).send_at(content, at_members)

    def send_collection(self, nickname: str, keyword: str) -> bool:
        """发送收藏内容"""
        return self.chat_with(nickname).send_collection(keyword)

    def send_emotion(self, nickname: str, keyword: str = None, index: int = 1) -> bool:
        """发送表情，keyword 为 None 时发送自定义表情"""
        return self.chat_with(nickname).send_emotion(keyword, index)

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

        使用 BitBlt API 捕获窗口内容，返回 PNG bytes。
        """
        hwnd = self._win.NativeWindowHandle
        if not hwnd:
            raise RuntimeError("无法获取微信窗口句柄")
        return capture_window(hwnd)

    def screenshot(self, save_path: str) -> None:
        """
        对微信主窗口截图并保存到指定路径。

        截图前会自动恢复最小化窗口并激活，确保截图内容完整。

        Args:
            save_path: 保存路径（含文件名），如 "C:\\screenshots\\wx.png"
        """
        hwnd = self._win.NativeWindowHandle
        if not hwnd:
            raise RuntimeError("无法获取微信窗口句柄")
        if self.is_minimized:
            self.restore()
            time.sleep(0.3)
        self.activate()
        dir_path = os.path.dirname(save_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        png_bytes = capture_window(hwnd)
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
            png_bytes = capture_control(hwnd, wx_btn, offset_right=20)
            with open("_debug_check_new_msg.png", "wb") as f:
                f.write(png_bytes)
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
            tmp_path = os.path.join(tempfile.gettempdir(), "_pywxauto_ocr_tmp.png")
            try:
                with open(tmp_path, "wb") as f:
                    f.write(image)
                result = wcocr.ocr(tmp_path)
            finally:
                if os.path.exists(tmp_path):
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
        self._offscreen = _state.background

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
            time.sleep(0.3)

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
