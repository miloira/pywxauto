"""
pywxauto 朋友圈模块。

包含 FriendCircle 和 Moment 类。
"""

from __future__ import annotations

import re
import time
from typing import Optional

import uiautomation as auto
import win32api
import win32con
import win32gui

from pywxauto import _state
from pywxauto.pim import PIM
from pywxauto.windows import WeixinWindow
from pywxauto import input_wx, input_wm
from pywxauto.utils import rand_ratio as _rand_ratio

import logging
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
            if not _state.background:
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
