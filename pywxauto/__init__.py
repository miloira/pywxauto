"""
pywxauto - 微信自动化库

用法:
    from pywxauto import Weixin, Event, Chat, SeparateChat

    # 也可以从子模块精确导入
    from pywxauto.wx import TextMessage, ImageMessage, Event
    from pywxauto.wx import SendError, OCRError
"""

try:
    # 优先加载编译后的 .pyd
    from pywxauto.wx import *
except ImportError:
    # 回退到多模块源码版本
    from pywxauto.core import *