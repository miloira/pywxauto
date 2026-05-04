"""
pywxauto - 微信自动化库

模块结构:
    _state.py          - 全局可变状态
    exceptions.py      - 异常体系
    utils.py           - 底层工具函数（注册表、剪贴板、路径检测等）
    input_wm.py        - 底层 SendMessage 输入（窗口句柄级别）
    input_wx.py        - 控件级输入封装（根据 background 自动选择前台/后台）
    pim.py             - PIM 物理输入监控器
    messages.py        - 消息类体系（Event、Message 及所有子类）
    capture.py         - 截图工具
    windows.py         - 窗口基类（WeixinWindow、Login、VoipCallWindow、NoteEditorWindow）
    session.py         - 会话模块（Navigator、Session、SessionItem）
    friend_circle.py   - 朋友圈（FriendCircle、Moment）
    file_manager.py    - 文件管理器（FileManager、ChatFile）
    chat.py            - 聊天模块（Chat、SeparateChat）
    core.py            - 主入口（Weixin）

用法:
    from pywxauto import Weixin, Event, Chat, SeparateChat

    # 也可以从子模块精确导入
    from pywxauto.messages import TextMessage, ImageMessage, Event
    from pywxauto.exceptions import SendError, OCRError
    from pywxauto.input_wx import click, send_keys, paste
"""

from .core import *
