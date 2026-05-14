from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import fnmatch
import functools
import glob
import hashlib
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
from collections import deque
from datetime import date
from enum import Enum
from queue import Empty, Queue
from typing import Deque, Dict, Iterable, List, Literal, Optional, Set, Tuple, Union

import psutil
import requests
import uiautomation as auto
import win32api
import win32clipboard
import win32con
import win32gui
import win32process
import win32ui
import winreg
from PIL import Image, ImageFilter, ImageDraw
from pyee.base import EventEmitter
from rapidocr import RapidOCR
import sys

try:
    from . import wcocr
except (ImportError, SystemError):
    try:
        import wcocr
    except ImportError:
        wcocr = None


# ---- 日志配置 ----
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# 全局后台模式标志，由 Weixin.__init__ 设置
background: bool = False

LANGUAGE_DESCRIPTION = {
    "cn": "简体中文",
    "cn_t": "繁體中文",
    "en": "English"
}

LANGUAGE = {
    # ============================================================
    # 登录窗口 (Login 类)
    # ============================================================
    "进入微信": {"cn": "进入微信", "cn_t": "", "en": "Enter Weixin"},
    "切换账号": {"cn": "切换账号", "cn_t": "", "en": "Switch Account"},
    "仅传输文件": {"cn": "仅传输文件", "cn_t": "", "en": "Transfer files only"},
    "网络代理设置": {"cn": "网络代理设置", "cn_t": "", "en": "Network proxy settings"},
    "关闭": {"cn": "关闭", "cn_t": "", "en": "Disable"},
    "返回": {"cn": "返回", "cn_t": "", "en": "Back"},
    "使用代理": {"cn": "使用代理", "cn_t": "", "en": "Use proxy"},
    "保存": {"cn": "保存", "cn_t": "", "en": "Save"},
    "地址": {"cn": "地址", "cn_t": "", "en": "Address"},
    "端口": {"cn": "端口", "cn_t": "", "en": "Port"},
    "账户": {"cn": "账户", "cn_t": "", "en": "Account"},
    "密码": {"cn": "密码", "cn_t": "", "en": "Password"},
    "当前登录用户": {"cn": "当前登录用户", "cn_t": "", "en": "Current User"},
    "正在进入": {"cn": "正在进入", "cn_t": "", "en": "Entering"},
    "需在手机上完成登录": {"cn": "需在手机上完成登录", "cn_t": "", "en": "Confirm on Phone"},
    "二维码": {"cn": "二维码", "cn_t": "", "en": "QR Code"},

    # ============================================================
    # 更新窗口 (WeixinUpdate 类)
    # ============================================================
    "忽略本次更新": {"cn": "忽略本次更新", "cn_t": "", "en": ""},
    "稍后处理": {"cn": "稍后处理", "cn_t": "", "en": ""},
    "更新": {"cn": "更新", "cn_t": "", "en": ""},

    # ============================================================
    # 通话窗口 (VoipCall 类)
    # ============================================================
    "麦克风已开": {"cn": "麦克风已开", "cn_t": "", "en": "Mic is on"},
    "麦克风已关": {"cn": "麦克风已关", "cn_t": "", "en": "Mic is off"},
    "扬声器已开": {"cn": "扬声器已开", "cn_t": "", "en": "Speaker is on"},
    "扬声器已关": {"cn": "扬声器已关", "cn_t": "", "en": "Speaker is off"},
    "摄像头已开": {"cn": "摄像头已开", "cn_t": "", "en": "Camera is on"},
    "摄像头已关": {"cn": "摄像头已关", "cn_t": "", "en": "Camera is off"},
    "无摄像头": {"cn": "无摄像头", "cn_t": "", "en": "No Camera"},
    "取消": {"cn": "取消", "cn_t": "", "en": "Cancel"},
    "挂断": {"cn": "挂断", "cn_t": "", "en": "Hang Up"},
    "切换到视频通话": {"cn": "切换到视频通话", "cn_t": "", "en": "Switch to Video"},
    "语音通话": {"cn": "语音通话", "cn_t": "", "en": "Voice Call"},
    "视频通话": {"cn": "视频通话", "cn_t": "", "en": "Video Call"},

    # ============================================================
    # 导航栏 (Navigator 类)
    # ============================================================
    "微信": {"cn": "微信", "cn_t": "", "en": "Weixin"},
    "通讯录": {"cn": "通讯录", "cn_t": "", "en": "Contacts"},
    "收藏": {"cn": "收藏", "cn_t": "", "en": "Favorites"},
    "朋友圈": {"cn": "朋友圈", "cn_t": "", "en": "Moments"},
    "视频号": {"cn": "视频号", "cn_t": "", "en": "Channels"},
    "搜一搜": {"cn": "搜一搜", "cn_t": "", "en": "Search"},
    "手机": {"cn": "手机", "cn_t": "", "en": "Mobile"},
    "更多": {"cn": "更多", "cn_t": "", "en": "More"},

    # ============================================================
    # 会话列表 (Session 类)
    # ============================================================
    "搜索": {"cn": "搜索", "cn_t": "", "en": "Search"},
    "消息免打扰": {"cn": "消息免打扰", "cn_t": "", "en": "Mute Notifications"},
    "快捷操作": {"cn": "快捷操作", "cn_t": "", "en": "Shortcuts"},
    "发起群聊": {"cn": "发起群聊", "cn_t": "", "en": "Start Group Chat"},
    "添加朋友": {"cn": "添加朋友", "cn_t": "", "en": "Add Contacts"},
    "新建笔记": {"cn": "新建笔记", "cn_t": "", "en": "New Note"},
    "完成": {"cn": "完成", "cn_t": "", "en": "Finish"},
    "置顶": {"cn": "置顶", "cn_t": "", "en": "Sticky"},
    "取消置顶": {"cn": "取消置顶", "cn_t": "", "en": "Remove Sticky"},
    "标为未读": {"cn": "标为未读", "cn_t": "", "en": "Mark as Unread"},
    "标为已读": {"cn": "标为已读", "cn_t": "", "en": "Mark as read"},
    "允许消息通知": {"cn": "允许消息通知", "cn_t": "", "en": "New Message Alert"},
    "独立窗口显示": {"cn": "独立窗口显示", "cn_t": "", "en": "Display in New Window"},
    "不显示": {"cn": "不显示", "cn_t": "", "en": "Hide"},
    "删除": {"cn": "删除", "cn_t": "", "en": "Delete"},
    "联系人": {"cn": "联系人", "cn_t": "", "en": "Contacts"},
    "群聊": {"cn": "群聊", "cn_t": "", "en": "Group Chats"},
    "功能": {"cn": "功能", "cn_t": "", "en": "Features"},
    "最常使用": {"cn": "最常使用", "cn_t": "", "en": "Most used"},
    "添加到通讯录": {"cn": "添加到通讯录", "cn_t": "", "en": "Add to Contacts"},
    "发消息": {"cn": "发消息", "cn_t": "", "en": "Messages"},
    "发送添加朋友申请": {"cn": "发送添加朋友申请", "cn_t": "", "en": "Search Friend Request"},
    "修改备注": {"cn": "修改备注", "cn_t": "", "en": "Remark"},
    "仅聊天": {"cn": "仅聊天", "cn_t": "", "en": "Chats Only"},
    "不让他（她）看": {"cn": "不让他（她）看", "cn_t": "", "en": "Hide My Posts"},
    "不看他（她）": {"cn": "不看他（她）", "cn_t": "", "en": "Hide Their Posts"},
    "确定": {"cn": "确定", "cn_t": "", "en": "OK"},
    "取消": {"cn": "取消", "cn_t": "", "en": "Cancel"},

    # ============================================================
    # 聊天区域 (Chat 类) - 发送相关
    # ============================================================
    "发送": {"cn": "发送", "cn_t": "", "en": "Send"},
    "发送文件": {"cn": "发送文件", "cn_t": "", "en": "Send File"},
    "发送收藏": {"cn": "发送收藏", "cn_t": "", "en": "Send Favorites​Item"},
    "发送表情(Alt+E)": {"cn": "发送表情(Alt+E)", "cn_t": "", "en": "Send sticker(Alt+E)"},
    "搜索表情": {"cn": "搜索表情", "cn_t": "", "en": "Search Stickers"},
    "自定义表情": {"cn": "自定义表情", "cn_t": "", "en": "Custom Stickers"},
    "表情搜索": {"cn": "表情搜索", "cn_t": "", "en": "Search Stickers"},

    # ============================================================
    # 聊天区域 (Chat 类) - 消息右键菜单
    # ============================================================
    "引用": {"cn": "引用", "cn_t": "", "en": "Quote"},
    "复制": {"cn": "复制", "cn_t": "", "en": "Copy"},
    "翻译": {"cn": "翻译", "cn_t": "", "en": "Translate"},
    "转发...": {"cn": "转发...", "cn_t": "", "en": "Forward..."},
    "撤回": {"cn": "撤回", "cn_t": "", "en": "Recall"},
    "放大阅读": {"cn": "放大阅读", "cn_t": "", "en": "Enlarge"},
    "添加到表情": {"cn": "添加到表情", "cn_t": "", "en": "Add to Favorites"},
    "另存为...": {"cn": "另存为...", "cn_t": "", "en": "Save as..."},
    "语音转文字": {"cn": "语音转文字", "cn_t": "", "en": "Audio to Text"},

    # ============================================================
    # 聊天区域 (Chat 类) - 转发/发送弹窗
    # ============================================================
    "微信发送给": {"cn": "微信发送给", "cn_t": "", "en": "WeixinSend To"},

    # ============================================================
    # 聊天区域 (Chat 类) - 聊天信息面板
    # ============================================================
    "聊天信息": {"cn": "聊天信息", "cn_t": "", "en": "Chat Info"},
    "清空聊天记录": {"cn": "清空聊天记录", "cn_t": "", "en": "Clear Chat History"},
    "清空": {"cn": "清空", "cn_t": "", "en": "Clear"},
    "退出群聊": {"cn": "退出群聊", "cn_t": "", "en": "Leave"},
    "添加": {"cn": "添加", "cn_t": "", "en": "Add"},
    "移出": {"cn": "移出", "cn_t": "", "en": "Remove"},
    "置顶聊天": {"cn": "置顶聊天", "cn_t": "", "en": "Sticky on Top"},
    "保存到通讯录": {"cn": "保存到通讯录", "cn_t": "", "en": "Save to Contacts"},
    "显示群成员昵称": {"cn": "显示群成员昵称", "cn_t": "", "en": "On-screen Names"},
    "折叠该聊天": {"cn": "折叠该聊天", "cn_t": "", "en": "Minimize Group"},
    "群聊名称": {"cn": "群聊名称", "cn_t": "", "en": "Group Name"},
    "群公告": {"cn": "群公告", "cn_t": "", "en": "Group Notice"},
    "备注": {"cn": "备注", "cn_t": "", "en": "Remark"},
    "我在本群的昵称": {"cn": "我在本群的昵称", "cn_t": "", "en": "My Alias in Group"},
    "修改": {"cn": "修改", "cn_t": "", "en": "Modify"},
    "发布": {"cn": "发布", "cn_t": "", "en": "Post"},
    "编辑群公告": {"cn": "编辑群公告", "cn_t": "", "en": "Edit Group Notice"},
    "未能邀请": {"cn": "未能邀请", "cn_t": "", "en": "Unable to invite"},
    "我知道了": {"cn": "我知道了", "cn_t": "", "en": "OK"},
    "删除引用消息": {"cn": "删除引用消息", "cn_t": "", "en": "Delete quote"},

    # ============================================================
    # 聊天区域 (Chat 类) - 联系人资料面板
    # ============================================================
    "把他推荐给朋友": {"cn": "把他推荐给朋友", "cn_t": "", "en": "Share him with your friends"},
    "设置备注和标签": {"cn": "设置备注和标签", "cn_t": "", "en": "Edit Contact"},
    "设置朋友权限": {"cn": "设置朋友权限", "cn_t": "", "en": "Set privacy settings"},
    "删除联系人": {"cn": "删除联系人", "cn_t": "", "en": "Delete Contact"},
    "设为星标朋友": {"cn": "设为星标朋友", "cn_t": "", "en": "Star"},
    "不再设为星标朋友": {"cn": "不再设为星标朋友", "cn_t": "", "en": "Unstar"},
    "加入黑名单": {"cn": "加入黑名单", "cn_t": "", "en": "Block"},
    "移出黑名单": {"cn": "移出黑名单", "cn_t": "", "en": "Unblock"},
    "修改备注名": {"cn": "修改备注名", "cn_t": "", "en": "Alias"},
    "修改标签": {"cn": "修改标签", "cn_t": "", "en": "Tags"},
    "搜索或创建标签...": {"cn": "搜索或创建标签...", "cn_t": "", "en": "Search or create tag..."},
    "填写电话": {"cn": "填写电话", "cn_t": "", "en": "Mobile"},
    "添加电话": {"cn": "添加电话", "cn_t": "", "en": "Add mobile"},
    "删除电话": {"cn": "删除电话", "cn_t": "", "en": "DeleteMobile"},
    "修改描述": {"cn": "修改描述", "cn_t": "", "en": "ModifyDescription"},
    "添加图片": {"cn": "添加图片", "cn_t": "", "en": "Add Image"},
    "描述图片": {"cn": "描述图片", "cn_t": "", "en": "DescriptionImage"},
    "朋友权限": {"cn": "朋友权限", "cn_t": "", "en": "Set Privacy Settings"},
    "聊天、朋友圈、微信运动等": {"cn": "聊天、朋友圈、微信运动等", "cn_t": "", "en": "Chats, Moments, WeRun, etc."},

    # ============================================================
    # 朋友圈 (Moment 类)
    # ============================================================
    "朋友圈": {"cn": "朋友圈", "cn_t": "", "en": "Moments"},
    "刷新": {"cn": "刷新", "cn_t": "", "en": "Refresh"},
    "发表": {"cn": "发表", "cn_t": "", "en": "Post"},
    "公开": {"cn": "公开", "cn_t": "", "en": "All"},
    "私密": {"cn": "私密", "cn_t": "", "en": "Private"},
    "谁可以看": {"cn": "谁可以看", "cn_t": "", "en": "Visible To"},
    "不给谁看": {"cn": "不给谁看", "cn_t": "", "en": "Don't Share"},
    "提醒谁看": {"cn": "提醒谁看", "cn_t": "", "en": "Mention"},
    "选照片或视频": {"cn": "选照片或视频", "cn_t": "", "en": "Select photos or videos"},
    "发表文字": {"cn": "发表文字", "cn_t": "", "en": "Post Text"},
    "标签": {"cn": "标签", "cn_t": "", "en": "Tag"},
    "朋友": {"cn": "朋友", "cn_t": "", "en": "Friends"},
    "赞": {"cn": "赞", "cn_t": "", "en": "Like"},
    "评论": {"cn": "评论", "cn_t": "", "en": "Comment"},
    "微信提醒谁看": {"cn": "微信提醒谁看", "cn_t": "", "en": "WeixinMention"},
    "微信谁可以看": {"cn": "微信谁可以看", "cn_t": "", "en": "WeixinVisible To"},
    "微信不给谁看": {"cn": "微信不给谁看", "cn_t": "", "en": "Do Not Share List"},

    # ============================================================
    # 文件管理器 (FileManager 类)
    # ============================================================
    "聊天文件": {"cn": "聊天文件", "cn_t": "", "en": "Chat Files"},
    "全部": {"cn": "全部", "cn_t": "", "en": "All"},
    "文档": {"cn": "文档", "cn_t": "", "en": "Document"},
    "表格": {"cn": "表格", "cn_t": "", "en": "Spreadsheets"},
    "图片": {"cn": "图片", "cn_t": "", "en": "Image"},
    "视频": {"cn": "视频", "cn_t": "", "en": "Video"},
    "下载到...": {"cn": "下载到...", "cn_t": "", "en": "Download to..."},
    "下载": {"cn": "下载", "cn_t": "", "en": "Download"},

    # ============================================================
    # 笔记编辑器 (NoteEditor 类)
    # ============================================================
    "笔记": {"cn": "笔记", "cn_t": "", "en": "Note"},

    # ============================================================
    # 设置/个人资料 (Weixin)
    # ============================================================
    "设置": {"cn": "设置", "cn_t": "", "en": "Settings"},
    "账号与存储": {"cn": "账号与存储", "cn_t": "", "en": "My Account"},
    "锁定": {"cn": "锁定", "cn_t": "", "en": "Lock"},

    # ============================================================
    # 红包/转账 (RedPacketMessage / TransferMessage)
    # ============================================================
    "拆开": {"cn": "拆开", "cn_t": "", "en": "Open"},
    "收款": {"cn": "收款", "cn_t": "", "en": "Accept"},
    "退还": {"cn": "退还", "cn_t": "", "en": "Reject"},

    # ============================================================
    # 消息解析关键词
    # ============================================================
    "语音": {"cn": "语音", "cn_t": "", "en": "Audio"},
    "未播放": {"cn": "未播放", "cn_t": "", "en": "Unplayed"},
    "已播放": {"cn": "已播放", "cn_t": "", "en": "Played"},
    "文件": {"cn": "文件", "cn_t": "", "en": "File"},
    "进度": {"cn": "进度", "cn_t": "", "en": "Progress"},
    "未下载": {"cn": "未下载", "cn_t": "", "en": "Not Downloaded"},
    "下载中": {"cn": "未下载", "cn_t": "", "en": "Downloading"},
    "对方上传中": {"cn": "对方上传中", "cn_t": "", "en": "Uploading by the other user"},
    "已过期": {"cn": "已过期", "cn_t": "", "en": ""},
    "已取消": {"cn": "已取消", "cn_t": "", "en": "Canceled"},
    "已下载": {"cn": "已下载", "cn_t": "", "en": "Downloaded"},
    "位置": {"cn": "位置", "cn_t": "", "en": "Location"},
    "链接": {"cn": "链接", "cn_t": "", "en": "Link"},
    "聊天记录": {"cn": "聊天记录", "cn_t": "", "en": "Chat History"},
    "合并": {"cn": "合并", "cn_t": "", "en": ""},
    "微信红包": {"cn": "微信红包", "cn_t": "", "en": "Weixin Red Packet"},
    "微信转账": {"cn": "微信转账", "cn_t": "", "en": "WeChat Transfer"},
    "动画表情": {"cn": "动画表情", "cn_t": "", "en": "Animated Stickers"},
    "上传中": {"cn": "上传中", "cn_t": "", "en": "Uploading"},
    "发送中断": {"cn": "发送中断", "cn_t": "", "en": "Sending interrupted"},
    "发送失败": {"cn": "发送失败", "cn_t": "", "en": "Unable to send"},
    "发送中": {"cn": "发送中", "cn_t": "", "en": "Sending"},
    "个人名片": {"cn": "_个人名片", "cn_t": "", "en": "Name Card"},
    "所有人": {"cn": "所有人", "cn_t": "", "en": "Metion All"},
    "我": {"cn": "我", "cn_t": "", "en": ""},
    "系统": {"cn": "系统", "cn_t": "", "en": ""},
    "消息": {"cn": "消息", "cn_t": "", "en": ""},
    "网络不可用": {"cn": "网络不可用", "cn_t": "", "en": "Network unavailable"},

    # ============================================================
    # 朋友圈动态解析关键词
    # ============================================================
    "包含": {"cn": "包含", "cn_t": "", "en": "Contain"},
    "张图片": {"cn": "张图片", "cn_t": "", "en": "image(s)"},
    "分钟前": {"cn": "分钟前", "cn_t": "", "en": "minute(s) ago"},
    "小时前": {"cn": "小时前", "cn_t": "", "en": "hour(s) ago"},
    "天前": {"cn": "天前", "cn_t": "", "en": "day(s) ago"},
    "昨天": {"cn": "昨天", "cn_t": "", "en": "Yesterday"},

    # ============================================================
    # 文件管理器日期解析
    # ============================================================
    "今天": {"cn": "今天", "cn_t": "", "en": "Today"},

    # ============================================================
    # 联系人资料字段标签
    # ============================================================
    "昵称：": {"cn": "昵称：", "cn_t": "", "en": "Name"},
    "微信号：": {"cn": "微信号：", "cn_t": "", "en": "Weixin ID"},
    "地区：": {"cn": "地区：", "cn_t": "", "en": "Region"},

    # ============================================================
    # 锁定状态检测
    # ============================================================
    "Windows 微信已被锁定": {"cn": "Windows 微信已被锁定", "cn_t": "", "en": "Weixin for Windows locked"},

    # ============================================================
    # 发送按钮正则 (RegexName)
    # ============================================================
    "发送按钮正则": {"cn": "^发送(\\(S\\))?$", "cn_t": "", "en": "^Send(\\(S\\))?$"},

    # ============================================================
    # 引用消息正则
    # ============================================================
    "引用正则": {"cn": r"^(.+?)引用\s+(.+?)\s+的消息\s*:\s*(.+?)[\n\r]*$", "cn_t": "", "en": r"^(.+?)Quote\s+(.+?)\s+'s message\s*:\s*(.+?)[\n\r]*$"},

    # ============================================================
    # 微信发起群聊弹窗
    # ============================================================
    "微信发起群聊": {"cn": "微信发起群聊", "cn_t": "", "en": "WeixinStart Group Chat"},

    # ============================================================
    # 保存对话框
    # ============================================================
    "保存(&S)": {"cn": "保存(&S)", "cn_t": "", "en": "Save(&S)"},

    # ============================================================
    # 打开对话框
    # ============================================================
    "打开(&O)": {"cn": "打开(&O)", "cn_t": "", "en": "Open(&O)"},
}

# 当前语言，由 Weixin.__init__ 根据实际检测设置
_current_lang: str = "cn"


def i_(text: str, *args, **kwargs) -> str:
    """
    翻译控件文本。

    根据 _current_lang 从 LANGUAGE 字典中查找对应语言的翻译文本。
    支持占位符 {} 和 {key} 格式化。

    查找逻辑：
    1. 在 LANGUAGE 中查找 key=text 的条目
    2. 取当前语言对应的值，如果为空字符串则回退到 "cn"
    3. 如果 LANGUAGE 中没有该 key，直接返回原文
    4. 最后用 args/kwargs 格式化占位符

    Args:
        text: 简体中文原文（作为 LANGUAGE 字典的 key）
        *args: 位置参数，用于填充 {} 占位符
        **kwargs: 关键字参数，用于填充 {key} 占位符

    Returns:
        翻译后的文本（已格式化占位符）

    用法::

        i_(\"进入微信\")           # -> \"Enter Weixin\" (en) / \"进入微信\" (cn)
        i_(\"当前登录用户\")       # -> \"Current User\" (en)
        i_(\"微信{}\", \"谁可以看\")  # -> \"微信谁可以看\" (cn) / 格式化后的英文
    """
    entry = LANGUAGE.get(text)
    if entry is None:
        # LANGUAGE 中没有该 key，直接用原文格式化
        if args or kwargs:
            return text.format(*args, **kwargs)
        return text

    # 取当前语言的翻译
    translated = entry.get(_current_lang, "")
    if not translated:
        # 当前语言翻译为空，回退到简体中文
        translated = entry.get("cn", text)
    if not translated:
        translated = text

    # 格式化占位符
    if args or kwargs:
        try:
            return translated.format(*args, **kwargs)
        except (IndexError, KeyError):
            # 格式化失败（翻译文本的占位符数量不匹配），返回原文格式化
            return text.format(*args, **kwargs)

    return translated


def _set_language(lang: str) -> None:
    """
    设置当前语言。

    Args:
        lang: 语言代码，"cn" / "cn_t" / "en"
    """
    global _current_lang
    if lang not in ("cn", "cn_t", "en"):
        raise ValueError(f"不支持的语言: {lang!r}，可选: cn, cn_t, en")
    _current_lang = lang


def _detect_language(pid: int = None) -> str:
    kwargs = {"RegexName": "微信|Weixin", "searchDepth": 1}
    if pid:
        kwargs["ProcessId"] = pid
    win = auto.WindowControl(**kwargs)
    if win.Exists(0, 0):
        # 检测微信主窗口语言
        lang = _detect_language_by_main_window(win)
        if lang:
            return lang
        # 检测微信登录窗口语言
        lang = _detect_language_by_login_window(win)
        if lang:
            return lang
    return "cn"


def _detect_language_by_main_window(win: auto.WindowControl) -> Optional[str]:
    try:
        tabbar = win.ToolBarControl(ClassName="mmui::MainTabBar", searchDepth=5)
        if not tabbar.Exists(0, 0):
            return None
        name = tabbar.Name or ""
        if name == "导航":
            return "cn"
        elif name == "導航":
            return "cn_t"
        elif name == "Navigation":
            return "en"
    except Exception:
        pass
    return None


def _detect_language_by_login_window(win: auto.WindowControl) -> Optional[str]:
    try:
        # 检测"网络代理设置"按钮（标题栏始终存在）
        if win.ButtonControl(ClassName="mmui::XButton", Name="网络代理设置").Exists(0, 0):
            return "cn"
        if win.ButtonControl(ClassName="mmui::XButton", Name="網路Proxy設定").Exists(0, 0):
            return "cn_t"
        if win.ButtonControl(ClassName="mmui::XButton", Name="Network proxy settings").Exists(0, 0):
            return "en"
    except Exception:
        pass
    return None


class WxAutoError(Exception):
    """异常基类"""
    pass


class WxWindowNotFoundError(WxAutoError):
    """窗口未找到"""
    pass


class WxControlNotFoundError(WxAutoError):
    """窗口控件未找到"""
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
        """
        初始化 PIM 实例，设置全局等待时间和锁定输入参数。

        Args:
            idle_wait: 等待物理空闲的秒数，0 表示不等待。
            lock_input: True 时在操作期间锁定物理输入（需管理员权限）。
        """
        PIM.idle_wait = idle_wait
        PIM.lock_input = lock_input

    def __call__(self, idle_wait: float = None, lock_input: bool = None) -> PIM:
        if idle_wait is not None:
            PIM.idle_wait = idle_wait
        if lock_input is not None:
            PIM.lock_input = lock_input
        return self

    def __enter__(self) -> PIM:
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
    def _keyboard_hook(nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0 and lParam:
            kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if not (kb.flags & _LLKHF_INJECTED):
                PIM._touch()
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    @staticmethod
    def _mouse_hook(nCode: int, wParam: int, lParam: int) -> int:
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


def find_process(name: str) -> List[dict]:
    """
    查询指定名称的进程信息（使用 psutil）。

    Args:
        name: 进程名，如 "Weixin.exe"

    Returns:
        进程列表，每项包含 pid 和 name
    """
    processes = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == name.lower():
                processes.append({"name": proc.info["name"], "pid": proc.info["pid"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

######## 窗口操作
def minimize_window(hwnd: int) -> bool:
    """最小化窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MINIMIZE, 0)

def maximize_window(hwnd: int) -> bool:
    """最大化窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MAXIMIZE, 0)

def restore_window(hwnd: int) -> bool:
    """还原窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)

def close_window(hwnd: int) -> bool:
    """关闭窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)

def focus_window(hwnd: int) -> None:
    """聚焦窗口（不激活）"""
    win32gui.SendMessage(hwnd, win32con.WM_SETFOCUS, 0, 0)

def activate_window(hwnd: int) -> None:
    """激活窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)

def deactivate_window(hwnd: int) -> None:
    """取消激活窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_INACTIVE, 0)

def move_window(hwnd: int, x: int, y: int) -> bool:
    """移动窗口"""
    return not win32gui.SendMessage(hwnd, win32con.WM_MOVE, 0, (y << 16) | x)

def resize_window(hwnd: int, width: int, height: int) -> bool:
    """设置窗口大小"""
    return not win32gui.SendMessage(hwnd, win32con.WM_SIZE, 0, (height << 16) | width)

def show_window(hwnd: int) -> None:
    """显示窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_SHOWWINDOW, True, 0)

def hide_window(hwnd: int) -> None:
    """隐藏窗口"""
    win32gui.SendMessage(hwnd, win32con.WM_SHOWWINDOW, False, 0)

def toggle_window(hwnd: int, status: str) -> Optional[bool]:
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
def move_window(hwnd: int, x: int, y: int) -> None:
    """鼠标移动到指定位置"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lParam)

def click_window(hwnd: int, x: int, y: int) -> None:
    """鼠标左键单击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)

def double_click_window(hwnd: int, x: int, y: int) -> None:
    """鼠标左键双击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)

def right_click_window(hwnd: int, x: int, y: int) -> None:
    """鼠标右键单击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_RBUTTONUP, 0, lParam)

def middle_click_window(hwnd: int, x: int, y: int) -> None:
    """鼠标中键单击"""
    lParam = win32api.MAKELONG(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_MBUTTONDOWN, win32con.MK_MBUTTON, lParam)
    win32gui.SendMessage(hwnd, win32con.WM_MBUTTONUP, 0, lParam)

def scroll_window(hwnd: int, x: int, y: int, delta: int = 120) -> bool:
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
def key_down_window(hwnd: int, key: Union[str, int]) -> bool:
    """按下一个键（不释放）"""
    vk = ord(key.upper()) if isinstance(key, str) else key
    return not win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)

def key_up_window(hwnd: int, key: Union[str, int]) -> bool:
    """释放一个键"""
    vk = ord(key.upper()) if isinstance(key, str) else key
    return not win32gui.SendMessage(hwnd, win32con.WM_KEYUP, vk, 0)

def key_press_window(hwnd: int, key: Union[str, int]) -> bool:
    """按下并释放一个键

    Args:
        hwnd: 窗口句柄
        key: 按键，可以是字符('A')或虚拟键码(win32con.VK_RETURN)
    """
    return key_down_window(hwnd, key) and key_up_window(hwnd, key)

def key_hotkey_window(hwnd: int, modifier: int, key: int) -> bool:
    """发送热键消息（需要目标窗口已注册该热键）

    Args:
        hwnd: 窗口句柄
        modifier: 修饰键，如 win32con.MOD_CONTROL, win32con.MOD_ALT, win32con.MOD_SHIFT
                  可组合使用：win32con.MOD_CONTROL | win32con.MOD_ALT
        key: 按键的虚拟键码，如 ord('A'), win32con.VK_F4
    """
    lParam = (key << 16) | modifier
    return not win32gui.SendMessage(hwnd, win32con.WM_HOTKEY, 0, lParam)

def key_type_window(hwnd: int, text: str) -> bool:
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

def get_weixin_install_path() -> str:
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
    appdata_path = os.getenv("APPDATA")
    if not appdata_path:
        user_profile = os.getenv("USERPROFILE", "")
        if user_profile:
            appdata_path = os.path.join(user_profile, "AppData", "Roaming")
        else:
            return None

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

def get_hwnd(title: Optional[str] = None, mode: Literal["exact", "wildcard", "regex"] = "exact", pid: Optional[int] = None) -> Optional[int]:
    """根据窗口标题获取窗口句柄

    Args:
        title: 窗口标题，传None获取当前激活的窗口句柄
        mode: 匹配模式
            - "exact": 完全匹配
            - "wildcard": 通配符匹配（支持 * 和 ?）
            - "regex": 正则表达式匹配
        pid: 进程 PID，传入时按 PID 过滤，None 不过滤

    Returns:
        匹配到的窗口句柄
    """
    if title is None and pid is None:
        return win32gui.GetForegroundWindow()

    results = []

    def enum_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if pid is not None:
            _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
            if win_pid != pid:
                return
        if title is None:
            results.append(hwnd)
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

def get_hwnds_by_pid(pid: int, visible_only: bool = True) -> List[int]:
    """
    获取指定进程 PID 的所有顶层窗口句柄。

    Args:
        pid: 进程 PID
        visible_only: True 只返回可见窗口，False 返回所有窗口

    Returns:
        窗口句柄列表
    """
    results = []

    def enum_callback(hwnd, _):
        if visible_only and not win32gui.IsWindowVisible(hwnd):
            return
        _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
        if win_pid == pid:
            results.append(hwnd)

    win32gui.EnumWindows(enum_callback, None)
    return results

def wx_pid_to_hwnd(pid: int) -> Optional[int]:
    """
    将进程 PID 转换为主窗口句柄。

    优先返回可见窗口中标题不为空的第一个，
    找不到则返回任意可见窗口，仍找不到返回 None。

    Args:
        pid: 进程 PID

    Returns:
        窗口句柄，未找到返回 None
    """
    hwnds = get_hwnds_by_pid(pid, visible_only=True)
    if not hwnds:
        # 尝试包含不可见窗口
        hwnds = get_hwnds_by_pid(pid, visible_only=False)

    if not hwnds:
        return None

    # 优先返回有标题的窗口
    for hwnd in hwnds:
        title = win32gui.GetWindowText(hwnd)
        if title.lower() in ["微信", "weixin"]:
            return hwnd
    return hwnds[0]

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
def _open_clipboard_with_retry(max_retries: int = 10, interval: float = 0.1) -> None:
    """带重试的 OpenClipboard，避免剪贴板被其他进程短暂占用时直接失败。"""
    for i in range(max_retries):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            if i == max_retries - 1:
                raise
            time.sleep(interval)

def get_clipboard_all() -> Dict[int, object]:
    result = {}
    _open_clipboard_with_retry()
    try:
        fmt = 0
        while True:
            fmt = win32clipboard.EnumClipboardFormats(fmt)
            if fmt == 0:
                break
            if win32clipboard.IsClipboardFormatAvailable(fmt):
                data = win32clipboard.GetClipboardData(fmt)
                result[fmt] = data
        return result
    finally:
        win32clipboard.CloseClipboard()

def get_clipboard(fmt: int) -> object:
    _open_clipboard_with_retry()
    try:
        if win32clipboard.IsClipboardFormatAvailable(fmt):
            data = win32clipboard.GetClipboardData(fmt)
            return data
    finally:
        win32clipboard.CloseClipboard()

def get_clipboard_text() -> Optional[str]:
    return get_clipboard(win32con.CF_UNICODETEXT)

def get_clipboard_file() -> Optional[str]:
    files = get_clipboard(win32con.CF_HDROP)
    return files[0] if files else None

def save_clipboard() -> Optional[Tuple[int, object]]:
    """
    保存当前剪贴板中的一条数据（按优先级匹配格式）。

    Returns:
        (format, data) 元组，剪贴板为空时返回 None
    """
    _open_clipboard_with_retry()
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

def restore_clipboard(saved: Optional[Tuple[int, object]]) -> None:
    """
    恢复之前保存的剪贴板数据。

    Args:
        saved: save_clipboard 返回的 (format, data)，None 则清空剪贴板
    """
    _open_clipboard_with_retry()
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

def set_clipboard(fmt: int, data: object) -> None:
    _open_clipboard_with_retry()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(fmt, data)
    finally:
        win32clipboard.CloseClipboard()

def copy_text(text: str) -> None:
    if text.isdigit():
        text += "\0"
    set_clipboard(win32con.CF_UNICODETEXT, text)

def copy_files(file_paths: List[str]) -> None:
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
    name_part, ext_part = os.path.splitext(basename)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext_part, prefix=f"{name_part}_", dir=tmp_dir)
    os.close(tmp_fd)

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
    from windows_capture import WindowsCapture, Frame, InternalCaptureControl # pip install windows-capture
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
    mode: Literal["bitblt", "print_window", "window_capture"] = "bitblt"
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
    uia_control: auto.Control,
    offset_left: int = 0, 
    offset_top: int = 0,
    offset_right: int = 0, 
    offset_bottom: int = 0, 
    mode: Literal["bitblt", "print_window", "window_capture"] = "bitblt"
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

def rand_ratio() -> float:
    """返回 0.2~0.6 之间的随机比例，用于模拟人类点击偏移"""
    return random.uniform(0.2, 0.6)


def _find_contour_rects(
    image_bytes: bytes,
    threshold: int = 1,
    min_area: int = 100,
    border_margin: int = 2,
) -> Tuple[bytes, List[Tuple[int, int, int, int]]]:
    """
    检测图片中的轮廓区域，用红色矩形框出并返回标注图和坐标。

    规则：
    - 触碰图片边缘的区域视为图片边框，排除
    - 被其他矩形完全包含的矩形排除，只保留最外层

    Args:
        image_bytes: 输入图片的字节数据（PNG/JPG 等）
        threshold: 边缘二值化阈值（0-255）
        min_area: 最小区域面积（像素数），过滤噪点
        border_margin: 边缘容差像素

    Returns:
        (标注后的 PNG 图片字节数据, 矩形坐标列表 [(x1, y1, x2, y2), ...])
    """
    from PIL import ImageFilter, ImageDraw

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    gray = img.convert("L")
    w, h = img.size

    edges = gray.filter(ImageFilter.FIND_EDGES)
    binary = edges.point(lambda p: 1 if p > threshold else 0, mode="1")

    pixels = binary.load()
    visited = [[False] * h for _ in range(w)]
    raw_rects: List[Tuple[int, int, int, int]] = []

    for y in range(h):
        for x in range(w):
            if pixels[x, y] == 0 or visited[x][y]:
                continue
            min_x, min_y, max_x, max_y = x, y, x, y
            stack = [(x, y)]
            area = 0
            while stack:
                cx, cy = stack.pop()
                if cx < 0 or cx >= w or cy < 0 or cy >= h:
                    continue
                if visited[cx][cy] or pixels[cx, cy] == 0:
                    continue
                visited[cx][cy] = True
                area += 1
                min_x = min(min_x, cx)
                min_y = min(min_y, cy)
                max_x = max(max_x, cx)
                max_y = max(max_y, cy)
                stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
            if area >= min_area:
                raw_rects.append((min_x, min_y, max_x, max_y))

    # 过滤触碰图片边缘的区域
    rects = [r for r in raw_rects
             if not (r[0] <= border_margin or r[1] <= border_margin
                     or r[2] >= w - 1 - border_margin or r[3] >= h - 1 - border_margin)]

    # 去除被其他矩形完全包含的
    result_rects = []
    for i, a in enumerate(rects):
        contained = False
        for j, b in enumerate(rects):
            if i == j:
                continue
            if b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3]:
                if a == b and i < j:
                    continue
                contained = True
                break
        if not contained:
            result_rects.append(a)

    draw = ImageDraw.Draw(img)
    for rect in result_rects:
        draw.rectangle(rect, outline="red", width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), result_rects


def _classify_contour_rects(
    rects: List[Tuple[int, int, int, int]],
    image_bytes: bytes = None,
) -> Tuple[tuple, tuple, tuple]:
    """
    将轮廓矩形分类为头像、昵称、消息内容。

    规则：
    - 头像：宽高比接近 1:1（差异 < 20%）的矩形，且最靠近图片左边或右边
    - 剩余矩形：y1 较小的是昵称（上方），y1 较大的是消息内容（下方）

    分类完成后保存标注图到当前路径 classify_debug.png，
    用不同颜色标注：绿色=头像，蓝色=昵称，红色=消息内容。

    Args:
        rects: 矩形列表 [(x1, y1, x2, y2), ...]
        image_bytes: 原始图片字节数据，用于保存调试图

    Returns:
        (headimg_rect, nickname_rect, content_rect)
        每个为 (x1, y1, x2, y2) 或空元组 ()
    """
    from PIL import ImageDraw

    headimg_rect = ()
    nickname_rect = ()
    content_rect = ()

    if not rects:
        return headimg_rect, nickname_rect, content_rect

    # 获取图片宽度（用于判断靠近左边还是右边）
    img_width = 0
    if image_bytes:
        try:
            img_tmp = Image.open(io.BytesIO(image_bytes))
            img_width = img_tmp.size[0]
        except Exception:
            pass

    # 筛选正方形（宽高比接近 1:1）
    squares = []
    others = []
    for rect in rects:
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1
        if w <= 0 or h <= 0:
            continue
        ratio = min(w, h) / max(w, h)
        if ratio > 0.8:
            squares.append(rect)
        else:
            others.append(rect)

    # 头像：正方形中最靠近图片左边或右边的
    if squares and img_width > 0:
        def edge_distance(r):
            """矩形到图片左边或右边的最小距离"""
            return min(r[0], img_width - r[2])
        headimg_rect = min(squares, key=edge_distance)
    elif squares:
        headimg_rect = squares[0]

    # 剩余矩形（排除已选为头像的）
    remaining = [r for r in others]
    # 如果有多个正方形，非头像的正方形也加入剩余
    for sq in squares:
        if sq != headimg_rect:
            remaining.append(sq)

    # 分类昵称和消息内容
    # 昵称条件：top >= 头像top，bottom <= 头像中线（top + height/2）
    # 矩形top在头像bottom下面的忽略
    # 不满足昵称条件的归为消息内容
    if headimg_rect and remaining:
        head_top = headimg_rect[1]
        head_bottom = headimg_rect[3]
        head_mid = head_top + (head_bottom - head_top) // 2
        nickname_candidates = []
        content_candidates = []
        top_tolerance = 5  # content的top允许比头像top高几个像素（几乎平齐）
        for r in remaining:
            r_top, r_bottom = r[1], r[3]
            # 矩形top在头像bottom下面的忽略
            if r_top > head_bottom:
                continue
            if r_top >= head_top and r_bottom <= head_mid:
                nickname_candidates.append(r)
            elif r_top >= head_top - top_tolerance:
                content_candidates.append(r)
        # 昵称取第一个（应该只有一个）
        if nickname_candidates:
            nickname_rect = nickname_candidates[0]
        # 消息内容：取 top 和头像 top 最接近的（最平齐的）
        if content_candidates:
            content_rect = min(content_candidates, key=lambda r: abs(r[1] - head_top))
        # 验证：没有nickname时，content的top应和头像top几乎平齐
        # 如果差距过大，说明识别有误，丢弃content
        if not nickname_rect and content_rect:
            if abs(content_rect[1] - head_top) > top_tolerance:
                content_rect = ()
    elif len(remaining) >= 2:
        remaining.sort(key=lambda r: r[1])
        nickname_rect = remaining[0]
        content_rect = remaining[1]
    elif len(remaining) == 1:
        content_rect = remaining[0]

    # 保存分类调试图
    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            draw = ImageDraw.Draw(img)
            if headimg_rect:
                draw.rectangle(headimg_rect, outline="green", width=2)
                draw.text((headimg_rect[0], headimg_rect[1] - 12), "headimg", fill="green")
            if nickname_rect:
                draw.rectangle(nickname_rect, outline="blue", width=2)
                draw.text((nickname_rect[0], nickname_rect[1] - 12), "nickname", fill="blue")
            if content_rect:
                draw.rectangle(content_rect, outline="red", width=2)
                draw.text((content_rect[0], content_rect[1] - 12), "content", fill="red")
            img.save("classify_debug.png")
        except Exception:
            pass

    return headimg_rect, nickname_rect, content_rect


def _get_hwnd(control: auto.Control) -> int:
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

def _screen_to_client(control: auto.Control, randomize: bool = True) -> Tuple[int, int, int]:
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

def activate(control: auto.Control) -> None:
    """
    激活控件所属窗口。

    前台模式: uiautomation SetActive + SetFocus
    后台模式: SendMessage WM_ACTIVATE
    """
    if not background:
        control.SetActive()
        control.SetFocus()
    else:
        hwnd = _get_hwnd(control)
        if hwnd:
            input_wm.activate_window(hwnd)

def focus(control: auto.Control) -> None:
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

def click(control: auto.Control, button: Literal["left", "right", "middle"] = "left", click: Literal["once", "double"] = "once") -> None:
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
            control.DoubleClick(simulateMove=False)
        elif button == "right":
            control.RightClick(ratioX=rand_ratio(), ratioY=rand_ratio(), simulateMove=False)
        else:
            control.Click(ratioX=rand_ratio(), ratioY=rand_ratio(), simulateMove=False)
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

def send_keys(control: Optional[auto.Control], text: str) -> None:
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

def move_to(control: auto.Control) -> None:
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

def paste(content: object) -> None:
    """
    通过剪贴板粘贴内容。

    保存当前剪贴板 → 设置内容到剪贴板 → Ctrl+V 粘贴 → 恢复剪贴板。

    Args:
        content: str 粘贴文本，List[str] 粘贴文件路径列表
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

def paste_or_type(control: Optional[auto.Control], text: str) -> None:
    """
    输入纯文本内容（不含功能键）。

    后台模式: 通过 WM_CHAR/WM_IME_CHAR 逐字符发送（非 ASCII 用 WM_IME_CHAR）
    前台模式: 使用 paste 通过剪贴板粘贴

    Args:
        control: uiautomation 控件对象，后台模式下用于获取窗口句柄
        text:    要输入的纯文本字符串
    """
    if not background:
        paste(text)
    else:
        hwnd = 0
        if control is not None:
            hwnd = _get_hwnd(control)
        if not hwnd:
            hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise RuntimeError("无法获取目标窗口句柄")
        input_wm.focus_window(hwnd)
        for ch in text:
            code = ord(ch)
            if code > 127:
                # 非 ASCII（中文等）使用 WM_IME_CHAR
                win32gui.SendMessage(hwnd, 0x0286, code, 0)
            else:
                win32gui.SendMessage(hwnd, win32con.WM_CHAR, code, 0)

# ---- input_wx 命名空间（供其他模块通过 input_wx.xxx 调用） ----
class _InputWxNamespace:
    """模拟 input_wx 模块命名空间，使 input_wx.xxx() 调用方式继续工作"""
    activate = staticmethod(activate)
    focus = staticmethod(focus)
    click = staticmethod(click)
    send_keys = staticmethod(send_keys)
    move_to = staticmethod(move_to)
    scroll_at = staticmethod(scroll_at)
    send_shortcut = staticmethod(send_shortcut)
    select_all = staticmethod(select_all)
    copy = staticmethod(copy)
    paste = staticmethod(paste)
    paste_or_type = staticmethod(paste_or_type)

input_wx = _InputWxNamespace()

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
class Source(Enum):
    """消息来源类型"""
    SYSTEM = "system"
    SELF = "self"
    OTHERS = "others"
    UNKNOWN = "unknown"


class MessageStatus(Enum):
    """消息发送状态"""
    SENT = "sent"
    SENDING = "sending"
    FAILED = "failed"
    RECEIVED = "received"
    UNKNOWN = "unknown"


class Message:
    """聊天消息基类"""

    def __init__(self, *, sender: str = "", source: Source = Source.UNKNOWN,
                 content: str = "", raw_name: str = "", ui_cls: str = "",
                 status: MessageStatus = MessageStatus.UNKNOWN,
                 runtime_id: tuple = (), bubble_rect: tuple = (),
                 room: Optional[str] = None, chat: object = None,
                 control: object = None, pid: int = 0,
                 headimg_rect: tuple = (), nickname_rect: tuple = (),
                 content_rect: tuple = ()):
        self.sender: str = sender
        self.source: Source = source
        self.content: str = content
        self.raw_name: str = raw_name
        self.ui_cls: str = ui_cls
        self.status: MessageStatus = status
        self.runtime_id: tuple = runtime_id
        self.bubble_rect: tuple = bubble_rect
        self.room: Optional[str] = room
        self.control: object = control
        self.chat: object = chat
        self.chat_type: str = self.chat.chat_type if self.chat else "未知"
        self.pid: int = pid
        self.headimg_rect: tuple = headimg_rect
        self.nickname_rect: tuple = nickname_rect
        self.content_rect: tuple = content_rect
        self.msg_id: int = hash((runtime_id, ui_cls, raw_name))

    @property
    def type_label(self) -> str:
        return "消息"

    def to_dict(self) -> dict:
        result = {
            "type": self.__class__.__name__,
            "type_label": self.type_label,
            "msg_id": self.msg_id,
            "sender": self.sender,
            "source": self.source.value,
            "room": self.room,
            "content": self.content,
            "raw_name": self.raw_name,
            "status": self.status.value,
        }
        _base_keys = {"sender", "source", "content", "raw_name", "ui_cls",
                      "status", "runtime_id", "bubble_rect", "chat",
                      "msg_id", "control", "room", "pid", "chat_type",
                      "headimg_rect", "nickname_rect", "content_rect"}
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
        return (f"{cls}(msg_id={self.msg_id}, chat_type={self.chat_type!r}, "
                f"room={self.room!r}, sender={self.sender!r}, "
                f"source={self.source.value}, content={self.content!r}, pid={self.pid})")

    def __str__(self) -> str:
        cls = self.__class__.__name__
        return (f"{cls}(msg_id={self.msg_id}, chat_type={self.chat_type!r}, "
                f"room={self.room!r}, sender={self.sender!r}, "
                f"source={self.source.value}, content={self.content!r}, pid={self.pid})")

    def _find_ctrl(self) -> Optional[auto.Control]:
        """
        在当前可见的消息列表中查找此消息对应的控件。

        优先使用已缓存的 control 引用，其次通过 runtime_id 在控件树中匹配。
        避免调用 get_visible_messages 以防止截图导致的闪烁。
        """
        if not self.chat:
            return None

        # 优先使用已缓存的 control 引用
        if self.control is not None:
            try:
                # 验证控件仍然有效（未被回收）
                _ = self.control.BoundingRectangle
                return self.control
            except Exception:
                self.control = None

        # 通过 runtime_id 在控件树中匹配
        if not self.runtime_id:
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
                rid = ()
            if rid == self.runtime_id:
                self.control = ctrl
                return ctrl

        return None

    @property
    def is_visible(self) -> bool:
        """
        判断消息是否在聊天可见区域内。

        通过消息控件的 BoundingRectangle 与 chat.message_view_rect 比较，
        消息控件的顶部和底部都在可见区域内则视为可见。

        Returns:
            True 消息在可见区域内，False 不在或无法判断
        """
        if not self.chat:
            return False
        view_rect = self.chat.message_view_rect
        if not view_rect:
            return False
        ctrl = self._find_ctrl()
        if not ctrl:
            return False
        try:
            rect = ctrl.BoundingRectangle
            return rect.top >= view_rect[1] and rect.bottom <= view_rect[3]
        except Exception:
            return False

    @property
    def center(self) -> Optional[Tuple[int, int]]:
        """
        获取消息内容区域的屏幕中心点坐标。

        x 使用 content_rect（相对于控件截图的坐标）计算，
        y 使用控件实时的 BoundingRectangle 中心并向上偏移 10px，
        因为消息滚动时 y 会变动，content_rect 的 y 是截图时的静态值。

        Returns:
            (x, y) 屏幕坐标，无法计算时返回 None
        """
        ctrl = self._find_ctrl()
        if not ctrl:
            return None
        try:
            rect = ctrl.BoundingRectangle
            x1, _, x2, _ = self.content_rect
            cx = rect.left + (x1 + x2) // 2
            cy = (rect.top + rect.bottom) // 2 - 8
            return (cx, cy)
        except Exception:
            rect = ctrl.BoundingRectangle
            cy = (rect.top + rect.bottom) // 2 - 8 # 向上偏移10px保证引用消息悬浮位置正确
            if self.bubble_rect:
                bl, bt, br, bb = self.bubble_rect
                # bubble_rect 的 x 坐标不变，y 坐标从控件实时位置重新计算
                cx = (bl + br) // 2
            elif self.source == Source.SELF:
                cx = rect.right - rect.width() // 4
            elif self.source == Source.OTHERS:
                cx = rect.left + rect.width() // 4
            else:
                cx = (rect.left + rect.right) // 2
            return (cx, cy)

    @PIM.guard
    def scroll_to_visible(self, max_scroll: int = 30) -> bool:
        """
        将消息滚动到可见区域。

        智能策略：
        1. 通过 is_visible 检查消息是否已在可见区域，是则直接返回
        2. 不在可见区域时，向上平滑滚动查找，最多滚动 max_scroll 次
        3. 每次滚动后用 message_view_rect 判断是否进入可见区域
        4. 超过最大滚动次数仍未找到，调用 page_end 回到最新消息位置，返回 False

        Args:
            max_scroll: 最大滚动次数，默认 30 次。超过后放弃查找并回到底部。

        Returns:
            True 消息已在可见区域，False 未找到或超出滚动范围
        """
        if not self.chat:
            return False

        # 1. 先检查消息是否已在可见区域
        if self.is_visible:
            return True

        view_rect = self.chat.message_view_rect
        if not view_rect:
            return False

        # 2. 不在可见区域，向上平滑滚动查找
        self.chat._scan_paused = True
        try:
            cx = (view_rect[0] + view_rect[2]) // 2
            cy = (view_rect[1] + view_rect[3]) // 2

            for _ in range(max_scroll):
                scroll_at(cx, cy, 120)  # 向上滚动 1 格
                ctrl = self._find_ctrl()
                if not ctrl:
                    continue
                # 找到控件后微调确保完全可见
                try:
                    ctrl_rect = ctrl.BoundingRectangle
                    if ctrl_rect.top >= view_rect[1] and ctrl_rect.bottom <= view_rect[3]:
                        return True
                    # 微调滚动
                    for _ in range(10):
                        ctrl_rect = ctrl.BoundingRectangle
                        if ctrl_rect.top >= view_rect[1] and ctrl_rect.bottom <= view_rect[3] - 10:
                            return True
                        if ctrl_rect.top < view_rect[1]:
                            scroll_at(cx, cy, 120)
                        else:
                            scroll_at(cx, cy, -120)
                        time.sleep(0.1)
                    return True
                except Exception:
                    return True

            # 3. 超过最大滚动次数，回到底部
            self.chat.page_end()
            return False
        finally:
            self.chat._scan_paused = False

    @PIM.guard
    def view(self) -> None:
        """
        查看/打开消息内容。

        通过先悬浮到消息气泡位置再点击触发查看操作：
        - 图片消息: 打开图片预览窗口
        - 视频消息: 打开视频播放窗口
        - 文件消息: 打开文件（使用默认程序）
        - 链接/卡片消息: 打开链接详情
        - 语音消息: 播放语音
        - 其他消息: 点击气泡（触发默认行为）

        Raises:
            RuntimeError: 消息未关联 chat 或控件未找到时抛出
        """
        if not self.chat:
            raise RuntimeError("消息未关联聊天窗口，无法查看消息")

        self.chat._activate_window()

        if not self.hover():
            raise RuntimeError("无法悬浮到消息位置")

        # hover 后鼠标已在气泡位置，原地点击
        if not background:
            x, y = auto.GetCursorPos()
            auto.Click(x, y)
        else:
            ctrl = self._find_ctrl()
            if not ctrl:
                raise WxControlNotFoundError("未找到消息控件")
            input_wx.click(ctrl)

    @PIM.guard
    def hover(self) -> bool:
        if not self.chat:
            return False

        self.chat._activate_window()

        if not self.scroll_to_visible():
            return False

        cx, cy = self.center

        if not background:
            auto.SetCursorPos(cx, cy)
        else:
            hwnd = self.chat._win.NativeWindowHandle
            if hwnd:
                client_x, client_y = win32gui.ScreenToClient(hwnd, (cx, cy))
                input_wm.move_window(hwnd, client_x, client_y)

        return True

    def _click_context_menu(self, menu_name: str) -> None:
        """
        右键点击消息气泡并在弹出菜单中点击指定项。

        流程: hover 定位 → 右键 → 查找菜单 → 点击菜单项

        Args:
            menu_name: 菜单项名称，如 "引用"、"删除"、"转发"、"收藏"、"多选"

        Raises:
            RuntimeError: 消息未关联 chat、hover 失败、菜单未弹出或菜单项未找到时抛出
        """
        if not self.chat:
            raise RuntimeError(f"消息未关联聊天窗口，无法执行'{menu_name}'操作")

        self.chat._activate_window()

        if not self.hover():
            raise RuntimeError("无法将消息滚动到可见区域或悬浮失败")

        # hover 后鼠标已在气泡位置，原地右键
        if not background:
            x, y = auto.GetCursorPos()
            auto.RightClick(x, y)
        else:
            target = self._find_ctrl()
            if not target:
                raise WxControlNotFoundError("未找到消息控件")
            input_wx.click(target, button="right")

        time.sleep(0.5)

        # 查找右键菜单
        win = self.chat._win
        menu_win = win.WindowControl(ClassName="mmui::XMenu")
        if not menu_win.Exists(maxSearchSeconds=2):
            raise RuntimeError("右键菜单未弹出")

        # 点击指定菜单项
        menu_item = menu_win.MenuItemControl(
            ClassName="mmui::XMenuView",
            AutomationId="XMenuItem",
            Name=menu_name,
        )
        if not menu_item.Exists(maxSearchSeconds=1):
            input_wx.send_keys(win, "{Esc}")
            raise WxControlNotFoundError(f"右键菜单中未找到'{menu_name}'选项")

        input_wx.click(menu_item)
        time.sleep(0.3)

    @PIM.guard
    def quote(self) -> None:
        """
        引用此条消息。

        右键点击消息气泡，在菜单中点击"引用"，
        输入框进入引用模式，可继续输入回复内容。

        智能滚动策略：
        - 消息在可见区域内时直接操作，不触发任何滚动
        - 消息不在可见区域时向上滚动查找（最多 20 次）
        - 超出范围时自动回到底部
        """
        self._click_context_menu(i_("引用"))

    @PIM.guard
    def copy(self) -> str:
        """
        复制此条消息内容到剪贴板并返回。

        右键点击消息气泡，在菜单中点击"复制"，
        然后从剪贴板读取复制的文本内容。

        Returns:
            复制到剪贴板的文本内容
        """
        self._click_context_menu(i_("复制"))
        return get_clipboard_text()

    @PIM.guard
    def collect(self) -> None:
        """
        收藏此条消息。

        右键点击消息气泡，在菜单中点击"收藏"。

        Returns:
            True 收藏成功
        """
        self._click_context_menu(i_("收藏"))

    @PIM.guard
    def translate(self) -> bool:
        """
        翻译此条消息。

        右键点击消息气泡，在菜单中点击"翻译"。
        翻译结果会显示在消息气泡下方。

        Returns:
            True 翻译成功
        """
        self._click_context_menu(i_("翻译"))

    @PIM.guard
    def forward(self, nicknames: Union[str, List[str]], remark: Optional[str] = None) -> bool:
        """
        转发此条消息给指定联系人。

        流程:
        1. 右键点击消息气泡，在菜单中点击"转发..."
        2. 在"微信发送给"弹窗中逐个搜索并勾选接收者
        3. 可选填写留言（remark）
        4. 点击"发送"按钮

        弹窗控件结构:
        - 弹窗: WindowControl, ClassName="mmui::SessionPickerWindow", Name="微信发送给"
        - 搜索框: EditControl, Name=i_("搜索"), ClassName="mmui::XValidatorTextEdit"
          位于 mmui::XSearchField 内
        - 搜索结果列表: ListControl, AutomationId="sp_search_result_list"
        - 搜索结果项: CheckBoxControl, ClassName="mmui::SearchContactCellView"
        - 留言输入框: EditControl, Name="输入", AutomationId="leave_message_view.chat_input_field"
        - 发送按钮: ButtonControl, Name="发送", AutomationId="confirm_btn"

        Args:
            nicknames: 接收者昵称，支持单个字符串或列表（多人转发）
            remark:    留言内容，空字符串不填写留言

        Returns:
            True 转发成功

        Raises:
            RuntimeError: 操作失败时抛出
        """
        if isinstance(nicknames, str):
            nicknames = [nicknames]
        if not nicknames:
            raise ValueError("nicknames 不能为空")

        self._click_context_menu(i_("转发..."))

        # 等待"微信发送给"弹窗出现
        win = self.chat._win
        picker_win = win.WindowControl(
            ClassName="mmui::SessionPickerWindow",
            Name=i_("微信发送给"),
        )
        if not picker_win.Exists(maxSearchSeconds=3):
            raise RuntimeError("'微信发送给'弹窗未打开")

        # 逐个搜索并勾选接收者
        for nickname in nicknames:
            # 定位搜索框
            search_field = picker_win.GroupControl(
                ClassName="mmui::XSearchField",
                searchDepth=3,
            )
            if not search_field.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("弹窗中未找到搜索区域")
            search_edit = search_field.EditControl(
                ClassName="mmui::XValidatorTextEdit",
                Name=i_("搜索"),
                searchDepth=1,
            )
            if not search_edit.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("弹窗中未找到搜索框")

            input_wx.click(search_edit)
            time.sleep(0.3)
            input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
            time.sleep(0.2)
            input_wx.paste_or_type(search_edit, nickname)
            time.sleep(1.5)

            # 在搜索结果中勾选第一个匹配项
            result_list = picker_win.ListControl(
                ClassName="mmui::XTableView",
                AutomationId="sp_search_result_list",
                searchDepth=5,
            )
            if not result_list.Exists(maxSearchSeconds=3):
                raise RuntimeError(f"搜索 '{nickname}' 后未出现结果列表")

            contact_row = result_list.CheckBoxControl(
                ClassName="mmui::SearchContactCellView",
                searchDepth=2,
            )
            if not contact_row.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError(f"搜索结果中未找到联系人: {nickname}")

            input_wx.click(contact_row)
            time.sleep(0.5)

        # 填写留言
        if remark:
            leave_msg_edit = picker_win.EditControl(
                ClassName="mmui::ChatInputField",
                AutomationId="leave_message_view.chat_input_field",
                searchDepth=5,
            )
            if leave_msg_edit.Exists(maxSearchSeconds=2):
                input_wx.click(leave_msg_edit)
                time.sleep(0.2)
                input_wx.paste_or_type(leave_msg_edit, remark)
                time.sleep(0.3)

        # 点击"发送"/"分别发送"按钮
        send_btn = picker_win.ButtonControl(
            AutomationId="confirm_btn",
            searchDepth=5,
        )
        if not send_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'发送'按钮")

        # 等待按钮可用
        for _ in range(10):
            if send_btn.IsEnabled:
                break
            time.sleep(0.3)
        else:
            raise RuntimeError("'发送'按钮未启用，可能接收者未正确选中")

        input_wx.click(send_btn)

    @PIM.guard
    def search(self) -> None:
        """
        搜一搜此条消息内容。

        右键点击消息气泡，在菜单中点击"搜一搜"。
        微信会打开搜一搜窗口并搜索消息中的文本内容。

        Returns:
            True 操作成功
        """
        self._click_context_menu(i_("搜一搜"))

    @PIM.guard
    def revoke(self) -> None:
        """
        撤回此条消息（仅限自己发送的消息，且在 2 分钟内）。

        右键点击消息气泡，在菜单中点击"撤回"。

        Returns:
            True 撤回成功
        """
        self._click_context_menu(i_("撤回"))

    @PIM.guard
    def zoom_read(self) -> None:
        """
        放大阅读此条消息。

        右键点击消息气泡，在菜单中点击"放大阅读"。
        微信会弹出放大阅读窗口显示消息内容。
        """
        self._click_context_menu(i_("放大阅读"))

    @PIM.guard
    def add_to_emotion(self) -> None:
        """
        将此条消息添加到自定义表情。

        右键点击消息气泡，在菜单中点击"添加到表情"。
        适用于图片消息和动画表情消息。

        Raises:
            RuntimeError: 消息未关联 chat、hover 失败、菜单未弹出或
                         "添加到表情"选项未找到时抛出
        """
        self._click_context_menu(i_("添加到表情"))

    @PIM.guard
    def save_as(self, file_path: str) -> bool:
        """
        将消息内容另存为到指定路径。

        右键点击消息气泡，在菜单中点击"另存为..."，
        在弹出的系统文件保存对话框中输入保存路径并点击保存。
        适用于图片、视频、文件等可保存的消息类型。

        Args:
            file_path: 完整的保存路径（含文件名），如 "C:\\download\\image.png"

        Returns:
            True 保存成功，False 保存失败

        Raises:
            RuntimeError: 消息未关联 chat、hover 失败、菜单未弹出或
                         "另存为..."选项未找到时抛出
        """
        if not self.chat:
            raise RuntimeError("消息未关联聊天窗口，无法执行另存为操作")

        # 确保目标目录存在
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        self._click_context_menu(i_("另存为..."))
        time.sleep(1)

        # 等待系统文件保存对话框弹出（#32770）
        win = self.chat._win
        save_dlg = win.WindowControl(ClassName="#32770")
        if not save_dlg.Exists(maxSearchSeconds=5):
            # 尝试从桌面层级查找
            save_dlg = auto.WindowControl(
                ClassName="#32770",
                ProcessId=self.chat.wx.pid if self.chat.wx else 0,
            )
            if not save_dlg.Exists(maxSearchSeconds=3):
                raise RuntimeError("文件保存对话框未弹出")

        # 定位文件名输入框
        file_edit = save_dlg.EditControl(AutomationId="1001")
        if not file_edit.Exists(maxSearchSeconds=3):
            input_wx.send_keys(save_dlg, "{Esc}")
            raise WxControlNotFoundError("未找到文件名输入框")

        # 设置保存路径
        vp = file_edit.GetValuePattern()
        if vp:
            vp.SetValue(file_path)
        else:
            input_wx.click(file_edit)
            time.sleep(0.2)
            input_wx.send_keys(file_edit, "{Ctrl}a{Del}")
            time.sleep(0.1)
            input_wx.paste_or_type(file_edit, file_path)
        time.sleep(0.3)

        # 如果目标文件已存在，先删除（避免覆盖确认弹窗）
        if os.path.exists(file_path):
            os.remove(file_path)

        # 点击"保存(S)"按钮
        save_btn = save_dlg.ButtonControl(AutomationId="1")
        if not save_btn.Exists(maxSearchSeconds=2):
            save_btn = save_dlg.ButtonControl(Name=i_("保存(&S)"))
            if not save_btn.Exists(maxSearchSeconds=2):
                input_wx.send_keys(save_dlg, "{Alt}S")
                time.sleep(1)
                return not save_dlg.Exists(maxSearchSeconds=1)

        input_wx.click(save_btn)
        time.sleep(1)

        # 如果弹出覆盖确认，按 Y 确认
        if save_dlg.Exists(maxSearchSeconds=0.5):
            input_wx.send_keys(save_dlg, "{Alt}Y")
            time.sleep(0.5)

        # 验证对话框已关闭
        return not save_dlg.Exists(maxSearchSeconds=1)

    @PIM.guard
    def delete(self) -> None:
        """
        删除此条消息。

        右键点击消息气泡，在菜单中点击"删除"，
        然后在确认弹窗中点击"删除"按钮。

        Returns:
            True 删除成功
        """
        self._click_context_menu(i_("删除"))

        win = self.chat._win
        confirm_btn = win.ButtonControl(
            ClassName="mmui::XOutlineButton",
            Name=i_("删除"),
        )
        if not confirm_btn.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到删除确认弹窗的'删除'按钮")

        input_wx.click(confirm_btn)


class TextMessage(Message):
    """文本消息"""
    @property
    def type_label(self) -> str:
        return "文本消息"


class QuoteMessage(Message):
    """引用消息"""

    def __init__(self, *, reply_content: str = "", quote_sender: str = "", quote_content: str = "", **kw):
        super().__init__(**kw)
        self.reply_content: str = reply_content
        self.quote_sender: str = quote_sender
        self.quote_content: str = quote_content

    @property
    def type_label(self) -> str:
        return "引用消息"

    @staticmethod
    def _get_quote_re() -> re.Pattern:
        """动态构建引用消息正则（支持多语言）"""
        pattern = i_("引用正则")
        return re.compile(pattern, re.DOTALL)

    @staticmethod
    def match(raw_name: str) -> bool:
        return bool(QuoteMessage._get_quote_re().match(raw_name))

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str, str, str]:
        m = QuoteMessage._get_quote_re().match(raw_name)
        if m:
            reply_content = m.group(1).strip()
            quote_sender = m.group(2).strip()
            quote_content = m.group(3).strip()
            return reply_content, reply_content, quote_sender, quote_content
        return raw_name, raw_name, "", ""


class VoiceMessage(Message):
    """语音消息"""

    def __init__(self, *, duration: int = 0, played: bool = True, **kw):
        super().__init__(**kw)
        self.duration: int = duration
        self.played: bool = played

    @property
    def type_label(self) -> str:
        return "语音消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, int, bool]:
        voice_kw = i_("语音")
        unplayed_kw = i_("未播放")
        played_kw = i_("已播放")
        # 匹配 "{语音}N"秒" 格式（中文左双引号 \u201c）
        m = re.match(rf"{re.escape(voice_kw)}(\d+)\u201c秒(.*)", raw_name, re.DOTALL)
        if m:
            dur = int(m.group(1))
            rest = m.group(2).strip()
            played = unplayed_kw not in rest
            # 如果 rest 中有识别文字（非状态标记），提取出来作为 content
            transcribed = ""
            if rest:
                # 去掉 "未播放"/"已播放" 标记后的剩余部分就是识别文字
                cleaned = re.sub(rf'^({re.escape(unplayed_kw)}|{re.escape(played_kw)})\s*', '', rest).strip()
                if cleaned:
                    transcribed = cleaned
            if transcribed:
                content = f"{dur}s {voice_kw}: {transcribed}"
            else:
                content = f"{dur}s {voice_kw}{'(' + unplayed_kw + ')' if not played else ''}"
            return content, dur, played
        # 兼容旧格式（ASCII 双引号）
        m = re.match(rf'{re.escape(voice_kw)}(\d+)"秒(.*)', raw_name, re.DOTALL)
        if m:
            dur = int(m.group(1))
            rest = m.group(2).strip()
            played = unplayed_kw not in rest
            transcribed = ""
            if rest:
                cleaned = re.sub(rf'^({re.escape(unplayed_kw)}|{re.escape(played_kw)})\s*', '', rest).strip()
                if cleaned:
                    transcribed = cleaned
            if transcribed:
                content = f"{dur}s {voice_kw}: {transcribed}"
            else:
                content = f"{dur}s {voice_kw}{'(' + unplayed_kw + ')' if not played else ''}"
            return content, dur, played
        return raw_name, 0, True

    @PIM.guard
    def play(self) -> None:
        """
        播放语音消息。

        点击语音消息气泡触发播放，微信会在客户端播放语音。
        播放完成后 played 状态会变为 True。

        Raises:
            RuntimeError: 消息未关联 chat 或控件未找到时抛出
        """
        if not self.chat:
            raise RuntimeError("消息未关联聊天窗口，无法播放语音")

        self.chat._activate_window()

        if not self.scroll_to_visible():
            raise RuntimeError("无法将语音消息滚动到可见区域")

        ctrl = self._find_ctrl()
        if not ctrl:
            raise WxControlNotFoundError("未找到语音消息控件")

        input_wx.click(ctrl)
        self.played = True

    @PIM.guard
    def to_text(self, timeout: float = 10) -> str:
        """
        语音转文字。

        右键点击语音消息气泡，在菜单中点击"转文字"，
        等待微信识别完成后，从消息控件的 Name 属性中提取转换后的文本。

        微信语音转文字后，消息控件的 Name 会变化：
        - 转换前: "语音{N}"秒" 或 "语音{N}"秒 未播放"
        - 转换中: 可能出现 "语音转文字" 等中间状态
        - 转换后: Name 中会追加识别出的文字内容，
                  格式为 "语音{N}"秒\\n{识别文字}" 或直接包含文字

        流程:
        1. 右键点击语音消息气泡
        2. 在菜单中点击"转文字"
        3. 轮询消息控件的 Name 属性，等待文字出现
        4. 从 Name 中提取并返回识别出的文字

        Args:
            timeout: 等待语音识别完成的超时时间（秒），默认 10 秒。
                     较长的语音可能需要更长时间。

        Returns:
            识别出的文字内容。识别失败或超时返回空字符串。

        Raises:
            RuntimeError: 消息未关联 chat、hover 失败、菜单未弹出或
                         "转文字"选项未找到时抛出。

        用法::

            @wx.on(Event.VOICE)
            def on_voice(wx_client, message):
                text = message.to_text(timeout=15)
                if text:
                    print(f"语音内容: {text}")
                    message.chat.send_text(f"你说的是: {text}", quote=message)
                else:
                    print("语音识别失败")
        """
        if not self.chat:
            raise RuntimeError("消息未关联聊天窗口，无法执行转文字操作")
        if not self.runtime_id:
            raise RuntimeError("消息无 runtime_id，无法追踪控件状态")

        # 记录原始 Name
        original_name = self.raw_name or ""

        # 点击右键菜单"语音转文字"
        self._click_context_menu(i_("语音转文字"))

        # 轮询：通过 runtime_id 在消息列表中重新查找控件，读取最新 Name
        # 转文字后微信会重建控件，旧引用的 .Name 不会更新，
        # 必须每次遍历消息列表按 RuntimeId 匹配到新控件
        lc = self.chat._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return ""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)

            current_name = self._get_current_name_by_rid(lc)
            if current_name is None:
                continue

            # Name 发生变化，尝试提取识别文字
            if current_name != original_name:
                text = self._extract_transcribed_text(current_name)
                if text:
                    return text

        # 超时后最后尝试一次
        current_name = self._get_current_name_by_rid(lc)
        if current_name and current_name != original_name:
            text = self._extract_transcribed_text(current_name)
            if text:
                return text

        return ""

    def _get_current_name_by_rid(self, lc: auto.ListControl) -> Optional[str]:
        """
        通过 runtime_id 在消息列表中重新查找控件，返回其当前 Name。

        微信转文字后会重建控件（RuntimeId 不变但旧 Python 引用失效），
        必须遍历消息列表按 RuntimeId 匹配到新控件才能读取最新 Name。

        Args:
            lc: 消息列表 ListControl

        Returns:
            当前 Name 字符串，未找到返回 None
        """
        target_rid = self.runtime_id
        if not target_rid:
            return None

        try:
            for ctrl, _ in auto.WalkControl(lc):
                if ctrl.ControlType != auto.ControlType.ListItemControl:
                    continue
                try:
                    rid = tuple(ctrl.GetRuntimeId())
                except Exception:
                    continue
                if rid == target_rid:
                    return ctrl.Name or ""
        except Exception:
            pass

        return None

    @staticmethod
    def _extract_transcribed_text(name: str) -> str:
        """
        从语音转文字后的控件 Name 中提取识别出的文字。

        实际观察到的转换后 Name 格式：
        - "语音2\u201c秒你好，你好。"  → 识别文字直接跟在"秒"后面
        - "语音5\u201c秒今天天气不错"  → 无分隔符
        - "语音3\u201c秒 未播放你好"   → 可能带"未播放"标记

        转换前 Name 格式：
        - "语音2\u201c秒"             → 已播放，无文字
        - "语音2\u201c秒 未播放"      → 未播放，无文字

        注意: \u201c 是中文左双引号 "

        Args:
            name: 控件的 Name 属性值

        Returns:
            提取出的文字，未匹配到返回空字符串
        """
        if not name:
            return ""

        voice_kw = i_("语音")
        unplayed_kw = i_("未播放")
        played_kw = i_("已播放")

        # 主格式: "{语音}N"秒{文字}" — 文字直接跟在"秒"后面
        # 支持中文左双引号(\u201c)和 ASCII 双引号
        m = re.match(
            rf'^{re.escape(voice_kw)}\d+[\u201c"]秒\s*(?:{re.escape(unplayed_kw)}|{re.escape(played_kw)})?\s*(.+)',
            name,
            re.DOTALL,
        )
        if m:
            text = m.group(1).strip()
            # 排除仍是状态文本的情况
            if text and text not in (unplayed_kw, played_kw, "转文字中"):
                return text

        # 备选格式: 带换行 "{语音}N"秒\n识别文字"
        m = re.match(rf'^{re.escape(voice_kw)}\d+[\u201c"]秒(?:\s*{re.escape(unplayed_kw)})?\s*\n(.+)', name, re.DOTALL)
        if m:
            return m.group(1).strip()

        # 备选格式: "识别文字\n{语音}N"秒"
        m = re.match(rf'^(.+?)\n{re.escape(voice_kw)}\d+[\u201c"]秒', name, re.DOTALL)
        if m:
            return m.group(1).strip()

        # Name 不再包含 "语音" 前缀，整体就是识别文字
        if not name.startswith(voice_kw):
            return name.strip()

        return ""


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

    def __init__(self, *, file_name: str = "", file_size: str = "", file_status: str = "", **kw):
        super().__init__(**kw)
        self.file_name: str = file_name
        self.file_size: str = file_size
        self.file_status: str = file_status

    @property
    def type_label(self) -> str:
        return "文件消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str, str, str]:
        """
        解析文件消息的 raw_name。

        已知格式（换行分隔）：
        - "文件\\n{文件名}\\n{大小}"                → 已下载/已发送
        - "文件\\n{文件名}\\n{大小}\\n未下载"       → 未下载
        - "文件\\n{文件名}\\n{大小}\\n对方上传中"   → 对方上传中
        - "文件\\n进度: {N}%\\n{文件名}\\n..."      → 自己发送中（由状态检测处理）

        Returns:
            (content, file_name, file_size, file_status)
            content: 显示用的摘要文本
            file_name: 文件名
            file_size: 文件大小文本（如 "5.5K"、"1.2M"）
            file_status: 状态文本（""=正常, "未下载", "对方上传中" 等）
        """
        if not raw_name:
            return raw_name, "", "", ""

        parts = [p.strip() for p in raw_name.split("\n") if p.strip()]

        # 跳过第一个 "文件" 标记
        file_kw = i_("文件")
        progress_kw = i_("进度")
        if parts and parts[0] == file_kw:
            parts = parts[1:]

        # 跳过 "进度: XX%" 行（发送中状态）
        if parts and re.match(rf'^{re.escape(progress_kw)}[:：]\s*\d+%', parts[0]):
            parts = parts[1:]

        file_name = ""
        file_size = ""
        file_status = ""

        # 文件大小的正则：数字+单位（B/K/KB/M/MB/G/GB/T/TB）
        size_pattern = re.compile(r'^[\d.]+\s*[BKMGT][B]?$', re.IGNORECASE)
        # 已知状态文本
        status_texts = {i_("未下载"), i_("对方上传中"), i_("发送中断"), i_("已过期"), i_("已取消")}

        # 逐个解析 parts：第一个非大小非状态的是文件名，
        # 匹配大小正则的是文件大小，在状态集合中的是状态
        for p in parts:
            if p in status_texts:
                file_status = p
            elif size_pattern.match(p):
                file_size = p
            elif not file_name:
                file_name = p

        # 生成 content 摘要
        if file_status:
            content = f"{file_name} ({file_size}) [{file_status}]"
        else:
            file_status = i_("已下载")
            content = f"{file_name} ({file_size})" if file_size else file_name

        return content, file_name, file_size, file_status

    def get_status(self) -> str:
        """
        获取文件消息的最新状态。

        通过 runtime_id 在消息列表中重新查找控件，
        读取最新的 Name 属性并解析出当前 file_status。

        文件状态可能随时间变化：
        - "对方上传中" → "未下载"（上传完成）
        - "未下载" → "已下载"（用户手动下载后）

        Returns:
            最新的状态文本（"已下载"、"未下载"、"对方上传中"、"发送中断" 等）。
            无法获取时返回当前缓存的 file_status。
        """
        if not self.chat or not self.runtime_id:
            return self.file_status

        lc = self.chat._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return self.file_status

        # 通过 runtime_id 查找控件获取最新 Name
        target_rid = self.runtime_id
        current_name = None
        try:
            for ctrl, _ in auto.WalkControl(lc):
                if ctrl.ControlType != auto.ControlType.ListItemControl:
                    continue
                try:
                    rid = tuple(ctrl.GetRuntimeId())
                except Exception:
                    continue
                if rid == target_rid:
                    current_name = ctrl.Name or ""
                    break
        except Exception:
            return self.file_status

        if current_name is None:
            return self.file_status

        # 解析最新 Name 获取状态
        _, _, _, new_status = FileMessage.parse(current_name)
        self.file_status = new_status
        return new_status


class LocationMessage(Message):
    """位置消息"""

    def __init__(self, *, address: str = "", **kw):
        super().__init__(**kw)
        self.address: str = address

    @property
    def type_label(self) -> str:
        return "位置消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str]:
        loc_kw = i_("位置")
        addr = raw_name[len(loc_kw):] if raw_name.startswith(loc_kw) else raw_name
        return addr, addr


class LinkMessage(Message):
    """链接消息"""

    def __init__(self, *, title: str = "", link_source: str = "", **kw):
        super().__init__(**kw)
        self.title: str = title
        self.link_source: str = link_source

    @property
    def type_label(self) -> str:
        return "链接消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str, str]:
        link_kw = i_("链接")
        bracket_prefix = f"[{link_kw}]"
        if raw_name.startswith(bracket_prefix):
            body = raw_name[len(bracket_prefix):]
            parts = [p.strip() for p in body.split("\n") if p.strip()]
            title = parts[0] if parts else body
            link_source = parts[1] if len(parts) > 1 else ""
            return title, title, link_source

        if raw_name.startswith(f"{link_kw}\n") or raw_name.startswith(f"{link_kw}\r"):
            parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
            title = parts[1] if len(parts) > 1 else raw_name
            link_source = parts[2] if len(parts) > 2 else ""
            return title, title, link_source

        parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
        title = parts[0] if parts else raw_name
        link_source = parts[1] if len(parts) > 1 else ""
        return title, title, link_source


class EmotionMessage(Message):
    """表情消息"""

    _EMOJI_NAME_RE = re.compile(r"\[(.+?)\]")

    def __init__(self, *, emoji_name: str = "", **kw):
        super().__init__(**kw)
        self.emoji_name: str = emoji_name

    @property
    def type_label(self) -> str:
        return "表情消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str]:
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

    def __init__(self, *, card_name: str = "", **kw):
        super().__init__(**kw)
        self.card_name: str = card_name

    @property
    def type_label(self) -> str:
        return "名片消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str]:
        card_suffix = i_("个人名片")
        if raw_name.endswith(card_suffix):
            name = raw_name[:-len(card_suffix)]
        else:
            name = raw_name
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

    def __init__(self, *, music_source: str = "", song_name: str = "", artist: str = "", **kw):
        super().__init__(**kw)
        self.music_source: str = music_source
        self.song_name: str = song_name
        self.artist: str = artist

    @property
    def type_label(self) -> str:
        return "音乐消息"

    @staticmethod
    def match(raw_name: str) -> bool:
        return any(raw_name.startswith(src) for src in MusicMessage._MUSIC_SOURCES)

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str, str, str]:
        music_source = ""
        rest = raw_name
        for src in MusicMessage._MUSIC_SOURCES:
            if raw_name.startswith(src):
                music_source = src
                rest = raw_name[len(src):]
                break
        return rest, music_source, rest, ""


class CardMessage(Message):
    """卡片消息"""

    def __init__(self, *, title: str = "", description: str = "", **kw):
        super().__init__(**kw)
        self.title: str = title
        self.description: str = description

    @property
    def type_label(self) -> str:
        return "卡片消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str, str]:
        parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
        title = parts[0] if parts else raw_name
        description = parts[1] if len(parts) > 1 else ""
        content = title
        return content, title, description


class SystemMessage(Message):
    """系统消息"""

    def __init__(self, *, timestamp: str = "", **kw):
        kw.setdefault("source", Source.SYSTEM)
        kw.setdefault("sender", "系统")
        kw.setdefault("status", MessageStatus.RECEIVED)
        super().__init__(**kw)
        self.timestamp: str = timestamp

    @property
    def type_label(self) -> str:
        return "系统消息"


class VoipMessage(Message):
    """语音/视频通话消息"""

    def __init__(self, *, call_type: str = "", call_status: str = "", **kw):
        super().__init__(**kw)
        self.call_type: str = call_type
        self.call_status: str = call_status

    @property
    def type_label(self) -> str:
        return "通话消息"

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str, str]:
        voice_call_kw = i_("语音通话")
        video_call_kw = i_("视频通话")
        for prefix in (voice_call_kw, video_call_kw):
            if raw_name.startswith(prefix):
                call_status = raw_name[len(prefix):]
                return raw_name, prefix, call_status
        return raw_name, "", raw_name


class TransferMessage(Message):
    """微信转账消息"""

    def __init__(self, *, amount: str = "", remark: str = "", **kw):
        super().__init__(**kw)
        self.amount: str = amount
        self.remark: str = remark

    @property
    def type_label(self) -> str:
        return "转账消息"

    def accept(self) -> bool:
        return self._click_transfer_button(i_("收款"))

    def reject(self) -> bool:
        return self._click_transfer_button(i_("退还"))

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
        # btn.GetInvokePattern().Invoke()
        input_wx.click(btn)
        time.sleep(1)
        return True

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str, str]:
        transfer_kw = i_("微信转账")
        transfer_re = re.compile(rf"^￥([\d.]+)\s+(.+?)\s+{re.escape(transfer_kw)}$")
        transfer_no_remark_re = re.compile(rf"^￥([\d.]+)\s+{re.escape(transfer_kw)}$")
        m = transfer_re.match(raw_name)
        if m:
            amount = m.group(1)
            remark = m.group(2).strip()
            return f"￥{amount}", amount, remark
        m = transfer_no_remark_re.match(raw_name)
        if m:
            amount = m.group(1)
            return f"￥{amount}", amount, ""
        return raw_name, "", ""


class RedPacketMessage(Message):
    """微信红包消息"""

    def __init__(self, *, greeting: str = "", **kw):
        super().__init__(**kw)
        self.greeting: str = greeting

    @property
    def type_label(self) -> str:
        return "红包消息"

    def open(self) -> dict:
        """
        打开（拆开）红包。

        流程:
        1. 悬浮鼠标到红包消息，点击打开弹窗
        2. 在弹窗中点击"拆开"按钮
        3. 等待结果页面（mmui::PayRedEnvelopDetailWindow）出现
        4. 截图 OCR 识别结果页面内容
        5. 关闭结果页面

        弹窗控件结构（在聊天窗口内）:
        - 发送者: TextControl, Name="{昵称}发出的红包"
        - 祝福语: TextControl, Name="{祝福语}"
        - 拆开按钮: ButtonControl, Name=i_("拆开"), ClassName="mmui::XButton"
        - 关闭按钮: ButtonControl, Name=i_("关闭"), ClassName="mmui::XButton"

        Returns:
            dict: {
                "desc": str,   # OCR 识别文本拼接
                "ocr": dict,   # OCR 原始结果 {text: {center, left_top, right_bottom, width, height}}
            }
            空字典表示拆开失败或无法识别
        """
        if not self.chat:
            return {}

        self.chat._activate_window()

        if not self.hover():
            return {}

        ctrl = self._find_ctrl()
        if not ctrl:
            return {}

        input_wx.click(ctrl)
        time.sleep(0.5)

        # 查找"拆开"按钮
        open_btn = self.chat._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=i_("拆开"),
            searchDepth=10,
        )
        if open_btn.Exists(maxSearchSeconds=3):
            input_wx.click(open_btn)

        # 等待红包结果窗口出现，截图 OCR 识别
        # 通过 ProcessId 过滤，避免多开场景下匹配到其他微信实例的窗口
        pid = self.chat.wx.pid if self.chat.wx else 0
        result = {}
        pay_detail_win = auto.WindowControl(
            ClassName="mmui::PayRedEnvelopDetailWindow",
            ProcessId=pid,
            searchDepth=1,
        )
        if pay_detail_win.Exists(maxSearchSeconds=5):
            try:
                hwnd = pay_detail_win.NativeWindowHandle or 0
                if hwnd:
                    png_bytes = capture_window(
                        hwnd,
                        offset_left=12,
                        offset_right=22,
                        offset_bottom=12,
                        mode="print_window",
                    )
                    result = self.chat.wx.get_image_text(png_bytes)
            except Exception:
                pass

            # 关闭结果窗口
            try:
                wp = pay_detail_win.GetWindowPattern()
                if wp:
                    wp.Close()
            except Exception:
                pass

        return {
            "desc": "\n".join(result),
            "ocr": result,
        }

    @staticmethod
    def parse(raw_name: str) -> Tuple[str, str]:
        red_packet_kw = i_("微信红包")
        red_packet_re = re.compile(rf"^(.+?)\s{{2,}}{re.escape(red_packet_kw)}$")
        m = red_packet_re.match(raw_name)
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
_MSG_CLASS_TO_EVENT: Dict[type, Event] = {
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


class WeixinWindow:

    @property
    def _window(self) -> auto.WindowControl:
        return self._win

    @property
    def _hwnd(self) -> int:
        return self._window.NativeWindowHandle

    @property
    def exists(self) -> bool:
        """窗口是否存在"""
        return self._win.Exists(0, 0)

    @property
    def is_topmost(self) -> bool:
        ex_style = win32gui.GetWindowLong(self._hwnd, win32con.GWL_EXSTYLE)
        return bool(ex_style & win32con.WS_EX_TOPMOST)

    @property
    def is_minimized(self) -> bool:
        return bool(win32gui.IsIconic(self._hwnd))

    @property
    def is_maximized(self) -> bool:
        placement = win32gui.GetWindowPlacement(self._hwnd)
        return placement[1] == win32con.SW_SHOWMAXIMIZED

    @property
    def is_visible(self) -> bool:
        return bool(win32gui.IsWindowVisible(self._hwnd))

    def activate(self) -> None:
        if self.is_minimized:
            self._window.Restore()
        self._window.SetActive()
        self._window.SetFocus()

    def deactivate(self) -> None:
        win32gui.SendMessage(self._hwnd, win32con.WM_ACTIVATE, win32con.WA_INACTIVE, 0)

    def focus(self) -> None:
        win32gui.SendMessage(self._hwnd, win32con.WM_SETFOCUS, 0, 0)

    def unfocus(self) -> None:
        win32gui.SendMessage(self._hwnd, win32con.WM_KILLFOCUS, 0, 0)

    def pin(self) -> None:
        win32gui.SetWindowPos(self._hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

    def unpin(self) -> None:
        win32gui.SetWindowPos(self._hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

    def minimize(self) -> None:
        win32gui.ShowWindow(self._hwnd, win32con.SW_MINIMIZE)

    def maximize(self) -> None:
        win32gui.ShowWindow(self._hwnd, win32con.SW_MAXIMIZE)

    def restore(self) -> None:
        win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)

    def close(self) -> None:
        win32gui.SendMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)

    def show(self) -> None:
        win32gui.ShowWindow(self._hwnd, win32con.SW_SHOW)

    def hide(self) -> None:
        win32gui.ShowWindow(self._hwnd, win32con.SW_HIDE)

    def move_to(self, x: int, y: int) -> None:
        hwnd = self._hwnd
        rect = win32gui.GetWindowRect(hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        win32gui.MoveWindow(hwnd, x, y, w, h, True)

    def resize_to(self, width: int, height: int) -> None:
        hwnd = self._hwnd
        rect = win32gui.GetWindowRect(hwnd)
        win32gui.MoveWindow(hwnd, rect[0], rect[1], width, height, True)

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        return win32gui.GetWindowRect(self._hwnd)

    @property
    def size(self) -> Tuple[int, int]:
        r = self.rect
        return (r[2] - r[0], r[3] - r[1])

    @property
    def position(self) -> Tuple[int, int]:
        r = self.rect
        return (r[0], r[1])

    def move_offscreen(self) -> None:
        """将窗口移到屏幕外（不可见但仍处于正常状态）。"""
        hwnd = self._hwnd
        rect = self._win.BoundingRectangle
        self._offscreen_rect = (rect.left, rect.top,
                                rect.width(), rect.height())
        ctypes.windll.user32.MoveWindow(hwnd, -9999, -9999,
                                        rect.width(), rect.height(), True)

    def move_back(self) -> None:
        """将窗口从屏幕外移回原始位置。"""
        offscreen_rect = getattr(self, '_offscreen_rect', None)
        if not offscreen_rect:
            return
        hwnd = self._hwnd
        x, y, w, h = offscreen_rect
        ctypes.windll.user32.MoveWindow(hwnd, x, y, w, h, True)
        self._offscreen_rect = None

    @property
    def is_offscreen(self) -> bool:
        """窗口是否在屏幕外"""
        rect = self._win.BoundingRectangle
        return rect.right <= 0


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
    NICKNAME_ID = "current_login_nick_name"
    ENTER_BTN_CLASS = "mmui::XOutlineButton"

    def __init__(self, pid: int):
        """初始化登录窗口操作实例，绑定微信登录窗口控件。

        Args:
            pid: 微信进程 PID，精确绑定该进程的登录窗口。
        """
        self.pid = pid
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            ProcessId=pid,
            searchDepth=1,
        )

    @property
    def state(self) -> str:
        """
        获取登录窗口当前状态。

        通过检测关键控件判断当前处于哪个界面：
        - "enter":    进入微信状态（显示"进入微信"按钮，已有登录账号）
        - "qrcode":   扫码登录状态（显示二维码）
        - "confirm":  待确认登录状态（已扫码，等待手机确认）
        - "entering": 正在进入状态（手机已确认，正在加载主界面）
        - "unknown":  未知状态（可能在代理设置页面或其他过渡状态）

        Returns:
            "enter" / "qrcode" / "confirm" / "entering" / "unknown"
        """
        self._ensure_exists()
        # 检测"进入微信"按钮
        enter_btn = self._win.ButtonControl(
            ClassName=self.ENTER_BTN_CLASS,
            Name=i_("进入微信"),
        )
        if enter_btn.Exists(0, 0):
            return "enter"
        # 检测正在进入状态
        entering_txt = self._win.TextControl(
            ClassName="mmui::XTextView",
            Name=i_("正在进入"),
        )
        if entering_txt.Exists(0, 0):
            return "entering"
        # 检测待确认登录状态
        confirm_txt = self._win.TextControl(
            ClassName="mmui::XTextView",
            Name=i_("需在手机上完成登录"),
        )
        if confirm_txt.Exists(0, 0):
            return "confirm"
        # 检测二维码控件
        qr_ctrl = self._win.ButtonControl(
            ClassName="mmui::XImage",
            Name=i_("二维码"),
        )
        if qr_ctrl.Exists(0, 0):
            return "qrcode"
        return "unknown"

    @property
    def is_logined(self) -> bool:
        """
        判断是否已登录成功（微信主窗口是否已出现）。

        通过检测当前进程的微信主窗口（mmui::MainWindow）是否存在来判断。

        Returns:
            True 已登录（主窗口存在），False 未登录
        """
        win = auto.WindowControl(
            ClassName="mmui::MainWindow",
            ProcessId=self.pid,
            searchDepth=1,
        )
        return win.Exists(0, 0)

    def _ensure_exists(self) -> None:
        if not self._win.Exists(maxSearchSeconds=3):
            raise WxWindowNotFoundError("微信登录窗口未找到")

    @property
    def nickname(self) -> Optional[str]:
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
            return None
        name = txt.Name or None
        prefix = i_("当前登录用户")
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
            Name=i_("进入微信"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'进入微信'按钮")
        input_wx.click(btn)

        # 等待登录窗口消失
        for _ in range(timeout):
            if not self._win.Exists(maxSearchSeconds=1):
                logger.debug("已进入微信")
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
            Name=i_("切换账号"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'切换账号'按钮")
        input_wx.click(btn)

    def get_qrcode(self) -> bytes:
        """
        获取登录二维码图片数据。

        从登录窗口中截取二维码控件区域，返回 PNG 格式的字节数据。
        二维码控件: ButtonControl, ClassName="mmui::XImage", Name="二维码"

        注意：二维码仅在"切换账号"后的扫码登录界面显示。
        如果当前是"进入微信"界面（已有登录账号），需要先调用
        switch_account() 切换到扫码界面。

        Returns:
            PNG 格式的二维码图片字节数据

        Raises:
            WxWindowNotFoundError: 登录窗口未找到
            RuntimeError: 二维码控件未找到
        """
        self._ensure_exists()
        qr_ctrl = self._win.ButtonControl(
            ClassName="mmui::XImage",
            Name=i_("二维码"),
        )
        if not qr_ctrl.Exists(maxSearchSeconds=5):
            raise WxControlNotFoundError("未找到二维码控件，请确认当前处于扫码登录界面")

        # 通过窗口截图 + 裁剪二维码区域获取图片
        hwnd = self._win.NativeWindowHandle
        if not hwnd:
            raise RuntimeError("无法获取登录窗口句柄")

        return capture_control(hwnd, qr_ctrl, offset_left=2, mode="print_window")

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
            Name=i_("仅传输文件"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'仅传输文件'按钮")
        input_wx.click(btn)

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
    # 保存按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name=i_("保存")

    PROXY_SWITCH_CLASS = "mmui::XSwitchButton"
    PROXY_SAVE_BTN_CLASS = "mmui::XOutlineButton"
    PROXY_EDIT_CLASS = "mmui::XLineEdit"

    def _is_proxy_page_open(self) -> bool:
        """判断当前是否在代理设置页面（通过检测"返回"按钮是否存在）"""
        back_btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=i_("返回"),
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
            Name=i_("网络代理设置"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'网络代理设置'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

        # 等待代理设置页面出现
        back_btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=i_("返回"),
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
            Name=i_("返回"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'返回'按钮")
        input_wx.click(btn)

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
            Name=i_("使用代理"),
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'使用代理'开关")
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
            Name=i_("使用代理"),
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'使用代理'开关")
        input_wx.click(sw)

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
            Name=i_("使用代理"),
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'使用代理'开关")
        input_wx.click(sw)

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
            raise WxControlNotFoundError(f"未找到'{name}'输入框")
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
            input_wx.paste_or_type(edit, value)

    def _get_proxy_field(self, name: str) -> str:
        """获取代理表单字段的值"""
        edit = self._find_proxy_edit(name)
        vp = edit.GetValuePattern()
        if vp:
            return vp.Value or ""
        return ""

    @PIM.guard
    def set_proxy(
        self, 
        address: Optional[str] = None, 
        port: Optional[str] = None,
        username: Optional[str] = None, 
        password: Optional[str] = None
    ) -> None:
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
            self._set_proxy_field(i_("地址"), address)
        if port:
            self._set_proxy_field(i_("端口"), port)
        if username:
            self._set_proxy_field(i_("账户"), username)
        if password:
            self._set_proxy_field(i_("密码"), password)

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
            result["address"] = self._get_proxy_field(i_("地址"))
            result["port"] = self._get_proxy_field(i_("端口"))
            result["username"] = self._get_proxy_field(i_("账户"))
            result["password"] = self._get_proxy_field(i_("密码"))
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
            Name=i_("保存"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'保存'按钮")
        input_wx.click(btn)

    @property
    def has_safe_window(self) -> bool:
        """
        检测登录窗口内是否弹出了安全验证弹窗。

        安全弹窗是登录窗口内部的子控件：
        - WindowControl, ClassName="mmui::XDialog", Name="Weixin"
        包含"我知道了"确认按钮。

        Returns:
            True 安全弹窗存在，False 不存在
        """
        self._ensure_exists()
        dlg = self._win.WindowControl(
            ClassName="mmui::XDialog",
        )
        return dlg.Exists(0, 0)

    @PIM.guard
    def safe_window_confirm(self) -> None:
        """
        点击登录窗口内安全验证弹窗中的"我知道了"按钮确认。

        安全弹窗控件结构（位于登录窗口 mmui::LoginWindow 内部）：
        - 弹窗: WindowControl, ClassName="mmui::XDialog", Name="Weixin"
        - 确认按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="我知道了"

        Raises:
            WxWindowNotFoundError: 登录窗口或安全弹窗未找到
            WxControlNotFoundError: "我知道了"按钮未找到
        """
        self._ensure_exists()

        dlg = self._win.WindowControl(
            ClassName="mmui::XDialog",
        )
        if not dlg.Exists(maxSearchSeconds=3):
            raise WxWindowNotFoundError("安全验证弹窗未找到")

        btn = dlg.ButtonControl(
            ClassName="mmui::XOutlineButton",
            Name=i_("我知道了"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'我知道了'按钮")

        input_wx.click(btn)
        time.sleep(0.5)

    @PIM.guard
    def close(self) -> None:
        self._ensure_exists()
        self.activate()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=i_("关闭"),
        )
        if not btn.Exists(maxSearchSeconds=1):
            raise WxControlNotFoundError("未找到关闭按钮")
        input_wx.click(btn)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "Login(closed)"
        nick = self.nickname
        return f"Login(user={nick!r})"


class WeixinUpdate(WeixinWindow):
    """
    微信更新提示窗口操作类。

    微信检测到新版本时弹出的独立窗口，提供"立即更新"和"忽略本次更新"操作。

    关键控件信息：
    - 窗口: WindowControl, ClassName="mmui::UpdateWindow", AutomationId="UpdateWindow", Name="微信"
    - 忽略本次更新: ButtonControl, Name="忽略本次更新"
    - 立即更新: ButtonControl, Name="立即更新"
    - 关闭按钮: ButtonControl, Name="关闭"
    """

    WINDOW_CLASS = "mmui::UpdateWindow"
    WINDOW_ID = "UpdateWindow"

    def __init__(self, wx: Weixin):
        """
        初始化更新窗口操作实例。

        Args:
            pid: 微信进程 PID
        """
        self.wx = wx
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            AutomationId=self.WINDOW_ID,
            ProcessId=self.wx.pid,
            searchDepth=1,
        )

    @PIM.guard
    def ignore(self) -> None:
        """点击"忽略本次更新"按钮"""
        if not self.exists:
            raise WxWindowNotFoundError("更新窗口未找到")
        self.activate()
        btn = self._win.ButtonControl(Name=i_("忽略本次更新"))
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'忽略本次更新'按钮")
        input_wx.click(btn)

    @PIM.guard
    def process_later(self) -> None:
        """点击"稍后处理"按钮"""
        if not self.exists:
            raise WxWindowNotFoundError("更新窗口未找到")
        self.activate()
        btn = self._win.ButtonControl(Name=i_("稍后处理"))
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'稍后处理'按钮")
        input_wx.click(btn)

    @PIM.guard
    def update(self) -> None:
        """点击"立即更新"按钮"""
        if not self.exists:
            raise WxWindowNotFoundError("更新窗口未找到")
        self.activate()
        btn = self._win.ButtonControl(Name=i_("更新"))
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'更新'按钮")
        input_wx.click(btn)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "UpdateWindow(closed)"
        return "UpdateWindow(open)"


class VoipCall(WeixinWindow):
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

    def __init__(self, chat: Chat):
        """
        初始化通话窗口控制实例，绑定 VOIPWindow 控件。

        Args:
            chat: 发起通话的 Chat 或 SeparateChat 实例。
        """
        self.chat = chat
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            AutomationId=self.WINDOW_ID,
            ProcessId=self.chat.wx.pid,
        )

    def _ensure_exists(self) -> None:
        if not self._win.Exists(maxSearchSeconds=3):
            raise WxWindowNotFoundError("通话窗口未找到")

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
        raise WxControlNotFoundError(f"工具栏中未找到按钮: {names}")

    @property
    def contact_name(self) -> Optional[str]:
        """获取通话对方名称"""
        self._ensure_exists()
        txt = self._win.TextControl(
            AutomationId="voip_caller_view.voip_caller_name",
        )
        return txt.Name if txt.Exists(0, 0) else None

    @property
    def status(self) -> Optional[str]:
        """获取通话状态文本（如 '等待对方接受邀请...'、'通话中 01:23'）"""
        self._ensure_exists()
        txt = self._win.TextControl(
            AutomationId="voip_caller_view.voip_caller_tips",
        )
        return txt.Name if txt.Exists(0, 0) else None

    @property
    def is_mic_on(self) -> bool:
        """麦克风是否开启"""
        try:
            self._find_toolbar_button(i_("麦克风已开"))
            return True
        except RuntimeError:
            return False

    @property
    def is_speaker_on(self) -> bool:
        """扬声器是否开启"""
        try:
            self._find_toolbar_button(i_("扬声器已开"))
            return True
        except RuntimeError:
            return False

    @property
    def is_camera_on(self) -> bool:
        """摄像头是否开启（仅视频通话）"""
        try:
            self._find_toolbar_button(i_("摄像头已开"))
            return True
        except RuntimeError:
            return False

    @property
    def has_camera(self) -> bool:
        """是否有可用摄像头（仅视频通话）"""
        try:
            self._find_toolbar_button(i_("无摄像头"))
            return False
        except RuntimeError:
            return True

    @PIM.guard
    def toggle_mic(self) -> None:
        """切换麦克风开关"""
        btn = self._find_toolbar_button(i_("麦克风已开"), i_("麦克风已关"))
        input_wx.click(btn)

    @PIM.guard
    def toggle_speaker(self) -> None:
        """切换扬声器开关"""
        btn = self._find_toolbar_button(i_("扬声器已开"), i_("扬声器已关"))
        input_wx.click(btn)

    @PIM.guard
    def toggle_camera(self) -> None:
        """切换摄像头开关（仅视频通话）"""
        btn = self._find_toolbar_button(i_("摄像头已开"), i_("摄像头已关"), i_("无摄像头"))
        input_wx.click(btn)

    @PIM.guard
    def cancel(self) -> None:
        """取消通话（呼叫中未接通时）"""
        btn = self._find_toolbar_button(i_("取消"))
        input_wx.click(btn)

    @PIM.guard
    def hangup(self) -> None:
        """挂断通话（通话中）"""
        btn = self._find_toolbar_button(i_("挂断"))
        input_wx.click(btn)

    @PIM.guard
    def end_call(self) -> None:
        """结束通话（自动识别取消/挂断）"""
        try:
            btn = self._find_toolbar_button(i_("取消"), i_("挂断"))
        except WxControlNotFoundError:
            raise WxControlNotFoundError("未找到取消或挂断按钮")
        input_wx.click(btn)

    @PIM.guard
    def switch_to_video(self) -> None:
        """切换到视频通话（通话中可用）"""
        btn = self._find_toolbar_button(i_("切换到视频通话"))
        input_wx.click(btn)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "VoipCall(closed)"
        return (f"VoipCall(contact={self.contact_name!r}, "
                f"status={self.status!r})")


class NoteEditor(WeixinWindow):
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
    EDITOR_INPUT_ID = "xeditorInputId"
    MAIN_CONTAINER_ID = "mainContainer"

    def __init__(self, wx: Weixin):
        """
        初始化笔记编辑窗口。

        Args:
            wx: Weixin 实例，通过其 PID 精确查找并绑定笔记窗口。

        Raises:
            RuntimeError: 窗口未找到时抛出。
        """
        self.wx = wx
        win = auto.PaneControl(
            ClassName=self.WINDOW_CLASS,
            Name=i_("笔记"),
            ProcessId=wx.pid
        )
        if not win.Exists(0, 0):
            raise WxWindowNotFoundError("笔记编辑窗口未找到")
        self._hwnd = win.NativeWindowHandle
        self._win = win

    @property
    def exists(self) -> bool:
        """窗口是否存在（通过句柄刷新后检测）"""
        if self._hwnd:
            try:
                self._win = auto.ControlFromHandle(self._hwnd)
            except Exception:
                return False
        return self._win.Exists(0, 0)

    def _ensure_exists(self) -> None:
        if not self.exists:
            raise WxWindowNotFoundError("笔记编辑窗口未找到")

    def activate(self) -> None:
        self._ensure_exists()
        super().activate()

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

        force_click=True:  点击 mainContainer 强制聚焦（会清除选区）。
        force_click=False: 仅激活窗口，保留当前选区（用于格式快捷键）。
        """
        self.activate()
        if force_click:
            container = self._main_container
            if container.Exists(maxSearchSeconds=2):
                input_wx.click(container)

    def _editor_shortcut(self, keys: str, force_click: bool = False, delay: float = 0.1) -> None:
        """向编辑器发送快捷键的通用方法"""
        self.focus_editor(force_click=force_click)
        input_wx.send_keys(self._editor, keys)
        time.sleep(delay)

    @property
    def content(self) -> Optional[str]:
        """读取编辑器当前内容（优先 ValuePattern，备选 TextPattern）"""
        self._ensure_exists()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            return None
        vp = editor.GetValuePattern()
        if vp and vp.Value:
            return vp.Value
        tp = editor.GetTextPattern()
        if tp:
            doc_range = tp.DocumentRange
            if doc_range:
                return doc_range.GetText(-1) or None
        return None

    @PIM.guard
    def set_content(self, text: str) -> None:
        """设置编辑器内容（覆盖现有内容，通过 ValuePattern.SetValue）"""
        self.focus_editor()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到笔记编辑器输入控件")
        vp = editor.GetValuePattern()
        if not vp:
            raise RuntimeError("编辑器不支持 ValuePattern")
        vp.SetValue(text)

    @PIM.guard
    def type_text(self, text: str) -> None:
        """在编辑器中输入文本（追加到当前光标位置）"""
        self.focus_editor()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到笔记编辑器输入控件")
        input_wx.paste_or_type(editor, text)

    @PIM.guard
    def clear(self) -> None:
        """清空编辑器内容"""
        self._editor_shortcut("{Ctrl}a{Del}", force_click=True, delay=0.2)

    @PIM.guard
    def select_all(self) -> None:
        """全选编辑器内容"""
        self._editor_shortcut("{Ctrl}a", force_click=True)

    # -- 富文本格式快捷键 --
    # 底部工具栏渲染在 WebView 内部，不暴露为 UI Automation 控件，
    # 因此通过键盘快捷键操作格式。

    @PIM.guard
    def begin_voice_input(self) -> None:
        """开始语音输入：按下 Ctrl+Win 不松开"""
        self.focus_editor(force_click=False)
        ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)  # VK_CONTROL down
        ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)  # VK_LWIN down

    @PIM.guard
    def end_voice_input(self) -> None:
        """结束语音输入：释放 Ctrl+Win 按键"""
        ctypes.windll.user32.keybd_event(0x5B, 0, 0x2, 0)  # VK_LWIN up
        ctypes.windll.user32.keybd_event(0x11, 0, 0x2, 0)  # VK_CONTROL up

    @PIM.guard
    def add_file(self, file_path: str) -> None:
        """通过 Ctrl+O 打开文件选择对话框，输入路径并确认添加文件"""
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Ctrl}O")
        time.sleep(1)

        dlg = auto.WindowControl(ClassName="#32770", ProcessId=self.wx.pid)
        if not dlg.Exists(maxSearchSeconds=5):
            raise RuntimeError("文件选择对话框未弹出")

        input_wx.send_keys(dlg, "{Alt}N")
        time.sleep(0.3)
        edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
        if not edit.Exists(0, 0):
            edit = dlg.EditControl(AutomationId="1148")
        input_wx.paste_or_type(edit, file_path)
        time.sleep(0.3)
        input_wx.send_keys(dlg, "{Alt}O")

    @PIM.guard
    def bold(self) -> None:
        """加粗（Ctrl+B）"""
        self._editor_shortcut("{Ctrl}B")

    @PIM.guard
    def italic(self) -> None:
        """斜体（Ctrl+I）"""
        self._editor_shortcut("{Ctrl}I")

    @PIM.guard
    def underline(self) -> None:
        """下划线（Ctrl+U）"""
        self._editor_shortcut("{Ctrl}U")

    @PIM.guard
    def highlight(self) -> None:
        """高亮（Ctrl+Shift+H）"""
        self._editor_shortcut("{Ctrl}{Shift}H")

    @PIM.guard
    def undo(self) -> None:
        """撤销（Ctrl+Z）"""
        self._editor_shortcut("{Ctrl}z")

    @PIM.guard
    def redo(self) -> None:
        """重做（Ctrl+Y）"""
        self._editor_shortcut("{Ctrl}y")

    @PIM.guard
    def new_line(self) -> None:
        """换行（Enter）"""
        self._editor_shortcut("{Enter}", force_click=True)

    @PIM.guard
    def save(self) -> None:
        """保存笔记（Ctrl+S）"""
        self._editor_shortcut("{Ctrl}s", delay=0.3)

    @PIM.guard
    def add_tags(self, *tags: str) -> None:
        """
        添加标签（通过 Ctrl+T 打开标签弹窗，逐个输入）。

        标签弹窗渲染在 WebView 内部，需通过窗口级别 SendKeys 输入。
        """
        self.focus_editor()
        for tag in tags:
            if not tag:
                continue
            input_wx.send_keys(self._editor, "{Ctrl}T")
            time.sleep(1)
            input_wx.paste_or_type(None, tag)
            time.sleep(0.3)
            input_wx.send_keys(None, "{Down}")
            input_wx.send_keys(None, "{Enter}")
            time.sleep(0.3)
        input_wx.send_keys(None, "{Esc}")

    @PIM.guard
    def paste(self) -> None:
        """粘贴剪贴板内容（Ctrl+V）"""
        self._editor_shortcut("{Ctrl}v", force_click=True, delay=0.2)

    @PIM.guard
    def paste_file(self, file_path: str) -> None:
        """通过剪贴板粘贴文件到笔记中"""
        self.focus_editor()
        input_wx.paste([file_path])

    def __str__(self) -> str:
        if not self.exists:
            return "NoteEditor(closed)"
        preview = self.content[:30]
        if len(self.content) > 30:
            preview += "..."
        return f"NoteEditor(content={preview!r})"


def _parse_session_name(raw: str, session: Optional[Session] = None) -> SessionItem:
    """
    解析会话 ListItem 的 Name 属性。

    典型格式（换行分隔）：
      "雕虫小技 一群\\n...\\n17:15\\n消息免打扰\\n"
    """
    parts = [p for p in raw.split("\n") if p.strip()]
    item = SessionItem(session)
    item.name = parts[0] if parts else ""
    item.last_msg = parts[1] if len(parts) > 1 else ""
    item.msg_time = parts[2] if len(parts) > 2 else ""
    item.muted = i_("消息免打扰") in raw
    m = re.search(r"\[(\d+)条\]", raw)
    if m:
        item.unread = m.group(0)
    return item


class Navigator:
    @property
    def TABS(self) -> Dict[str, str]:
        return {
            i_("微信"): i_("微信"),
            i_("通讯录"): i_("通讯录"),
            i_("收藏"): i_("收藏"),
            i_("朋友圈"): i_("朋友圈"),
            i_("视频号"): i_("视频号"),
            i_("搜一搜"): i_("搜一搜"),
            i_("手机"): i_("手机"),
            i_("更多"): i_("更多"),
        }

    def __init__(self, wx: Weixin):
        """
        初始化导航栏。

        Args:
            wx: Weixin 实例。
        """
        self.wx = wx
        self._win = wx._win
        self._tabbar = self._win.ToolBarControl(ClassName="mmui::MainTabBar", searchDepth=5)

    def switch_to(self, tab_name: str) -> None:
        self.wx.activate()
        if tab_name not in self.TABS:
            raise ValueError(f"未知标签页: {tab_name}，可选: {list(self.TABS.keys())}")

        if tab_name not in [i_("手机"), i_("更多")]:
            btn = self._tabbar.ButtonControl(ClassName="mmui::XTabBarItem", Name=self.TABS[tab_name], searchDepth=1)
        else:
            btn = self._tabbar.ButtonControl(ClassName="mmui::MainTabBarSettingView", Name=self.TABS[tab_name], searchDepth=1)

        input_wx.click(btn)

    @PIM.guard
    def get_self_profile(self) -> dict:
        """
        获取当前登录账号的个人资料（昵称、微信号）。

        通过导航栏"更多" → 点击"设置"按钮打开设置窗口，
        点击"账号与存储"菜单项，从右侧面板读取昵称和微信号，
        然后关闭设置窗口。

        Returns:
            dict: {"nickname": str, "account": str}
        """
        self.wx.activate()
        self.switch_to(i_("更多"))
        time.sleep(0.3)

        # 点击"设置"按钮
        setting_btn = self._win.ButtonControl(Name=i_("设置"), searchDepth=10)
        if not setting_btn.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到'设置'按钮")
        input_wx.click(setting_btn)
        time.sleep(0.5)

        # 等待设置窗口出现
        setting_win = auto.WindowControl(
            ClassName="mmui::PreferenceWindow",
            ProcessId=self.wx.pid,
            searchDepth=1,
        )
        if not setting_win.Exists(maxSearchSeconds=5):
            raise RuntimeError("设置窗口未打开")

        try:
            page = setting_win.GroupControl(
                ClassName="mmui::PreferencePageAccount",
            )
            if not page.Exists(maxSearchSeconds=3):
                account_btn = setting_win.ButtonControl(
                    ClassName="mmui::XButton",
                    Name=i_("账号与存储"),
                )
                if account_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(account_btn)
                    time.sleep(0.5)
                page = setting_win.GroupControl(
                    ClassName="mmui::PreferencePageAccount",
                )
                if not page.Exists(maxSearchSeconds=3):
                    raise WxControlNotFoundError("未找到账号与存储页面")

            nickname = ""
            account = ""
            head_view = page.ButtonControl(ClassName="mmui::ContactHeadView")
            if head_view.Exists(maxSearchSeconds=2):
                parent = head_view.GetParentControl()
                if parent:
                    texts = []
                    for ctrl in parent.GetChildren():
                        if (ctrl.ControlType == auto.ControlType.GroupControl
                                and ctrl.ClassName == "QWidget"):
                            for child in ctrl.GetChildren():
                                if (child.ControlType == auto.ControlType.TextControl
                                        and child.ClassName == "mmui::XTextView"
                                        and child.Name):
                                    texts.append(child.Name)
                            if texts:
                                break

                    if len(texts) >= 1:
                        nickname = texts[0]
                    if len(texts) >= 2:
                        account = texts[1]

            return {"nickname": nickname, "account": account}
        finally:
            try:
                wp = setting_win.GetWindowPattern()
                if wp:
                    wp.Close()
                else:
                    close_btn = setting_win.ButtonControl(
                        ClassName="mmui::XButton", Name=i_("关闭"),
                    )
                    if close_btn.Exists(maxSearchSeconds=1):
                        input_wx.click(close_btn)
            except Exception:
                pass
            time.sleep(0.3)

    @PIM.guard
    def get_self_info(self) -> dict:
        """
        获取当前登录账号的个人资料（通过点击头像打开资料面板）。

        点击导航栏"微信"按钮上方 35px 处（即头像位置）打开个人资料面板，
        从面板中读取昵称、微信号和头像，然后关闭面板。

        Returns:
            dict: {"nickname": str, "account": str, "avatar": str}
            avatar 为头像图片的 base64 编码字符串（PNG 格式）
        """
        self.wx.activate()

        wx_btn = self._tabbar.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name=i_("微信"),
            searchDepth=5,
        )
        if not wx_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到导航栏'微信'按钮")

        rect = wx_btn.BoundingRectangle
        click_x = (rect.left + rect.right) // 2
        click_y = rect.top - 35
        auto.Click(click_x, click_y)
        time.sleep(0.5)

        profile = self._win.GroupControl(
            ClassName="mmui::ContactProfileView",
        )
        if not profile.Exists(maxSearchSeconds=3):
            raise RuntimeError("个人资料面板未打开")

        try:
            result = {"nickname": "", "account": "", "avatar": ""}

            display_name = profile.TextControl(
                AutomationId="right_v_view.nickname_button_view.display_name_text",
            )
            if display_name.Exists(0, 0):
                val = (display_name.Name or "").strip()
                if val:
                    result["nickname"] = val

            key_map = {
                "微信号：": "account",
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

            avatar_ctrl = profile.ButtonControl(
                ClassName="mmui::ContactHeadView",
                AutomationId="head_image_v_view.head_view_",
            )
            if avatar_ctrl.Exists(0, 0):
                try:
                    input_wx.click(avatar_ctrl)

                    img_viewer = auto.WindowControl(
                        ClassName="mmui::PreviewWindow",
                        ProcessId=self.wx.pid,
                        searchDepth=1,
                    )
                    if img_viewer.Exists(maxSearchSeconds=3):
                        save_btn = img_viewer.ButtonControl(
                            ClassName="mmui::XButton",
                            Name=i_("保存"),
                        )
                        if save_btn.Exists(maxSearchSeconds=2):
                            tmp_dir = os.path.join(tempfile.gettempdir(), "pywxauto_avatar")
                            os.makedirs(tmp_dir, exist_ok=True)
                            tmp_path = os.path.join(tmp_dir, f"{result['account']}_avatar.png")
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)

                            input_wx.click(save_btn)

                            save_dlg = auto.WindowControl(ClassName="#32770", ProcessId=self.wx.pid)
                            if save_dlg.Exists(maxSearchSeconds=5):
                                file_edit = save_dlg.EditControl(AutomationId="1001")
                                if file_edit.Exists(maxSearchSeconds=2):
                                    vp = file_edit.GetValuePattern()
                                    if vp:
                                        vp.SetValue(tmp_path)
                                    else:
                                        input_wx.send_keys(file_edit, "{Ctrl}a{Del}")
                                        input_wx.paste_or_type(file_edit, tmp_path)

                                    dlg_save_btn = save_dlg.ButtonControl(AutomationId="1")
                                    if dlg_save_btn.Exists(maxSearchSeconds=2):
                                        input_wx.click(dlg_save_btn)
                                    else:
                                        input_wx.send_keys(save_dlg, "{Alt}S")

                                    if os.path.exists(tmp_path):
                                        with open(tmp_path, "rb") as f:
                                            avatar_bytes = f.read()
                                        result["avatar"] = base64.b64encode(avatar_bytes).decode("ascii")
                                        os.remove(tmp_path)
                                else:
                                    input_wx.send_keys(save_dlg, "{Esc}")

                        img_hwnd = img_viewer.NativeWindowHandle
                        if img_hwnd:
                            close_window(img_hwnd)
                except Exception:
                    try:
                        iv = auto.WindowControl(
                            ClassName="mmui::PreviewWindow",
                            ProcessId=self.wx.pid,
                            searchDepth=1,
                        )
                        if iv.Exists(maxSearchSeconds=0.5):
                            iv_hwnd = iv.NativeWindowHandle
                            if iv_hwnd:
                                close_window(iv_hwnd)
                    except Exception:
                        pass
            return result
        finally:
            pass

    @PIM.guard
    def lock(self) -> None:
        """锁定微信（Ctrl+L）"""
        self.wx.activate()
        input_wx.send_keys(None, "{Ctrl}l")

    def __str__(self) -> str:
        tabs = ", ".join(self.TABS.keys())
        return f"Navigator(tabs=[{tabs}])"


class SessionItem:
    """会话列表中的一条会话"""

    def __init__(self, session: Optional[Session] = None, *, name: str = "", last_msg: str = "", msg_time: str = "",
                 muted: bool = False, unread: str = "", is_active: bool = False,
                 runtime_id: tuple = ()):
        """
        初始化会话项。

        Args:
            session: 关联的 Session 实例，用于执行右键菜单等操作。
            name: 会话名称。
            last_msg: 最后一条消息摘要。
            msg_time: 消息时间文本。
            muted: 是否消息免打扰。
            unread: 未读条数文本，如 "[9条]"。
            is_active: 是否为当前选中（激活）的会话。
            runtime_id: UI Automation RuntimeId，用于唯一标识控件。
        """
        self.session = session
        self.name = name
        self.last_msg = last_msg
        self.msg_time = msg_time
        self.muted = muted
        self.unread = unread
        self.is_active = is_active
        self.runtime_id = runtime_id

    def pin(self) -> None:
        """置顶会话"""
        self.session._session_context_action(self.name, i_("置顶"))

    def unpin(self) -> None:
        """取消置顶会话"""
        self.session._session_context_action(self.name, i_("取消置顶"))

    def mark_as_unread(self) -> None:
        """标为未读"""
        self.session._session_context_action(self.name, i_("标为未读"))

    def mark_as_read(self) -> None:
        """标为已读"""
        self.session._session_context_action(self.name, i_("标为已读"))

    def mute(self) -> None:
        """消息免打扰"""
        self.session._session_context_action(self.name, i_("消息免打扰"))

    def unmute(self) -> None:
        """允许消息通知"""
        self.session._session_context_action(self.name, i_("允许消息通知"))

    def separate(self) -> None:
        """独立窗口显示"""
        self.session._session_context_action(self.name, i_("独立窗口显示"))

    def separate_by_click(self) -> SeparateChat:
        """双击打开独立窗口，返回 SeparateChat 实例"""
        session = self.session
        if session.wx:
            session.wx.activate()
        item = session._ensure_session_visible(self.name)
        input_wx.click(item, click="double")
        return SeparateChat(session.wx, self.name)

    def hide(self) -> None:
        """不显示该会话"""
        self.session._session_context_action(self.name, i_("不显示"))

    def delete(self) -> None:
        """删除会话（危险操作，会清除聊天记录）"""
        session = self.session
        session._session_context_action(self.name, i_("删除"))
        confirm_btn = session._win.ButtonControl(Name=i_("删除"), ClassName="mmui::XOutlineButton")
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到删除确认弹窗")
        input_wx.click(confirm_btn)

    def open(self) -> None:
        """激活会话"""
        self.session.open(self.name)

    def close(self) -> None:
        """取消激活（如果处于激活状态则取消选中）"""
        self.session.close(self.name)

    def __repr__(self) -> str:
        muted_tag = " [免打扰]" if self.muted else ""
        active_tag = " [激活]" if self.is_active else ""
        return f"SessionItem({self.name!r}, {self.msg_time}{muted_tag}{active_tag})"


class Session:
    """
    会话列表面板，包含搜索框和会话列表。

    关键控件：
    - 搜索框: EditControl, ClassName="mmui::XValidatorTextEdit", Name="搜索"
    - 会话列表: ListControl, ClassName="mmui::XTableView", AutomationId="session_list"
    - 会话项: ListItemControl, ClassName="mmui::ChatSessionCell",
              AutomationId="session_item_{name}"
    """

    def __init__(self, wx: Weixin):
        """
        初始化会话列表面板。

        Args:
            wx: Weixin 实例。
        """
        self.wx = wx
        self._win = wx._win

    @property
    def is_visible(self) -> bool:
        """会话列表面板是否可见"""
        return self._list_control.Exists(0, 0)

    def _ensure_ready(self) -> None:
        """确保微信窗口激活且会话列表可见"""
        self.wx.activate()
        if not self.is_visible:
            self.wx.navigator.switch_to(i_("微信"))

    @property
    def _list_control(self) -> auto.ListControl:
        return self._win.ListControl(ClassName="mmui::XTableView", AutomationId="session_list")

    def visible(self) -> List[SessionItem]:
        """获取当前可见的会话列表"""
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到会话列表控件")

        sessions: List[SessionItem] = []
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
                    item.is_active = True
            except Exception:
                pass
            sessions.append(item)
        return sessions

    def names(self) -> List[str]:
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
            raise WxControlNotFoundError(f"会话列表中未找到: {name}")
        input_wx.click(item)
        time.sleep(0.3)

    def _get_search_edit(self) -> auto.EditControl:
        return self._win.EditControl(
            ClassName="mmui::XValidatorTextEdit",
            Name=i_("搜索"),
        )

    @PIM.guard
    def search(self, keyword: str, chat_type: Optional[List[str]] = None) -> None:
        """搜索并打开会话（search_and_select 的别名，失败时抛异常）"""
        if not self.search_and_select(keyword, chat_type):
            raise WxControlNotFoundError(f"搜索未找到结果: {keyword}")

    @PIM.guard
    def open_by_search(self, name: str, chat_type: Optional[List[str]] = None,
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
        self._ensure_ready()
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
                # 如果已激活，检查聊天区域标题是否匹配
                try:
                    pattern = item.GetSelectionItemPattern()
                    if pattern and pattern.IsSelected:
                        # 已选中但聊天区域可能未显示该会话，验证标题
                        for aid in Chat.TITLE_LABEL_IDS:
                            title = self._win.TextControl(AutomationId=aid)
                            if title.Exists(0, 0) and title.Name == name:
                                return
                        # 标题不匹配，点击刷新
                        input_wx.click(item)
                        return
                except Exception:
                    pass
                input_wx.click(item)
                return

        # 列表中没有（或强制搜索），走搜索
        self.search(name, chat_type)

    @PIM.guard
    def scroll(self, direction: Literal["up", "down"] = "down", clicks: int = 3) -> None:
        """
        滚动会话列表。
        direction: "up" 或 "down"
        clicks: 滚动次数
        """
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到会话列表控件")
        delta = -clicks if direction == "down" else clicks
        rect = lc.BoundingRectangle
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        auto.WheelDown(cx, cy, abs(delta)) if direction == "down" else auto.WheelUp(cx, cy, abs(delta))
        time.sleep(0.3)

    def all(self, step: int = 5, max_scrolls: int = 500) -> List[SessionItem]:
        """
        通过滚动获取完整的会话列表。

        使用 RuntimeId 集合去重，精确识别新会话，
        支持重名会话（不同会话的 RuntimeId 不同）。

        step: 每次按 Down 键的次数（固定滚动幅度）
        max_scrolls: 最大滚动轮次

        Returns:
            按出现顺序排列的完整会话列表
        """
        self._ensure_ready()
        lc = self._list_control
        if not lc.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到会话列表控件")

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

        all_sessions: List[SessionItem] = []
        seen_rids: Set[tuple] = set()
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
            raise WxControlNotFoundError("未找到会话列表控件")

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
        prev_names: Set[str] = set()
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

        raise WxControlNotFoundError(f"会话列表中未找到: {name}")

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
            raise WxControlNotFoundError(f"菜单中未找到: {menu_name}")
        input_wx.click(menu_item)

    def _session_context_action(self, name: str, menu_name: str) -> None:
        """对指定会话执行右键菜单操作"""
        self._ensure_ready()
        self._right_click_session(name)
        self._click_context_menu_item(menu_name)

    @PIM.guard
    def pin(self, name: str) -> None:
        """置顶会话"""
        self._session_context_action(name, i_("置顶"))

    @PIM.guard
    def unpin(self, name: str) -> None:
        """取消置顶会话"""
        self._session_context_action(name, i_("取消置顶"))

    @PIM.guard
    def mark_as_unread(self, name: str) -> None:
        """标为未读"""
        self._session_context_action(name, i_("标为未读"))

    @PIM.guard
    def mark_as_read(self, name: str) -> None:
        """标为已读"""
        self._session_context_action(name, i_("标为已读"))

    @PIM.guard
    def mute(self, name: str) -> None:
        """消息免打扰"""
        self._session_context_action(name, i_("消息免打扰"))

    @PIM.guard
    def unmute(self, name: str) -> None:
        """允许消息通知"""
        self._session_context_action(name, i_("允许消息通知"))

    @PIM.guard
    def separate(self, name: str) -> None:
        """独立窗口显示"""
        self._session_context_action(name, i_("独立窗口显示"))

    @PIM.guard
    def hide(self, name: str) -> None:
        """不显示该会话"""
        self._session_context_action(name, i_("不显示"))

    @PIM.guard
    def close(self, name: str) -> None:
        """关闭指定会话：如果该会话处于激活状态，点击一下取消选中"""
        self._ensure_ready()
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
        self._ensure_ready()
        item = self._ensure_session_visible(name)
        try:
            pattern = item.GetSelectionItemPattern()
            if pattern and pattern.IsSelected:
                # 已激活但可能聊天区域未显示该会话（窗口之前未打开），
                # 点击一下确保聊天区域切换到该会话
                for aid in Chat.TITLE_LABEL_IDS:
                    title = self._win.TextControl(AutomationId=aid)
                    if title.Exists(0, 0) and title.Name == name:
                        return
                # 标题不匹配，说明聊天区域未显示，点击刷新
                input_wx.click(item)
                return
        except Exception:
            pass
        input_wx.click(item)

    @PIM.guard
    def delete(self, name: str) -> None:
        """删除会话（危险操作，会清除聊天记录）"""
        self._session_context_action(name, i_("删除"))
        confirm_btn = self._win.ButtonControl(
            Name=i_("删除"), ClassName="mmui::XOutlineButton",
        )
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到删除确认弹窗")
        input_wx.click(confirm_btn)

    @PIM.guard
    def search_and_select(self, keyword: str, chat_type: Optional[List[str]] = None) -> bool:
        """
        在搜索框中输入关键词并点击第一个匹配结果。
        返回是否成功找到并点击了结果。

        keyword: 搜索关键词
        chat_type: 优先匹配的分类，如 ["联系人", "群聊", "功能", "公众号", "更多", "聊天记录", "聊天文件", "搜索网络结果", "收藏", "最近使用过的小程序", "服务号", "最近使用", "最常使用"]
        """
        chat_type = chat_type or [i_("最常使用"), i_("联系人"), i_("群聊"), i_("功能")]
        edit = self._get_search_edit()
        input_wx.click(edit)
        input_wx.paste_or_type(edit, keyword)

        # 按分类优先级查找搜索结果
        for category in chat_type:
            category_item = self._win.ListItemControl(
                ClassName="mmui::XTableCell",
                Name=category,
            )
            if category_item.Exists(0, 0):
                result_item = category_item.GetNextSiblingControl()
                if result_item:
                    input_wx.click(result_item)
                    return True
        return False

    @PIM.guard
    def cancel_search(self) -> None:
        """取消搜索（按 Esc 退出搜索模式）"""
        input_wx.send_keys(self._win, "{Esc}")

    @PIM.guard
    def search_contact(self, keyword: str) -> bool:
        """搜索联系人并打开会话"""
        return self.search_and_select(keyword, chat_type=[i_("最常使用"), i_("联系人"), i_("功能")])

    @PIM.guard
    def search_group(self, keyword: str) -> bool:
        """搜索群聊并打开会话"""
        return self.search_and_select(keyword, chat_type=[i_("最常使用"), i_("群聊"), i_("功能")])

    def _click_quick_action_button(self) -> None:
        """点击快捷操作按钮"""
        self._ensure_ready()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=i_("快捷操作"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到快捷操作按钮")
        input_wx.click(btn)

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
            raise WxControlNotFoundError(f"快捷操作菜单中未找到: {item_name}")
        input_wx.click(item)

    def _quick_action(self, item_name: str) -> None:
        """执行快捷操作"""
        self._click_quick_action_button()
        self._click_quick_action_item(item_name)

    @PIM.guard
    def create_room(self, nickname_list: List[str]) -> None:
        """
        发起群聊。

        nickname_list: 好友昵称列表，至少需要两个好友才能创建群聊。

        流程：
        1. 通过快捷操作菜单打开"发起群聊"弹窗
        2. 在搜索框中逐个输入好友昵称
        3. 点击搜索结果中的第一条联系人进行勾选
        4. 全部添加完成后，点击"完成"按钮

        窗口控件信息：
        - 发起群聊窗口: mmui::SessionPickerWindow, Name=i_("微信发起群聊")
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

        self._quick_action(i_("发起群聊"))

        # --- 第1步：等待发起群聊窗口出现 ---
        picker_win = self._win.WindowControl(
            ClassName="mmui::SessionPickerWindow",
        )
        if not picker_win.Exists(maxSearchSeconds=3):
            raise WxWindowNotFoundError("发起群聊窗口未打开")

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
                raise WxWindowNotFoundError("发起群聊窗口已关闭")
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
                raise WxControlNotFoundError("发起群聊窗口中未找到搜索区域")
            search_edit = search_field.EditControl(
                ClassName="mmui::XValidatorTextEdit", Name=i_("搜索"),
                searchDepth=1,
            )
            if not search_edit.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("发起群聊窗口中未找到搜索框")

            # 清空搜索框并通过键盘输入昵称
            input_wx.click(search_edit)
            time.sleep(0.3)
            input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
            time.sleep(0.3)
            input_wx.paste_or_type(search_edit, nickname)
            time.sleep(1.5)

            # 从左侧 SearchContactNewChatView 容器中查找搜索结果列表
            search_view = fresh_picker.GroupControl(
                ClassName="mmui::SearchContactNewChatView",
                searchDepth=3,
            )
            if not search_view.Exists(maxSearchSeconds=3):
                raise WxWindowNotFoundError(f"搜索联系人 '{nickname}' 后未出现搜索视图")

            result_list = search_view.ListControl(
                ClassName="mmui::XTableView",
                AutomationId="sp_search_new_chat_result_list",
                searchDepth=1,
            )
            if not result_list.Exists(maxSearchSeconds=5):
                raise WxWindowNotFoundError(f"搜索联系人 '{nickname}' 后未出现结果列表")

            contact_row = result_list.CheckBoxControl(
                ClassName="mmui::SearchContactCellView",
                searchDepth=1,
            )
            if not contact_row.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError(f"未找到联系人: {nickname}")

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
            raise WxWindowNotFoundError("发起群聊窗口已关闭")
        detail_view = final_picker.GroupControl(
            ClassName="mmui::SPDetailView",
            searchDepth=3,
        )
        if not detail_view.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到详情面板")
        confirm_btn = detail_view.ButtonControl(
            ClassName="mmui::XOutlineButton",
            AutomationId="confirm_btn",
            Name=i_("完成"),
            searchDepth=2,
        )
        if not confirm_btn.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到完成按钮")
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
          - 申请消息: EditControl, Name=i_("发送添加朋友申请")
          - 备注: EditControl, Name="修改备注", ClassName="mmui::XLineEdit"
          - 朋友权限选项: GroupControl, ClassName="mmui::ProfileFormPermissionItemUi"
            - Name=i_("聊天、朋友圈、微信运动等") (默认选中)
            - Name=i_("仅聊天")
          - 朋友圈开关: CheckBoxControl, ClassName="mmui::XSwitchButton"
            - Name=i_("不让他（她）看")
            - Name=i_("不看他（她）")
          - 确定/取消按钮
        """
        self._quick_action(i_("添加朋友"))

        add_friend_win = auto.WindowControl(
            ClassName="mmui::AddFriendWindow",
            AutomationId="AddFriendWindow",
            ProcessId=self.wx.pid
        )
        if not add_friend_win.Exists(maxSearchSeconds=3):
            raise RuntimeError("添加朋友窗口未打开")

        # --- 第1步：输入关键词并搜索 ---
        search_edit = add_friend_win.EditControl(
            ClassName="mmui::XValidatorTextEdit", Name=i_("搜索"),
        )
        if not search_edit.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("添加朋友窗口中未找到搜索框")
        input_wx.click(search_edit)
        time.sleep(0.2)
        # search_edit.GetValuePattern().SetValue(keyword)
        input_wx.paste_or_type(search_edit, keyword)
        time.sleep(0.3)
        search_btn = add_friend_win.ButtonControl(
            ClassName="mmui::XOutlineButton", Name=i_("搜索"),
        )
        if not search_btn.Exists(maxSearchSeconds=1):
            raise WxControlNotFoundError("未找到搜索按钮")
        input_wx.click(search_btn)
        time.sleep(1)

        # --- 第2步：点击"添加到通讯录" ---
        add_btn = add_friend_win.ButtonControl(Name=i_("添加到通讯录"))
        if not add_btn.Exists(maxSearchSeconds=3):
            # 检查是否已经是好友（出现"发消息"按钮）
            chat_btn = add_friend_win.ButtonControl(Name=i_("发消息"))
            if chat_btn.Exists(0, 0):
                raise RuntimeError("对方已经是好友，无需添加")
            raise WxControlNotFoundError("未找到'添加到通讯录'按钮，可能搜索无结果")
        input_wx.click(add_btn)
        time.sleep(1)

        # --- 第3步：填写申请表单 ---
        verify_win = auto.WindowControl(ClassName="mmui::VerifyFriendWindow", ProcessId=self.wx.pid)
        if not verify_win.Exists(maxSearchSeconds=3):
            raise RuntimeError("申请添加朋友窗口未打开")

        # 填写申请消息
        if message is not None:
            msg_edit = verify_win.EditControl(
                ClassName="mmui::XValidatorTextEdit", Name=i_("发送添加朋友申请"),
            )
            if msg_edit.Exists(maxSearchSeconds=1):
                input_wx.click(msg_edit)
                time.sleep(0.1)
                input_wx.send_keys(msg_edit, "{Ctrl}a{Del}")
                time.sleep(0.1)
                # msg_edit.GetValuePattern().SetValue(message)
                input_wx.paste_or_type(msg_edit, message)
                time.sleep(0.2)

        # 填写备注
        if remark is not None:
            remark_edit = verify_win.EditControl(
                ClassName="mmui::XLineEdit", Name=i_("修改备注"),
            )
            if remark_edit.Exists(maxSearchSeconds=1):
                input_wx.click(remark_edit)
                time.sleep(0.1)
                input_wx.send_keys(remark_edit, "{Ctrl}a{Del}")
                time.sleep(0.1)
                # remark_edit.GetValuePattern().SetValue(remark)
                input_wx.paste_or_type(remark_edit, remark)
                time.sleep(0.2)

        # 设置朋友权限（单选：点击整行切换）
        if permission == "chatonly":
            perm_item = verify_win.GroupControl(
                ClassName="mmui::ProfileFormPermissionItemUi",
                Name=i_("仅聊天"),
            )
            if perm_item.Exists(maxSearchSeconds=1):
                input_wx.click(perm_item)
                time.sleep(0.2)

        # 设置朋友圈和状态开关
        if hide_my_posts:
            sw = verify_win.CheckBoxControl(
                ClassName="mmui::XSwitchButton", Name=i_("不让他（她）看"),
            )
            if sw.Exists(maxSearchSeconds=1):
                toggle = sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 0:
                    input_wx.click(sw)
                    time.sleep(0.2)

        if hide_their_posts:
            sw = verify_win.CheckBoxControl(
                ClassName="mmui::XSwitchButton", Name=i_("不看他（她）"),
            )
            if sw.Exists(maxSearchSeconds=1):
                toggle = sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 0:
                    input_wx.click(sw)
                    time.sleep(0.2)

        # --- 第4步：点击确定 ---
        confirm_btn = verify_win.ButtonControl(
            Name=i_("确定"), ClassName="mmui::XOutlineButton",
        )
        if not confirm_btn.Exists(maxSearchSeconds=1):
            raise WxControlNotFoundError("未找到确定按钮")
        input_wx.click(confirm_btn)

    @PIM.guard
    def new_note(self) -> NoteEditor:
        """
        新建笔记，返回笔记编辑窗口对象。

        通过快捷操作菜单打开新建笔记窗口，
        等待笔记编辑窗口出现后返回 NoteEditor 实例。
        """
        self._quick_action(i_("新建笔记"))
        return NoteEditor(self.wx)

    @PIM.guard
    def open_session(self, nickname: str) -> Chat:
        """通过在会话列表中查找并点击来打开指定会话，返回 Chat 对象"""
        self._ensure_ready()
        self.open(nickname)
        for _ in range(10):
            chat = self.wx.chat
            if chat is not None:
                return chat
            time.sleep(0.3)
        raise RuntimeError(f"打开会话失败: {nickname}")

    @PIM.guard
    def open_session_by_search(self, nickname: str, chat_type: Optional[List[str]] = None,
                               force_search: bool = False) -> Chat:
        """通过搜索打开指定会话，返回 Chat 对象"""
        self._ensure_ready()
        self.open_by_search(nickname, chat_type, force_search)
        for _ in range(10):
            chat = self.wx.chat
            if chat is not None:
                return chat
            time.sleep(0.3)
        raise RuntimeError(f"打开会话失败: {nickname}")

    @PIM.guard
    def create_note(self, content: str) -> None:
        """
        创建笔记并写入内容，完成后关闭笔记窗口。

        Args:
            content: 笔记内容
        """
        self._ensure_ready()
        note = self.new_note()
        note.set_content(content)
        note.save()
        note.close()

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
    SUB_TITLE_IDS = [
        # 4.1.8.28
        "content_view.top_content_view.title_h_view.left_v_view.left_content_v_view.left_ui_.sub_title_",
    ]

    # ---- ClassName -> 消息类型映射（供状态检测使用） ----
    _TEXT_CLASS_NAMES = {"mmui::ChatTextItemView"}
    _EMOTION_CLASS_NAMES = {"mmui::ChatEmojiItemView", "mmui::ChatBubbleReferItemView"}
    _FILE_BUBBLE_CLASS_NAMES = {"mmui::ChatFileItemView", "mmui::ChatBubbleItemView"}

    # ---- 消息状态前缀映射 ----
    # 注意：状态前缀通过 _check_status_by_prefix 动态匹配，不再使用静态字典

    # ---- 发送收藏相关常量 ----
    FAV_SEND_BTN_CLASS = "mmui::XButton"
    FAV_DETAIL_LIST_ID = "fav_detail_list"
    FAV_DETAIL_LIST_CLASS = "mmui::XRecyclerTableView"
    FAV_ITEM_CLASS = "mmui::XTableCell"
    FAV_SEARCH_CLASS = "mmui::XValidatorTextEdit"
    FAV_SEND_CONFIRM_CLASS = "mmui::XOutlineButton"
    FAV_CANCEL_CLASS = "mmui::XOutlineButton"

    # ---- 发送表情相关常量 ----
    EMOJI_BTN_CLASS = "mmui::XButton"
    EMOJI_POPOVER_CLASS = "mmui::XPopover"
    EMOJI_POPOVER_ID = "EmoticonPopover"
    EMOJI_PANEL_TOOLBAR_ID = "emoticon_panel_tool_bar"
    EMOJI_SEARCH_TAB_CLASS = "mmui::EmoticonToolbarItem"
    EMOJI_SEARCH_INPUT_CLASS = "mmui::XValidatorTextEdit"
    EMOJI_SEARCH_FIELD_CLASS = "mmui::XSearchField"
    EMOJI_SEARCH_RESULT_CLASS = "Chrome_RenderWidgetHostHWND"
    EMOJI_CUSTOM_TAB_CLASS = "mmui::EmoticonToolbarItem"
    EMOJI_CUSTOM_GRID_CLASS = "mmui::EmoticonGridView"
    EMOJI_CUSTOM_ITEM_CLASS = "mmui::FavEmoticonItemView"

    def __init__(self, wx: Weixin):
        """
        初始化聊天区域。

        Args:
            wx: Weixin 实例。
        """
        self.wx = wx
        self._win = wx._win
        self._scan_paused: bool = False  # 监听线程暂停标志

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
        self.wx.activate()

    def __str__(self) -> str:
        try:
            name = self.chat_name
            chat_type = self.chat_type
            return f"Chat(type={chat_type!r}, name={name!r})"
        except Exception as e:
            return f"Chat(error={e!r})"

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

    def _find_sub_title_label(self) -> Optional[auto.TextControl]:
        """查找副标题控件（存在时表示 current_chat_name_label 显示的是备注）"""
        for aid in self.SUB_TITLE_IDS:
            ctrl = self._win.TextControl(AutomationId=aid)
            if ctrl.Exists(0, 0):
                return ctrl
        return None

    @property
    def chat_name(self) -> Optional[str]:
        """获取当前聊天对象名称（优先返回备注，无备注时返回原始名称）"""
        label = self._find_title_label()
        return label.Name if label else None

    @property
    def nickname(self) -> Optional[str]:
        """
        获取聊天的原始名称（群名/昵称）。

        当存在副标题控件时，副标题的 Name 为原始名称；
        不存在时，私聊无法区分昵称和备注，返回 None。
        """
        sub = self._find_sub_title_label()
        if sub:
            return sub.Name
        return None

    @property
    def remark(self) -> Optional[str]:
        """
        获取聊天备注名。

        当存在副标题控件时，标题栏的 Name 为备注名；
        不存在时，私聊无法区分昵称和备注，返回 None。
        """
        sub = self._find_sub_title_label()
        if sub:
            label = self._find_title_label()
            return label.Name if label else None
        return None

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

    @PIM.guard
    def cancel_reply(self) -> bool:
        """
        取消当前输入框中的引用消息。

        点击输入框上方的"删除引用消息"按钮，取消引用状态。
        如果当前没有引用消息（按钮不存在），则不操作并返回 False。

        Returns:
            True 取消成功，False 当前无引用消息
        """
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=i_("删除引用消息"),
        )
        if not btn.Exists(maxSearchSeconds=1):
            return False
        input_wx.click(btn)
        return True

    def _resolve_quote(self, quote: Optional[Union[Message, int]]) -> None:
        """
        解析 quote 参数并执行引用操作。

        Args:
            quote: 支持三种类型：
                - None: 不引用
                - Message: 直接调用 refer()
                - int (msg_id): 从当前可见消息中查找匹配的消息并 refer()

        Raises:
            ValueError: msg_id 未在当前可见消息中找到时抛出
        """
        if quote is None:
            return
        if isinstance(quote, Message):
            quote.quote()
            return
        if isinstance(quote, int):
            messages = self.get_visible_messages()
            for msg in messages:
                if msg.msg_id == quote:
                    msg.quote()
                    return
            raise ValueError(f"当前可见消息中未找到 msg_id={quote} 的消息")
        raise TypeError(f"quote 参数类型错误: {type(quote)}, 支持 Message | int | None")

    def _find_last_self_message_ctrl(
        self, class_names: Set[str],
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
        candidates: List[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            if (ctrl.ClassName or "") in class_names:
                candidates.append(ctrl)

        # 倒序查找自己发的
        for ctrl in reversed(candidates):
            sender, source, *_ = self._detect_sender(
                hwnd, ctrl, self.chat_name or "对方",
            )
            if source == Source.SELF:
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
        failed_kw = i_("发送失败")
        sending_kw = i_("发送中")
        if name.startswith(f"{failed_kw}{sep}"):
            return MessageStatus.FAILED
        if name.startswith(f"{sending_kw}{sep}"):
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
        candidates: List[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            candidates.append(ctrl)

        # 倒序查找最后一条自己发的消息
        for ctrl in reversed(candidates):
            sender, source, *_ = self._detect_sender(
                hwnd, ctrl, self.chat_name or "对方",
            )
            if source != Source.SELF:
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
                if name.startswith(i_("文件") + "\n"):
                    return self.check_file_message_status(timeout=timeout)
                # 其他气泡类型（链接、位置等）无传输状态，直接返回 SENT
                return MessageStatus.SENT

            # ChatBubbleReferItemView — 图片/视频/表情
            if cls == "mmui::ChatBubbleReferItemView":
                failed_kw = i_("发送失败")
                sending_kw = i_("发送中")
                image_kw = i_("图片")
                video_kw = i_("视频")
                emoji_kw = i_("动画表情")
                if re.match(rf"^(?:{re.escape(failed_kw)}\s+|{re.escape(sending_kw)}\s+)?{re.escape(image_kw)}$", name):
                    return self.check_image_message_status(timeout=timeout)
                if re.match(rf"^{re.escape(video_kw)}(?:\s|$)", name):
                    return self.check_video_message_status(timeout=timeout)
                if re.match(rf"^(?:{re.escape(failed_kw)}\s+|{re.escape(sending_kw)}\s+)?{re.escape(emoji_kw)}", name):
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
                    failed_kw = i_("发送失败")
                    sending_kw = i_("发送中")
                    expected = {content, f"{failed_kw} {content}", f"{sending_kw} {content}"}
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

        candidates: List[auto.Control] = []
        for ctrl, _ in auto.WalkControl(lc):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            if not ctrl.Name:
                continue
            cls = ctrl.ClassName or ""
            if cls not in self._FILE_BUBBLE_CLASS_NAMES:
                continue
            # ChatBubbleItemView 是通用气泡，需要通过 Name 过滤文件消息
            if cls == "mmui::ChatBubbleItemView" and not ctrl.Name.startswith(i_("文件") + "\n"):
                continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, source, *_ = self._detect_sender(
                hwnd, ctrl, self.chat_name or "对方",
            )
            if source == Source.SELF:
                return ctrl
        return None

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
        file_kw = i_("文件")
        progress_kw = i_("进度")
        interrupted_kw = i_("发送中断")
        if re.match(rf"^{re.escape(file_kw)}\n{re.escape(progress_kw)}[:：]\s*\d+%\n.+\n{re.escape(interrupted_kw)}\n", name, re.DOTALL):
            return MessageStatus.FAILED
        if re.match(rf"^{re.escape(file_kw)}\n{re.escape(progress_kw)}[:：]\s*\d+%\n.+\n(?!.*{re.escape(interrupted_kw)})", name, re.DOTALL):
            return MessageStatus.SENDING
        if re.match(rf"^{re.escape(file_kw)}\n(?!{re.escape(progress_kw)}[:：])", name):
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
        candidates: List[auto.Control] = []
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
                failed_kw = i_("发送失败")
                sending_kw = i_("发送中")
                image_kw = i_("图片")
                if not re.match(rf"^(?:{re.escape(failed_kw)}\s+|{re.escape(sending_kw)}\s+)?{re.escape(image_kw)}$", ctrl.Name):
                    continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, source, *_ = self._detect_sender(
                hwnd, ctrl, self.chat_name or "对方",
            )
            if source == Source.SELF:
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

        candidates: List[auto.Control] = []
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
                failed_kw = i_("发送失败")
                sending_kw = i_("发送中")
                emoji_kw = i_("动画表情")
                if not re.match(rf"^(?:{re.escape(failed_kw)}\s+|{re.escape(sending_kw)}\s+)?{re.escape(emoji_kw)}", ctrl.Name):
                    continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, source, *_ = self._detect_sender(
                hwnd, ctrl, self.chat_name or "对方",
            )
            if source == Source.SELF:
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
        candidates: List[auto.Control] = []
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
                video_kw = i_("视频")
                if not re.match(rf"^{re.escape(video_kw)}(?:\s|$)", ctrl.Name):
                    continue
            candidates.append(ctrl)

        for ctrl in reversed(candidates):
            sender, source, *_ = self._detect_sender(
                hwnd, ctrl, self.chat_name or "对方",
            )
            if source == Source.SELF:
                return ctrl
        return None

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
        video_kw = i_("视频")
        progress_kw = i_("进度")
        upload_kw = i_("上传中")
        if re.match(rf"^{re.escape(video_kw)}\s+{re.escape(upload_kw[:2])}\s*暂停", name):
            return MessageStatus.FAILED
        if re.match(rf"^{re.escape(video_kw)}\s+{re.escape(progress_kw)}[:：]\s*\d+%", name):
            return MessageStatus.SENDING
        if re.match(rf"^{re.escape(video_kw)}(?:\s+\d+:\d+)?$", name):
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
    def send_text(self, content: str, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送文本，返回发送状态。

        Args:
            content: 文本内容
            quote: 要引用的消息，支持 Message 对象或 msg_id (int)，None 不引用
            timeout: 状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待

        前台模式：ValuePattern 设置文本 + 点击发送按钮
        后台模式：ValuePattern 设置文本 + send_keys 回车发送
        """
        self._activate_window()

        self._resolve_quote(quote)

        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到聊天输入框")
        
        if background:
            input_wx.paste_or_type(field, content)
        else:
            input_wx.paste(content)

        send_btn = self._win.ButtonControl(RegexName=i_("发送按钮正则"))
        input_wx.click(send_btn)

        # 发送后校验：输入框应已清空
        remaining = self._get_input_value()
        if remaining:
            raise SendError(
                f"发送后输入框未清空: Value={remaining!r}，消息可能未发出"
            )

        return self.check_text_message_status(content, timeout=timeout)

    @PIM.guard
    def send_file(self, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送文件，返回最后一个文件的发送状态。

        Args:
            file_path: 文件路径或路径列表，支持本地路径和网络 URL
            quote:  要引用的消息，支持 Message 对象或 msg_id (int)，None 不引用
            timeout:   状态检测超时时间（秒），大于 0 时轮询等待传输完成，默认 0 不等待

        Returns:
            最后一个文件的发送状态
        """
        self._resolve_quote(quote)
        return self._send_media(file_path, "文件", self.check_file_message_status, timeout)

    @PIM.guard
    def send_image(self, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送图片，返回最后一张图片的发送状态。

        Args:
            file_path: 图片路径或路径列表，支持本地路径和网络 URL
            quote:  要引用的消息，支持 Message 对象或 msg_id (int)，None 不引用
            timeout:   状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待

        Returns:
            最后一张图片的发送状态
        """
        self._resolve_quote(quote)
        return self._send_media(file_path, "图片", self.check_image_message_status, timeout)

    @PIM.guard
    def send_video(self, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送视频，返回最后一个视频的发送状态。

        Args:
            file_path: 视频路径或路径列表，支持本地路径和网络 URL
            quote:  要引用的消息，支持 Message 对象或 msg_id (int)，None 不引用
            timeout:   状态检测超时时间（秒），大于 0 时轮询等待上传完成，默认 0 不等待

        Returns:
            最后一个视频的发送状态
        """
        self._resolve_quote(quote)
        return self._send_media(file_path, "视频", self.check_video_message_status, timeout)

    def _send_media(self, file_path: Union[str, List[str]], label: str,
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
        local_paths: List[str] = []
        tmp_files: List[str] = []
        for p in paths:
            if is_url(p):
                tmp = download_to_temp(p)
                local_paths.append(os.path.abspath(tmp))
                tmp_files.append(tmp)
            else:
                local_paths.append(os.path.abspath(p))

        try:
            self.clear_input()
            field = self._input_field
            if not field.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("未找到聊天输入框")

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

                send_btn = self._win.ButtonControl(RegexName=i_("发送按钮正则"))
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

                send_btn = self._win.ButtonControl(RegexName=i_("发送按钮正则"))
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
            searchDepth=20
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到聊天工具栏")

        file_btn = toolbar.ButtonControl(Name=i_("发送文件"))
        if not file_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'发送文件'按钮")
        input_wx.click(file_btn)
        time.sleep(0.5)

        # 等待文件选择对话框弹出（系统 #32770 对话框）
        dlg = auto.WindowControl(ClassName="#32770", ProcessId=self.wx.pid)
        if not dlg.Exists(maxSearchSeconds=5):
            raise RuntimeError("文件选择对话框未弹出")

        # 填入文件路径
        edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
        if not edit.Exists(0, 0):
            edit = dlg.EditControl(AutomationId="1148")
        if not edit.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到文件名输入框")
        # edit.GetValuePattern().SetValue(file_path)
        input_wx.focus(edit)
        input_wx.paste_or_type(edit, file_path)
        time.sleep(0.2)

        # 点击"打开"按钮
        open_btn = dlg.ButtonControl(Name=i_("打开(&O)"))
        if not open_btn.Exists(maxSearchSeconds=2):
            open_btn = dlg.ButtonControl(Name="Open(&O)")
        if not open_btn.Exists(0, 0):
            open_btn = dlg.ButtonControl(AutomationId="1")
        if not open_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'打开'按钮")
        input_wx.click(open_btn)
        time.sleep(0.5)

    @PIM.guard
    def send_voice(self, duration: float = 3) -> None:
        """
        在当前会话中发送语音消息。

        通过按住右 Alt 键触发微信的语音输入功能，
        按住指定秒数后松开完成录制并自动发送。

        注意：需要电脑有可用的麦克风设备，且微信已授权麦克风权限。
        微信 4.x 的语音输入快捷键为按住右 Alt（VK_RMENU）。

        Args:
            duration: 录制时长（秒），默认 3 秒。
                      最小 1 秒（太短可能发送失败），
                      最长 60 秒（微信语音上限）。

        Raises:
            ValueError: duration 不在有效范围内时抛出
            RuntimeError: 未找到输入框时抛出
        """
        if duration < 1:
            raise ValueError("语音时长不能小于 1 秒")
        if duration > 60:
            raise ValueError("语音时长不能超过 60 秒")

        self._activate_window()

        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到聊天输入框")

        # 点击输入框确保聊天窗口获得焦点
        input_wx.click(field)
        time.sleep(0.3)

        # 按住右 Alt 键开始录音
        VK_RMENU = 0xA5  # 右 Alt 虚拟键码
        ctypes.windll.user32.keybd_event(VK_RMENU, 0, 0, 0)  # key down

        # 保持按住指定时长
        time.sleep(duration)

        # 松开右 Alt 键，结束录音并发送
        ctypes.windll.user32.keybd_event(VK_RMENU, 0, 0x0002, 0)  # key up
        time.sleep(0.5)

    @PIM.guard
    def send_at(self, content: str, at_members: List[str], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """
        在当前群聊会话中 @指定成员并发送消息，返回发送状态。

        Args:
            content:    消息正文（追加在 @成员 之后）
            at_members: 要 @ 的成员昵称列表，传 ["所有人"] 可 @所有人
            quote:   要引用的消息，支持 Message 对象或 msg_id (int)，None 不引用
            timeout:    状态检测超时时间（秒），大于 0 时轮询等待发送完成，默认 0 不等待
        """
        self._resolve_quote(quote)

        self._activate_window()
        self.clear_input()
        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到聊天输入框")

        self._add_at_members(field, at_members)

        if content:
            if background:
                input_wx.paste_or_type(field, content)
            else:
                input_wx.paste(content)

        send_btn = self._win.ButtonControl(RegexName=i_("发送按钮正则"))
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
    # 发送收藏按钮: ButtonControl, Name=i_("发送收藏"), ClassName="mmui::XButton"
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
            searchDepth=20
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到聊天工具栏")

        # 查找"发送收藏"按钮（嵌套在 GroupControl 内）
        fav_btn = toolbar.ButtonControl(
            ClassName=self.FAV_SEND_BTN_CLASS,
            Name=i_("发送收藏"),
            searchDepth=5,
        )
        if not fav_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'发送收藏'按钮")

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
            Name=i_("取消"),
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
            Name=i_("搜索"),
        )
        # 第一个搜索框通常就是收藏面板内的
        # 通过检查其位置是否在收藏面板区域附近来确认
        if edit.Exists(maxSearchSeconds=2):
            edit_rect = edit.BoundingRectangle
            # 搜索框应该在详情列表的左侧或上方区域
            if edit_rect.top >= detail_rect.top - 100 and edit_rect.left < detail_rect.left:
                return edit

        raise WxControlNotFoundError("未找到收藏面板搜索框")

    def _find_collection_item(self, detail_list: auto.ListControl, keyword: str) -> Optional[auto.ListItemControl]:
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
    def send_collection(self, keyword: str, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
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
            quote: 要引用的消息，支持 Message 对象或 msg_id (int)，None 不引用
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

        self._resolve_quote(quote)

        # 1. 打开收藏选择面板
        self._open_collection_panel()

        # 2. 在搜索框中输入关键词
        search_edit = self._find_fav_search_edit()
        input_wx.click(search_edit)
        input_wx.paste_or_type(search_edit, keyword)

        # 3. 获取搜索后的详情列表
        detail_list = self._win.ListControl(
            ClassName=self.FAV_DETAIL_LIST_CLASS,
            AutomationId=self.FAV_DETAIL_LIST_ID,
        )
        if not detail_list.Exists(maxSearchSeconds=3):
            self._close_collection_panel()
            raise WxControlNotFoundError("搜索后未找到收藏详情列表")

        # 4. 选中第一个搜索结果
        matched_item = self._find_collection_item(detail_list, keyword)
        if not matched_item:
            self._close_collection_panel()
            raise WxControlNotFoundError(f"未找到匹配的收藏项: {keyword}")
        input_wx.click(matched_item)

        # 5. 点击"发送"按钮
        send_btn = self._win.ButtonControl(
            ClassName=self.FAV_SEND_CONFIRM_CLASS,
            Name=i_("发送"),
        )
        if not send_btn.Exists(maxSearchSeconds=2):
            self._close_collection_panel()
            raise WxControlNotFoundError("未找到'发送'按钮")

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

        logger.debug("收藏发送成功")
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
    #     搜索输入框: EditControl, Name=i_("搜索"), ClassName="mmui::XValidatorTextEdit"
    #   搜索结果区: DocumentControl, Name="表情搜索",
    #               ClassName="Chrome_RenderWidgetHostHWND"
    #     搜索结果为 Chromium 内嵌网页渲染，表情项为 ListItemControl，
    #     Name 格式: "{关键词}表情，来自{来源}"，支持 InvokePattern 直接点击发送。

    @PIM.guard
    def send_emotion(self, keyword: str = None, index: int = 1, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """
        在当前会话中发送表情。

        当 keyword 不为 None 时，通过搜索关键词发送表情；
        当 keyword 为 None 时，发送自定义表情列表中第 index 个表情。

        Args:
            keyword: 表情搜索关键词，如 "哈喽"、"开心" 等。
                为 None 时发送自定义表情。
            index:   选择第几个表情，从 1 开始，默认为 1。
            quote: 要引用的消息，支持 Message 对象或 msg_id (int)，None 不引用
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

        self._resolve_quote(quote)

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
                input_wx.paste_or_type(search_edit, keyword)
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
                ProcessId=self.wx.pid,
                searchDepth=1
            )
            if emoji_popover.Exists(maxSearchSeconds=1):
                self._close_emoji_panel()
                label = "自定义表情" if keyword is None else "表情"
                raise SendError(f"发送{label}失败，表情面板未关闭")

            logger.debug("表情发送成功")
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
            ProcessId=self.wx.pid,
            searchDepth=1
        )
        if not popover.Exists(maxSearchSeconds=3):
            raise WxWindowNotFoundError("未找到表情弹窗")
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
            ProcessId=self.wx.pid,
            searchDepth=1
        )
        if emoji_popover.Exists(maxSearchSeconds=0.5):
            return

        # 查找工具栏
        toolbar = self._win.ToolBarControl(
            AutomationId="tool_bar_accessible",
            searchDepth=20
        )
        if not toolbar.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到聊天工具栏")

        # 查找"发送表情"按钮
        emoji_btn = toolbar.ButtonControl(
            ClassName=self.EMOJI_BTN_CLASS,
            Name=i_("发送表情(Alt+E)"),
            searchDepth=5,
        )
        if not emoji_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'发送表情'按钮")

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
                ProcessId=self.wx.pid,
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
            raise WxControlNotFoundError("未找到表情面板工具栏")

        search_tab = panel_toolbar.TabItemControl(
            ClassName=self.EMOJI_SEARCH_TAB_CLASS,
            Name=i_("搜索表情"),
        )
        if not search_tab.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'搜索表情'标签")

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
                Name=i_("搜索"),
            )
            if edit.Exists(maxSearchSeconds=2):
                return edit

        raise WxControlNotFoundError("未找到表情搜索输入框")

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
            Name=i_("表情搜索"),
        )
        if not result_doc.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到表情搜索结果区域")

        # 收集所有 ListItemControl（即表情项）
        items = result_doc.GetChildren()
        emotion_items = []
        for i, child in enumerate(items):
            if i == 0:
                if not child.Exists(maxSearchSeconds=10):
                    raise WxControlNotFoundError("未找到任何表情")
            self._collect_emotion_items(child, emotion_items)

        if not emotion_items:
            raise WxControlNotFoundError("搜索结果为空，未找到任何表情")

        if index > len(emotion_items):
            raise RuntimeError(
                f"第 {index} 个表情不存在，"
                f"搜索结果共 {len(emotion_items)} 个表情"
            )

        input_wx.click(emotion_items[index - 1])

    def _collect_emotion_items(self, control: auto.Control, result: list) -> None:
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
            raise WxControlNotFoundError("未找到表情面板工具栏")

        custom_tab = panel_toolbar.TabItemControl(
            ClassName=self.EMOJI_CUSTOM_TAB_CLASS,
            Name=i_("自定义表情"),
        )
        if not custom_tab.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'自定义表情'标签")
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
            raise WxControlNotFoundError("未找到自定义表情列表")

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
    # 聊天信息按钮: ButtonControl, Name=i_("聊天信息"), ClassName="mmui::XButton",
    #   AutomationId 末尾为 "more_button"
    # 联系人头像: ButtonControl, ClassName="mmui::ChatMemberCell",
    #   AutomationId="single_chat_member_cell"
    # 资料面板更多: ButtonControl, Name=i_("更多"), ClassName="mmui::XButton"
    # 推荐菜单项: MenuItemControl, Name=i_("把他推荐给朋友"),
    #   ClassName="mmui::XMenuView", AutomationId="XMenuItem"
    # 发送给弹窗: WindowControl, Name=i_("微信发送给"),
    #   ClassName="mmui::SessionPickerWindow"
    # 弹窗搜索框: EditControl, Name=i_("搜索"),
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

        contact_name = self.chat_name
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

            logger.debug(f"名片发送成功: {contact_name} -> {receiver_nickname}")
            return True
        except Exception:
            # 出错时尝试关闭可能残留的弹窗
            self._cleanup_send_card()
            raise

    def _click_chat_info_button(self) -> None:
        """点击聊天标题栏右上角的"聊天信息"按钮"""
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=i_("聊天信息"),
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'聊天信息'按钮")
        input_wx.click(btn)

    def _click_contact_avatar(self) -> None:
        """点击聊天信息面板中的联系人头像"""
        avatar = self._win.ButtonControl(
            ClassName="mmui::ChatMemberCell",
            AutomationId="single_chat_member_cell",
        )
        if not avatar.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到联系人头像")
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
                    and child.Name == i_("更多")):
                child_rect = child.BoundingRectangle
                if child_rect.left > win_center_x:
                    input_wx.click(child)
                    return

        raise WxControlNotFoundError("未找到资料面板'更多'按钮")

    def _click_recommend_contact(self) -> None:
        """点击弹出菜单中的"把他推荐给朋友" """
        menu_item = self._win.MenuItemControl(
            ClassName="mmui::XMenuView",
            Name=i_("把他推荐给朋友"),
        )
        if not menu_item.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'把他推荐给朋友'菜单项")
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
            raise WxControlNotFoundError("弹窗中未找到搜索区域")

        search_edit = search_field.EditControl(
            ClassName="mmui::XValidatorTextEdit", Name=i_("搜索"),
        )
        if not search_edit.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("弹窗中未找到搜索框")

        # 输入接收者昵称（通过剪贴板粘贴，确保触发搜索）
        input_wx.click(search_edit)
        time.sleep(0.3)
        input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
        time.sleep(0.2)
        input_wx.paste_or_type(search_edit, receiver_nickname)
        time.sleep(1.5)

        # 重新获取 picker_win，避免控件缓存问题
        fresh_picker = auto.WindowControl(
            ClassName="mmui::SessionPickerWindow",
            ProcessId=self.wx.pid,
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
            raise WxControlNotFoundError(f"搜索结果中未找到联系人: {receiver_nickname}")

        # 关键：在选中联系人之前先获取发送按钮引用，
        # 因为选中后 SPDetailView 面板会刷新重建，旧控件引用会失效，
        # 此时面板尚未刷新，控件树是稳定的，可以可靠地找到按钮。
        send_btn = fresh_picker.ButtonControl(
            AutomationId="confirm_btn",
        )
        if not send_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'发送'按钮")

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

    @staticmethod
    def _get_selected_mention_item(menu: auto.ListControl) -> Optional[auto.ListItemControl]:
        """
        获取 @候选菜单中当前被选中（高亮/激活）的 ListItem。

        通过 SelectionItemPattern.IsSelected 判断选中状态。
        """
        for ctrl, _ in auto.WalkControl(menu):
            if ctrl.ControlType != auto.ControlType.ListItemControl:
                continue
            sip = ctrl.GetSelectionItemPattern()
            if sip and sip.IsSelected:
                return ctrl
        return None

    def _add_at_members(self, chat_input: auto.EditControl,
                        at_members: List[str]) -> None:
        """
        在输入框中 @指定群成员。

        @菜单控件:
        - ListControl, AutomationId="chat_mention_list", searchDepth=4
        - 菜单项: ListItemControl, Name 为成员昵称

        支持完全匹配和模糊匹配，包含 "所有人" 时只 @所有人。
        对于昵称含空格的成员，取最长关键字搜索，然后通过 Down 键逐项
        匹配直到找到完全匹配的群成员昵称。
        """
        if not at_members:
            return
        if i_("所有人") in at_members:
            at_members = [i_("所有人")]

        for member in at_members:
            if not member:
                continue

            has_space = " " in member

            if not has_space:
                # 昵称不含空格：直接输入 @昵称
                if not chat_input.HasKeyboardFocus:
                    input_wx.click(chat_input)

                if member == i_("所有人"):
                    input_wx.paste_or_type(chat_input, "@")
                else:
                    input_wx.paste_or_type(chat_input, "@")
                    input_wx.paste_or_type(chat_input, member)

                menu = self._win.ListControl(
                    AutomationId="chat_mention_list", searchDepth=4,
                )
                if not menu.Exists(maxSearchSeconds=2):
                    raise RuntimeError(f"@群成员失败，未弹出候选菜单: {member}")

                controls = []
                for ctrl, _ in auto.WalkControl(menu):
                    if (ctrl.ControlType == auto.ControlType.ListItemControl
                            and ctrl.Name):
                        controls.append(ctrl)

                full = [c for c in controls if c.Name == member]
                fuzzy = [c for c in controls if member in c.Name]

                if full or len(fuzzy) == 1 or len(controls) == 1:
                    input_wx.send_keys(None, "{Enter}")
                    time.sleep(0.5)
                elif len(fuzzy) > 1:
                    names = [c.Name for c in fuzzy]
                    raise RuntimeError(f"@群成员模糊匹配到多个: {names}")
                else:
                    raise WxControlNotFoundError(f"@群成员失败，未找到: {member}")
            else:
                # 昵称含空格：取最长关键字搜索，然后逐项匹配
                member_keywords = member.split(" ")
                member_keyword = max(member_keywords, key=len)

                if not chat_input.HasKeyboardFocus:
                    input_wx.click(chat_input)

                input_wx.paste_or_type(chat_input, "@")
                input_wx.paste_or_type(chat_input, member_keyword)

                menu = self._win.ListControl(
                    AutomationId="chat_mention_list", searchDepth=4,
                )
                if not menu.Exists(maxSearchSeconds=2):
                    raise RuntimeError(f"@群成员失败，未弹出候选菜单: {member}")

                controls = []
                for ctrl, _ in auto.WalkControl(menu):
                    if (ctrl.ControlType == auto.ControlType.ListItemControl
                            and ctrl.Name):
                        controls.append(ctrl)

                fuzzy = [c for c in controls if member_keyword in c.Name]

                if len(fuzzy) == 0:
                    raise WxControlNotFoundError(f"@群成员失败，未找到: {member}")
                elif len(fuzzy) == 1:
                    # 唯一匹配，直接回车选中
                    input_wx.send_keys(None, "{Enter}")
                    time.sleep(0.5)
                else:
                    # 多个匹配结果：通过 Down 键逐项匹配，直到找到完全匹配的昵称
                    # 搜索结果数 < 5 时没有更多结果，>= 5 时可能有更多
                    max_match = len(fuzzy) if len(fuzzy) < 5 else 15
                    matched = False
                    count = 0

                    while count < max_match:
                        current_item = self._get_selected_mention_item(menu)
                        if not current_item:
                            break

                        if current_item.Name == member:
                            input_wx.send_keys(None, "{Enter}")
                            time.sleep(0.5)
                            matched = True
                            break

                        input_wx.send_keys(None, "{Down}")
                        time.sleep(0.2)
                        count += 1

                    if not matched:
                        input_wx.send_keys(None, "{Esc}")
                        time.sleep(0.3)
                        raise WxControlNotFoundError(f"@群成员失败，未找到完全匹配: {member}")

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
            raise WxControlNotFoundError("未找到通话按钮")
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
            raise WxControlNotFoundError(f"通话菜单中未找到: {menu_name}")
        input_wx.click(item)
        time.sleep(0.3)

    @PIM.guard
    def voice_call(self) -> VoipCall:
        self._activate_window()
        self._click_voip_menu("语音通话")
        return VoipCall(self)

    @PIM.guard
    def video_call(self) -> VoipCall:
        self._activate_window()
        self._click_voip_menu("视频通话")
        return VoipCall(self)

    @PIM.guard
    def separate(self) -> SeparateChat:
        """
        将当前聊天会话打开为独立窗口，返回 SeparateChat 实例。

        通过双击会话列表中的对应 SessionItem 打开独立窗口。
        等待独立窗口出现后返回 SeparateChat 对象。
        """
        self._activate_window()
        
        contact_name = self.chat_name
        if not contact_name:
            raise RuntimeError("无法获取当前聊天对象名称")

        # 在会话列表中找到对应的 SessionItem 并双击
        item = self._win.ListItemControl(
            ClassName="mmui::ChatSessionCell",
            AutomationId=f"session_item_{contact_name}",
        )
        
        if not item.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError(f"会话列表中未找到: {contact_name}")
        
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

    @property
    def message_view_rect(self) -> Tuple[int, int, int, int]:
        """
        获取聊天消息可见区域的坐标 (left, top, right, bottom)。

        通过查找 mmui::MessageView 控件的 BoundingRectangle 获取。

        Returns:
            (left, top, right, bottom) 屏幕坐标，未找到时返回空元组
        """
        view = self._win.GroupControl(ClassName="mmui::MessageView")
        if not view.Exists(0, 0):
            return ()
        rect = view.BoundingRectangle
        return (rect.left, rect.top, rect.right, rect.bottom)

    @PIM.guard
    def page_end(self) -> None:
        """
        将消息列表滚动到底部（最新消息处）。

        通过向消息列表发送 End 快捷键实现快速跳转到底部。
        如果消息列表不存在则不操作。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return
        self._activate_window()
        input_wx.focus(lc)
        time.sleep(0.1)
        input_wx.send_keys(lc, "{End}")
        time.sleep(0.3)

    def get_visible_messages(self, sender_cache: Dict[int, tuple] = None) -> List[Message]:
        """
        获取当前可见的消息列表，返回具体消息子类实例。

        消息项为 ListItemControl，通过 ClassName 区分类型，
        通过头像控件位置判断 Source。
        每条消息携带 runtime_id（UI Automation RuntimeId），
        作为控件的唯一标识，用于消息监听时的精确去重。

        Args:
            sender_cache: 可选的发送者缓存字典，格式为
                {msg_id: (sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect)}。
                传入后，已缓存的消息跳过截图检测直接使用缓存结果，
                新消息检测后自动写入缓存。
                用于监听场景下避免对已知消息重复截图导致窗口闪烁。
                msg_id 由 hash((runtime_id, class_name, raw_name)) 计算。
        """
        lc = self._message_list
        if not lc.Exists(maxSearchSeconds=2):
            return []

        # 获取窗口句柄，用于 PrintWindow 截图
        hwnd = self._win.NativeWindowHandle or 0

        # ClassName -> 消息子类映射
        cls_map: Dict[str, type] = {
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

        chat_name = self.chat_name or "对方"
        is_room = self.chat_type == "群聊"

        messages: List[Message] = []
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
                    ui_cls=ui_cls,
                    runtime_id=rid,
                    room=chat_name if is_room else None,
                    chat=self,
                    control=ctrl,
                )
                messages.append(sys_msg)
                continue

            # 缓存 key 与 msg_id 计算方式一致：hash((runtime_id, ui_cls, raw_name))
            cache_key = hash((rid, ui_cls, raw_name)) if rid else None

            # 判断发送者：优先从缓存读取，避免重复截图
            if sender_cache is not None and cache_key is not None and cache_key in sender_cache:
                sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect = sender_cache[cache_key]
            else:
                sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect = self._detect_sender(
                    hwnd, ctrl, chat_name,
                )
                # 群聊中对方发的消息，OCR 识别控件顶部 0-38px 区域提取真实发送者昵称
                if source == Source.OTHERS and is_room:
                    try:
                        ocr_sender = self._ocr_sender_name(hwnd, ctrl)
                        sender = ocr_sender if ocr_sender else None
                    except Exception:
                        sender = None
                # 写入缓存
                if sender_cache is not None and cache_key is not None:
                    sender_cache[cache_key] = (sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect)

            # 构造具体消息对象
            msg = self._build_message(
                msg_cls,
                raw_name, 
                sender, source,
                runtime_id=rid, 
                bubble_rect=bubble_rect,
                room=chat_name if is_room else None,
                chat=self, control=ctrl,
                headimg_rect=headimg_rect, 
                nickname_rect=nickname_rect,
                content_rect=content_rect,
                ui_cls=ui_cls,
            )
            messages.append(msg)
        return messages

    @staticmethod
    def _classify_bubble(name: str) -> type[Message]:
        """
        对 mmui::ChatBubbleItemView 通用气泡做二次分类。
        """
        loc_kw = i_("位置")
        file_kw = i_("文件")
        link_kw = i_("链接")
        voice_call_kw = i_("语音通话")
        video_call_kw = i_("视频通话")
        chat_history_kw = i_("聊天记录")
        merge_kw = i_("合并")
        note_kw = i_("笔记")
        red_packet_kw = i_("微信红包")
        transfer_kw = i_("微信转账")

        if name.startswith(loc_kw):
            return LocationMessage
        if name.startswith(f"{file_kw}\n") or name.startswith(f"{file_kw}\r"):
            return FileMessage
        if name.startswith(f"{link_kw}\n") or name.startswith(f"{link_kw}\r"):
            return LinkMessage
        if name.startswith(f"[{link_kw}]"):
            return LinkMessage
        if re.search(r"https?://", name):
            return LinkMessage
        if name.startswith(voice_call_kw) or name.startswith(video_call_kw):
            return VoipMessage
        if chat_history_kw in name or name.startswith(merge_kw):
            return MergeMessage
        if note_kw in name:
            return NoteMessage
        if name.endswith(red_packet_kw) and "  " in name:
            return RedPacketMessage
        if name.endswith(transfer_kw) and name.startswith("￥"):
            return TransferMessage
        if MusicMessage.match(name):
            return MusicMessage
        # ChatBubbleItemView 中未匹配的通常是卡片消息
        # （公众号文章、小程序卡片等）
        return CardMessage

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
        image_kw = i_("图片")
        video_kw = i_("视频")
        emoji_kw = i_("动画表情")
        if name == image_kw:
            return ImageMessage
        if name.startswith(video_kw):
            return VideoMessage
        if re.match(rf"^{re.escape(emoji_kw)}(\s+\[.+\])?$", name):
            return EmotionMessage
        return QuoteMessage

    # 图片 hash → OCR 识别结果缓存（避免重复 OCR 相同头像/昵称区域）
    _ocr_sender_cache: Dict[str, str] = {}

    def _ocr_sender_name(self, hwnd: int, ctrl: auto.Control) -> str:
        """
        通过 OCR 识别消息控件顶部 0-38px 区域，提取群聊中的发送者昵称。

        使用图片 hash 缓存：相同的昵称截图区域直接返回缓存结果，避免重复 OCR。

        Args:
            hwnd: 窗口句柄
            ctrl: 消息 ListItemControl 控件

        Returns:
            识别到的发送者昵称，识别失败返回空字符串
        """
        try:
            if hwnd:
                png_bytes = capture_control(hwnd, ctrl, offset_right=15, mode="print_window")
                img = Image.open(io.BytesIO(png_bytes))
            else:
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="_wxuia_sender_")
                os.close(tmp_fd)
                try:
                    ctrl.CaptureToImage(tmp_path)
                    img = Image.open(tmp_path)
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

            w, h = img.size
            if h <= 38 or w <= 0:
                return ""

            # 裁剪顶部 0-38px 区域（昵称显示区域）
            sender_area = img.crop((60, 0, w - 60, 38))

            # 计算图片 hash
            buf = io.BytesIO()
            sender_area.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            img_hash = hashlib.md5(img_bytes).hexdigest()

            # 命中缓存直接返回
            if img_hash in Chat._ocr_sender_cache:
                return Chat._ocr_sender_cache[img_hash]

            # OCR 识别
            ocr_result = self._get_image_text(img_bytes)

            if not ocr_result:
                Chat._ocr_sender_cache[img_hash] = ""
                return ""

            # 取第一个识别结果作为发送者昵称
            sender_name = next(iter(ocr_result), "").strip()
            Chat._ocr_sender_cache[img_hash] = sender_name
            return sender_name

        except Exception:
            return ""

    @staticmethod
    def _detect_sender(
        hwnd: int, ctrl: auto.Control, chat_name: str,
    ) -> Tuple[str, Source, tuple, tuple, tuple, tuple]:
        """
        判断消息发送者、来源类型，并检测气泡区域坐标和轮廓区域。

        通过截图后从左右两侧向内扫描非白色像素，判断头像在哪侧。

        Args:
            hwnd:      窗口句柄，用于 PrintWindow 截图
            ctrl:      消息 ListItemControl 控件
            chat_name: 当前聊天对象名称（用于标记对方消息的 sender）

        Returns:
            (sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect)
            bubble_rect 为气泡区域屏幕坐标 (left, top, right, bottom)，空元组表示未检测到
        """
        return Chat._detect_sender_by_pixel(ctrl, chat_name, hwnd)

    @staticmethod
    def _detect_sender_by_pixel(
        ctrl: auto.Control, chat_name: str, hwnd: int = 0,
    ) -> Tuple[str, Source, tuple, tuple, tuple, tuple]:
        """
        通过截图轮廓检测判断消息发送者。

        通过 headimg_rect 的位置推断发送者：
        - 头像 left 离图片左边的距离 < 头像 right 离图片右边的距离 → 对方发送
        - 反之 → 自己发送

        Returns:
            (sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect)
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
            return "", Source.UNKNOWN, (), (), (), ()

        w, h = img.size

        # ---- 轮廓检测：识别头像、昵称、消息内容区域 ----
        headimg_rect = ()
        nickname_rect = ()
        content_rect = ()

        try:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            contour_img_bytes, contour_rects = _find_contour_rects(
                img_bytes, threshold=5, min_area=100, border_margin=2,
            )
            headimg_rect, nickname_rect, content_rect = _classify_contour_rects(
                contour_rects, image_bytes=img_bytes,
            )
        except Exception:
            pass

        # ---- 通过 headimg_rect 推断发送者 ----
        sender = ""
        source = Source.UNKNOWN
        bubble_rect = ()

        if headimg_rect and w > 0:
            head_left = headimg_rect[0]
            head_right = headimg_rect[2]
            dist_to_left = head_left
            dist_to_right = w - head_right

            if dist_to_left < dist_to_right:
                # 头像靠左 → 对方发送
                sender = chat_name
                source = Source.OTHERS
            else:
                # 头像靠右 → 自己发送
                sender = "我"
                source = Source.SELF
        else:
            # 无法识别头像，回退到边缘扫描
            edge_result = Chat._detect_sender_by_edge_scan(img, w, h, chat_name)
            if edge_result is not None:
                sender, source, _, _, _ = edge_result

        # ---- 从 content_rect 推断 bubble_rect（屏幕坐标） ----
        if content_rect:
            try:
                ctrl_rect = ctrl.BoundingRectangle
                bubble_rect = (
                    content_rect[0] + ctrl_rect.left,
                    ctrl_rect.top,
                    content_rect[2] + ctrl_rect.left,
                    ctrl_rect.bottom,
                )
            except Exception:
                pass

        # # ---- 边缘扫描（已注释） ----
        # edge_result = Chat._detect_sender_by_edge_scan(img, w, h, chat_name)
        # edge_scan_y, edge_left_x, edge_right_x = -1, -1, -1
        # if edge_result is not None:
        #     sender, source, edge_scan_y, edge_left_x, edge_right_x = edge_result
        # else:
        #     sender, source = "", Source.UNKNOWN

        # # ---- 检测气泡区域（已注释） ----
        # bubble_left, bubble_right = Chat._detect_bubble_rect(img, w, h, source)
        # bubble_rect = ()
        # if bubble_left > 0 or bubble_right > 0:
        #     try:
        #         ctrl_rect = ctrl.BoundingRectangle
        #         bubble_rect = (
        #             bubble_left + ctrl_rect.left,
        #             ctrl_rect.top,
        #             bubble_right + ctrl_rect.left,
        #             ctrl_rect.bottom,
        #         )
        #     except Exception:
        #         pass

        return sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect

    @staticmethod
    def _detect_bubble_rect(
        img: Image.Image, w: int, h: int,
        source: Source,
    ) -> Tuple[int, int]:
        """
        检测气泡的左边缘和右边缘 x 坐标（相对于控件截图）。

        在 y=38、h*1/4、h*2/4、h*3/4 四个高度分别扫描，
        取左右距离最大的结果（气泡最宽处）。

        - 对方消息（OTHERS）：先从左侧扫描找气泡左边缘，再从右侧扫描找气泡右边缘
        - 自己消息（SELF）：先从右侧扫描找气泡右边缘，再从左侧扫描找气泡左边缘

        Returns:
            (bubble_left, bubble_right) 相对于控件的 x 坐标，(0, 0) 表示未检测到
        """
        if h <= 0:
            return 0, 0

        threshold = 3  # 连续非白色像素数
        skip_px = 65   # 跳过头像区域的像素

        # 多个扫描高度
        scan_ys = [40, h // 4, h // 2, h * 3 // 4]
        # 去重并过滤无效值
        scan_ys = list(dict.fromkeys(y for y in scan_ys if 0 < y < h))

        best_left = 0
        best_right = 0
        best_distance = 0

        for scan_y in scan_ys:
            def _scan_left_to_right(start: int, end: int, sy: int = scan_y) -> int:
                count = 0
                for x in range(start, end):
                    r, g, b = img.getpixel((x, sy))[:3]
                    if Chat._is_non_white(r, g, b):
                        count += 1
                        if count >= threshold:
                            return x - threshold + 1
                    else:
                        count = 0
                return 0

            def _scan_right_to_left(start: int, end: int, sy: int = scan_y) -> int:
                count = 0
                for x in range(start, end, -1):
                    r, g, b = img.getpixel((x, sy))[:3]
                    if Chat._is_non_white(r, g, b):
                        count += 1
                        if count >= threshold:
                            return x + threshold - 1
                    else:
                        count = 0
                return 0

            if source == Source.OTHERS:
                bubble_left = _scan_left_to_right(skip_px, w)
                bubble_right = _scan_right_to_left(w - 1 - skip_px, -1)
            elif source == Source.SELF:
                bubble_right = _scan_right_to_left(w - 1 - skip_px, -1)
                bubble_left = _scan_left_to_right(skip_px, w)
            else:
                continue

            # 取左右距离最大的结果
            if bubble_left > 0 and bubble_right > 0:
                distance = bubble_right - bubble_left
                if distance > best_distance:
                    best_distance = distance
                    best_left = bubble_left
                    best_right = bubble_right

        return best_left, best_right

    @staticmethod
    def _is_non_white(r: int, g: int, b: int) -> bool:
        """判断像素是否为非白色背景（排除纯白和接近纯白的背景色）"""
        return not (r > 245 and g > 245 and b > 245)

    @staticmethod
    def _detect_sender_by_edge_scan(
        img: Image.Image, w: int, h: int, chat_name: str,
    ) -> Optional[Tuple[str, Source, int, int, int]]:
        """
        从左右两侧同时向中间扫描，先找到非白色像素的一侧即为头像侧。

        Returns:
            (sender, source, scan_y, left_x, right_x) 或 None
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
                return chat_name, Source.OTHERS, scan_y, left_x, right_x
            elif (w - 1 - right) < left:
                return "我", Source.SELF, scan_y, left_x, right_x
            else:
                return None

        if found_left:
            return chat_name, Source.OTHERS, scan_y, left_x, right_x
        return "我", Source.SELF, scan_y, left_x, right_x

    @staticmethod
    def _detect_message_status(
        msg_cls: type[Message],
        raw_name: str,
        source: Source,
    ) -> Tuple[MessageStatus, str]:
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

        failed_kw = i_("发送失败")
        sending_kw = i_("发送中")

        # 文件消息优先检测换行分隔的前缀
        if msg_cls is FileMessage:
            for prefix, status in [
                (f"{failed_kw}\n", MessageStatus.FAILED),
                (f"{sending_kw}\n", MessageStatus.SENDING),
            ]:
                if raw_name.startswith(prefix):
                    return status, raw_name[len(prefix):]

        # 通用前缀检测（空格分隔）
        for prefix, status in [
            (f"{failed_kw} ", MessageStatus.FAILED),
            (f"{sending_kw} ", MessageStatus.SENDING),
        ]:
            if raw_name.startswith(prefix):
                return status, raw_name[len(prefix):]

        # 无前缀，根据发送者推断
        if source == Source.SELF:
            return MessageStatus.SENT, raw_name
        if source == Source.OTHERS:
            return MessageStatus.RECEIVED, raw_name
        return MessageStatus.UNKNOWN, raw_name

    @staticmethod
    def _build_message(
        msg_cls: type[Message],
        raw_name: str,
        sender: str,
        source: Source,
        runtime_id: tuple = (),
        bubble_rect: tuple = (),
        room: Optional[str] = None,
        chat: object = None,
        control: object = None,
        headimg_rect: tuple = (),
        nickname_rect: tuple = (),
        content_rect: tuple = (),
        ui_cls: str = "",
    ) -> Message:
        """根据消息子类构造具体消息对象，调用各子类的 parse 方法提取字段"""
        msg_status, actual_name = Chat._detect_message_status(
            msg_cls, raw_name, source,
        )

        base = dict(sender=sender, source=source,
                    raw_name=raw_name, ui_cls=ui_cls, status=msg_status,
                    runtime_id=runtime_id, bubble_rect=bubble_rect,
                    room=room, chat=chat, control=control,
                    headimg_rect=headimg_rect, nickname_rect=nickname_rect,
                    content_rect=content_rect)

        if msg_cls is VoiceMessage:
            content, duration, played = VoiceMessage.parse(actual_name)
            return VoiceMessage(**base, content=content, duration=duration, played=played)

        if msg_cls is FileMessage:
            content, file_name, file_size, file_status = FileMessage.parse(actual_name)
            return FileMessage(**base, content=content, file_name=file_name,
                               file_size=file_size, file_status=file_status)

        if msg_cls is LocationMessage:
            content, address = LocationMessage.parse(actual_name)
            return LocationMessage(**base, content=content, address=address)

        if msg_cls is LinkMessage:
            content, title, link_source = LinkMessage.parse(actual_name)
            return LinkMessage(**base, content=content, title=title, link_source=link_source)

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
            content, music_source, song_name, artist = MusicMessage.parse(actual_name)
            return MusicMessage(**base, content=content, music_source=music_source,
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
                Name=i_("清空聊天记录"),
            )
            if not clear_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'清空聊天记录'按钮")
            input_wx.click(clear_btn)
            time.sleep(0.5)

            # 3. 确认弹窗中点击"清空"
            confirm_btn = self._win.ButtonControl(
                Name=i_("清空"),
                ClassName="mmui::XOutlineButton",
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'清空'确认按钮")
            input_wx.click(confirm_btn)
            time.sleep(0.3)

            logger.debug(f"清空聊天记录成功: {self.chat_name}")

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
                raise WxControlNotFoundError("未找到群聊信息面板 (mmui::ChatRoomMemberInfoView)")

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

            if i_("清空聊天记录") not in ocr_data:
                raise RuntimeError(
                    "OCR 未识别到'清空聊天记录'文本，"
                    "请确认聊天信息面板已展开且已滚动到底部"
                )

            info = ocr_data[i_("清空聊天记录")]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1])
            auto.Click(click_x, click_y)
            time.sleep(0.5)

            # 5. 确认弹窗中点击"清空"
            confirm_btn = self._win.ButtonControl(
                Name=i_("清空"),
                ClassName="mmui::XOutlineButton",
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'清空'确认按钮")
            input_wx.click(confirm_btn)
            time.sleep(0.3)

            logger.debug(f"清空群聊聊天记录成功: {self.chat_name}")

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
                raise WxControlNotFoundError("未找到群聊信息面板 (mmui::ChatRoomMemberInfoView)")

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

            if i_("退出群聊") not in ocr_data:
                raise RuntimeError(
                    "OCR 未识别到'退出群聊'文本，"
                    "请确认聊天信息面板已展开且已滚动到底部"
                )

            info = ocr_data[i_("退出群聊")]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1])
            auto.Click(click_x, click_y)

            # 5. 确认弹窗中点击"确定"
            confirm_btn = self._win.ButtonControl(
                Name=i_("确定"),
                ClassName="mmui::XOutlineButton",
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'确定'确认按钮")
            input_wx.click(confirm_btn)
            logger.debug(f"退出群聊成功: {self.chat_name}")

        finally:
            # 退出群聊后面板可能已自动关闭，尝试收回
            self._close_chat_info_panel()

    @PIM.guard
    def add_room_members(self, members: List[str]) -> None:
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

            if i_("添加") not in ocr_data:
                raise OCRError("OCR 未识别到'添加'文本")

            info = ocr_data[i_("添加")]
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
                    raise WxControlNotFoundError("未找到搜索区域")
                search_edit = search_field.EditControl(
                    ClassName="mmui::XValidatorTextEdit", Name=i_("搜索"),
                    searchDepth=1,
                )
                if not search_edit.Exists(maxSearchSeconds=2):
                    raise WxControlNotFoundError("未找到搜索框")

                input_wx.click(search_edit)
                time.sleep(0.3)
                input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
                time.sleep(0.3)
                input_wx.paste_or_type(search_edit, nickname)
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
                    raise WxControlNotFoundError(f"未找到联系人: {nickname}")

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
                raise WxControlNotFoundError("未找到详情面板")
            confirm_btn = detail_view.ButtonControl(
                ClassName="mmui::XOutlineButton",
                AutomationId="confirm_btn",
                Name=i_("添加"),
                searchDepth=2,
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'添加'按钮")
            input_wx.click(confirm_btn)

            time.sleep(0.5)

            # 非好友会邀请失败
            if self._win.TextControl(Name=i_("未能邀请")).Exists(0, 0):
                input_wx.click(self._win.ButtonControl(Name=i_("我知道了")))

            # 等待操作窗口消失后再收起聊天信息面板
            for _ in range(30):
                check_picker = self._win.WindowControl(
                    ClassName="mmui::SessionPickerWindow",
                    searchDepth=1,
                )
                if not check_picker.Exists(maxSearchSeconds=1):
                    break
                time.sleep(1)

            logger.debug(f"添加群成员成功: {self.chat_name} -> {members}")

        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def remove_room_members(self, members: List[str]) -> None:
        """
        移除群成员。

        仅群聊可用。

        移除群成员窗口与添加群成员窗口的控件结构不同：
        - 搜索结果视图: mmui::SearchGroupMemberView（非 SearchContactNewChatView）
        - 搜索结果列表: mmui::XTableView, AutomationId="sp_search_list"
        - 搜索结果项: mmui::XTableCell (ListItemControl)
        - 确认按钮: Name=i_("移出")（非"完成"）

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

            if i_("移出") not in ocr_data:
                raise OCRError("OCR 未识别到'移出'文本")

            info = ocr_data[i_("移出")]
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
                    raise WxControlNotFoundError("未找到搜索区域")
                search_edit = search_field.EditControl(
                    ClassName="mmui::XValidatorTextEdit", Name=i_("搜索"),
                    searchDepth=1,
                )
                if not search_edit.Exists(maxSearchSeconds=2):
                    raise WxControlNotFoundError("未找到搜索框")

                input_wx.click(search_edit)
                time.sleep(0.3)
                input_wx.send_keys(search_edit, "{Ctrl}a{Del}")
                time.sleep(0.3)
                input_wx.paste_or_type(search_edit, nickname)
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
                    raise WxControlNotFoundError(f"未找到成员: {nickname}")

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
                raise WxControlNotFoundError("未找到详情面板")
            confirm_btn = detail_view.ButtonControl(
                ClassName="mmui::XOutlineButton",
                AutomationId="confirm_btn",
                Name=i_("移出"),
                searchDepth=2,
            )
            if not confirm_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'移出'按钮")
            input_wx.click(confirm_btn)
            time.sleep(0.5)

            # 确认弹窗中点击"确定"
            ok_btn = self._win.ButtonControl(
                Name=i_("确定"),
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

            logger.debug(f"移除群成员成功: {self.chat_name} -> {members}")

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
            raise WxControlNotFoundError("未找到群聊信息面板 (mmui::ChatRoomMemberInfoView)")

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
            logger.debug(f"{action}{switch_name}成功: {self.chat_name}")

        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def pin_room_chat(self) -> None:
        """置顶当前群聊会话（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("置顶聊天"), True)

    @PIM.guard
    def unpin_room_chat(self) -> None:
        """取消置顶当前群聊会话（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("置顶聊天"), False)

    @PIM.guard
    def mute_room_chat(self) -> None:
        """开启当前群聊的消息免打扰（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("消息免打扰"), True)

    @PIM.guard
    def unmute_room_chat(self) -> None:
        """关闭当前群聊的消息免打扰（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("消息免打扰"), False)

    @PIM.guard
    def add_room_address_book(self) -> None:
        """将当前群聊保存到通讯录（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("保存到通讯录"), True)

    @PIM.guard
    def remove_room_address_book(self) -> None:
        """将当前群聊从通讯录移除（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("保存到通讯录"), False)

    @PIM.guard
    def display_room_member_nickname(self) -> None:
        """显示群成员昵称（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("显示群成员昵称"), True)

    @PIM.guard
    def hidden_room_member_nickname(self) -> None:
        """隐藏群成员昵称（通过 OCR 识别开关）"""
        self._set_room_ocr_switch(i_("显示群成员昵称"), False)

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
            self._toggle_ocr_switch(img, ocr_data, hwnd, i_("消息免打扰"), True)

            # 开启消息免打扰后，"折叠该聊天"选项才会出现，重新截图
            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)
            img = Image.open(io.BytesIO(png_bytes))
            self._toggle_ocr_switch(img, ocr_data, hwnd, i_("折叠该聊天"), True)

            logger.debug(f"折叠群聊成功: {self.chat_name}")

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
            if i_("折叠该聊天") in ocr_data:
                self._toggle_ocr_switch(img, ocr_data, hwnd, i_("折叠该聊天"), False)

            logger.debug(f"取消折叠群聊成功: {self.chat_name}")

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

    def _toggle_ocr_switch(self, img: Image.Image, ocr_data: Dict[str, dict], hwnd: int,
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

            def _fresh_ocr() -> Tuple[bytes, dict, int, int]:
                """每次操作前重新截图 + OCR，确保坐标准确"""
                _png = capture_window(hwnd, mode="print_window")
                _ocr = self._get_image_text(_png)
                _left, _top, _, _ = win32gui.GetWindowRect(hwnd)
                return _png, _ocr, _left, _top

            # ---- 第一组：文本字段（每个字段操作前独立截图 OCR） ----

            # -- 群聊名称 --
            if name is not None:
                png_bytes, ocr_data, win_left, win_top = _fresh_ocr()
                if i_("群聊名称") not in ocr_data:
                    raise OCRError("OCR 未识别到'群聊名称'文本")
                info = ocr_data[i_("群聊名称")]
                click_x = int(win_left + info["center"][0])
                click_y = int(win_top + info["center"][1] + 1.5 * info["height"])
                auto.Click(click_x, click_y)
                time.sleep(0.2)
                input_wx.send_keys(self._win, "{Ctrl}a{Del}")
                time.sleep(0.1)
                input_wx.paste(name)
                input_wx.send_keys(self._win, "{Enter}")
                update_btn = self._win.ButtonControl(Name=i_("修改"))
                if update_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(update_btn)
                time.sleep(0.5)

            # -- 群公告 --
            if announcement is not None:
                png_bytes, ocr_data, win_left, win_top = _fresh_ocr()
                if i_("群公告") not in ocr_data:
                    raise OCRError("OCR 未识别到'群公告'文本")
                info = ocr_data[i_("群公告")]
                click_x = int(win_left + info["center"][0])
                click_y = int(win_top + info["center"][1] + 1.5 * info["height"])
                auto.Click(click_x, click_y)

                # 等待群公告窗口出现
                pane_title = f"“{self.chat_name}”的群公告"
                announcement_pane = auto.PaneControl(Name=pane_title)
                if not announcement_pane.Exists(maxSearchSeconds=3):
                    raise WxWindowNotFoundError("未找到群公告编辑窗口")

                pane_hwnd = announcement_pane.NativeWindowHandle
                if not pane_hwnd:
                    raise RuntimeError("无法获取群公告窗口句柄")
                pane_png = capture_window(pane_hwnd, mode="print_window")
                pane_ocr = self._get_image_text(pane_png)

                # 如果之前发布过群公告，需要先点击"编辑群公告"
                if i_("编辑群公告") in pane_ocr:
                    ei = pane_ocr[i_("编辑群公告")]
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
                if i_("完成") not in pane_ocr:
                    raise OCRError("OCR 未识别到'完成'按钮")
                fi = pane_ocr[i_("完成")]
                pane_left, pane_top, _, _ = win32gui.GetWindowRect(pane_hwnd)
                auto.Click(int(pane_left + fi["center"][0]),
                           int(pane_top + fi["center"][1]))
                time.sleep(0.5)

                publish_btn = announcement_pane.ButtonControl(Name=i_("发布"))
                if publish_btn.Exists(maxSearchSeconds=3):
                    # publish_btn.GetInvokePattern().Invoke()
                    input_wx.click(publish_btn)
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
                if i_("备注") not in ocr_data:
                    raise OCRError("OCR 未识别到'备注'文本")
                info = ocr_data[i_("备注")]
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
                for candidate in (i_("我在本群的昵称"), "我在本群的呢称"):
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
                update_btn = self._win.ButtonControl(Name=i_("修改"))
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
                    (i_("消息免打扰"), mute),
                    (i_("折叠该聊天"), fold),
                    (i_("置顶聊天"), pin),
                    (i_("保存到通讯录"), save_address_book),
                    (i_("显示群成员昵称"), display_member_nickname),
                ]:
                    if switch_val is None:
                        continue
                    png_bytes, ocr_data, _, _ = _fresh_ocr()
                    img = Image.open(io.BytesIO(png_bytes))
                    self._toggle_ocr_switch(
                        img, ocr_data, hwnd, switch_name, switch_val)

            logger.debug(f"设置群聊信息成功: {self.chat_name}")

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
            raise WxControlNotFoundError(f"未找到'{name}'开关")
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
                logger.debug(f"{action}{name}成功: {self.chat_name}")
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
            _, is_on = self._get_chat_info_switch(i_("消息免打扰"))
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
            mute_sw, mute_on = self._get_chat_info_switch(i_("消息免打扰"))
            if not mute_on:
                input_wx.click(mute_sw)
                time.sleep(0.5)

            # 设置折叠该聊天
            fold_sw, fold_on = self._get_chat_info_switch("折叠该聊天")
            if not fold_on:
                input_wx.click(fold_sw)
                time.sleep(0.3)
                logger.debug(f"折叠聊天成功: {self.chat_name}")
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
                Name=i_("折叠该聊天"),
            )
            if fold_sw.Exists(maxSearchSeconds=2):
                toggle = fold_sw.GetTogglePattern()
                if toggle and toggle.ToggleState == 1:
                    input_wx.click(fold_sw)
                    time.sleep(0.3)
                    logger.debug(f"取消折叠聊天成功: {self.chat_name}")
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
            raise WxControlNotFoundError(f"未找到'{item_name}'按钮")
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
                raise WxAutoError("无法获取微信窗口句柄")

            png_bytes = capture_window(hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)

            if i_("群聊名称") not in ocr_data:
                raise OCRError("OCR 未识别到'群聊名称'文本，请确认聊天信息面板已展开")

            info = ocr_data[i_("群聊名称")]
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
            update_bth = self._win.ButtonControl(Name=i_("修改"))
            input_wx.click(update_bth)
            logger.debug(f"设置群聊名称成功: {name}")

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
            if i_("群公告") not in ocr_data:
                raise OCRError("OCR 未识别到'%s'文本，请确认聊天信息面板已展开" % i_("群公告"))
            info = ocr_data[i_("群公告")]
            win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
            click_x = int(win_left + info["center"][0])
            click_y = int(win_top + info["center"][1] + info["height"])
            auto.Click(click_x, click_y)

            # 判断群公告窗口是否出现
            pane_title = f"“{self.chat_name}”的群公告"
            announcement_pane = auto.PaneControl(Name=pane_title)
            if not announcement_pane.Exists(maxSearchSeconds=3):
                raise WxWindowNotFoundError("未找到群公告编辑窗口")

            # 识别群公告编辑窗口
            pane_hwnd = announcement_pane.NativeWindowHandle
            if not pane_hwnd:
                raise RuntimeError("无法获取群公告窗口句柄")
            png_bytes = capture_window(pane_hwnd, mode="print_window")
            ocr_data = self._get_image_text(png_bytes)
            if not ocr_data:
                raise OCRError("群公告窗口 OCR 未识别到任何文本")

            # 如果之前发布过群公告，需要先点击"编辑群公告"
            if i_("编辑群公告") in ocr_data:
                info = ocr_data[i_("编辑群公告")]
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
            if i_("完成") not in ocr_data:
                raise OCRError(f"OCR 未识别到'完成'按钮，识别到的文本: {list(ocr_data.keys())}")
            info = ocr_data[i_("完成")]
            pane_left, pane_top, _, _ = win32gui.GetWindowRect(pane_hwnd)
            click_x = int(pane_left + info["center"][0])
            click_y = int(pane_top + info["center"][1])
            auto.Click(click_x, click_y)
            time.sleep(0.5)

            # 点击"发布"按钮（WebView 内的按钮，支持 InvokePattern）
            publish_btn = announcement_pane.ButtonControl(Name=i_("发布"))
            if not publish_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'%s'按钮" % i_("发布"))

            input_wx.click(publish_btn)

            time.sleep(1)

            for i in range(10):
                if not get_hwnd(pane_title):
                    logger.debug(f"设置群公告成功: {self.chat_name}")
                    return
                time.sleep(3)

            logger.debug(f"设置群公告失败: {self.chat_name}")
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

            if i_("备注") not in ocr_data:
                raise OCRError("OCR 未识别到'备注'文本，请确认聊天信息面板已展开")

            info = ocr_data[i_("备注")]
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

            logger.debug(f"设置群聊备注成功: {self.chat_name} -> {remark}")

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
            for candidate in (i_("我在本群的昵称"), "我在本群的呢称"):
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
            update_btn = self._win.ButtonControl(Name=i_("修改"))
            input_wx.click(update_btn)

            logger.debug(f"设置群内昵称成功: {self.chat_name} -> {nickname}")

        finally:
            self._close_chat_info_panel()

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
            raise WxControlNotFoundError(f"未找到'{menu_name}'菜单项")
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
                Name=i_("聊天信息"),
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
                "tags": List[str],
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
                raise WxControlNotFoundError("未找到联系人资料面板")

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

            logger.debug(f"获取联系人资料成功: {self.chat_name}")
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
            self._click_profile_menu_item(i_("设置备注和标签"))

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'%s'弹窗" % i_("设置备注和标签"))

            # ---- 1. 备注 ----
            if remark is not None:
                remark_edit = remark_pop.EditControl(
                    ClassName="mmui::XLineEdit",
                    Name=i_("修改备注名"),
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
                    Name=i_("修改标签"), AutomationId="button",
                )
                if tag_btn.Exists(maxSearchSeconds=2):
                    existing_labels = set()
                    tag_text = tag_btn.TextControl(ClassName="mmui::XTextView")
                    if tag_text.Exists(0, 0):
                        name = tag_text.Name
                        if name and name != i_("搜索或创建标签..."):
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
                                ClassName="mmui::XValidatorTextEdit", Name=i_("搜索"),
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
                            Name=i_("设置备注和标签"),
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
                        if not name or name == i_("填写电话"):
                            break
                        separator_view = phone_field.GetParentControl()
                        if separator_view:
                            num_view = separator_view.GetParentControl()
                            if num_view:
                                del_btn = num_view.ButtonControl(Name=i_("删除电话"))
                                if del_btn.Exists(0, 0):
                                    input_wx.click(del_btn)
                                    continue
                        break

                    for phone in phones:
                        empty_field = phone_area.TextControl(
                            ClassName="mmui::XLineField", Name=i_("填写电话"),
                        )
                        if not empty_field.Exists(0, 0):
                            add_btn = phone_area.ButtonControl(
                                Name=i_("添加电话"), AutomationId="button",
                            )
                            if add_btn.Exists(maxSearchSeconds=1):
                                input_wx.click(add_btn)

                        empty_field = phone_area.TextControl(
                            ClassName="mmui::XLineField", Name=i_("填写电话"),
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
                    ClassName="mmui::XValidatorTextEdit", Name=i_("修改描述"),
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
                            Name=i_("描述图片"),
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
                            ClassName="mmui::XMenuView", Name=i_("删除"),
                        )
                        if not del_item.Exists(maxSearchSeconds=1):
                            input_wx.send_keys(self._win, "{Esc}")
                            break
                        input_wx.click(del_item)

                for img_path in images:
                    add_img_btn = remark_pop.GroupControl(
                        Name=i_("添加图片"),
                        AutomationId="desc_img_list_view_.add_button_view",
                    )
                    if not add_img_btn.Exists(maxSearchSeconds=2):
                        break
                    input_wx.click(add_img_btn)
                    dlg = auto.WindowControl(ClassName="#32770", ProcessId=self.wx.pid)
                    if not dlg.Exists(maxSearchSeconds=5):
                        break
                    input_wx.send_keys(dlg, "{Alt}N")
                    edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
                    if not edit.Exists(0, 0):
                        edit = dlg.EditControl(AutomationId="1148")
                    if edit.Exists(maxSearchSeconds=2):
                        # edit.GetValuePattern().SetValue(os.path.abspath(img_path))
                        input_wx.send_keys(edit, os.path.abspath(img_path))
                        input_wx.send_keys(dlg, "{Alt}O")
                        time.sleep(0.5)

            # ---- 点击"完成"保存 ----
            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton", Name=i_("完成"),
            )
            if ok_btn.Exists(maxSearchSeconds=2):
                input_wx.click(ok_btn)

            logger.debug(f"设置联系人信息成功: {self.chat_name}")

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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

            remark_edit = remark_pop.EditControl(
                ClassName="mmui::XLineEdit",
                Name=i_("修改备注名"),
            )
            if not remark_edit.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'修改备注名'编辑框")

            input_wx.click(remark_edit)
            time.sleep(0.2)
            input_wx.send_keys(remark_edit, "{Ctrl}a{Del}")
            time.sleep(0.1)

            input_wx.paste(remark)
            time.sleep(0.3)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name=i_("完成"),
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("未找到'完成'按钮")
            input_wx.click(ok_btn)
            time.sleep(0.3)

            logger.debug(f"设置备注成功: {self.chat_name} -> {remark}")

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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

            existing_labels = set()
            tag_btn = remark_pop.ButtonControl(
                Name=i_("修改标签"),
                AutomationId="button",
            )
            if not tag_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'修改标签'按钮")

            tag_text = tag_btn.TextControl(
                ClassName="mmui::XTextView",
            )
            if tag_text.Exists(maxSearchSeconds=1):
                name = tag_text.Name
                if name and name != i_("搜索或创建标签..."):
                    existing_labels = {t.strip() for t in name.split(",") if t.strip()}

            new_labels = [l for l in labels if l not in existing_labels]
            if not new_labels:
                logger.debug(f"所有标签已存在，跳过: {self.chat_name} -> {labels}")
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            input_wx.click(tag_btn)
            time.sleep(0.3)

            for label in new_labels:
                tag_edit = remark_pop.EditControl(
                    ClassName="mmui::XValidatorTextEdit",
                    Name=i_("搜索"),
                )
                if not tag_edit.Exists(maxSearchSeconds=3):
                    raise WxControlNotFoundError("未找到标签搜索输入框")

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
                    logger.debug(f"搜索结果中未找到标签，跳过: {label}")

                input_wx.send_keys(tag_edit, "{Ctrl}a{Del}")
                time.sleep(0.2)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name=i_("完成"),
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.debug(f"添加标签成功: {self.chat_name} -> {labels}")

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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

            existing_labels = set()
            tag_btn = remark_pop.ButtonControl(
                Name=i_("修改标签"),
                AutomationId="button",
            )
            if not tag_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'修改标签'按钮")

            tag_text = tag_btn.TextControl(
                ClassName="mmui::XTextView",
            )
            if tag_text.Exists(maxSearchSeconds=1):
                name = tag_text.Name
                if name and name != i_("搜索或创建标签..."):
                    existing_labels = {t.strip() for t in name.split(",") if t.strip()}

            to_remove = [l for l in labels if l in existing_labels]
            if not to_remove:
                logger.debug(f"标签均不存在，跳过: {self.chat_name} -> {labels}")
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
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
                Name=i_("完成"),
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.debug(f"移除标签成功: {self.chat_name} -> {labels}")

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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

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
                logger.debug(f"所有电话号码已存在，跳过: {self.chat_name} -> {phones}")
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            for phone in new_phones:
                empty_field = phone_area.TextControl(
                    ClassName="mmui::XLineField",
                    Name=i_("填写电话"),
                )
                if not empty_field.Exists(0, 0):
                    add_btn = phone_area.ButtonControl(
                        Name=i_("添加电话"),
                        AutomationId="button",
                    )
                    if not add_btn.Exists(maxSearchSeconds=2):
                        raise WxControlNotFoundError("未找到'添加电话'按钮")
                    input_wx.click(add_btn)
                    time.sleep(0.3)

                empty_field = phone_area.TextControl(
                    ClassName="mmui::XLineField",
                    Name=i_("填写电话"),
                )
                if not empty_field.Exists(maxSearchSeconds=2):
                    raise WxControlNotFoundError("未找到空的电话号码输入框")

                phone_edit = empty_field.EditControl(
                    ClassName="mmui::XLineEdit",
                )
                if not phone_edit.Exists(maxSearchSeconds=2):
                    raise WxControlNotFoundError("未找到电话号码编辑框")

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
                Name=i_("完成"),
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.debug(f"添加电话号码成功: {self.chat_name} -> {phones}")

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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

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
                    Name=i_("添加图片"),
                    AutomationId="desc_img_list_view_.add_button_view",
                )
                if not add_img_btn.Exists(maxSearchSeconds=2):
                    raise WxControlNotFoundError("未找到'添加图片'按钮")

                input_wx.click(add_img_btn)
                time.sleep(1)

                dlg = auto.WindowControl(ClassName="#32770", ProcessId=self.wx.pid)
                if not dlg.Exists(maxSearchSeconds=5):
                    raise RuntimeError("文件选择对话框未弹出")

                input_wx.send_keys(dlg, "{Alt}N")
                time.sleep(0.3)
                edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
                if not edit.Exists(0, 0):
                    edit = dlg.EditControl(AutomationId="1148")
                if not edit.Exists(maxSearchSeconds=2):
                    raise WxControlNotFoundError("未找到文件名输入框")

                abs_path = os.path.abspath(img_path)
                # edit.GetValuePattern().SetValue(abs_path)
                input_wx.paste_or_type(edit, abs_path)
                time.sleep(0.3)

                input_wx.send_keys(dlg, "{Alt}O")
                time.sleep(1)

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name=i_("完成"),
            )
            if not ok_btn.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("未找到'完成'按钮")
            input_wx.click(ok_btn)
            time.sleep(0.3)

            logger.debug(f"添加备注图片成功: {self.chat_name} -> {images}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def remove_contact_phone(self, phones: List[str]) -> None:
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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

            phone_area = remark_pop.GroupControl(
                ClassName="mmui::ProfileFormPhoneView",
            )
            if not phone_area.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("未找到电话区域")

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
                logger.debug(f"电话号码均不存在，跳过: {self.chat_name} -> {phones}")
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
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
                            del_btn = num_view.ButtonControl(Name=i_("删除电话"))
                            if del_btn.Exists(maxSearchSeconds=1):
                                input_wx.click(del_btn)
                                time.sleep(0.3)
                            else:
                                logger.warning(f"未找到删除按钮: {phone}")
                else:
                    logger.warning(f"未找到电话号码项: {phone}")

            ok_btn = remark_pop.ButtonControl(
                ClassName="mmui::XOutlineButton",
                Name=i_("完成"),
            )
            input_wx.click(ok_btn)
            time.sleep(0.3)
            logger.debug(f"移除电话号码成功: {self.chat_name} -> {phones}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def remove_contact_image(self, indexes: List[int]) -> None:
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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

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
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == i_("描述图片"):
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
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
                    Name=i_("删除"),
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
                    Name=i_("完成"),
                )
                if ok_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(ok_btn)
                    time.sleep(0.3)
                logger.debug(f"删除备注图片成功: {self.chat_name} -> 删除{deleted}张")
            else:
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_contact_star(self) -> None:
        """将当前私聊联系人设为星标朋友，已是星标则跳过"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_more_button()
            time.sleep(0.3)

            # 发现"不再设为星标朋友"说明已是星标
            unstar_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("不再设为星标朋友"),
            )
            if unstar_item.Exists(0, 0):
                input_wx.send_keys(self._win, "{Esc}")
                logger.debug(f"已是星标朋友，跳过: {self.chat_name}")
                return

            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("设为星标朋友"),
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                input_wx.send_keys(self._win, "{Esc}")
                raise WxControlNotFoundError("未找到'设为星标朋友'菜单项")
            input_wx.click(menu_item)
            time.sleep(0.3)
            logger.debug(f"设为星标朋友成功: {self.chat_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def cancel_contact_star(self) -> None:
        """取消当前私聊联系人的星标朋友，非星标则跳过"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_more_button()
            time.sleep(0.3)

            # 发现"设为星标朋友"说明当前不是星标
            star_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("设为星标朋友"),
            )
            if star_item.Exists(0, 0):
                input_wx.send_keys(self._win, "{Esc}")
                logger.debug(f"非星标朋友，跳过: {self.chat_name}")
                return

            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("不再设为星标朋友"),
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                input_wx.send_keys(self._win, "{Esc}")
                raise WxControlNotFoundError("未找到'不再设为星标朋友'菜单项")
            input_wx.click(menu_item)
            time.sleep(0.3)
            logger.debug(f"取消星标朋友成功: {self.chat_name}")
        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def black_contact(self) -> None:
        """将当前私聊联系人加入黑名单，已在黑名单中则跳过"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_more_button()
            time.sleep(0.3)

            # 检查菜单中是否有"移出黑名单"（说明已在黑名单中）
            unblack_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("移出黑名单"),
            )
            if unblack_item.Exists(0, 0):
                input_wx.send_keys(self._win, "{Esc}")
                logger.debug(f"已在黑名单中，跳过: {self.chat_name}")
                return

            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("加入黑名单"),
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                input_wx.send_keys(self._win, "{Esc}")
                raise WxControlNotFoundError("未找到'加入黑名单'菜单项")
            input_wx.click(menu_item)
            time.sleep(0.5)

            confirm_btn = self._win.ButtonControl(Name=i_("确定"))
            if confirm_btn.Exists(maxSearchSeconds=3):
                input_wx.click(confirm_btn)
                time.sleep(0.3)
                logger.debug(f"加入黑名单成功: {self.chat_name}")
            else:
                logger.warning(f"未找到确认按钮，加入黑名单可能未完成: {self.chat_name}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def unblack_contact(self) -> None:
        """将当前私聊联系人移出黑名单，不在黑名单中则跳过"""
        self._activate_window()
        try:
            self._open_contact_profile()
            self._click_profile_more_button()
            time.sleep(0.3)

            # 检查菜单中是否有"加入黑名单"（说明不在黑名单中）
            black_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("加入黑名单"),
            )
            if black_item.Exists(0, 0):
                input_wx.send_keys(self._win, "{Esc}")
                logger.debug(f"不在黑名单中，跳过: {self.chat_name}")
                return

            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView", Name=i_("移出黑名单"),
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                input_wx.send_keys(self._win, "{Esc}")
                raise WxControlNotFoundError("未找到'移出黑名单'菜单项")
            input_wx.click(menu_item)
            time.sleep(0.3)
            logger.debug(f"移出黑名单成功: {self.chat_name}")
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
            self._click_profile_menu_item(i_("删除联系人"))
            time.sleep(0.5)

            confirm_btn = self._win.ButtonControl(Name=i_("删除"))
            if confirm_btn.Exists(maxSearchSeconds=3):
                input_wx.click(confirm_btn)
                time.sleep(0.3)
                logger.debug(f"删除联系人成功: {self.chat_name}")
            else:
                logger.warning(f"未找到'删除'确认按钮，删除联系人可能未完成: {self.chat_name}")

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
            self._click_profile_menu_item(i_("设置朋友权限"))
            time.sleep(0.5)

            perm_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("朋友权限"),
            )
            if not perm_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'朋友权限'弹窗")

            result = {
                "permission": "all",
                "hide_my_posts": False,
                "hide_their_posts": False,
            }

            chatonly_item = perm_pop.GroupControl(
                ClassName="mmui::ProfileFormPermissionItemUi",
                Name=i_("仅聊天"),
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
                    Name=i_("不让他（她）看"),
                )
                if hide_my.Exists(maxSearchSeconds=1):
                    toggle = hide_my.GetTogglePattern()
                    if toggle:
                        result["hide_my_posts"] = toggle.ToggleState == 1

                hide_their = perm_pop.CheckBoxControl(
                    ClassName="mmui::XSwitchButton",
                    Name=i_("不看他（她）"),
                )
                if hide_their.Exists(maxSearchSeconds=1):
                    toggle = hide_their.GetTogglePattern()
                    if toggle:
                        result["hide_their_posts"] = toggle.ToggleState == 1

            cancel_btn = perm_pop.ButtonControl(Name=i_("取消"))
            if cancel_btn.Exists(maxSearchSeconds=1):
                input_wx.click(cancel_btn)
            time.sleep(0.3)

            logger.debug(f"获取朋友权限成功: {self.chat_name} -> {result}")
            return result

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def set_friend_permission(self, permission: Literal["all", "chatonly"] = "all",
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
            self._click_profile_menu_item(i_("设置朋友权限"))
            time.sleep(0.5)

            perm_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("朋友权限"),
            )
            if not perm_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'朋友权限'弹窗")

            changed = False

            target_name = i_("仅聊天") if permission == "chatonly" else i_("聊天、朋友圈、微信运动等")
            target_item = perm_pop.GroupControl(
                ClassName="mmui::ProfileFormPermissionItemUi",
                Name=target_name,
            )
            if not target_item.Exists(maxSearchSeconds=1):
                raise WxControlNotFoundError(f"未找到权限选项: {target_name}")

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
                    Name=i_("不让他（她）看"),
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
                    Name=i_("不看他（她）"),
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
                    Name=i_("完成"),
                )
                if ok_btn.Exists(maxSearchSeconds=2):
                    input_wx.click(ok_btn)
                    time.sleep(0.3)
            else:
                cancel_btn = perm_pop.ButtonControl(Name=i_("取消"))
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                    time.sleep(0.2)

            logger.debug(f"设置朋友权限成功: {self.chat_name} -> permission={permission}, "
                        f"hide_my={hide_my_posts}, hide_their={hide_their_posts}")

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def collect_contact_image(self, indexes: List[int]) -> int:
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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

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
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return 0

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == i_("描述图片"):
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
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
                    Name=i_("收藏"),
                )
                if not collect_item.Exists(maxSearchSeconds=1):
                    input_wx.send_keys(self._win, "{Esc}")
                    logger.warning(f"右键菜单中未找到'收藏'，跳过第{idx}张")
                    continue

                input_wx.click(collect_item)
                time.sleep(0.5)
                collected += 1

            # 收藏不修改数据，点"取消"关闭弹窗
            cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
            if cancel_btn.Exists(maxSearchSeconds=1):
                input_wx.click(cancel_btn)

            logger.debug(f"收藏备注图片成功: {self.chat_name} -> 收藏{collected}张")
            return collected

        except Exception:
            self._cleanup_profile()
            raise
        finally:
            self._close_chat_info_panel()

    @PIM.guard
    def save_contact_image(self, indexes: List[int], save_path: str) -> int:
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
            self._click_profile_menu_item(i_("设置备注和标签"))
            time.sleep(0.5)

            remark_pop = self._win.WindowControl(
                ClassName="mmui::ProfileUniquePop",
                Name=i_("设置备注和标签"),
            )
            if not remark_pop.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'设置备注和标签'弹窗")

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
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
                if cancel_btn.Exists(maxSearchSeconds=1):
                    input_wx.click(cancel_btn)
                return 0

            # 收集所有图片项
            img_items = []
            for child in img_list.GetChildren():
                if child.Name == i_("描述图片"):
                    img_items.append(child)

            if not img_items:
                cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
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
                    Name=i_("另存为..."),
                )
                if not save_item.Exists(maxSearchSeconds=1):
                    input_wx.send_keys(self._win, "{Esc}")
                    continue

                input_wx.click(save_item)
                time.sleep(1)

                # 等待系统文件保存对话框
                dlg = remark_pop.WindowControl(ClassName="#32770")
                if not dlg.Exists(maxSearchSeconds=5):
                    dlg = auto.WindowControl(ClassName="#32770", ProcessId=self.wx.pid)
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
            cancel_btn = remark_pop.ButtonControl(Name=i_("取消"))
            if cancel_btn.Exists(maxSearchSeconds=1):
                input_wx.click(cancel_btn)

            logger.debug(f"保存备注图片成功: {self.chat_name} -> {save_dir} ({saved}张)")
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

    def __init__(self, wx: Optional[Weixin], contact_name: str):
        """
        初始化独立聊天窗口。

        Args:
            wx: Weixin 实例，可为 None（仅用于独立操作时）。
            contact_name: 联系人或群聊名称（即窗口标题）。

        Raises:
            ValueError: contact_name 为空时抛出。
            RuntimeError: 独立聊天窗口未找到时抛出。
        """
        if not contact_name:
            raise ValueError("contact_name 不能为空")

        self.wx = wx
        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            Name=contact_name,
            ProcessId=self.wx.pid,
            searchDepth=1
        )
        if not self.exists:
            # UIA 搜索失败时，通过 get_hwnd 按标题和 PID 查找
            found_hwnd = get_hwnd(contact_name, pid=self.wx.pid)
            if found_hwnd:
                self._win = auto.ControlFromHandle(found_hwnd)
                if self._win is None or not self._win.Exists(0, 0):
                    raise WxWindowNotFoundError(f"独立聊天窗口未找到: {contact_name}")
            else:
                raise WxWindowNotFoundError(f"独立聊天窗口未找到: {contact_name}")

        # 如果关联的 Weixin 启用了 resize，调整聊天窗口大小
        if wx and wx.resize:
            hwnd = self._win.NativeWindowHandle
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                x, y = rect[0], rect[1]
                ctypes.windll.user32.MoveWindow(
                    hwnd, x, y,
                    wx.CHAT_WINDOW_WIDTH, wx.CHAT_WINDOW_HEIGHT, True
                )

        self._scan_paused: bool = False  # 监听线程暂停标志

    def _activate_window(self) -> None:
        """激活独立聊天窗口（覆盖 Chat 的主窗口激活）"""
        if background:
            return
        # 最小化的窗口需要先还原才能激活
        if self.is_minimized:
            self.restore()

        self._window.SetActive()
        self._window.SetFocus()

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "SeparateChat(closed)"
        return (f"SeparateChat(pid={self.wx.pid}, chat_type={self.chat_type!r}, "
                f"name={self.chat_name!r})")

    def __repr__(self) -> str:
        return self.__str__()


class MomentItem:
    """朋友圈动态条目"""

    def __init__(self, moment: Moment, runtime_id: tuple, *,
                 type: str = "", sender: str = "", content: str = "",
                 raw_text: str = "", timestamp: str = "", image_count: int = 0,
                 cell_type: str = "", scroll_offset: int = 0):
        """
        初始化朋友圈动态条目。

        Args:
            moment: 关联的 Moment 实例。
            runtime_id: UI Automation RuntimeId。
            type: 动态类型（如 "文本"、"图片"、"视频"、"分享"）。
            sender: 发送者昵称。
            content: 正文内容。
            raw_text: 原始 Name 属性文本。
            timestamp: 时间戳文本。
            image_count: 图片数量。
            cell_type: 控件 ClassName。
            scroll_offset: 该动态在列表中的累计滚动偏移（像素）。
        """
        self.moment = moment
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
        self.moment._ensure_ready()
        ctrl = self._find_cell()
        if not ctrl:
            raise WxControlNotFoundError(f"未找到朋友圈动态: {self.sender}")
        self._scroll_into_view(ctrl)

        win = self.moment._win
        if not self._open_action_bar(ctrl):
            return False

        # 已点赞时显示"取消"，未点赞时显示"赞"
        # 先检查是否已点赞（"取消"按钮），避免重复点赞
        for cls in ("mmui::XTextView", "mmui::XButton"):
            cancel_btn = win.Control(Name=i_("取消"), ClassName=cls)
            if cancel_btn.Exists(0, 0):
                # 已点赞，关闭操作栏
                input_wx.send_keys(None, "{Esc}")
                time.sleep(0.2)
                return True

        # 未点赞，点击"赞"
        btn = win.TextControl(Name=i_("赞"), ClassName="mmui::XTextView")
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
        self.moment._ensure_ready()
        ctrl = self._find_cell()
        if not ctrl:
            raise WxControlNotFoundError(f"未找到朋友圈动态: {self.sender}")
        self._scroll_into_view(ctrl)

        win = self.moment._win
        if not self._open_action_bar(ctrl):
            return False

        # 检查是否已点赞（"取消"按钮）
        for cls in ("mmui::XTextView", "mmui::XButton"):
            cancel_btn = win.Control(Name=i_("取消"), ClassName=cls)
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

        self.moment._ensure_ready()
        ctrl = self._find_cell()
        if not ctrl:
            raise WxControlNotFoundError(f"未找到朋友圈动态: {self.sender}")
        self._scroll_into_view(ctrl)

        if not self._click_action_button(ctrl, "评论"):
            raise RuntimeError("未能打开评论输入框")

        input_wx.paste(content)
        time.sleep(0.5)

        # 当前动态的下一个兄弟控件就是其评论区
        comment_cell = ctrl.GetNextSiblingControl()
        if (not comment_cell
                or comment_cell.ClassName != "mmui::TimelineCommentCell"):
            raise WxControlNotFoundError("未找到当前动态的评论区控件")

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
        self.moment._ensure_ready()
        ctrl = self._find_cell()
        if not ctrl:
            raise WxControlNotFoundError(f"未找到朋友圈动态: {self.sender}")
        return self._scroll_into_view(ctrl)

    def _find_cell(self) -> Optional[auto.Control]:
        """
        在朋友圈列表中查找此条动态的控件。

        利用 scroll_offset（前面所有朋友圈高度累加）快速定位：
        1. 先在当前可见区域查找（命中直接返回）
        2. 点击"刷新"回到列表顶部
        3. 边滚动边匹配：每滚一小段就检查可见区域，命中立即返回
        """
        lc = self.moment._find_sns_list()

        def _match_in_visible():
            for ctrl, _ in auto.WalkControl(lc):
                if ctrl.ControlType != auto.ControlType.ListItemControl:
                    continue
                cls_name = ctrl.ClassName or ""
                if not cls_name.startswith(Moment.TIMELINE_CELL_PREFIX):
                    continue
                if cls_name in Moment.SKIP_CELL_CLASSES:
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
        refresh_btn = self.moment._win.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name=i_("刷新"),
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

    def _scroll_into_view(self, ctrl: auto.Control) -> bool:
        """将控件滚动到朋友圈列表可见区域内"""
        lc = self.moment._find_sns_list()
        list_rect = lc.BoundingRectangle
        for _ in range(30):
            ctrl_rect = ctrl.BoundingRectangle
            if ctrl_rect.bottom <= list_rect.bottom - 10:
                return True
            lc.WheelDown(wheelTimes=3)
            time.sleep(0.3)
        return False

    def _open_action_bar(self, ctrl: auto.Control) -> bool:
        """
        触发朋友圈动态的操作栏（赞/评论按钮）。

        从动态右下角逐步向左移动鼠标并点击，直到操作栏出现。
        """
        win = self.moment._win
        distance = 30
        while distance < 200:
            ctrl_rect = ctrl.BoundingRectangle
            auto.MoveTo(ctrl_rect.right - distance, ctrl_rect.bottom - 5)
            time.sleep(0.1)
            auto.Click(ctrl_rect.right - distance, ctrl_rect.bottom - 5)
            time.sleep(0.3)

            # 检查操作栏是否出现
            if (win.TextControl(Name=i_("赞"), ClassName="mmui::XTextView").Exists(0, 0)
                    or win.TextControl(Name=i_("评论"), ClassName="mmui::XTextView").Exists(0, 0)
                    or win.Control(Name=i_("取消"), ClassName="mmui::XTextView").Exists(0, 0)
                    or win.Control(Name=i_("取消"), ClassName="mmui::XButton").Exists(0, 0)):
                return True

            distance += 20
        return False

    def _click_action_button(self, ctrl: auto.Control, button_name: str) -> bool:
        """触发操作栏后点击指定按钮（用于评论等）"""
        win = self.moment._win
        if not self._open_action_bar(ctrl):
            return False

        btn = win.TextControl(Name=button_name, ClassName="mmui::XTextView")
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.3)
            return True
        return False

    def __repr__(self) -> str:
        return (f"MomentItem(type={self.type!r}, sender={self.sender!r}, "
                f"content={self.content!r}, timestamp={self.timestamp!r})")

    def __str__(self) -> str:
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


class Moment(WeixinWindow):
    """
    朋友圈（Moment）操作类。

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

    # ---- 发布相关常量 ----
    PUBLISH_PANEL_CLASS = "mmui::SnsPublishPanel"
    PUBLISH_PANEL_ID = "SnsPublishPanel"
    PUBLISH_INPUT_CLASS = "mmui::XValidatorTextEdit"
    PUBLISH_BTN_CLASS = "mmui::XOutlineButton"
    TOOLBAR_CLASS = "mmui::SNSWindowToolBar"
    TOOLBAR_ID = "sns_window_tool_bar"

    # ---- 隐私设置相关常量 ----
    PRIVACY_BTN_CLASS = "mmui::PublishPrivacyView"
    PRIVACY_SELECTION_CLASS = "mmui::PublishPrivacySelection"

    def __init__(self, wx: Weixin):
        """
        初始化朋友圈操作实例。

        Args:
            wx: Weixin 实例。
        """
        self.wx = wx
        self._win = auto.WindowControl(
            ClassName=self.SNS_WINDOW_CLASS,
            AutomationId=self.SNS_WINDOW_ID,
            ProcessId=self.wx.pid,
            searchDepth=1
        )

    def _ensure_ready(self) -> None:
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
        self.wx.navigator.switch_to(i_("朋友圈"))

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
            raise WxControlNotFoundError("未找到朋友圈列表控件 (sns_list)")
        return lc

    def _parse_moment_name(self, runtime_id: tuple, raw_name: str,
                           cls_name: str = "", scroll_offset: int = 0) -> Optional[MomentItem]:
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

    def _collect_moments(self, lc: auto.ListControl) -> List[Tuple[str, str, tuple, int]]:
        """
        收集当前可见的动态条目的 (raw_name, cls_name, runtime_id, ctrl_height) 列表。
        跳过评论区、辅助行等非动态 Cell。
        ctrl_height 为控件的高度（像素），用于累加计算滚动偏移。
        """
        items: List[Tuple[str, str, tuple, int]] = []
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
    def get_moments(self, count: int = 10, position: Literal["top", "current"] = "top") -> List[MomentItem]:
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
        self._ensure_ready()

        if position == "top":
            refresh_btn = self._win.ButtonControl(
                ClassName="mmui::XTabBarItem",
                Name=i_("刷新"),
            )
            if refresh_btn.Exists(maxSearchSeconds=2):
                input_wx.click(refresh_btn)
                time.sleep(2)

        lc = self._find_sns_list()

        moments: List[MomentItem] = []
        seen_keys: Set[tuple] = set()  # (runtime_id, raw_text) 组合去重
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
    def iter_moments(self, count: int = 10, position: Literal["top", "current"] = "top"):
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

            for item in wx.moment.iter_moments(10):
                print(item)
                wx.moment.like(item)
        """
        # 手动执行 guard 等待（替代 @PIM.guard）
        if PIM._running and PIM.idle_wait > 0:
            PIM.wait_for_idle(PIM.idle_wait)

        self._ensure_ready()

        if position == "top":
            refresh_btn = self._win.ButtonControl(
                ClassName="mmui::XTabBarItem",
                Name=i_("刷新"),
            )
            if refresh_btn.Exists(maxSearchSeconds=2):
                input_wx.click(refresh_btn)
                time.sleep(2)

        lc = self._find_sns_list()

        yielded = 0
        seen_keys: Set[tuple] = set()
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

    def like(self, moment_item: MomentItem) -> bool:
        """对指定动态点赞"""
        return moment_item.like()

    def unlike(self, moment_item: MomentItem) -> bool:
        """取消指定动态的点赞"""
        return moment_item.unlike()

    def comment(self, moment_item: MomentItem, content: str) -> bool:
        """对指定动态评论"""
        return moment_item.comment(content)

    def scroll_into_visible(self, moment_item: MomentItem) -> bool:
        """将指定动态滚动到可见区域"""
        return moment_item.scroll_to_visible()

    @PIM.guard
    def like_when(self, func: callable,
                  position: Literal["top", "current"] = "top") -> List[MomentItem]:
        """
        条件批量点赞：遍历朋友圈，回调返回 True 时点赞。

        Args:
            func:     回调函数，签名 func(liked_count: int, item: MomentItem) -> bool。
                      liked_count 为当前已点赞数（从 0 开始），item 为当前动态。
                      返回 True 点赞，返回 False 跳过。
            position: 起始位置，"top" 从顶部开始，"current" 从当前位置。

        Returns:
            成功点赞的 MomentItem 列表

        用法::

            # 全部点赞
            wx.moment.like_when(lambda c, item: True)

            # 只点赞包含"旅行"的动态
            wx.moment.like_when(lambda c, item: "旅行" in item.content)

            # 只点赞"张三"发的
            wx.moment.like_when(lambda c, item: "张三" in item.sender)

            # 点赞前 5 条后停止（通过 liked_count 控制）
            wx.moment.like_when(lambda c, item: c < 5)

            # 复杂条件
            wx.moment.like_when(
                lambda c, item: item.image_count > 0 and "美食" in item.content,
            )
        """
        liked: List[MomentItem] = []

        for item in self.iter_moments(count=500, position=position):
            try:
                should = func(len(liked), item)
            except Exception as e:
                logger.warning(f"回调异常: {item.sender} - {e}")
                continue

            if not should:
                continue

            try:
                if item.like():
                    liked.append(item)
                    logger.info(
                        f"点赞 [{len(liked)}]: "
                        f"{item.sender} - {item.content[:30] if item.content else '(无文字)'}"
                    )
            except Exception as e:
                logger.warning(f"点赞失败: {item.sender} - {e}")
                continue

            time.sleep(0.5)

        logger.info(f"批量点赞完成: 成功 {len(liked)} 条")
        return liked

    @PIM.guard
    def comment_when(self, func: callable,
                     position: Literal["top", "current"] = "top") -> List[MomentItem]:
        """
        条件批量评论：遍历朋友圈，回调返回评论内容时评论。

        Args:
            func:     回调函数，签名 func(commented_count: int, item: MomentItem) -> str | None。
                      commented_count 为当前已评论数（从 0 开始），item 为当前动态。
                      返回非空字符串时评论该动态，返回 None 或空字符串跳过。
            position: 起始位置，"top" 从顶部开始，"current" 从当前位置。

        Returns:
            成功评论的 MomentItem 列表

        用法::

            # 对所有动态评论"好棒"
            wx.moment.comment_when(lambda c, item: "好棒")

            # 评论前 3 条后停止
            wx.moment.comment_when(lambda c, item: "不错" if c < 3 else None)

            # 只评论"张三"发的
            wx.moment.comment_when(
                lambda c, item: "赞一个" if "张三" in item.sender else None
            )

            # 根据内容生成不同评论
            def gen_comment(count, item):
                if "旅行" in item.content:
                    return "风景真美！"
                if "美食" in item.content:
                    return "看起来好好吃"
                return None  # 其他跳过

            wx.moment.comment_when(gen_comment)
        """
        commented: List[MomentItem] = []

        for item in self.iter_moments(count=500, position=position):
            try:
                content = func(len(commented), item)
            except Exception as e:
                logger.warning(f"回调异常: {item.sender} - {e}")
                continue

            if not content:
                continue

            try:
                if item.comment(content):
                    commented.append(item)
                    logger.info(
                        f"评论 [{len(commented)}]: "
                        f"{item.sender} - {content[:30]!r}"
                    )
            except Exception as e:
                logger.warning(f"评论失败: {item.sender} - {e}")
                continue

            time.sleep(0.5)

        logger.info(f"批量评论完成: 成功 {len(commented)} 条")
        return commented

    # ---- 发布相关控件信息 ----
    # 发布面板: GroupControl, ClassName="mmui::SnsPublishPanel",
    #           AutomationId="SnsPublishPanel"
    # 文本输入: EditControl, ClassName="mmui::XValidatorTextEdit"
    #           位于 mmui::PublishInputView > mmui::ReplyTextView 内
    # 表情按钮: ButtonControl, ClassName="mmui::XButton", Name="发送表情"
    # 提醒谁看: GroupControl, ClassName="mmui::PublishComponent", Name=i_("提醒谁看")
    # 谁可以看: ButtonControl, ClassName="mmui::PublishPrivacyView", Name 以 "谁可以看" 开头
    # 发表按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="发表"
    # 取消按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="取消"
    # 工具栏发表: ButtonControl, ClassName="mmui::XTabBarItem", Name="发表"

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
            raise WxControlNotFoundError("未找到朋友圈工具栏")

        # 查找工具栏中的"发表"按钮
        publish_tab = toolbar.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name=i_("发表"),
        )
        if not publish_tab.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到工具栏'发表'按钮")

        if text_only:
            # 纯文本发布：移动鼠标到"发表"按钮，长按 3 秒触发文字发布面板
            rect = publish_tab.BoundingRectangle
            cx = rect.left + int(rect.width() * rand_ratio())
            cy = rect.top + int(rect.height() * rand_ratio())
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
            raise WxControlNotFoundError("未找到朋友圈文本输入框")
        return edit

    def _find_publish_button(self, panel: auto.Control) -> auto.ButtonControl:
        """
        在发布面板中查找"发表"按钮。

        按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="发表"
        """
        btn = panel.ButtonControl(
            ClassName=self.PUBLISH_BTN_CLASS,
            Name=i_("发表"),
            searchDepth=3,
        )
        if not btn.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到'发表'按钮")
        return btn

    def _find_cancel_button(self, panel: auto.Control) -> auto.ButtonControl:
        """
        在发布面板中查找"取消"按钮。

        按钮: ButtonControl, ClassName="mmui::XOutlineButton", Name="取消"
        """
        btn = panel.ButtonControl(
            ClassName=self.PUBLISH_BTN_CLASS,
            Name=i_("取消"),
            searchDepth=10,
        )
        if not btn.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到'取消'按钮")
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
            raise WxControlNotFoundError("未找到文件名输入框")

        vp = file_edit.GetValuePattern()
        if vp:
            vp.SetValue(file_path)
        else:
            input_wx.paste(file_path)
        time.sleep(0.3)

        # Alt+O 打开
        input_wx.send_keys(file_dlg, "{Alt}O")

    def _set_remind_contacts(self, panel: auto.Control,
                             contacts: List[str]) -> None:
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
            Name=i_("提醒谁看"),
        )
        if not remind_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'提醒谁看'按钮")
        input_wx.click(remind_btn)
        time.sleep(0.5)

        # 复用 SessionPickerWindow 选择逻辑
        self._select_in_session_picker(i_("微信提醒谁看"), contacts=contacts)

    def _set_privacy(self, panel: auto.Control, permission: str,
                     permission_contacts: Optional[List[str]] = None,
                     permission_labels: Optional[List[str]] = None) -> None:
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
        if permission not in (i_("公开"), i_("私密"), i_("谁可以看"), i_("不给谁看")):
            raise ValueError(
                f"无效的隐私选项 '{permission}'，"
                f"有效值: {(i_('公开'), i_('私密'), i_('谁可以看'), i_('不给谁看'))}"
            )

        # 点击隐私按钮打开隐私选择面板
        privacy_btn = panel.ButtonControl(
            ClassName=self.PRIVACY_BTN_CLASS,
            searchDepth=5,
        )
        if not privacy_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到'谁可以看'隐私按钮")
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
            raise WxControlNotFoundError(f"未找到隐私选项 '{permission}'")
        input_wx.click(radio)
        time.sleep(0.5)

        # "谁可以看"和"不给谁看"需要选择联系人/标签
        if permission in (i_("谁可以看"), i_("不给谁看")):
            # 根据 permission 查找对应的 picker 窗口名称
            if permission == i_("谁可以看"):
                picker_name = i_("微信谁可以看")
            else:
                picker_name = i_("微信不给谁看")
            self._select_in_session_picker(
                picker_name, permission_contacts, permission_labels,
            )

        # 点击"确定"关闭隐私选择面板（同样在 SNSWindow 上搜索）
        confirm_btn = self._win.ButtonControl(
            ClassName=self.PUBLISH_BTN_CLASS,
            Name=i_("确定"),
            searchDepth=10,
        )
        if not confirm_btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError("未找到隐私设置'确定'按钮")
        input_wx.click(confirm_btn)

    def _select_in_session_picker(
        self,
        picker_name: str,
        contacts: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
    ) -> None:
        """
        在 SessionPickerWindow 中选择联系人和/或标签。

        "谁可以看"/"不给谁看"/"提醒谁看"共用此方法。
        SessionPickerWindow 内部结构:
        - 搜索框: EditControl, Name=i_("搜索"), ClassName="mmui::XValidatorTextEdit"
        - 搜索结果: CheckBoxControl, ClassName="mmui::SearchContactCellView"
        - "标签" tab: ButtonControl, Name=i_("标签"), ClassName="mmui::XButton"
        - "朋友" tab: ButtonControl, Name=i_("朋友"), ClassName="mmui::XButton"
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
                Name=i_("标签"),
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
                Name=i_("朋友"),
                searchDepth=5,
            )
            if friend_tab.Exists(maxSearchSeconds=2):
                input_wx.click(friend_tab)
                time.sleep(0.5)

            # 通过搜索逐个选择联系人
            search_edit = picker.EditControl(
                ClassName="mmui::XValidatorTextEdit",
                Name=i_("搜索"),
                searchDepth=5,
            )
            if not search_edit.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("未找到搜索框")

            not_found: List[str] = []

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
            raise WxControlNotFoundError("未找到'完成'按钮")
        input_wx.click(confirm_btn)

    @PIM.guard
    def publish(self, text: Optional[str] = None, images: List[str] = None,
                video: str = None, remind_contacts: List[str] = None,
                permission: str = None,
                permission_contacts: List[str] = None,
                permission_labels: List[str] = None) -> bool:
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

        self._ensure_ready()

        # 右键"发表"按钮弹出菜单
        publish_tab = self._find_toolbar_button(i_("发表"))
        input_wx.click(publish_tab, button="right")
        time.sleep(0.5)

        if has_media:
            # 点击"选照片或视频"
            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView",
                Name=i_("选照片或视频"),
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("未找到'选照片或视频'菜单项")
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
                        Name=i_("添加图片"),
                        searchDepth=10,
                    )
                    if not add_cell.Exists(maxSearchSeconds=3):
                        raise WxControlNotFoundError("未找到'添加图片'按钮")

                    input_wx.click(add_cell)
                    time.sleep(1)

                    self._select_file_in_dialog(img_path)
        else:
            # 纯文字：点击"发表文字"
            menu_item = self._win.MenuItemControl(
                ClassName="mmui::XMenuView",
                Name=i_("发表文字"),
            )
            if not menu_item.Exists(maxSearchSeconds=2):
                raise WxControlNotFoundError("未找到'发表文字'菜单项")
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
            # input_wx.send_keys(edit, text)

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
                logger.debug("朋友圈发布成功")
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
            raise WxControlNotFoundError("未找到朋友圈工具栏")

        btn = toolbar.ButtonControl(
            ClassName="mmui::XTabBarItem",
            Name=name,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise WxControlNotFoundError(f"未找到工具栏'{name}'按钮")
        return btn

    @PIM.guard
    def refresh(self) -> None:
        """
        刷新朋友圈。

        点击工具栏"刷新"按钮，回到列表顶部并加载最新动态。
        """
        self._ensure_ready()
        btn = self._find_toolbar_button(i_("刷新"))
        input_wx.click(btn)

    def __str__(self) -> str:
        return "Moment(朋友圈)"


class ChatFile:
    """聊天文件信息（来自"聊天文件"管理器窗口）"""

    def __init__(self, file_manager: Optional[FileManager] = None, *, file_name: str = "",
                 sender_name: str = "", source_name: str = "", source_type: str = "",
                 file_date: str = "", file_status: str = "", file_size: str = "",
                 raw_text: str = "", _cell: Optional[auto.Control] = None):
        """
        初始化聊天文件信息。

        Args:
            file_manager: 关联的 FileManager 实例。
            file_name: 文件名。
            sender_name: 发送人昵称。
            source_name: 来源（群名或个人昵称）。
            source_type: 来源类型，"contact"(私聊) 或 "room"(群聊)。
            file_date: 日期文本。
            file_status: 状态文本（空字符串表示已下载）。
            file_size: 文件大小文本。
            raw_text: 原始 Name 属性文本。
            _cell: UI 控件引用（内部使用）。
        """
        self.file_manager = file_manager
        self.file_name = file_name
        self.sender_name = sender_name
        self.source_name = source_name
        self.source_type = source_type
        self.file_date = file_date
        self.file_status = file_status
        self.file_size = file_size
        self.raw_text = raw_text
        self._cell = _cell

    def __str__(self) -> str:
        status = self.file_status if self.file_status else "已下载"
        type_label = "联系人" if self.source_type == "contact" else "群聊"
        return (f"[{self.file_date}] [{type_label}] {self.file_name} | "
                f"发送人: {self.sender_name} | 来源: {self.source_name} | "
                f"大小: {self.file_size} | 状态: {status}")

    def _ensure_ready(self) -> None:
        """确保 file_manager 和 _cell 可用，且文件管理器窗口已打开"""
        if not self.file_manager:
            raise RuntimeError("ChatFile 未关联 FileManager 实例")
        if not self._cell:
            raise RuntimeError("ChatFile 未关联 UI 控件（_cell 为空）")
        if not self.file_manager.exists:
            raise RuntimeError("聊天文件窗口未打开")

    def _right_click_and_find_menu(self) -> auto.Control:
        """右键点击文件项并返回弹出的菜单控件"""
        self.file_manager.activate()
        input_wx.click(self._cell, button="right")
        menu = self.file_manager._find_context_menu_by_point()
        if not menu:
            raise WxControlNotFoundError("未找到右键菜单")
        return menu

    def _click_menu_item(self, menu: auto.Control, item_name: str) -> auto.Control:
        """在菜单中查找并点击指定名称的菜单项"""
        target = None
        for child in menu.GetChildren():
            if child.Name == item_name:
                target = child
                break
        if not target:
            raise WxControlNotFoundError(f"未找到'{item_name}'菜单项")
        input_wx.click(target)
        return target

    def _context_action(self, menu_name: str) -> None:
        """
        通用右键菜单操作：确保就绪 → 右键点击 → 点击指定菜单项。

        Args:
            menu_name: 菜单项名称
        """
        self._ensure_ready()
        menu = self._right_click_and_find_menu()
        self._click_menu_item(menu, menu_name)

    def _handle_save_dialog(self, file_path: str) -> bool:
        """处理 Windows 文件保存对话框：填入路径并保存"""
        save_dialog = self.file_manager._win.WindowControl(ClassName="#32770", searchDepth=3)
        if not save_dialog.Exists(maxSearchSeconds=5):
            raise WxControlNotFoundError("未找到 Windows 文件保存对话框")

        file_name_edit = save_dialog.EditControl(AutomationId="1001", searchDepth=10)
        if not file_name_edit.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError("未找到文件名输入框")

        input_wx.paste_or_type(file_name_edit, file_path)

        # 如果目标文件已存在，先删除（避免覆盖确认弹窗）
        if os.path.exists(file_path):
            os.remove(file_path)

        input_wx.send_keys(None, "{Alt}s")
        if not save_dialog.Exists(maxSearchSeconds=2):
            return True
        else:
            input_wx.send_keys(None, "{Esc}")
            return False

    @PIM.guard
    def save_as(self, file_path: str) -> bool:
        """
        将文件另存为到指定路径。

        流程:
        1. 右键点击文件项 → 弹出微信右键菜单
        2. 点击"另存为..."菜单项 → 弹出 Windows 文件保存对话框
        3. 设置保存路径 → 按 Alt+S 保存

        Args:
            file_path: 完整的保存路径（含文件名），如 "C:\\download\\test.xlsx"

        Returns:
            True 保存成功，False 保存失败
        """
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        self._context_action("另存为...")
        return self._handle_save_dialog(file_path)

    @PIM.guard
    def download_to(self, file_path: str) -> bool:
        """
        将文件下载到指定路径。

        流程:
        1. 右键点击文件项 → 弹出微信右键菜单
        2. 点击"下载到..."菜单项 → 弹出 Windows 文件保存对话框
        3. 设置保存路径 → 按 Alt+S 保存

        Args:
            file_path: 完整的保存路径（含文件名），如 "C:\\download\\test.xlsx"

        Returns:
            True 下载成功，False 下载失败
        """
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        self._context_action("下载到...")
        return self._handle_save_dialog(file_path)

    @PIM.guard
    def download(self) -> bool:
        """
        下载文件（下载到微信默认路径）。

        流程:
        1. 获取当前文件控件的 RuntimeId 作为唯一标识
        2. 右键点击文件项 → 弹出微信右键菜单
        3. 点击"下载"菜单项 → 开始下载

        Returns:
            True 下载成功（状态变为已下载），False 下载超时
        """
        self._context_action(i_("下载"))

    @PIM.guard
    def delete(self) -> bool:
        """
        删除此文件。

        流程:
        1. 右键点击文件项 → 弹出微信右键菜单
        2. 点击"删除"菜单项 → 弹出确认对话框
        3. 点击"删除"确认按钮完成删除

        Returns:
            True 删除成功，False 删除失败
        """
        self._context_action(i_("删除"))

        # 点击确认弹窗中的"删除"按钮
        delete_btn = self.file_manager._win.ButtonControl(
            ClassName="mmui::XOutlineButton", Name=i_("删除"),
        )
        if delete_btn.Exists(maxSearchSeconds=2):
            input_wx.click(delete_btn)
            return True
        return False

    @PIM.guard
    def copy(self) -> str:
        """
        复制此文件到剪贴板并返回复制的文件路径。

        右键点击文件项，在菜单中点击"复制"，
        然后从剪贴板读取复制的内容。

        Returns:
            复制到剪贴板的文本内容（通常为文件路径或文件名）
        """
        self._context_action(i_("复制"))
        return get_clipboard_file()

    @PIM.guard
    def collect(self) -> None:
        """
        收藏此文件。

        右键点击文件项，在菜单中点击"收藏"。
        """
        self._context_action(i_("收藏"))

    @PIM.guard
    def switch_to_message(self) -> None:
        """
        定位到聊天位置。

        右键点击文件项，在菜单中点击"定位到聊天位置"，
        微信会跳转到该文件消息所在的聊天会话并滚动到对应位置。
        """
        self._context_action("定位到聊天位置")


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

    FILE_LIST_CELL_CLASS = "mmui::FileListCell"
    FILE_TYPE_FILTER_CLASS = "mmui::XTableCell"
    CONTEXT_MENU_WIN_CLASS = "mmui::XMenu"
    # 确认对话框的类名（微信 v4 使用 mmui::XDialog，浮动于桌面层级）
    CONFIRM_DIALOG_WIN_CLASS = "mmui::XDialog"

    def __init__(self, wx: Weixin):
        """
        初始化聊天文件管理器。

        Args:
            wx: Weixin 实例。
        """
        self.wx = wx
        self._win = auto.WindowControl(
            Name=i_("聊天文件"),
            ProcessId=self.wx.pid,
            searchDepth=1,
        )

    @PIM.guard
    def open(self, filter_type: Optional[str] = None) -> bool:
        """
        打开聊天文件管理器窗口。

        Args:
            filter_type: 文件类型筛选，可选值:
                - "全部"、"文档"、"表格"、"图片"、"视频"等
                - "": 不筛选（默认）
        """
        if not self.exists:
            self.wx.navigator.switch_to(i_("更多"))
            chat_file_btn = self.wx._win.ButtonControl(
                Name=i_("聊天文件"), searchDepth=10
            )
            if not chat_file_btn.Exists(maxSearchSeconds=3):
                raise WxControlNotFoundError("未找到'聊天文件'按钮")

            input_wx.click(chat_file_btn)

            if not self.exists:
                raise RuntimeError("聊天文件窗口未能打开")
        self.activate()

        if filter_type:
            self._click_filter(filter_type)

        return True

    def _click_filter(self, filter_name: str) -> bool:
        """
        点击聊天文件窗口中的文件类型筛选按钮。

        已知的筛选选项: "全部"、"文档"、"表格"、"图片"、"视频"等。
        """
        if not self.exists:
            raise RuntimeError("聊天文件窗口未打开")
        self.activate()
        filter_btn = self._win.ListItemControl(
            Name=filter_name,
            ClassName=self.FILE_TYPE_FILTER_CLASS,
            searchDepth=10,
        )
        if not filter_btn.Exists(maxSearchSeconds=3):
            raise WxControlNotFoundError(f"未找到'{filter_name}'筛选按钮")

        input_wx.click(filter_btn)
        return True

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
    def save_file_as(self, chat_file: ChatFile, file_path: str) -> bool:
        """
        对文件执行"另存为"操作。

        Args:
            chat_file: ChatFile 实例
            file_path: 完整的保存路径（含文件名），如 "C:\\download\\test.xlsx"
        """
        return chat_file.save_as(file_path)

    @PIM.guard
    def download_to(self, chat_file: ChatFile, file_path: str) -> bool:
        """
        对文件执行"下载到"操作。

        Args:
            chat_file: ChatFile 实例
            file_path: 完整的保存路径（含文件名），如 "C:\\download\\test.xlsx"
        """
        return chat_file.download_to(file_path)

    @PIM.guard
    def delete_file(self, chat_file: ChatFile) -> bool:
        """
        删除文件。

        Args:
            chat_file: ChatFile 实例

        Returns:
            True 删除成功，False 删除失败
        """
        return chat_file.delete()

    @PIM.guard
    def download_file(self, chat_file: ChatFile, timeout: int = 60) -> bool:
        """
        下载文件。

        Args:
            chat_file: ChatFile 实例
            timeout:   等待下载完成的超时时间（秒），默认 60 秒

        Returns:
            True 下载成功（状态变为已下载），False 下载超时
        """
        return chat_file.download(timeout)

    def parse_file_cell_text(self, cell_text: str) -> Optional[ChatFile]:
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
                date_str = i_("今天")
                date_idx = i
                break
            if token in (i_("今天"), i_("昨天")) or "星期" in token:
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
        not_downloaded = i_("未下载")
        if source_name.endswith(f" {not_downloaded}"):
            source_name = source_name[:-len(f" {not_downloaded}")]
            file_status = not_downloaded

        left_tokens = left_part.rsplit(" ", 1)
        if len(left_tokens) == 2:
            file_name = left_tokens[0].strip()
            sender_name = left_tokens[1].strip()
        else:
            file_name = left_part
            sender_name = ""

        source_type = "contact" if sender_name and sender_name == source_name else "room"

        return ChatFile(
            self,
            file_name=file_name,
            sender_name=sender_name,
            source_name=source_name,
            source_type=source_type,
            file_date=date_str,
            file_status=file_status,
            file_size=file_size,
            raw_text=cell_text,
        )

    def _find_all_file_cells(self, parent: auto.Control) -> List:
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

    def get_all_files(self) -> List[ChatFile]:
        """获取聊天文件窗口中所有可见的文件列表"""
        if not self.exists:
            raise RuntimeError("聊天文件窗口未打开")
        self.activate()

        files = []
        for cell in self._find_all_file_cells(self._win):
            chat_file = self.parse_file_cell_text(cell.Name)
            if chat_file:
                chat_file._cell = cell
                files.append(chat_file)
        return files

    def get_today_files(self) -> List[ChatFile]:
        """获取今天的文件列表"""
        all_files = self.get_all_files()
        today_str = i_("今天")
        today_date = date.today()
        today_formatted = f"{today_date.year}年{today_date.month}月{today_date.day}日"
        return [f for f in all_files
                if f.file_date == today_str or f.file_date == today_formatted]

    def __str__(self) -> str:
        if self._win.Exists(0, 0):
            return "FileManager(open)"
        return "FileManager(closed)"


class Weixin(WeixinWindow):

    WINDOW_CLASS = "mmui::MainWindow"
    WINDOW_REGEX = "微信|Weixin"
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 1000
    CHAT_WINDOW_WIDTH = 400
    CHAT_WINDOW_HEIGHT = 1000
    SHORTCUTS = {
        "发送消息": "Enter",
        "语音输入文字": "Ctrl+Win",
        "截图": "Alt+A",
        "锁定": "Ctrl+L",
        "显示窗口": "Ctrl+Alt+W",
    }

    def __init__(
        self, 
        pid: Optional[int] = None,
        on_login: Optional[callable] = None,
        default_login_timeout: float = 60,
        background: bool = False, 
        idle_wait: float = 0, 
        lock_input: bool = False, 
        resize: bool = False,
        install_path: Optional[str] = None,
        ocr_engine: Literal["wcocr", "rapidocr"] = "wcocr",
        wxocr_weixin_install_path: Optional[str] = None, 
        wxocr_plugin_path: Optional[str] = None
    ):
        """
        初始化微信自动化实例，连接微信客户端。

        Args:
            pid: 微信进程 PID。传入时精确绑定该进程的主窗口，
                None 时自动查找或启动微信（兼容旧行为）。
            on_login: 登录回调函数，签名为 callback(login: Login)。
                微信未登录时调用此回调处理登录流程，
                None 时等待用户手动登录（60秒超时）。
            background: True 时使用后台模式（通过 SendMessage 发送虚拟鼠标/键盘消息，
                不需要窗口在前台），默认 False。
            idle_wait: 人类操作等待时间（秒），大于 0 时自动启动物理输入监控，
                所有 UI 操作方法执行前会等待用户停止物理键盘/鼠标操作达到该秒数。
                默认 0 表示不等待。
            lock_input: True 时在自动化操作期间锁定物理键盘鼠标（需管理员权限），
                默认 False。
            resize: True 时根据桌面大小自动调整微信窗口尺寸（宽高为桌面的 1/3 1/2），
                False 时保持原窗口大小。默认 False。
            install_path: 微信安装路径，None 时自动从注册表检测。
            ocr_engine: OCR 引擎选择，可选值：
                - "wcocr": 使用微信自带 OCR（默认，速度快）
                - "rapidocr": 使用 RapidOCR（无需微信 OCR 插件）
            wxocr_weixin_install_path: 微信 OCR 插件所需的带版本号微信安装路径，
                None 时自动检测。仅 ocr_engine="wcocr" 时有效。
            wxocr_plugin_path: 微信 OCR 插件 wxocr.dll 路径，
                None 时自动检测。仅 ocr_engine="wcocr" 时有效。

        Raises:
            LoginError: 微信未安装、启动超时或登录超时时抛出。
            ValueError: ocr_engine 参数无效时抛出。
        """
        self.pid = pid
        self.background = background
        globals()["background"] = background # 设置全局后台模式标志
        self.idle_wait = idle_wait
        self.lock_input = lock_input
        self._ee = EventEmitter()
        if self.idle_wait > 0:
            PIM(idle_wait=self.idle_wait, lock_input=self.lock_input)
            PIM.start()

        if ocr_engine not in ("wcocr", "rapidocr"):
            raise ValueError(f"ocr_engine 参数必须为 'wcocr' 或 'rapidocr'，当前: {ocr_engine!r}")

        self.version = get_wechat_version(4)
        self.install_path = install_path or get_weixin_install_path()
        self.on_login = on_login
        self.default_login_timeout = default_login_timeout
        self.language = None
        self.language_name = None

        ensure_narrator_registry()

        # 存在微信进程但是没有找到微信窗口
        self.weixin_window = auto.WindowControl(RegexName=self.WINDOW_REGEX, searchDepth=1)
        if not self.weixin_window.Exists(0, 0):
            weixin_processes = find_process("Weixin.exe")
            if weixin_processes:
                weixin_process = weixin_processes[0]
                # 1.可能是主窗口在托盘 -> 唤醒
                self.wakeup() # 注意：快捷键显示微信窗口 仅第一个微信有效
                # 2.可能是当前桌面没有微信窗口 -> 把微信窗口调到前台(自动切换到存在微信窗口的桌面)
                wx_pid = self.pid if self.pid else weixin_process["pid"]
                weixin_hwnd = None
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    weixin_hwnd = wx_pid_to_hwnd(wx_pid)
                    if weixin_hwnd is not None:
                        break
                    time.sleep(0.1)
                if weixin_hwnd is not None:
                    win32gui.SetForegroundWindow(weixin_hwnd)

        self._win = auto.WindowControl(
            ClassName=self.WINDOW_CLASS,
            ProcessId=self.pid,
            searchDepth=1
        )
        if not self._win.Exists(maxSearchSeconds=3):
            # 主窗口未找到，检查是否存在登录窗口
            login_win = auto.WindowControl(
                ClassName=Login.WINDOW_CLASS,
                ProcessId=self.pid,
                searchDepth=1
            )
            if login_win.Exists(maxSearchSeconds=3):
                self.pid = login_win.ProcessId
                login = Login(pid=self.pid)
                self._handle_login(login)
                # 登录完成后重新绑定主窗口
                self._win = auto.WindowControl(
                    ClassName=self.WINDOW_CLASS,
                    ProcessId=self.pid,
                    searchDepth=1
                )
                if not self._win.Exists(maxSearchSeconds=5):
                    raise LoginError(f"登录后未找到 PID={self.pid} 的微信主窗口")
            else:
                if not self.pid:
                    self.pid = self.open()
                    if login_win.Exists(maxSearchSeconds=3):
                        login = Login(pid=self.pid)
                        self._handle_login(login)
                        # 登录完成后重新绑定主窗口
                        self._win = auto.WindowControl(
                            ClassName=self.WINDOW_CLASS,
                            ProcessId=self.pid,
                            searchDepth=1
                        )
                        if not self._win.Exists(maxSearchSeconds=5):
                            raise LoginError(f"登录后未找到 PID={self.pid} 的微信主窗口")
                    else:
                        raise WxWindowNotFoundError(f"未找到 PID={self.pid} 的登录窗口")
                else:
                    raise WxWindowNotFoundError(f"未找到 PID={self.pid} 的微信主窗口或登录窗口")

        self.pid = self._win.ProcessId

        if not self.language and not self.language_name:
            # 微信语言未检测 开始自动检测
            self.auto_detect_lang(self.pid)

        self._ocr_engine = ocr_engine
        if self._ocr_engine == "wcocr":
            self.wxocr_weixin_install_path = wxocr_weixin_install_path or get_wechat_install_path(4)
            self.wxocr_plugin_path = wxocr_plugin_path or get_wechat_wxocr_path()
            wcocr.init(self.wxocr_plugin_path, self.wxocr_weixin_install_path)
        else:
            self._rapid_ocr = RapidOCR()

        self.resize = resize
        hwnd = self._win.NativeWindowHandle
        if self.resize and hwnd:
            # 根据桌面大小计算窗口尺寸：宽高为桌面的 1/6
            desktop_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            desktop_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            self.WINDOW_WIDTH = desktop_width // 3
            self.WINDOW_HEIGHT = desktop_height // 2
            # 聊天窗口宽度为微信窗口的 1/3，高度与微信窗口一致
            self.CHAT_WINDOW_WIDTH = self.WINDOW_WIDTH // 3
            self.CHAT_WINDOW_HEIGHT = self.WINDOW_HEIGHT
            # 将微信窗口移动到屏幕中心
            x = (desktop_width - self.WINDOW_WIDTH) // 2
            y = (desktop_height - self.WINDOW_HEIGHT) // 2
            ctypes.windll.user32.MoveWindow(hwnd, x, y,
                                            self.WINDOW_WIDTH, self.WINDOW_HEIGHT, True)
        if background and hwnd:
            self.move_offscreen()

        self.weixin_update = WeixinUpdate(self)
        self.navigator = Navigator(self)
        self.session = Session(self)
        self.file_manager = FileManager(self)
        self.moment = Moment(self)
        logger.info(f"微信客户端({self.version}) - 已连接")

    def __del__(self):
        self.move_back()

    def auto_detect_lang(self, pid: int) -> None:
        # 自动检测微信界面语言并设置全局语言
        detected_lang = _detect_language(pid)
        _set_language(detected_lang)
        self.language = detected_lang
        self.language_name = LANGUAGE_DESCRIPTION[self.language]
        logger.info(f"当前微信语言：{self.language_name}")

    @classmethod
    def open(
        cls, 
        install_path: Optional[str] = None, 
        timeout: float = 30,
        **kwargs
    ) -> int:
        """
        启动一个新的微信客户端并连接，返回 PID。

        每次调用都会启动一个新进程（支持多开）。

        Args:
            install_path: 微信安装路径，None 时自动从注册表检测
            timeout:      等待微信进程启动的超时时间（秒），默认 30 秒
            **kwargs:     覆盖默认的 Weixin 参数

        Returns:
            新启动的微信进程 PID

        Raises:
            LoginError: 微信未安装或启动超时时抛出
        """
        # 获取安装路径
        if not install_path:
            install_path = get_weixin_install_path()

        exe_path = os.path.join(install_path, "Weixin.exe")
        if not os.path.exists(exe_path):
            raise LoginError(f"微信可执行文件不存在: {exe_path}")

        # 记录启动前已有的微信进程 PID
        existing_pids = {p["pid"] for p in find_process("Weixin.exe")}

        # 启动微信进程
        proc = subprocess.Popen([exe_path])

        # 等待新进程出现
        pid = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current_procs = find_process("Weixin.exe")
            new_procs = [p for p in current_procs if p["pid"] not in existing_pids]
            if new_procs:
                pid = new_procs[0]["pid"]
                break
            time.sleep(0.5)

        if not pid:
            if proc.pid and psutil.pid_exists(proc.pid):
                pid = proc.pid
            else:
                raise LoginError("微信启动超时，未检测到新微信进程")

        logger.info(f"微信已启动，PID: {pid}")
        return pid

    def find_new_version_window(self) -> bool:
        """检测是否弹出了新版本更新窗口"""
        return self.weixin_update.exists

    def ignore_version_update(self) -> None:
        """忽略本次更新"""
        return self.weixin_update.ignore()

    def update_new_version(self) -> None:
        """更新新版本"""
        return self.weixin_update.update()

    def process_later(self) -> None:
        """稍后处理"""
        return self.weixin_update.process_later()

    @staticmethod
    def find_wechat_window_by_pid(pid: int) -> bool:
        """检查指定 PID 的微信主窗口是否存在"""
        win = auto.WindowControl(
            ClassName="mmui::MainWindow",
            ProcessId=pid,
            searchDepth=1,
        )
        return win.Exists(0, 0)

    @staticmethod
    def _find_window_by_pid(pid: int) -> auto.WindowControl:
        """
        通过 PID 查找微信主窗口控件。

        Args:
            pid: 微信进程 PID

        Returns:
            匹配的 WindowControl

        Raises:
            WxWindowNotFoundError: 未找到匹配的窗口
        """
        win = auto.WindowControl(
            ClassName="mmui::MainWindow",
            ProcessId=pid,
            searchDepth=1,
        )
        if not win.Exists(maxSearchSeconds=3):
            raise WxWindowNotFoundError(f"未找到 PID={pid} 的微信主窗口")
        return win

    def is_exists_window(self, timeout: float = 30, interval: float = 0.1) -> bool:
        """轮询检测微信主窗口是否存在"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.find_wechat_window_by_pid(self.pid):
                return True
            time.sleep(interval)
        return False

    def _handle_login(self, login: Login) -> None:
        """
        处理登录窗口。

        如果传入了 on_login 回调，调用回调让用户处理登录；
        否则等待用户手动操作（超时由 default_login_timeout 控制）。
        """
        self.auto_detect_lang(self.pid)
        nickname = login.nickname
        logger.info(f"检测到登录窗口: {nickname}")

        # 恢复并激活登录窗口（可能处于最小化状态）
        if login.is_minimized:
            login.restore()

        login.activate()

        if self.on_login:
            self.on_login(login)
        else:
            # 等待用户手动登录
            timeout = self.default_login_timeout
            logger.info(f"等待手动登录...(请在{timeout}秒内完成登录)")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                # 检测方式1: 主窗口已出现（同 PID）
                if self.find_wechat_window_by_pid(self.pid):
                    break
                # 检测方式2: 登录窗口已消失（说明登录流程完成）
                if not login.exists:
                    # 登录窗口关闭后等一下主窗口加载
                    time.sleep(2)
                    break
                time.sleep(0.5)

        # 验证登录结果
        if not self.find_wechat_window_by_pid(self.pid):
            raise LoginError("登录超时，主窗口未出现")

    @property
    def is_online(self) -> bool:
        """微信是否在线（主窗口是否存在）"""
        return self._win.Exists(0, 0)

    @property
    def is_locked(self) -> bool:
        txt = self._win.TextControl(ClassName="mmui::XTextView", Name=i_("Windows 微信已被锁定"))
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
    def chats(self) -> List[Union[Chat, SeparateChat]]:
        """
        获取所有已打开的聊天窗口对象。

        包括主窗口中的当前聊天（Chat）和所有独立聊天窗口（SeparateChat）。
        通过桌面顶层窗口按 PID 过滤，避免匹配到其他微信实例的窗口。
        """
        result: List = []  # type: List[Union[Chat, SeparateChat]]

        # 主窗口中的当前聊天
        main_chat = self.chat
        if main_chat is not None:
            result.append(main_chat)

        # 从桌面一次性获取所有顶层窗口，按类名和 PID 过滤独立聊天窗口
        for ctrl in auto.GetRootControl().GetChildren():
            try:
                if (ctrl.ClassName == SeparateChat.WINDOW_CLASS
                        and ctrl.Name
                        and (not self.pid or ctrl.ProcessId == self.pid)):
                    result.append(SeparateChat(self, ctrl.Name))
            except Exception:
                pass

        return result

    @PIM.guard
    def open_session(self, nickname: str) -> Chat:
        """通过在会话列表中查找并点击来打开指定会话，返回 Chat 对象"""
        return self.session.open_session(nickname)

    @PIM.guard
    def open_session_by_search(self, nickname: str, chat_type: Optional[List[str]] = None, force_search: bool = False) -> Chat:
        """通过搜索打开指定会话，返回 Chat 对象"""
        return self.session.open_session_by_search(nickname, chat_type, force_search)

    def close_session(self, nickname: str) -> None:
        return self.session.close(nickname)

    def send_text(self, nickname: str, content: str, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送文本"""
        return self.chat_with(nickname).send_text(content, quote=quote, timeout=timeout)

    def send_file(self, nickname: str, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送文件"""
        return self.chat_with(nickname).send_file(file_path, quote=quote, timeout=timeout)

    def send_image(self, nickname: str, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送图片"""
        return self.chat_with(nickname).send_image(file_path, quote=quote, timeout=timeout)

    def send_video(self, nickname: str, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送视频"""
        return self.chat_with(nickname).send_video(file_path, quote=quote, timeout=timeout)

    def send_at(self, nickname: str, content: str, at_members: List[str], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送群@消息"""
        return self.chat_with(nickname).send_at(content, at_members, quote=quote, timeout=timeout)

    def send_collection(self, nickname: str, keyword: str, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送收藏内容"""
        return self.chat_with(nickname).send_collection(keyword, quote=quote, timeout=timeout)

    def send_emotion(self, nickname: str, keyword: str = None, index: int = 1, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送表情"""
        return self.chat_with(nickname).send_emotion(keyword, index, quote=quote, timeout=timeout)

    def send_card(self, nickname: str, share: str) -> bool:
        """发送名片"""
        return self.chat_with(share).send_card(nickname)

    def send_voice(self, nickname: str, duration: float = 3) -> None:
        """发送语音消息"""
        return self.chat_with(nickname).send_voice(duration)

    def create_note(self, content: str) -> None:
        """创建笔记并写入内容，完成后关闭笔记窗口。"""
        return self.session.create_note(content)

    def create_room(self, nickname_list: List[str]) -> None:
        """发起群聊。"""
        self.session.create_room(nickname_list)

    def add_friend(self, keyword: str, message: Optional[str] = None, remark: Optional[str] = None,
                   permission: Optional[str] = None, hide_my_posts: bool = False,
                   hide_their_posts: bool = False) -> None:
        """添加朋友。"""
        self.session.add_friend(
            keyword, message=message, remark=remark,
            permission=permission, hide_my_posts=hide_my_posts,
            hide_their_posts=hide_their_posts,
        )

    def get_separate_chat(self, contact_name: str) -> Optional[SeparateChat]:
        """
        获取独立窗口的聊天会话。

        contact_name: 联系人名称
        返回 SeparateChat 实例，若窗口不存在则返回 None
        """
        try:
            return SeparateChat(self, contact_name)
        except (WxWindowNotFoundError, ValueError):
            return None

    def get_separate_chats(self) -> List[SeparateChat]:
        """
        获取所有已打开的独立聊天窗口（按 PID 过滤）。

        遍历桌面顶层窗口，返回属于当前微信进程的所有独立聊天窗口。
        """
        result: List[SeparateChat] = []
        skip_names = {"微信", "Weixin"}
        for ctrl in auto.GetRootControl().GetChildren():
            try:
                if (ctrl.ClassName == SeparateChat.WINDOW_CLASS
                        and ctrl.Name
                        and ctrl.Name not in skip_names
                        and (not self.pid or ctrl.ProcessId == self.pid)):
                    result.append(SeparateChat(self, ctrl.Name))
            except (WxWindowNotFoundError, ValueError, Exception):
                pass
        return result

    def chat_with(self, nickname: str, chat_type: Optional[List[str]] = None,
                  force_search: bool = False) -> Union[Chat, SeparateChat]:
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
            if separate.is_minimized:
                separate.restore()
            return separate
        return self.open_session_by_search(nickname, chat_type, force_search)

    def get_contact_profile(self, nickname: str) -> dict:
        """获取联系人的资料信息"""
        return self.chat_with(nickname).get_contact_profile()

    def set_contact_info(self, nickname: str, *,
                         remark: str = None,
                         labels: list = None,
                         phones: list = None,
                         description: str = None,
                         images: list = None) -> None:
        """一次性设置联系人的备注、标签、电话、描述、图片"""
        return self.chat_with(nickname).set_contact_info(remark=remark, labels=labels, phones=phones,
                              description=description, images=images)

    def set_contact_remark(self, nickname: str, remark: str) -> None:
        """设置联系人的备注名"""
        return self.chat_with(nickname).set_contact_remark(remark)

    def set_contact_label(self, nickname: str, labels: List[str]) -> None:
        """为联系人设置标签"""
        return self.chat_with(nickname).set_contact_info(labels=labels)

    def set_contact_phone(self, nickname: str, phones: List[str]) -> None:
        """为联系人设置电话号码"""
        return self.chat_with(nickname).set_contact_info(phones=phones)

    def set_contact_description(self, nickname: str, description: str) -> None:
        """设置联系人的描述信息"""
        return self.chat_with(nickname).set_contact_info(description=description)

    def set_contact_image(self, nickname: str, images: List[str]) -> None:
        """设置联系人的备注图片（覆盖式）"""
        return self.chat_with(nickname).set_contact_info(images=images)

    def add_contact_label(self, nickname: str, labels: List[str]) -> None:
        """为联系人添加标签"""
        return self.chat_with(nickname).add_contact_label(labels)

    def add_contact_phone(self, nickname: str, phones: List[str]) -> None:
        """为联系人添加电话号码"""
        return self.chat_with(nickname).add_contact_phone(phones)

    def add_contact_image(self, nickname: str, images: List[str]) -> None:
        """为联系人添加备注图片"""
        return self.chat_with(nickname).add_contact_image(images)

    def remove_contact_label(self, nickname: str, labels: List[str]) -> None:
        """移除联系人的标签"""
        return self.chat_with(nickname).remove_contact_label(labels)

    def remove_contact_phone(self, nickname: str, phones: List[str]) -> None:
        """移除联系人的电话号码"""
        return self.chat_with(nickname).remove_contact_phone(phones)

    def remove_contact_image(self, nickname: str, images: List[int]) -> None:
        """删除联系人的备注图片（按序号）"""
        return self.chat_with(nickname).remove_contact_image(images)

    def collect_contact_image(self, nickname: str, images: List[int]) -> int:
        """收藏联系人的指定备注图片"""
        return self.chat_with(nickname).collect_contact_image(images)

    def save_contact_image(self, nickname: str, images: List[int], save_path: str) -> int:
        """保存联系人的指定备注图片到指定目录"""
        return self.chat_with(nickname).save_contact_image(images, save_path)

    def set_contact_star(self, nickname: str) -> None:
        """将联系人设为星标朋友"""
        return self.chat_with(nickname).set_contact_star()

    def cancel_contact_star(self, nickname: str) -> None:
        """取消联系人的星标朋友"""
        return self.chat_with(nickname).cancel_contact_star()

    def get_friend_permission(self, nickname: str) -> dict:
        """获取联系人的朋友权限设置"""
        return self.chat_with(nickname).get_friend_permission()

    def set_friend_permission(self, nickname: str, permission: Literal["all", "chatonly"] = "all",
                              hide_my_posts: bool = False,
                              hide_their_posts: bool = False) -> None:
        """设置联系人的朋友权限"""
        return self.chat_with(nickname).set_friend_permission(permission, hide_my_posts, hide_their_posts)

    def black_contact(self, nickname: str) -> None:
        """将联系人加入黑名单"""
        return self.chat_with(nickname).black_contact()

    def unblack_contact(self, nickname: str) -> None:
        """将联系人移出黑名单"""
        return self.chat_with(nickname).unblack_contact()

    def delete_contact(self, nickname: str) -> None:
        """删除联系人"""
        return self.chat_with(nickname).delete_contact()

    def recommend_contact(self, nickname: str, receiver_nickname: str) -> bool:
        """将指定联系人推荐给另一个朋友（发送名片）"""
        return self.chat_with(nickname).recommend_contact(receiver_nickname)

    def clear_chat_history(self, nickname: str) -> None:
        """清空指定会话的聊天记录"""
        return self.chat_with(nickname).clear_chat_history()

    def clear_room_chat_history(self, nickname: str) -> None:
        """清空指定群聊会话的聊天记录"""
        return self.chat_with(nickname).clear_room_chat_history()

    def exit_room(self, nickname: str) -> None:
        """退出指定群聊"""
        return self.chat_with(nickname).exit_room()

    def add_room_members(self, nickname: str, members: List[str]) -> None:
        """添加指定群聊的成员"""
        return self.chat_with(nickname).add_room_members(members)

    def remove_room_members(self, nickname: str, members: List[str]) -> None:
        """移除指定群聊的成员"""
        return self.chat_with(nickname).remove_room_members(members)

    def pin_room_chat(self, nickname: str) -> None:
        """置顶指定群聊会话"""
        return self.chat_with(nickname).pin_room_chat()

    def unpin_room_chat(self, nickname: str) -> None:
        """取消置顶指定群聊会话"""
        return self.chat_with(nickname).unpin_room_chat()

    def mute_room_chat(self, nickname: str) -> None:
        """开启指定群聊的消息免打扰"""
        return self.chat_with(nickname).mute_room_chat()

    def unmute_room_chat(self, nickname: str) -> None:
        """关闭指定群聊的消息免打扰"""
        return self.chat_with(nickname).unmute_room_chat()

    def add_room_address_book(self, nickname: str) -> None:
        """将指定群聊保存到通讯录"""
        return self.chat_with(nickname).add_room_address_book()

    def remove_room_address_book(self, nickname: str) -> None:
        """将指定群聊从通讯录移除"""
        return self.chat_with(nickname).remove_room_address_book()

    def display_room_member_nickname(self, nickname: str) -> None:
        """显示指定群聊的群成员昵称"""
        return self.chat_with(nickname).display_room_member_nickname()

    def hidden_room_member_nickname(self, nickname: str) -> None:
        """隐藏指定群聊的群成员昵称"""
        return self.chat_with(nickname).hidden_room_member_nickname()

    def set_room_info(self, nickname: str, name: str = None,
                      announcement: str = None, remark: str = None,
                      my_nickname: str = None, mute: bool = None,
                      pin: bool = None, save_address_book: bool = None,
                      display_member_nickname: bool = None,
                      fold: bool = None) -> None:
        """一次性设置指定群聊的多项信息"""
        return self.chat_with(nickname).set_room_info(
            name=name, announcement=announcement, remark=remark,
            my_nickname=my_nickname, mute=mute, pin=pin,
            save_address_book=save_address_book,
            display_member_nickname=display_member_nickname,
            fold=fold,
        )

    def fold_room_chat(self, nickname: str) -> None:
        """折叠指定群聊会话"""
        return self.chat_with(nickname).fold_room_chat()

    def unfold_room_chat(self, nickname: str) -> None:
        """取消折叠指定群聊会话"""
        return self.chat_with(nickname).unfold_room_chat()

    def pin_chat(self, nickname: str) -> None:
        """置顶指定会话"""
        return self.chat_with(nickname).pin_chat()

    def unpin_chat(self, nickname: str) -> None:
        """取消置顶指定会话"""
        return self.chat_with(nickname).unpin_chat()

    def mute_chat(self, nickname: str) -> None:
        """开启指定会话的消息免打扰"""
        return self.chat_with(nickname).mute_chat()

    def unmute_chat(self, nickname: str) -> None:
        """关闭指定会话的消息免打扰"""
        return self.chat_with(nickname).unmute_chat()

    def fold_chat(self, nickname: str) -> None:
        """折叠指定会话"""
        return self.chat_with(nickname).fold_chat()

    def unfold_chat(self, nickname: str) -> None:
        """取消折叠指定会话"""
        return self.chat_with(nickname).unfold_chat()

    def set_room_name(self, nickname: str, name: str) -> None:
        """设置指定群聊的名称"""
        return self.chat_with(nickname).set_room_name(name)

    def set_room_announcement(self, nickname: str, content: str) -> None:
        """设置指定群聊的群公告"""
        return self.chat_with(nickname).set_room_announcement(content)

    def set_room_remark(self, nickname: str, remark: str) -> None:
        """设置指定群聊的备注"""
        return self.chat_with(nickname).set_room_remark(remark)

    def set_room_nickname(self, nickname: str, my_nickname: str) -> None:
        """设置我在指定群聊中的昵称"""
        return self.chat_with(nickname).set_room_nickname(my_nickname)

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
            Name=i_("微信"),
            searchDepth=5,
        )
        if not wx_btn.Exists(0, 0):
            return 0

        # 截图微信按钮区域
        try:
            png_bytes = capture_control(hwnd, wx_btn, mode="print_window")
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

    def get_self_profile(self) -> dict:
        """获取当前登录账号的个人资料（昵称、微信号）"""
        return self.navigator.get_self_profile()

    def get_self_info(self) -> dict:
        """获取当前登录账号的个人资料（昵称、微信号、头像）"""
        return self.navigator.get_self_info()

    def lock(self) -> None:
        """锁定微信（Ctrl+L）"""
        return self.navigator.lock()

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
        self.activate()
        self.shortcut("发送消息")

    def click(self, control: auto.Control, button: Literal["left", "right", "middle"] = "left",
              click: Literal["once", "double"] = "once") -> None:
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

    def get_moments(self, count: int = 10, position: Literal["top", "current"] = "top") -> list:
        """获取朋友圈动态列表，委托给 moment"""
        return self.moment.get_moments(count, position)

    def iter_moments(self, count: int = 10, position: Literal["top", "current"] = "top"):
        """逐条获取朋友圈动态（生成器），委托给 moment"""
        yield from self.moment.iter_moments(count, position)

    def like_moment(self, moment_item: MomentItem) -> bool:
        """对指定动态点赞"""
        return self.moment.like(moment_item)

    def unlike_moment(self, moment_item: MomentItem) -> bool:
        """取消指定动态的点赞"""
        return self.moment.unlike(moment_item)

    def comment_moment(self, moment_item: MomentItem, content: str) -> bool:
        """对指定动态评论"""
        return self.moment.comment(moment_item, content)

    def refresh_moment(self) -> None:
        """刷新朋友圈，回到列表顶部并加载最新动态"""
        self.moment.refresh()

    def close_moment(self) -> None:
        """关闭朋友圈窗口"""
        self.moment.close()

    def ocr(self, image: Union[bytes, str]) -> dict:
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

    def get_image_text(self, image: Union[bytes, str]) -> dict:
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

    def _get_image_text_rapidocr(self, image: Union[bytes, str]) -> dict:
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

    def _get_image_text_wcocr(self, image: Union[bytes, str]) -> dict:
        """使用微信 OCR 识别图片"""
        if isinstance(image, str):
            result = wcocr.ocr(image)
        else:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="ocr_")
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

    def _register_handler(self, events: Optional[Union[Event, List[Event]]],
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

    def on(self, events: Optional[Union[Event, List[Event]]] = None) -> callable:
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

    def once(self, events: Optional[Union[Event, List[Event]]] = None) -> callable:
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

    def off(self, events: Optional[Union[Event, List[Event]]] = None, func: Optional[callable] = None) -> None:
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

    def _emit(self, message: Message) -> None:
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

    def add_chat_listen(self, names: Optional[Union[str, List[str]]] = None) -> List[SeparateChat]:
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
        if not hasattr(self, '_chat_listeners'):
            self._chat_listeners: Dict[str, SeparateChat] = {}
        self._offscreen = background

        # names 为 None 时，自动发现所有已打开的独立聊天窗口
        if names is None:
            skip_names = {"微信", "Weixin"}
            for ctrl in auto.GetRootControl().GetChildren():
                try:
                    cls_name = ctrl.ClassName
                    name = ctrl.Name
                    proc_pid = ctrl.ProcessId
                except Exception:
                    continue
                if (cls_name == SeparateChat.WINDOW_CLASS
                        and name and name not in skip_names
                        and (not self.pid or proc_pid == self.pid)):
                    if name not in self._chat_listeners or not self._chat_listeners[name].exists:
                        try:
                            chat = SeparateChat(self, name)
                            self._chat_listeners[name] = chat
                            logger.info("已注册监听: [%s] %s", chat.chat_type, name)
                        except (WxWindowNotFoundError, ValueError):
                            pass
            return list(self._chat_listeners.values())

        if isinstance(names, str):
            names = [names]

        if isinstance(names, Iterable):
            result: List[SeparateChat] = []
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

    def remove_chat_listen(self, names: Optional[Union[str, List[str]]] = None) -> None:
        """
        移除聊天监听。

        Args:
            names: 要移除的联系人/群聊名称。
                - None: 移除所有监听
                - str: 移除单个监听
                - List[str]: 移除列表中的监听

        移除后如果窗口在屏幕外（offscreen），会自动移回原位。
        """
        if not hasattr(self, '_chat_listeners'):
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
        msg_queue: Queue[Tuple[SeparateChat, Message]] = Queue()
        threads: Dict[str, threading.Thread] = {}

        def _watch_chat(chat: SeparateChat, name: str) -> None:
            # 滑动窗口：保留最近 N 条消息的 msg_id，N = 当前可见消息数量
            known_msg_ids: Deque[int] = deque()
            known_msg_id_set: Set[int] = set()
            # 发送者缓存：{msg_id: (sender, source, bubble_rect, headimg_rect, nickname_rect, content_rect)}
            sender_cache: Dict[int, tuple] = {}
            first_scan = True

            # 监听前滚动到最新消息
            chat.page_end()

            if self._offscreen:
                chat.move_offscreen()

            while not stop_event.is_set():
                if not chat.exists:
                    break

                # # 消息操作（如 refer/delete）期间暂停扫描，避免滚动时误判
                # if chat._scan_paused:
                #     if stop_event.wait(interval):
                #         break
                #     continue

                try:
                    visible = chat.get_visible_messages(sender_cache=sender_cache)
                except Exception as e:
                    logger.error(e)
                    if stop_event.wait(interval):
                        break
                    continue

                window_size = max(len(visible), 1)

                if first_scan:
                    for msg in visible:
                        known_msg_ids.append(msg.msg_id)
                        known_msg_id_set.add(msg.msg_id)
                    first_scan = False
                    if stop_event.wait(interval):
                        break
                    continue

                # 检测新消息（msg_id 不在已知集合中）
                new_messages = [msg for msg in visible if msg.msg_id not in known_msg_id_set]

                if not new_messages:
                    if stop_event.wait(idle_interval):
                        break
                    continue

                # 按消息在列表中的原始顺序推送新消息
                for msg in new_messages:
                    msg.pid = self.pid or 0
                    known_msg_ids.append(msg.msg_id)
                    known_msg_id_set.add(msg.msg_id)
                    msg_queue.put((chat, msg))

                # 滑动窗口：保留最近 window_size 条
                while len(known_msg_ids) > window_size:
                    old_id = known_msg_ids.popleft()
                    known_msg_id_set.discard(old_id)

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
                    logger.exception("事件分发异常 [%s]", chat.chat_name)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("正在停止监听线程...")
            stop_event.set()
            for t in threads.values():
                t.join(timeout=3)
            self._stop_event = None
            logger.info("监听已停止")


class WeixinManager:
    """
    微信多客户端管理器。

    管理多个 Weixin 实例，所有 API 第一个参数为 pid，
    内部路由到对应的 Weixin 执行操作。

    支持统一消息监听，回调中通过 pid 区分消息来源。

    用法::

        wx = WeixinManager()

        # 启动并连接微信
        pid1 = wx.open()
        pid2 = wx.open()

        # 发送消息
        wx.send_text(pid1, "张三", "来自账号1")
        wx.send_text(pid2, "李四", "来自账号2")

        # 统一监听
        @wx.on(Event.TEXT)
        def on_text(pid, weixin, message):
            print(f"[PID={pid}] {message.sender}: {message.content}")

        wx.add_chat_listen(pid1, ["张三", "李四"])
        wx.add_chat_listen(pid2, ["王五"])
        wx.run()
    """

    def __init__(
        self,
        background: bool = False,
        idle_wait: float = 0,
        lock_input: bool = False,
        resize: bool = False,
        ocr_engine: Literal["wcocr", "rapidocr"] = "wcocr",
        wxocr_weixin_install_path: Optional[str] = None,
        wxocr_plugin_path: Optional[str] = None,
    ):
        """
        初始化微信管理器。

        这些参数作为默认值，在 open/connect 创建 Weixin 时使用。

        Args:
            background:  后台模式，通过 SendMessage 发送虚拟消息，不需要窗口在前台
            idle_wait:   物理输入等待时间（秒），大于 0 时自动启动物理输入监控
            lock_input:  是否在操作期间锁定物理键盘鼠标（需管理员权限）
            resize:      是否根据桌面大小自动调整微信窗口尺寸并居中显示，
                         True 时微信窗口宽高为桌面的 1/3 和 1/2，
                         聊天独立窗口宽度为微信窗口的 1/3，高度与微信窗口一致。
                         默认 False 保持原窗口大小。
            ocr_engine:  OCR 引擎，"wcocr"（微信自带）或 "rapidocr"
            wxocr_weixin_install_path: 微信 OCR 安装路径，None 时自动检测
            wxocr_plugin_path:         微信 OCR 插件路径，None 时自动检测
        """
        self._instances: Dict[int, Weixin] = {}
        self._default_kwargs = {
            "background": background,
            "idle_wait": idle_wait,
            "lock_input": lock_input,
            "resize": resize,
            "ocr_engine": ocr_engine,
            "wxocr_weixin_install_path": wxocr_weixin_install_path,
            "wxocr_plugin_path": wxocr_plugin_path,
        }
        self._ee = EventEmitter()
        self._stop_event: Optional[threading.Event] = None
        self.connect_all()

    # ---- 客户端管理 ----

    def open(self, on_login: Optional[callable] = None,
             install_path: Optional[str] = None, timeout: float = 30,
             **kwargs) -> int:
        """
        启动一个新的微信客户端并连接，返回 PID。

        每次调用都会启动一个新进程（支持多开）。

        Args:
            on_login:     登录回调
            install_path: 微信安装路径，None 时自动从注册表检测
            timeout:      等待微信进程启动的超时时间（秒），默认 30 秒
            **kwargs:     覆盖默认的 Weixin 参数

        Returns:
            新启动的微信进程 PID

        Raises:
            LoginError: 微信未安装或启动超时时抛出
        """
        # 获取安装路径
        if not install_path:
            install_path = get_weixin_install_path()

        exe_path = os.path.join(install_path, "Weixin.exe")
        if not os.path.exists(exe_path):
            raise LoginError(f"微信可执行文件不存在: {exe_path}")

        # 记录启动前已有的微信进程 PID
        existing_pids = {p["pid"] for p in find_process("Weixin.exe")}

        # 启动微信进程
        proc = subprocess.Popen([exe_path])

        # 等待新进程出现
        pid = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current_procs = find_process("Weixin.exe")
            new_procs = [p for p in current_procs if p["pid"] not in existing_pids]
            if new_procs:
                pid = new_procs[0]["pid"]
                break
            time.sleep(0.5)

        if not pid:
            if proc.pid and psutil.pid_exists(proc.pid):
                pid = proc.pid
            else:
                raise LoginError("微信启动超时，未检测到新微信进程")

        logger.info(f"微信已启动，PID: {pid}")

        # 等待窗口就绪后连接
        time.sleep(2)
        return self.connect(pid, on_login=on_login, **kwargs)

    def connect(self, pid: int, on_login: Optional[callable] = None, **kwargs) -> int:
        """
        连接已运行的微信客户端。

        Args:
            pid:      微信进程 PID
            on_login: 登录回调
            **kwargs: 覆盖默认的 Weixin 参数

        Returns:
            连接成功的 PID

        Raises:
            WxWindowNotFoundError: 指定 PID 的微信窗口未找到
        """
        if pid in self._instances:
            weixin = self._instances[pid]
            if weixin.is_online:
                return pid

        # 合并参数
        params = {**self._default_kwargs, **kwargs}
        weixin = Weixin(pid=pid, on_login=on_login, **params)
        self._instances[pid] = weixin
        return pid

    def connect_all(self, on_login: Optional[callable] = None, **kwargs) -> List[int]:
        """
        连接所有已运行的微信客户端。

        Returns:
            所有已连接的 PID 列表
        """
        connected: List[int] = []
        seen_pids: Set[int] = set()

        for ctrl in auto.GetRootControl().GetChildren():
            try:
                if ctrl.ClassName == "mmui::MainWindow":
                    proc_pid = ctrl.ProcessId
                    if proc_pid and proc_pid not in seen_pids:
                        seen_pids.add(proc_pid)
                        try:
                            self.connect(proc_pid, on_login=on_login, **kwargs)
                            connected.append(proc_pid)
                        except Exception as e:
                            logger.warning(f"连接 PID={proc_pid} 失败: {e}")
            except Exception:
                continue

        return connected

    def disconnect(self, pid: int) -> None:
        """
        断开与指定微信客户端的连接（不关闭微信）。

        Args:
            pid: 要断开的微信进程 PID
        """
        weixin = self._instances.pop(pid, None)
        if weixin:
            weixin.move_back()
            logger.info(f"已断开 PID={pid}")

    def disconnect_all(self) -> None:
        """断开所有已连接的微信客户端。"""
        for pid in list(self._instances.keys()):
            self.disconnect(pid)

    def close(self, pid: int) -> None:
        """
        关闭指定微信客户端窗口并断开连接。

        Args:
            pid: 要关闭的微信进程 PID
        """
        weixin = self._instances.pop(pid, None)
        if weixin:
            weixin.move_back()
            try:
                weixin.close()
            except Exception:
                pass

    def get_weixin(self, pid: int) -> Weixin:
        """
        获取指定 PID 的 Weixin 实例。

        Args:
            pid: 微信进程 PID

        Returns:
            Weixin 实例

        Raises:
            KeyError: PID 未连接
        """
        if pid not in self._instances:
            raise KeyError(f"PID={pid} 未连接，请先调用 connect({pid})")
        return self._instances[pid]

    @property
    def pids(self) -> List[int]:
        """所有已连接的 PID 列表"""
        return list(self._instances.keys())

    @property
    def instances(self) -> Dict[int, Weixin]:
        """所有已连接的 {pid: Weixin} 字典"""
        return dict(self._instances)

    def __len__(self) -> int:
        return len(self._instances)

    def __contains__(self, pid: int) -> bool:
        return pid in self._instances

    def __getitem__(self, pid: int) -> Weixin:
        return self.get_weixin(pid)

    # ---- 消息发送 ----

    def send_text(self, pid: int, nickname: str, content: str, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送文本"""
        return self.get_weixin(pid).send_text(nickname, content, quote=quote, timeout=timeout)

    def send_file(self, pid: int, nickname: str, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送文件"""
        return self.get_weixin(pid).send_file(nickname, file_path, quote=quote, timeout=timeout)

    def send_image(self, pid: int, nickname: str, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送图片"""
        return self.get_weixin(pid).send_image(nickname, file_path, quote=quote, timeout=timeout)

    def send_video(self, pid: int, nickname: str, file_path: Union[str, List[str]], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送视频"""
        return self.get_weixin(pid).send_video(nickname, file_path, quote=quote, timeout=timeout)

    def send_at(self, pid: int, nickname: str, content: str, at_members: List[str], quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送群@消息"""
        return self.get_weixin(pid).send_at(nickname, content, at_members, quote=quote, timeout=timeout)

    def send_emotion(self, pid: int, nickname: str, keyword: str = None, index: int = 1, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送表情"""
        return self.get_weixin(pid).send_emotion(nickname, keyword, index, quote=quote, timeout=timeout)

    def send_collection(self, pid: int, nickname: str, keyword: str, quote: Optional[Union[Message, int]] = None, timeout: float = 0) -> MessageStatus:
        """发送收藏内容"""
        return self.get_weixin(pid).send_collection(nickname, keyword, quote=quote, timeout=timeout)

    def send_card(self, pid: int, nickname: str, share: str) -> bool:
        """发送名片"""
        return self.get_weixin(pid).send_card(nickname, share)

    # ---- 会话管理 ----

    def open_session(self, pid: int, nickname: str) -> Chat:
        """打开会话"""
        return self.get_weixin(pid).open_session(nickname)

    def open_session_by_search(self, pid: int, nickname: str, chat_type: Optional[List[str]] = None, force_search: bool = False) -> Chat:
        """通过搜索打开会话"""
        return self.get_weixin(pid).open_session_by_search(nickname, chat_type, force_search)

    def close_session(self, pid: int, nickname: str) -> None:
        """关闭会话"""
        return self.get_weixin(pid).close_session(nickname)

    def create_room(self, pid: int, nickname_list: List[str]) -> None:
        """发起群聊"""
        return self.get_weixin(pid).create_room(nickname_list)

    def add_friend(self, pid: int, keyword: str, message: Optional[str] = None,
                   remark: Optional[str] = None, permission: Optional[str] = None,
                   hide_my_posts: bool = False, hide_their_posts: bool = False) -> None:
        """添加朋友"""
        return self.get_weixin(pid).add_friend(
            keyword, message=message, remark=remark,
            permission=permission, hide_my_posts=hide_my_posts,
            hide_their_posts=hide_their_posts,
        )

    def create_note(self, pid: int, content: str) -> None:
        """创建笔记"""
        return self.get_weixin(pid).create_note(content)

    # ---- 联系人操作 ----

    def get_contact_profile(self, pid: int, nickname: str) -> dict:
        """获取联系人资料"""
        return self.get_weixin(pid).get_contact_profile(nickname)

    def set_contact_info(self, pid: int, nickname: str, **kwargs) -> None:
        """设置联系人信息"""
        return self.get_weixin(pid).set_contact_info(nickname, **kwargs)

    def set_contact_remark(self, pid: int, nickname: str, remark: str) -> None:
        """设置联系人备注"""
        return self.get_weixin(pid).set_contact_remark(nickname, remark)

    def add_contact_label(self, pid: int, nickname: str, labels: List[str]) -> None:
        """添加联系人标签"""
        return self.get_weixin(pid).add_contact_label(nickname, labels)

    def remove_contact_label(self, pid: int, nickname: str, labels: List[str]) -> None:
        """移除联系人标签"""
        return self.get_weixin(pid).remove_contact_label(nickname, labels)

    def set_contact_star(self, pid: int, nickname: str) -> None:
        """设为星标朋友"""
        return self.get_weixin(pid).set_contact_star(nickname)

    def cancel_contact_star(self, pid: int, nickname: str) -> None:
        """取消星标朋友"""
        return self.get_weixin(pid).cancel_contact_star(nickname)

    def black_contact(self, pid: int, nickname: str) -> None:
        """加入黑名单"""
        return self.get_weixin(pid).black_contact(nickname)

    def unblack_contact(self, pid: int, nickname: str) -> None:
        """移出黑名单"""
        return self.get_weixin(pid).unblack_contact(nickname)

    def delete_contact(self, pid: int, nickname: str) -> None:
        """删除联系人"""
        return self.get_weixin(pid).delete_contact(nickname)

    # ---- 群聊操作 ----

    def set_room_name(self, pid: int, nickname: str, name: str) -> None:
        """设置群聊名称"""
        return self.get_weixin(pid).set_room_name(nickname, name)

    def set_room_announcement(self, pid: int, nickname: str, content: str) -> None:
        """设置群公告"""
        return self.get_weixin(pid).set_room_announcement(nickname, content)

    def add_room_members(self, pid: int, nickname: str, members: List[str]) -> None:
        """添加群成员"""
        return self.get_weixin(pid).add_room_members(nickname, members)

    def remove_room_members(self, pid: int, nickname: str, members: List[str]) -> None:
        """移除群成员"""
        return self.get_weixin(pid).remove_room_members(nickname, members)

    def exit_room(self, pid: int, nickname: str) -> None:
        """退出群聊"""
        return self.get_weixin(pid).exit_room(nickname)

    def pin_chat(self, pid: int, nickname: str) -> None:
        """置顶会话"""
        return self.get_weixin(pid).pin_chat(nickname)

    def unpin_chat(self, pid: int, nickname: str) -> None:
        """取消置顶"""
        return self.get_weixin(pid).unpin_chat(nickname)

    def mute_chat(self, pid: int, nickname: str) -> None:
        """消息免打扰"""
        return self.get_weixin(pid).mute_chat(nickname)

    def unmute_chat(self, pid: int, nickname: str) -> None:
        """取消免打扰"""
        return self.get_weixin(pid).unmute_chat(nickname)

    # ---- 个人资料 ----

    def get_self_profile(self, pid: int) -> dict:
        """获取当前登录账号的个人资料（昵称、微信号）"""
        return self.get_weixin(pid).get_self_profile()

    def get_self_info(self, pid: int) -> dict:
        """通过点击头像打开资料面板获取个人资料（昵称、微信号）"""
        return self.get_weixin(pid).get_self_info()

    # ---- 朋友圈 ----

    def get_moments(self, pid: int, count: int = 10, position: Literal["top", "current"] = "top") -> list:
        """获取朋友圈动态"""
        return self.get_weixin(pid).get_moments(count, position)

    def publish(self, pid: int, text: Optional[str] = None, images: List[str] = None,
                video: str = None, **kwargs) -> bool:
        """发布朋友圈"""
        return self.get_weixin(pid).moment.publish(text=text, images=images, video=video, **kwargs)

    # ---- 统一消息监听 ----

    def on(self, events: Optional[Union[Event, List[Event]]] = None) -> callable:
        """
        注册消息事件处理器（装饰器）。

        回调签名: callback(weixin: Weixin, chat: SeparateChat, message: Message)
        message.pid 可获取来源微信进程 PID。

        用法::

            @wx.on(Event.TEXT)
            def on_text(weixin, chat, message):
                print(f"[PID={message.pid}] {message.sender}: {message.content}")

            @wx.on()  # 监听所有消息
            def on_all(weixin, chat, message):
                print(f"[PID={message.pid}] {message}")
        """
        def decorator(func):
            if not events:
                event_list = [Event.ALL]
            elif isinstance(events, list):
                event_list = events
            else:
                event_list = [events]
            for event in event_list:
                self._ee.on(event, func)
            return func
        return decorator

    def once(self, events: Optional[Union[Event, List[Event]]] = None) -> callable:
        """
        注册一次性消息事件处理器（装饰器）。

        回调签名: callback(weixin: Weixin, chat: SeparateChat, message: Message)
        """
        def decorator(func):
            if not events:
                event_list = [Event.ALL]
            elif isinstance(events, list):
                event_list = events
            else:
                event_list = [events]
            for event in event_list:
                self._ee.once(event, func)
            return func
        return decorator

    def off(self, events: Optional[Union[Event, List[Event]]] = None, func: Optional[callable] = None) -> None:
        """移除事件处理器"""
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

    def _emit(self, pid: int, weixin: Weixin, chat: SeparateChat, message: Message) -> None:
        """触发消息事件，回调签名: callback(weixin, chat, message)"""
        event_type = _MSG_CLASS_TO_EVENT.get(type(message), Event.OTHER)
        self._ee.emit(event_type, weixin, chat, message)
        self._ee.emit(Event.ALL, weixin, chat, message)

    @property
    def has_handlers(self) -> bool:
        """是否注册了任何事件处理器"""
        return bool(self._ee.event_names())

    def add_chat_listen(self, pid: int, names: Optional[Union[str, List[str]]] = None) -> List[SeparateChat]:
        """
        为指定客户端注册聊天监听。

        Args:
            pid:   微信进程 PID
            names: 联系人/群聊名称列表，None 时自动发现所有独立窗口

        Returns:
            注册成功的 SeparateChat 列表
        """
        weixin = self.get_weixin(pid)
        return weixin.add_chat_listen(names)

    def add_all_chats_listen(self) -> Dict[int, List[SeparateChat]]:
        """
        为所有已连接的客户端注册聊天监听（自动发现所有独立窗口）。

        Returns:
            {pid: [SeparateChat, ...]} 字典
        """
        result: Dict[int, List[SeparateChat]] = {}
        for pid, weixin in self._instances.items():
            chats = weixin.add_chat_listen(None)
            if chats:
                result[pid] = chats
        return result

    def remove_chat_listen(self, pid: int, names: Optional[Union[str, List[str]]] = None) -> None:
        """
        移除指定客户端的聊天监听。

        Args:
            pid:   微信进程 PID
            names: 要移除的名称，None 移除该客户端的所有监听
        """
        weixin = self.get_weixin(pid)
        weixin.remove_chat_listen(names)

    def remove_all_chat_listen(self) -> None:
        """移除所有客户端的所有聊天监听。"""
        for weixin in self._instances.values():
            weixin.remove_chat_listen(None)

    def run(self, interval: float = 0.1, idle_interval: float = 0.1) -> None:
        """
        启动统一消息监听（阻塞运行，Ctrl+C 退出）。

        监听所有已通过 add_chat_listen 注册的客户端和聊天窗口。
        消息通过 on/once 注册的处理器分发，回调带 pid 区分来源。

        Args:
            interval:      有新消息时的轮询间隔（秒）
            idle_interval: 无新消息时的轮询间隔（秒）
        """
        if not self.has_handlers:
            raise ValueError(
                "未注册任何事件处理器，请使用 @wx.on(Event) 装饰器注册"
            )

        # 收集所有有监听的客户端
        listen_instances: Dict[int, Weixin] = {}
        for pid, weixin in self._instances.items():
            if hasattr(weixin, '_chat_listeners') and weixin._chat_listeners:
                listen_instances[pid] = weixin

        if not listen_instances:
            raise RuntimeError("未注册任何监听，请先调用 add_chat_listen")

        self._stop_event = threading.Event()
        stop_event = self._stop_event
        msg_queue: Queue[Tuple[int, Weixin, SeparateChat, Message]] = Queue()
        threads: Dict[str, threading.Thread] = {}

        def _watch_chat(pid: int, weixin: Weixin, chat: SeparateChat, name: str) -> None:
            from collections import deque
            # 滑动窗口：保留最近 N 条消息的 msg_id，N = 当前可见消息数量
            known_msg_ids: Deque[int] = deque()
            known_msg_id_set: Set[int] = set()
            sender_cache: Dict[int, tuple] = {}
            first_scan = True
            offscreen = weixin.background

            # 监听前滚动到最新消息
            chat.page_end()

            if offscreen:
                chat.move_offscreen()

            while not stop_event.is_set():
                if not chat.exists:
                    break

                # # 消息操作期间暂停扫描
                # if chat._scan_paused:
                #     if stop_event.wait(interval):
                #         break
                #     continue

                try:
                    visible = chat.get_visible_messages(sender_cache=sender_cache)
                except Exception:
                    if stop_event.wait(interval):
                        break
                    continue

                window_size = max(len(visible), 1)

                if first_scan:
                    for msg in visible:
                        known_msg_ids.append(msg.msg_id)
                        known_msg_id_set.add(msg.msg_id)
                    first_scan = False
                    if stop_event.wait(interval):
                        break
                    continue

                # 检测新消息（msg_id 不在已知集合中）
                new_messages = [msg for msg in visible if msg.msg_id not in known_msg_id_set]

                if not new_messages:
                    if stop_event.wait(idle_interval):
                        break
                    continue

                # 按消息在列表中的原始顺序推送新消息
                for msg in new_messages:
                    msg.pid = pid
                    known_msg_ids.append(msg.msg_id)
                    known_msg_id_set.add(msg.msg_id)
                    msg_queue.put((pid, weixin, chat, msg))

                # 滑动窗口：保留最近 window_size 条
                while len(known_msg_ids) > window_size:
                    old_id = known_msg_ids.popleft()
                    known_msg_id_set.discard(old_id)

                if stop_event.wait(interval):
                    break

            if chat.exists and offscreen:
                try:
                    chat.move_back()
                except Exception:
                    pass

        # 为每个客户端的每个监听启动线程
        for pid, weixin in listen_instances.items():
            for name, chat in weixin._chat_listeners.items():
                if not chat.exists:
                    logger.warning("窗口已关闭，跳过: [PID=%d] %s", pid, name)
                    continue
                thread_name = f"listen-{pid}-{name}"
                t = threading.Thread(
                    target=_watch_chat,
                    args=(pid, weixin, chat, name),
                    daemon=True,
                    name=thread_name,
                )
                threads[thread_name] = t
                t.start()
                logger.info("开始监听: [PID=%d] [%s] %s", pid, chat.chat_type, name)

        if not threads:
            raise RuntimeError("没有可监听的窗口")

        # 输出监听列表
        tree_lines = ["*监听列表"]
        for pi, (pid, weixin) in enumerate(listen_instances.items()):
            is_last_pid = pi == len(listen_instances) - 1
            branch = "└── " if is_last_pid else "├── "
            tree_lines.append(f"{branch}PID={pid}")
            prefix = "    " if is_last_pid else "│   "
            items = list(weixin._chat_listeners.items())
            for ni, (name, chat) in enumerate(items):
                is_last = ni == len(items) - 1
                node = "└── " if is_last else "├── "
                tree_lines.append(f"{prefix}{node}[{chat.chat_type}] {name}")

        logger.info("\n" + "\n".join(tree_lines))
        logger.info("统一消息监听已启动 (Ctrl+C 退出)...")

        try:
            while not stop_event.is_set():
                alive = [n for n, t in threads.items() if t.is_alive()]
                if not alive:
                    logger.info("所有监听线程已退出")
                    break

                try:
                    pid, weixin, chat, msg = msg_queue.get(timeout=0.1)
                except Empty:
                    continue
                try:
                    self._emit(pid, weixin, chat, msg)
                except Exception:
                    logger.exception("事件分发异常 [PID=%d] [%s]", pid, chat.chat_name)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("正在停止监听线程...")
            stop_event.set()
            for t in threads.values():
                t.join(timeout=3)
            self._stop_event = None
            logger.info("监听已停止")

    def stop(self) -> None:
        """
        停止统一消息监听。

        可从其他线程调用。
        """
        if self._stop_event is not None:
            self._stop_event.set()
        for weixin in self._instances.values():
            weixin.move_back()

    def __str__(self) -> str:
        pids = self.pids
        return f"WeixinManager(instances={len(pids)}, pids={pids})"

    def __repr__(self) -> str:
        return self.__str__()
