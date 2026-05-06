"""
pywxauto 命令行工具。

用法:
    python wx-cli.py <command> --参数名 <参数值>

命令列表:
    send-text       发送文本消息
    send-file       发送文件
    send-image      发送图片
    send-video      发送视频
    send-at         在群聊中 @成员发送消息
    send-emotion    发送表情
    send-collection 发送收藏内容
    send-card       发送名片
    create-note     创建笔记
    create-room     发起群聊
"""

import argparse
import sys

from pywxauto.wx import Weixin, MessageStatus


def _print_status(status: MessageStatus) -> int:
    """打印发送状态并返回退出码"""
    print(f"发送状态: {status.value}")
    return 0 if status == MessageStatus.SENT else 1


def cmd_send_text(args):
    """发送文本消息"""
    wx = Weixin(resize=False)
    status = wx.send_text(args.to, args.content, timeout=args.timeout)
    return _print_status(status)


def cmd_send_file(args):
    """发送文件"""
    wx = Weixin(resize=False)
    status = wx.send_file(args.to, args.file, timeout=args.timeout)
    return _print_status(status)


def cmd_send_image(args):
    """发送图片"""
    wx = Weixin(resize=False)
    status = wx.send_image(args.to, args.file, timeout=args.timeout)
    return _print_status(status)


def cmd_send_video(args):
    """发送视频"""
    wx = Weixin(resize=False)
    status = wx.send_video(args.to, args.file, timeout=args.timeout)
    return _print_status(status)


def cmd_send_at(args):
    """在群聊中 @成员发送消息"""
    wx = Weixin(resize=False)
    status = wx.send_at(args.to, args.content, args.members, timeout=args.timeout)
    return _print_status(status)


def cmd_send_emotion(args):
    """发送表情"""
    wx = Weixin(resize=False)
    status = wx.send_emotion(args.to, keyword=args.keyword, index=args.index, timeout=args.timeout)
    return _print_status(status)


def cmd_send_collection(args):
    """发送收藏内容"""
    wx = Weixin(resize=False)
    status = wx.send_collection(args.to, args.keyword, timeout=args.timeout)
    return _print_status(status)


def cmd_send_card(args):
    """发送名片"""
    wx = Weixin(resize=False)
    success = wx.send_card(args.to, args.share)
    print(f"发送结果: {'成功' if success else '失败'}")
    return 0 if success else 1


def cmd_create_note(args):
    """创建笔记"""
    wx = Weixin(resize=False)
    wx.create_note(args.content)
    print("笔记创建成功")
    return 0


def cmd_create_room(args):
    """发起群聊"""
    wx = Weixin(resize=False)
    if len(args.members) < 2:
        print("错误: 至少需要两个好友昵称才能创建群聊")
        return 1
    wx.create_room(args.members)
    print("群聊创建成功")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="wx-cli",
        description="pywxauto 微信自动化命令行工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # send-text
    p = subparsers.add_parser("send-text", help="发送文本消息")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--content", required=True, help="消息内容")
    p.add_argument("--timeout", type=float, default=5, help="超时时间（秒），默认 5")
    p.set_defaults(func=cmd_send_text)

    # send-file
    p = subparsers.add_parser("send-file", help="发送文件")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--file", required=True, help="文件路径")
    p.add_argument("--timeout", type=float, default=30, help="超时时间（秒），默认 30")
    p.set_defaults(func=cmd_send_file)

    # send-image
    p = subparsers.add_parser("send-image", help="发送图片")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--file", required=True, help="图片路径")
    p.add_argument("--timeout", type=float, default=10, help="超时时间（秒），默认 10")
    p.set_defaults(func=cmd_send_image)

    # send-video
    p = subparsers.add_parser("send-video", help="发送视频")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--file", required=True, help="视频路径")
    p.add_argument("--timeout", type=float, default=60, help="超时时间（秒），默认 60")
    p.set_defaults(func=cmd_send_video)

    # send-at
    p = subparsers.add_parser("send-at", help="在群聊中 @成员发送消息")
    p.add_argument("--to", required=True, help="群聊名称")
    p.add_argument("--content", required=True, help="消息内容")
    p.add_argument("--members", required=True, nargs="+", help="要 @ 的成员昵称，多个用空格分隔，传 '所有人' 可 @所有人")
    p.add_argument("--timeout", type=float, default=5, help="超时时间（秒），默认 5")
    p.set_defaults(func=cmd_send_at)

    # send-emotion
    p = subparsers.add_parser("send-emotion", help="发送表情")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--keyword", default=None, help="表情搜索关键词（如 '哈喽'），不传则发送自定义表情")
    p.add_argument("--index", type=int, default=1, help="选择第几个表情，从 1 开始，默认 1")
    p.add_argument("--timeout", type=float, default=5, help="超时时间（秒），默认 5")
    p.set_defaults(func=cmd_send_emotion)

    # send-collection
    p = subparsers.add_parser("send-collection", help="发送收藏内容")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--keyword", required=True, help="收藏搜索关键词")
    p.add_argument("--timeout", type=float, default=5, help="超时时间（秒），默认 5")
    p.set_defaults(func=cmd_send_collection)

    # send-card
    p = subparsers.add_parser("send-card", help="发送名片")
    p.add_argument("--to", required=True, help="接收名片的联系人昵称")
    p.add_argument("--share", required=True, help="要分享名片的联系人昵称")
    p.set_defaults(func=cmd_send_card)

    # create-note
    p = subparsers.add_parser("create-note", help="创建笔记")
    p.add_argument("--content", required=True, help="笔记内容")
    p.set_defaults(func=cmd_create_note)

    # create-room
    p = subparsers.add_parser("create-room", help="发起群聊")
    p.add_argument("--members", required=True, nargs="+", help="好友昵称列表（至少两个），多个用空格分隔")
    p.set_defaults(func=cmd_create_room)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
