"""
pywxauto 文件管理器模块。

包含 FileManager 和 ChatFile 类。
"""

from __future__ import annotations

import ctypes
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import uiautomation as auto
import win32gui

from . import _state
from .pim import PIM
from .windows import WeixinWindow
from . import input_wx, input_wm

import logging
logger = logging.getLogger(__name__)


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

    WINDOW_NAME = "聊天文件"
    FILE_LIST_CELL_CLASS = "mmui::FileListCell"
    MORE_BTN_AUTOMATION_ID = "main_tabbar.tabbar_setting"
    FILE_TYPE_FILTER_CLASS = "mmui::XTableCell"
    CONTEXT_MENU_WIN_CLASS = "mmui::XMenu"
    # 确认对话框的类名（微信 v4 使用 mmui::XDialog，浮动于桌面层级）
    CONFIRM_DIALOG_WIN_CLASS = "mmui::XDialog"
    SAVE_AS_MENU_ITEM_NAME = "另存为..."
    DOWNLOAD_TO_MENU_ITEM_NAME = "下载到..."
    DOWNLOAD_MENU_ITEM_NAME = "下载"
    DELETE_MENU_ITEM_NAME = "删除"

    def __init__(self, wx: "Weixin"):
        self.wx = wx
        self._win = auto.WindowControl(
            Name=self.WINDOW_NAME, searchDepth=1,
        )

    def _find_window(self) -> Optional[auto.WindowControl]:
        """查找并激活聊天文件窗口（独立窗口）"""
        self._win = auto.WindowControl(
            Name=self.WINDOW_NAME, searchDepth=1
        )
        if self._win.Exists(maxSearchSeconds=3):
            if not _state.background:
                self._win.SetActive()
            return self._win
        return None

    @PIM.guard
    def open(self, filter_type: str = "") -> bool:
        """
        打开聊天文件管理器窗口。

        Args:
            filter_type: 文件类型筛选，可选值:
                - "全部"、"文档"、"表格"、"图片"、"视频"等
                - "": 不筛选（默认）
        """
        self.wx.activate()

        # 先关闭已有的文件管理器窗口
        self.close()

        # 通过导航栏 TabBar 缩小搜索范围，点击"更多"按钮
        self.wx.navigator.switch_to("更多")

        # 点击"聊天文件"按钮
        chat_file_btn = self.wx._win.ButtonControl(
            Name="聊天文件", searchDepth=10
        )
        if not chat_file_btn.Exists(maxSearchSeconds=3):
            raise RuntimeError("未找到'聊天文件'按钮")

        input_wx.click(chat_file_btn)
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

        input_wx.click(filter_btn)
        time.sleep(0.5)
        return True

    @PIM.guard
    def close(self, method: str = "event") -> None:
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
                input_wx.click(close_btn)
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

    @PIM.guard
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
        input_wx.click(file_cell, button="right")
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

        input_wx.click(save_as_item)
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
        input_wx.send_keys(None, "{Alt}s")
        if not save_dialog.Exists(maxSearchSeconds=2):
            return True
        else:
            input_wx.send_keys(None, "{Esc}")
            return False

    @PIM.guard
    def download_to(self, file_cell, file_path: str) -> bool:
        """
        对文件列表中的某个文件执行"下载到"操作。

        流程与 save_file_as 一致，只是点击的菜单项为"下载到..."。

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
        input_wx.click(file_cell, button="right")
        time.sleep(0.5)

        # 2. 定位右键菜单
        menu = self._find_context_menu_by_point()
        if not menu:
            raise RuntimeError("未找到右键菜单")

        # 查找"下载到..."菜单项
        download_to_item = None
        for child in menu.GetChildren():
            if child.Name == self.DOWNLOAD_TO_MENU_ITEM_NAME:
                download_to_item = child
                break

        if not download_to_item:
            raise RuntimeError("未找到'下载到'菜单项")

        input_wx.click(download_to_item)
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
        input_wx.send_keys(None, "{Alt}s")
        if not save_dialog.Exists(maxSearchSeconds=2):
            return True
        else:
            input_wx.send_keys(None, "{Esc}")
            return False

    @PIM.guard
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
        input_wx.click(file_cell, button="right")
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

        input_wx.click(delete_item)
        time.sleep(0.5)

        # 在确认对话框中查找"删除"或"确定"按钮并点击
        # 微信 v4 的删除确认弹窗使用 mmui::XOutlineButton，Name="删除"
        confirm_btn = None

        # 优先查找 mmui::XOutlineButton 的"删除"按钮
        delete_btn = self._win.ButtonControl(
            ClassName="mmui::XOutlineButton", Name="删除",
        )
        if delete_btn.Exists(maxSearchSeconds=2):
            input_wx.click(delete_btn)
            time.sleep(0.5)
            return True
        return False

    @PIM.guard
    def download_file(self, file_cell, timeout: int = 60) -> bool:
        """
        下载文件列表中的某个文件。

        流程:
        1. 右键点击文件项 → 弹出微信右键菜单
        2. 点击"下载"菜单项 → 开始下载
        3. 轮询文件状态，等待 file_status 变为空（即已下载）

        Args:
            file_cell: mmui::FileListCell 控件对象（从 get_all_files 返回的 ChatFile._cell）
            timeout:   等待下载完成的超时时间（秒），默认 60 秒

        Returns:
            True 下载成功（状态变为已下载），False 下载超时

        Raises:
            RuntimeError: 聊天文件窗口未打开、右键菜单未弹出或未找到"下载"菜单项时抛出
        """
        fm_win = self._find_window()
        if not fm_win:
            raise RuntimeError("聊天文件窗口未打开")

        # 1. 右键点击文件项
        input_wx.click(file_cell, button="right")
        time.sleep(0.5)

        # 2. 定位右键菜单
        menu = self._find_context_menu_by_point()
        if not menu:
            raise RuntimeError("未找到右键菜单")

        # 查找"下载"菜单项
        download_item = None
        for child in menu.GetChildren():
            if child.Name == self.DOWNLOAD_MENU_ITEM_NAME:
                download_item = child
                break

        if not download_item:
            raise RuntimeError("未找到'下载'菜单项，文件可能已下载")

        input_wx.click(download_item)
        time.sleep(0.5)

        # 3. 轮询文件状态，等待下载完成
        # 下载完成后，文件的 Name 属性中不再包含"将在X天后无法下载"等状态文本，
        # 即 parse_file_cell_text 解析出的 file_status 为空字符串。
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # 重新读取文件项的 Name 属性（下载过程中会实时更新）
            cell_text = file_cell.Name
            if not cell_text:
                time.sleep(1)
                continue

            chat_file = self.parse_file_cell_text(cell_text)
            if chat_file and not chat_file.file_status:
                # file_status 为空表示已下载
                return True

            time.sleep(1)

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

        # 处理 source_name 以 " 未下载" 结尾的情况：
        # 微信文件列表中未下载的文件，"未下载"会紧跟在来源名称后面，
        # 被错误地解析为 source_name 的一部分。
        # 例如: "泡泡马特发货群 未下载 18:20 ..." 中 source_name 会被解析为
        # "泡泡马特发货群 未下载"，需要将 "未下载" 拆分到 file_status 中。
        if source_name.endswith(" 未下载"):
            source_name = source_name.rstrip(" 未下载")
            file_status = "未下载"

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

    @property
    def exists(self) -> bool:
        """聊天文件窗口是否存在"""
        return self._win.Exists(maxSearchSeconds=1)

    def __str__(self) -> str:
        if self._win.Exists(0, 0):
            return "FileManager(open)"
        return "FileManager(closed)"
