#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信自动化命令行工具 (WeChat Automation CLI)

通过命令行操作微信 4.x 客户端，支持发送消息、朋友圈功能。

用法:
    python wx-cli.py <command> --参数名 <参数值>

示例:
    python wx-cli.py send-text --to "张三" --content "你好"
    python wx-cli.py send-file --to "张三" --file "C:\\docs\\report.pdf"
    python wx-cli.py send-image --to "张三" --file "C:\\pics\\photo.jpg"
    python wx-cli.py send-at --to "测试群" --content "开会了" --members "张三" "李四"
    python wx-cli.py get-moments --count 5
    python wx-cli.py publish-moment --text "今天天气真好" --images "C:\\pics\\1.jpg"
"""

import argparse
import json
import sys
import os
import traceback

# 确保当前目录在 path 中（wx.py 在同目录下）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wx import Weixin, WxAutoError, MessageStatus


def get_weixin():
    """获取 Weixin 实例（自动连接第一个微信客户端）"""
    try:
        weixin = Weixin()
    except Exception as e:
        print(f"错误: 未检测到运行中的微信客户端，请先登录微信 ({e})", file=sys.stderr)
        sys.exit(1)
    return weixin


# ============================================================
# 消息发送命令
# ============================================================

def cmd_send_text(args):
    """发送文本消息"""
    weixin = get_weixin()
    status = weixin.send_text(args.to, args.content, timeout=args.timeout)
    print(f"发送状态: {status}")


def cmd_send_file(args):
    """发送文件"""
    if not os.path.exists(args.file):
        print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)
    weixin = get_weixin()
    status = weixin.send_file(args.to, args.file, timeout=args.timeout)
    print(f"发送状态: {status}")


def cmd_send_image(args):
    """发送图片"""
    if not os.path.exists(args.file):
        print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)
    weixin = get_weixin()
    status = weixin.send_image(args.to, args.file, timeout=args.timeout)
    print(f"发送状态: {status}")


def cmd_send_video(args):
    """发送视频"""
    if not os.path.exists(args.file):
        print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)
    weixin = get_weixin()
    status = weixin.send_video(args.to, args.file, timeout=args.timeout)
    print(f"发送状态: {status}")


def cmd_send_at(args):
    """在群聊中 @成员发送消息"""
    weixin = get_weixin()
    status = weixin.send_at(args.to, args.content, args.members, timeout=args.timeout)
    print(f"发送状态: {status}")


def cmd_send_emotion(args):
    """发送表情"""
    weixin = get_weixin()
    status = weixin.send_emotion(args.to, keyword=args.keyword, index=args.index, timeout=args.timeout)
    print(f"发送状态: {status}")


def cmd_send_collection(args):
    """发送收藏内容"""
    weixin = get_weixin()
    status = weixin.send_collection(args.to, args.keyword, timeout=args.timeout)
    print(f"发送状态: {status}")


def cmd_send_card(args):
    """发送名片"""
    weixin = get_weixin()
    result = weixin.send_card(args.to, args.share)
    print(f"发送结果: {'成功' if result else '失败'}")


# ============================================================
# 朋友圈命令
# ============================================================

def cmd_get_moments(args):
    """获取朋友圈动态"""
    weixin = get_weixin()
    moments = weixin.get_moments(count=args.count, position=args.position)
    results = []
    for m in moments:
        item = {}
        if hasattr(m, 'nickname'):
            item['nickname'] = m.nickname
        if hasattr(m, 'content'):
            item['content'] = m.content
        if hasattr(m, 'time'):
            item['time'] = str(m.time) if m.time else None
        if hasattr(m, 'likes'):
            item['likes'] = m.likes
        if hasattr(m, 'comments'):
            item['comments'] = m.comments
        results.append(item)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def cmd_publish_moment(args):
    """发布朋友圈"""
    weixin = get_weixin()
    images = args.images if args.images else None
    video = args.video if args.video else None
    remind = args.remind if args.remind else None
    permission_contacts = args.permission_contacts if args.permission_contacts else None
    permission_labels = args.permission_labels if args.permission_labels else None

    result = weixin.moment.publish(
        text=args.text,
        images=images,
        video=video,
        remind_contacts=remind,
        permission=args.permission,
        permission_contacts=permission_contacts,
        permission_labels=permission_labels,
    )
    print(f"发布结果: {'成功' if result else '失败'}")


# ============================================================
# 参数解析
# ============================================================

def build_parser():
    parser = argparse.ArgumentParser(
        description="微信自动化命令行工具（消息发送 & 朋友圈）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ---- 消息发送 ----

    # send-text
    p = subparsers.add_parser("send-text", help="发送文本消息")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--content", required=True, help="消息内容")
    p.add_argument("--timeout", type=float, default=5, help="超时时间（秒），默认 5")
    p.set_defaults(func=cmd_send_text)

    # send-file
    p = subparsers.add_parser("send-file", help="发送文件")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--file", required=True, help="文件绝对路径")
    p.add_argument("--timeout", type=float, default=30, help="超时时间（秒），默认 30")
    p.set_defaults(func=cmd_send_file)

    # send-image
    p = subparsers.add_parser("send-image", help="发送图片")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--file", required=True, help="图片绝对路径")
    p.add_argument("--timeout", type=float, default=10, help="超时时间（秒），默认 10")
    p.set_defaults(func=cmd_send_image)

    # send-video
    p = subparsers.add_parser("send-video", help="发送视频")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--file", required=True, help="视频绝对路径")
    p.add_argument("--timeout", type=float, default=60, help="超时时间（秒），默认 60")
    p.set_defaults(func=cmd_send_video)

    # send-at
    p = subparsers.add_parser("send-at", help="在群聊中 @成员发送消息")
    p.add_argument("--to", required=True, help="群聊名称")
    p.add_argument("--content", required=True, help="消息内容")
    p.add_argument("--members", required=True, nargs="+", help="要 @ 的成员昵称，空格分隔如 \"张三\" \"李四\"，传 \"所有人\" 可 @所有人")
    p.add_argument("--timeout", type=float, default=5, help="超时时间（秒），默认 5")
    p.set_defaults(func=cmd_send_at)

    # send-emotion
    p = subparsers.add_parser("send-emotion", help="发送表情")
    p.add_argument("--to", required=True, help="接收者昵称")
    p.add_argument("--keyword", default=None, help="表情搜索关键词，不传则发送自定义表情")
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

    # ---- 朋友圈 ----

    # get-moments
    p = subparsers.add_parser("get-moments", help="获取朋友圈动态")
    p.add_argument("--count", type=int, default=10, help="获取条数，默认 10")
    p.add_argument("--position", default="top", choices=["top", "current"], help="起始位置: top=从顶部, current=当前位置")
    p.set_defaults(func=cmd_get_moments)

    # publish-moment
    p = subparsers.add_parser("publish-moment", help="发布朋友圈")
    p.add_argument("--text", default=None, help="文本内容")
    p.add_argument("--images", nargs="+", default=None, help="图片路径列表（最多9张，与 --video 互斥）")
    p.add_argument("--video", default=None, help="视频路径（与 --images 互斥）")
    p.add_argument("--remind", nargs="+", default=None, help="提醒谁看的联系人昵称")
    p.add_argument("--permission", default=None, choices=["公开", "私密", "谁可以看", "不给谁看"], help="隐私设置")
    p.add_argument("--permission-contacts", nargs="+", default=None, help="隐私联系人列表")
    p.add_argument("--permission-labels", nargs="+", default=None, help="隐私标签列表")
    p.set_defaults(func=cmd_publish_moment)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except WxAutoError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n操作已取消", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
