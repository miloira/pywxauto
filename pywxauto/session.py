"""
pywxauto 会话模块。

包含 Navigator、Session、SessionItem 类。
"""

from __future__ import annotations

import re
import time
from typing import Optional

import uiautomation as auto
import win32gui

from . import _state
from .pim import PIM
from . import input_wx, input_wm
from .utils import rand_ratio as _rand_ratio

import logging
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
            if not _state.background:
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
