"""
pywxauto 异常体系。
"""


class WxAutoError(Exception):
    """pywxauto 异常基类"""
    pass


class WindowNotFoundError(WxAutoError):
    """窗口或控件未找到"""
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
