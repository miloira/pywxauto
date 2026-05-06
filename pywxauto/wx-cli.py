"""
pywxauto 命令行工具。

用法:
    python -m pywxauto.wx-cli send-text --to <昵称> --content <内容>
    python -m pywxauto.wx-cli send-file --to <昵称> --file <文件路径>
    python -m pywxauto.wx-cli send-image --to <昵称> --file <图片路径>
"""

import argparse
import sys

from wx import Weixin, MessageStatus


def cmd_send_text(args):
    """发送文本消息"""
    wx = Weixin(resize=False)
    status = wx.send_text(args.to, args.content, timeout=args.timeout)
    print(f"发送状态: {status.value}")
    return 0 if status == MessageStatus.SENT else 1


def cmd_send_file(args):
    """发送文件"""
    wx = Weixin(resize=False)
    status = wx.send_file(args.to, args.file, timeout=args.timeout)
    print(f"发送状态: {status.value}")
    return 0 if status == MessageStatus.SENT else 1


def cmd_send_image(args):
    """发送图片"""
    wx = Weixin(resize=False)
    status = wx.send_image(args.to, args.file, timeout=args.timeout)
    print(f"发送状态: {status.value}")
    return 0 if status == MessageStatus.SENT else 1


def cmd_send_video(args):
    """发送视频"""
    wx = Weixin(resize=False)
    status = wx.send_video(args.to, args.file, timeout=args.timeout)
    print(f"发送状态: {status.value}")
    return 0 if status == MessageStatus.SENT else 1


def main():
    parser = argparse.ArgumentParser(
        prog="pywxauto",
        description="pywxauto 微信自动化命令行工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # send-text
    p_text = subparsers.add_parser("send-text", help="发送文本消息")
    p_text.add_argument("--to", required=True, help="接收者昵称")
    p_text.add_argument("--content", required=True, help="消息内容")
    p_text.add_argument("--timeout", type=float, default=5, help="等待发送完成的超时时间（秒），默认 5")
    p_text.set_defaults(func=cmd_send_text)

    # send-file
    p_file = subparsers.add_parser("send-file", help="发送文件")
    p_file.add_argument("--to", required=True, help="接收者昵称")
    p_file.add_argument("--file", required=True, help="文件路径")
    p_file.add_argument("--timeout", type=float, default=30, help="等待发送完成的超时时间（秒），默认 30")
    p_file.set_defaults(func=cmd_send_file)

    # send-image
    p_image = subparsers.add_parser("send-image", help="发送图片")
    p_image.add_argument("--to", required=True, help="接收者昵称")
    p_image.add_argument("--file", required=True, help="图片路径")
    p_image.add_argument("--timeout", type=float, default=10, help="等待发送完成的超时时间（秒），默认 10")
    p_image.set_defaults(func=cmd_send_image)

    # send-video
    p_video = subparsers.add_parser("send-video", help="发送视频")
    p_video.add_argument("--to", required=True, help="接收者昵称")
    p_video.add_argument("--file", required=True, help="视频路径")
    p_video.add_argument("--timeout", type=float, default=60, help="等待发送完成的超时时间（秒），默认 60")
    p_video.set_defaults(func=cmd_send_video)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
