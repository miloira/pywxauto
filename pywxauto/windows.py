"""
pywxauto 窗口类模块。

包含 WeixinWindow 基类、Login、VoipCallWindow、NoteEditorWindow。
"""

from __future__ import annotations

import ctypes
import time
from typing import Optional

import uiautomation as auto
import win32api
import win32con
import win32gui

from . import _state
from .pim import PIM
from . import input_wx, input_wm
from .utils import rand_ratio as _rand_ratio
from .exceptions import LoginError, WindowNotFoundError

import logging
logger = logging.getLogger(__name__)


class WeixinWindow:
    """
    微信窗口基类，封装通用的窗口操作。

    子类需要设置 self._win 为 uiautomation 的 WindowControl 实例。
    提供 activate、pin、unpin、minimize、maximize、restore、close 等通用操作，
    支持两种模式：
    - event=True（默认）: 通过 Windows 消息 API 操作，不需要窗口可见
    - event=False: 通过点击标题栏按钮操作，模拟用户行为
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

    @PIM.guard
    def activate(self) -> None:
        """激活窗口（置前并聚焦），后台模式下跳过"""
        self._window.SetActive()
        self._window.SetFocus()
        time.sleep(0.2)

    @PIM.guard
    def pin(self, event: bool = True, simulate_move: bool = True) -> None:
        """置顶窗口"""
        if event:
            self._window.SetTopmost(True)
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._PIN_BTN_CLASS, Name="置顶",
            )
            if btn.Exists(0, 0):
                input_wx.click(btn)

    @PIM.guard
    def unpin(self, event: bool = True, simulate_move: bool = True) -> None:
        """取消置顶窗口"""
        if event:
            self._window.SetTopmost(False)
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._PIN_BTN_CLASS, Name="取消置顶",
            )
            if btn.Exists(0, 0):
                input_wx.click(btn)

    @PIM.guard
    def minimize(self, event: bool = True, simulate_move: bool = True) -> None:
        """最小化窗口"""
        if event:
            self._window.Minimize()
        else:
            self.activate()
            btn = self._window.ButtonControl(
                ClassName=self._BTN_CLASS, Name="最小化",
            )
            if not btn.Exists(maxSearchSeconds=1):
                raise RuntimeError("未找到最小化按钮")
            input_wx.click(btn)

    @PIM.guard
    def maximize(self, event: bool = True, simulate_move: bool = True) -> None:
        """最大化/还原窗口"""
        if event:
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
                    input_wx.click(btn)
                    return
            raise RuntimeError("未找到最大化/还原按钮")

    def restore(self) -> None:
        """还原窗口"""
        self._window.Restore()

    @PIM.guard
    def close(self, event: bool = True, simulate_move: bool = True) -> None:
        """关闭窗口"""
        if event:
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
            input_wx.click(btn)


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

    def _ensure_exists(self) -> None:
        if not self._win.Exists(maxSearchSeconds=3):
            raise WindowNotFoundError("微信登录窗口未找到")

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
            Name=self.ENTER_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'进入微信'按钮")
        input_wx.click(btn)

        # 等待登录窗口消失
        for _ in range(timeout):
            if not self._win.Exists(maxSearchSeconds=1):
                logger.info("已进入微信")
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
            Name=self.SWITCH_ACCOUNT_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'切换账号'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

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
            Name=self.TRANSFER_ONLY_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'仅传输文件'按钮")
        input_wx.click(btn)
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
            Name=self.PROXY_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'网络代理设置'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

        # 等待代理设置页面出现
        back_btn = self._win.ButtonControl(
            ClassName="mmui::XButton",
            Name=self.PROXY_BACK_BTN_NAME,
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
            Name=self.PROXY_BACK_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'返回'按钮")
        input_wx.click(btn)
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
            Name=self.PROXY_SWITCH_NAME,
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'使用代理'开关")
        input_wx.click(sw)
        time.sleep(0.5)

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
            Name=self.PROXY_SWITCH_NAME,
        )
        if not sw.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'使用代理'开关")
        input_wx.click(sw)
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
            input_wx.send_keys(edit, value)
        time.sleep(0.2)

    def _get_proxy_field(self, name: str) -> str:
        """获取代理表单字段的值"""
        edit = self._find_proxy_edit(name)
        vp = edit.GetValuePattern()
        if vp:
            return vp.Value or ""
        return ""

    @PIM.guard
    def set_proxy(self, address: str = "", port: str = "",
                  username: str = "", password: str = "") -> None:
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
            Name=self.PROXY_SAVE_BTN_NAME,
        )
        if not btn.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到'保存'按钮")
        input_wx.click(btn)
        time.sleep(0.5)

    @PIM.guard
    def close(self, event: bool = True, simulate_move: bool = True) -> None:
        """
        关闭登录窗口。

        Args:
            event: True — 通过 WindowPattern 关闭（默认）
                         False — 点击标题栏"关闭"按钮
            simulate_move: 是否模拟鼠标移动（仅 event=False 时有效）
        """
        self._ensure_exists()
        if event:
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
            input_wx.click(btn)
        time.sleep(0.3)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "Login(closed)"
        nick = self.nickname
        return f"Login(user={nick!r})"


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

    def _ensure_exists(self) -> None:
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError("通话窗口未找到")

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

    @PIM.guard
    def toggle_mic(self) -> None:
        """切换麦克风开关"""
        btn = self._find_toolbar_button("麦克风已开", "麦克风已关")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def toggle_speaker(self) -> None:
        """切换扬声器开关"""
        btn = self._find_toolbar_button("扬声器已开", "扬声器已关")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def toggle_camera(self) -> None:
        """切换摄像头开关（仅视频通话）"""
        btn = self._find_toolbar_button("摄像头已开", "摄像头已关", "无摄像头")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def cancel(self) -> None:
        """取消通话（呼叫中未接通时）"""
        btn = self._find_toolbar_button("取消")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def hangup(self) -> None:
        """挂断通话（通话中）"""
        btn = self._find_toolbar_button("挂断")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def end_call(self) -> None:
        """结束通话（自动识别取消/挂断）"""
        try:
            btn = self._find_toolbar_button("取消", "挂断")
        except RuntimeError:
            raise RuntimeError("未找到取消或挂断按钮")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def switch_to_video(self) -> None:
        """切换到视频通话（通话中可用）"""
        btn = self._find_toolbar_button("切换到视频通话")
        input_wx.click(btn)
        time.sleep(0.3)

    @PIM.guard
    def pin(self) -> None:
        """置顶窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::PinnedButton", Name="置顶",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @PIM.guard
    def minimize(self) -> None:
        """最小化通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="最小化",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @PIM.guard
    def maximize(self) -> None:
        """最大化通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="最大化",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @PIM.guard
    def close(self) -> None:
        """关闭通话窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(
            ClassName="mmui::XButton", Name="关闭",
        )
        if btn.Exists(0, 0):
            input_wx.click(btn)
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

    def _refresh_win(self) -> None:
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

    def _ensure_exists(self) -> None:
        self._refresh_win()
        if not self._win.Exists(maxSearchSeconds=3):
            raise RuntimeError("笔记编辑窗口未找到")

    def activate(self) -> None:
        self._ensure_exists()
        super().activate()

    # -- 笔记窗口特有的 pin/unpin（Chrome WebView 按钮无 ClassName 区分） --

    def pin(self, **kwargs) -> None:
        """置顶窗口（通过标题栏按钮）"""
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="置顶")
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    def unpin(self, **kwargs) -> None:
        """取消置顶窗口"""
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="取消置顶")
        if btn.Exists(0, 0):
            input_wx.click(btn)
            time.sleep(0.2)

    @property
    def is_pinned(self) -> bool:
        self._ensure_exists()
        btn = self._win.ButtonControl(Name="取消置顶")
        return btn.Exists(0, 0)

    def minimize(self, **kwargs) -> None:
        """最小化窗口（Chrome WebView 优先用窗口 API）"""
        self._ensure_exists()
        self._win.Minimize()
        time.sleep(0.2)

    def maximize(self, **kwargs) -> None:
        """最大化/还原窗口"""
        self._ensure_exists()
        if self._win.IsMaximize():
            self._win.Restore()
        else:
            self._win.Maximize()
        time.sleep(0.2)

    def close(self, **kwargs) -> None:
        """关闭笔记窗口（窗口有两个关闭按钮，取可见的）"""
        self._ensure_exists()
        btns = self._win.GetChildren()
        for child in btns:
            btn = child.ButtonControl(Name="关闭")
            if btn.Exists(0, 0):
                rect = btn.BoundingRectangle
                if rect.width() > 0 and rect.height() > 0:
                    input_wx.click(btn)
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

    @PIM.guard
    def focus_editor(self, force_click: bool = True) -> None:
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
                input_wx.click(container)
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

    @PIM.guard
    def set_content(self, text: str) -> None:
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

    @PIM.guard
    def type_text(self, text: str) -> None:
        """
        在编辑器中输入文本（追加到当前光标位置）。

        text: 要输入的文本
        """
        self.focus_editor()
        editor = self._editor
        if not editor.Exists(maxSearchSeconds=2):
            raise RuntimeError("未找到笔记编辑器输入控件")
        input_wx.send_keys(editor, text)
        time.sleep(0.2)

    @PIM.guard
    def clear(self) -> None:
        """清空编辑器内容"""
        self.focus_editor()
        editor = self._editor
        if editor.Exists(maxSearchSeconds=2):
            input_wx.send_keys(editor, "{Ctrl}a{Del}")
            time.sleep(0.2)

    @PIM.guard
    def select_all(self) -> None:
        """全选编辑器内容"""
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Ctrl}a")
        time.sleep(0.1)

    # -- 富文本格式快捷键 --
    # 底部工具栏渲染在 WebView 内部，不暴露为 UI Automation 控件，
    # 因此通过键盘快捷键操作格式。

    @PIM.guard
    def begin_voice_input(self) -> None:
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

    @PIM.guard
    def end_voice_input(self) -> None:
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

    @PIM.guard
    def add_file(self, file_path: str) -> None:
        """
        通过 Ctrl+O 打开文件选择对话框，输入路径并确认添加文件。

        file_path: 文件绝对路径
        """
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Ctrl}O")
        time.sleep(1)

        # 系统文件选择对话框
        dlg = auto.WindowControl(ClassName="#32770")
        if not dlg.Exists(maxSearchSeconds=5):
            raise RuntimeError("文件选择对话框未弹出")

        # Alt+N 激活文件名输入框，通过 ValuePattern 直接设置路径
        input_wx.send_keys(dlg, "{Alt}N")
        time.sleep(0.3)
        edit = dlg.ComboBoxControl(AutomationId="1148").EditControl()
        if not edit.Exists(0, 0):
            edit = dlg.EditControl(AutomationId="1148")
        edit.GetValuePattern().SetValue(file_path)
        time.sleep(0.3)
        # Alt+O 点击打开
        input_wx.send_keys(dlg, "{Alt}O")
        time.sleep(0.5)

    @PIM.guard
    def bold(self) -> None:
        """加粗（Ctrl+B）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}B")
        time.sleep(0.1)

    @PIM.guard
    def italic(self) -> None:
        """斜体（Ctrl+I）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}I")
        time.sleep(0.1)

    @PIM.guard
    def underline(self) -> None:
        """下划线（Ctrl+U）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}U")
        time.sleep(0.1)

    @PIM.guard
    def highlight(self) -> None:
        """高亮（Ctrl+Shift+H）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}{Shift}H")
        time.sleep(0.1)

    @PIM.guard
    def undo(self) -> None:
        """撤销（Ctrl+Z）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}z")
        time.sleep(0.1)

    @PIM.guard
    def redo(self) -> None:
        """重做（Ctrl+Y）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}y")
        time.sleep(0.1)

    @PIM.guard
    def new_line(self) -> None:
        """换行（Enter）"""
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Enter}")
        time.sleep(0.1)

    @PIM.guard
    def save(self) -> None:
        """保存笔记（Ctrl+S）"""
        self.focus_editor(force_click=False)
        input_wx.send_keys(self._editor, "{Ctrl}s")
        time.sleep(0.3)

    @PIM.guard
    def add_tags(self, *tags: str) -> None:
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
            input_wx.send_keys(self._editor, "{Ctrl}T")
            time.sleep(1)
            # 标签弹窗内的输入框不暴露为 UI Automation 控件，
            # 需要通过窗口级别 SendKeys 输入
            input_wx.send_keys(None, tag)
            time.sleep(0.3)
            input_wx.send_keys(None, "{Down}")
            input_wx.send_keys(None, "{Enter}")
            time.sleep(0.3)
        # 按 Esc 关闭标签弹窗
        input_wx.send_keys(None, "{Esc}")
        time.sleep(0.2)

    @PIM.guard
    def paste(self) -> None:
        """粘贴剪贴板内容（Ctrl+V）"""
        self.focus_editor()
        input_wx.send_keys(self._editor, "{Ctrl}v")
        time.sleep(0.2)

    @PIM.guard
    def paste_file(self, file_path: str) -> None:
        """
        通过剪贴板粘贴文件到笔记中。

        file_path: 文件路径
        """
        self.focus_editor()
        input_wx.paste([file_path])
        time.sleep(0.5)

    def __str__(self) -> str:
        if not self._win.Exists(0, 0):
            return "NoteEditorWindow(closed)"
        content = self.content
        preview = content[:30] + "..." if len(content) > 30 else content
        return f"NoteEditorWindow(content={preview!r})"
