"""
pywxauto 全局状态模块。

存放跨模块共享的可变状态（如后台模式标志）。
各模块通过 import _state 引用，避免循环依赖。
"""

# 全局后台模式标志，由 Weixin.__init__ 设置
background: bool = False
