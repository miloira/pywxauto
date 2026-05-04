"""
pywxauto 聊天模块。

包含 Chat（主窗口聊天区域）和 SeparateChat（独立窗口聊天）类。
"""

from __future__ import annotations

import ctypes
import io
import os
import re
import tempfile
import time
from typing import Optional

import uiautomation as auto
import win32api
import win32con
import win32gui
from PIL import Image

from pywxauto import _state
from pywxauto.pim import PIM
from pywxauto.exceptions import SendError, OCRError
from pywxauto.messages import (
    SenderType, MessageStatus,
    Message, TextMessage, QuoteMessage, VoiceMessage, ImageMessage,
    VideoMessage, FileMessage, LocationMessage, LinkMessage,
    EmotionMessage, MergeMessage, PersonalCardMessage, NoteMessage,
    MusicMessage, CardMessage, SystemMessage, VoipMessage,
    TransferMessage, RedPacketMessage, OtherMessage,
    MSG_CLASS_TO_EVENT as _MSG_CLASS_TO_EVENT,
)
from pywxauto import input_wx, input_wm
from pywxauto.utils import (
    rand_ratio as _rand_ratio,
    is_url as _is_url, download_to_temp as _download_to_temp,
    get_hwnd,
)
from pywxauto.capture import capture_window, capture_control
from pywxauto.windows import WeixinWindow, VoipCallWindow

import logging
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
                ctrl, list_center_x, self.current_name or "对方", hwnd,
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

    @PIM.guard
    def send_text(self, content: str) -> MessageStatus:
        """
        在当前会话中发送文本消息，返回发送状态。

        通过 ValuePattern 设置输入框文本，然后按回车键发送。
        后台模式下使用 vm_sendkeys 输入文本，避免窗口被激活。
        """
        self._activate_window()

        # 输入方式
        field = self._input_field
        if not field.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到聊天输入框")

        if _state.background:
            field.GetValuePattern().SetValue(content)
            # # 后台模式：先聚焦输入框，再通过虚拟按键输入
            # input_wx.click(field)
            # time.sleep(0.1)
            # input_wx.send_keys(field, content)
        else:
            # 前台模式：直接设置文本
            field.GetValuePattern().SetValue(content)

        send_btn = self._win.ButtonControl(Name="发送")
        input_wx.click(send_btn)

        # 回车发送
        # input_wx.send_keys(self._win, "{Enter}")

        # 发送后校验：输入框应已清空
        remaining = self._get_input_value()
        if remaining:
            raise SendError(
                f"发送后输入框未清空: Value={remaining!r}，消息可能未发出"
            )

        return self.check_text_message_status(content)

    @PIM.guard
    def send_file(self, file_path: "str | list[str]") -> MessageStatus:
        """
        在当前会话中发送文件，返回最后一个文件的发送状态。

        Args:
            file_path: 文件路径或路径列表，支持本地路径和网络 URL

        Returns:
            最后一个文件的发送状态
        """
        return self._send_media(file_path, "文件", self.check_file_message_status)

    @PIM.guard
    def send_image(self, file_path: "str | list[str]") -> MessageStatus:
        """
        在当前会话中发送图片，返回最后一张图片的发送状态。

        Args:
            file_path: 图片路径或路径列表，支持本地路径和网络 URL

        Returns:
            最后一张图片的发送状态
        """
        return self._send_media(file_path, "图片", self.check_image_message_status)

    @PIM.guard
    def send_video(self, file_path: "str | list[str]") -> MessageStatus:
        """
        在当前会话中发送视频，返回最后一个视频的发送状态。

        Args:
            file_path: 视频路径或路径列表，支持本地路径和网络 URL

        Returns:
            最后一个视频的发送状态
        """
        return self._send_media(file_path, "视频", self.check_video_message_status)

    def _send_media(self, file_path: "str | list[str]", label: str,
                    check_status: callable) -> MessageStatus:
        """
        发送文件/图片/视频的通用实现。

        支持单个路径或路径列表，多文件时一次性粘贴所有文件后发送。
        支持本地路径和网络 URL（自动下载到临时目录）。

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

        # 预处理：下载网络 URL 到临时文件
        local_paths: list[str] = []
        tmp_files: list[str] = []
        for p in paths:
            if _is_url(p):
                tmp = _download_to_temp(p)
                local_paths.append(tmp)
                tmp_files.append(tmp)
            else:
                local_paths.append(p)

        try:
            self.clear_input()

            # 一次性粘贴所有文件
            input_wx.paste(local_paths)

            doc_len = self._get_input_doc_length()
            if doc_len == 0:
                raise SendError(
                    f"{label}粘贴校验失败: 输入框文档长度为 0，{label}可能未粘贴成功"
                )

            input_wx.send_keys(self._win, "{Enter}")

            remaining_len = self._get_input_doc_length()
            if remaining_len > 0:
                raise SendError(
                    f"发送后输入框未清空: 文档长度={remaining_len}，{label}可能未发出"
                )

            return check_status()
        finally:
            # 清理临时文件
            for tmp in tmp_files:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

    @PIM.guard
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
            input_wx.paste(content)
            time.sleep(0.2)

        input_wx.send_keys(self._win, "{Enter}")

        # 发送后校验：输入框应已清空
        remaining = self._get_input_value()
        if remaining:
            raise SendError(
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

        input_wx.click(fav_btn)
        time.sleep(0.5)

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

        self._activate_window()

        # 1. 打开收藏选择面板
        self._open_collection_panel()
        time.sleep(0.5)

        # 2. 在搜索框中输入关键词
        search_edit = self._find_fav_search_edit()
        input_wx.click(search_edit)
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

        input_wx.click(matched_item)
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

        input_wx.click(send_btn)
        time.sleep(0.5)

        # 6. 验证面板已关闭（表示发送成功）
        check_list = self._win.ListControl(
            ClassName=self.FAV_DETAIL_LIST_CLASS,
            AutomationId=self.FAV_DETAIL_LIST_ID,
        )
        if check_list.Exists(maxSearchSeconds=1):
            raise SendError("发送收藏失败，选择面板未关闭")

        logger.info("收藏发送成功")
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

    @PIM.guard
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

        self._activate_window()

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
                input_wx.click(search_edit)
                time.sleep(0.2)
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
                raise SendError(f"发送{label}失败，表情面板未关闭")

            logger.info("表情发送成功")
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

        input_wx.click(emoji_btn)
        time.sleep(0.5)

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

        rect = custom_tab.BoundingRectangle
        auto.Click(
            int(rect.left + rect.width() / 2),
            int(rect.top + rect.height() / 2),
        )

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

        list_rect = lc.BoundingRectangle
        list_center_x = (list_rect.left + list_rect.right) // 2

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
                    ctrl, list_center_x, chat_name, hwnd,
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
        ctrl, list_center_x: int, chat_name: str,
        hwnd: int = 0,
    ) -> tuple[str, SenderType, tuple]:
        """
        判断消息发送者、来源类型，并检测气泡区域坐标。

        策略1: 截图后从左右两侧向内扫描非白色像素，判断头像在哪侧
        策略2: 通过气泡颜色（绿色/灰色）判断
        策略3: 通过控件水平位置判断（适用于图片/视频等无气泡消息）

        Returns:
            (sender, sender_type, bubble_rect)
            bubble_rect 为气泡区域屏幕坐标 (left, top, right, bottom)，空元组表示未检测到
        """
        sender, sender_type, bubble_rect = Chat._detect_sender_by_pixel(
            ctrl, chat_name, hwnd,
        )
        # 像素分析失败时，用控件位置兜底
        if sender_type == SenderType.OTHER:
            sender, sender_type = Chat._detect_sender_by_position(
                ctrl, list_center_x, chat_name,
            )
        return sender, sender_type, bubble_rect

    @staticmethod
    def _detect_sender_by_position(
        ctrl, list_center_x: int, chat_name: str,
    ) -> tuple[str, SenderType]:
        """
        策略3: 通过控件水平位置判断发送者。

        微信中对方消息偏左，自己消息偏右。
        控件中心 x > 列表中心 x → 自己发的
        控件中心 x < 列表中心 x → 对方发的
        """
        try:
            rect = ctrl.BoundingRectangle
            ctrl_center_x = (rect.left + rect.right) // 2
        except Exception:
            return "", SenderType.OTHER

        if ctrl_center_x > list_center_x:
            return "我", SenderType.SELF
        return chat_name, SenderType.FRIEND

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
                png_bytes = capture_control(hwnd, ctrl, offset_right=15)
                img = Image.open(io.BytesIO(png_bytes))
            else:
                tmp_path = os.path.join(tempfile.gettempdir(), "_wxuia_msg.png")
                try:
                    ctrl.CaptureToImage(tmp_path)
                    img = Image.open(tmp_path)
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
        except Exception:
            return "", SenderType.OTHER, ()

        w, h = img.size

        # ---- 策略1: 边缘扫描 ----
        edge_result = Chat._detect_sender_by_edge_scan(img, w, h, chat_name)
        edge_scan_y, edge_left_x, edge_right_x = -1, -1, -1
        if edge_result is not None:
            sender, sender_type, edge_scan_y, edge_left_x, edge_right_x = edge_result
        else:
            # ---- 策略2: 气泡颜色 ----
            sender, sender_type = Chat._detect_sender_by_bubble_color(img, w, h, chat_name)

        # ---- 检测气泡区域 ----
        bubble_left, bubble_right = Chat._detect_bubble_rect(img, w, h, sender_type)

        # ---- 调试：标记扫描点和气泡区域并保存图片 ----
        try:
            from PIL import ImageDraw
            debug_img = img.copy()
            draw = ImageDraw.Draw(debug_img)
            ms = 6  # marker size
            # 边缘扫描：左侧（蓝色）
            if edge_left_x >= 0:
                draw.ellipse(
                    [edge_left_x - ms, edge_scan_y - ms,
                     edge_left_x + ms, edge_scan_y + ms],
                    fill="blue", outline="white",
                )
                draw.text((edge_left_x + 10, edge_scan_y - 8),
                          f"L({edge_left_x},{edge_scan_y})", fill="blue")
            # 边缘扫描：右侧（红色）
            if edge_right_x >= 0:
                draw.ellipse(
                    [edge_right_x - ms, edge_scan_y - ms,
                     edge_right_x + ms, edge_scan_y + ms],
                    fill="red", outline="white",
                )
                draw.text((edge_right_x - 90, edge_scan_y - 8),
                          f"R({edge_right_x},{edge_scan_y})", fill="red")
            # 气泡区域（绿色矩形）
            if bubble_left > 0 or bubble_right > 0:
                scan_y = 38
                draw.line([(bubble_left, scan_y), (bubble_right, scan_y)],
                          fill="green", width=2)
                draw.ellipse(
                    [bubble_left - ms, scan_y - ms,
                     bubble_left + ms, scan_y + ms],
                    fill="green", outline="white",
                )
                draw.text((bubble_left + 10, scan_y + 10),
                          f"BL({bubble_left})", fill="green")
                draw.ellipse(
                    [bubble_right - ms, scan_y - ms,
                     bubble_right + ms, scan_y + ms],
                    fill="lime", outline="white",
                )
                draw.text((bubble_right - 80, scan_y + 10),
                          f"BR({bubble_right})", fill="lime")
            # 发送者标注
            draw.text((5, 5), f"{sender} ({sender_type.value})", fill="yellow")
            debug_img.save(os.path.join(".", "_debug_edge_scan.png"))
        except Exception:
            pass
        # ---- 调试结束 ----

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

    @staticmethod
    def _detect_sender_by_bubble_color(
        img: "Image.Image", w: int, h: int, chat_name: str,
    ) -> tuple[str, SenderType]:
        """
        策略3: 通过气泡颜色判断发送者。

        微信气泡颜色规则：
        - 绿色气泡：自己发的消息 (G > 180, G-R > 50, G-B > 80)
        - 灰色/白色气泡：对方发的消息 (R,G,B 接近且 > 200)
        """
        green_count = 0
        gray_count = 0

        sample_rows = [h // 3, h // 2, h * 2 // 3]
        for y in sample_rows:
            for x in range(w):
                r, g, b = img.getpixel((x, y))[:3]
                if g > 180 and g - r > 50 and g - b > 80:
                    green_count += 1
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

            png_bytes = capture_window(hwnd)
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
                if not _state.background:
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
                if not _state.background:
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
            png_bytes = capture_window(hwnd)
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

            png_bytes = capture_window(hwnd)
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

            png_bytes = capture_window(hwnd)
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
    def send_text(self, content: str) -> MessageStatus:
        self.activate()
        return super().send_text(content)

    @PIM.guard
    def send_file(self, file_path: "str | list[str]") -> MessageStatus:
        self.activate()
        return super().send_file(file_path)

    @PIM.guard
    def send_image(self, file_path: "str | list[str]") -> MessageStatus:
        self.activate()
        return super().send_image(file_path)

    @PIM.guard
    def send_video(self, file_path: "str | list[str]") -> MessageStatus:
        self.activate()
        return super().send_video(file_path)

    @PIM.guard
    def send_at(self, content: str, at_members: list[str]) -> MessageStatus:
        self.activate()
        return super().send_at(content, at_members)

    @PIM.guard
    def send_collection(self, keyword: str) -> bool:
        self.activate()
        return super().send_collection(keyword)

    @PIM.guard
    def send_emotion(self, keyword: str = None, index: int = 1) -> bool:
        self.activate()
        return super().send_emotion(keyword, index)

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
        ctypes.windll.user32.MoveWindow(hwnd, -9999, 0,
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
