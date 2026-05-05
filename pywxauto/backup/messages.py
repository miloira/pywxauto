"""
pywxauto 消息类体系。

包含 Event 枚举、Message 基类及所有消息子类。
"""

from __future__ import annotations

import json
import re
import time
from enum import Enum
from typing import TYPE_CHECKING

import uiautomation as auto
import win32gui

from pywxauto import _state
from pywxauto import input_wx, input_wm

if TYPE_CHECKING:
    pass


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
    OTHER = "other"


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

    def __init__(self, *, sender: str = "", sender_type: SenderType = SenderType.OTHER,
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

        if not _state.background:
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
