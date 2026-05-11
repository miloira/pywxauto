#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信自动化命令行工具 (WeChat Automation CLI)

通过命令行操作微信 4.x 客户端，支持发送消息、联系人管理、群聊操作、朋友圈功能。

用法:
    python wx-cli.py <command> --参数名 <参数值>

示例:
    python wx-cli.py send-text --to "张三" --content "你好"
    python wx-cli.py send-file --to "张三" --file "C:\\docs\\report.pdf"
    python wx-cli.py get-contact-profile --nickname "张三"
    python wx-cli.py create-room --members "张三" "李四" "王五"
    python wx-cli.py send-at --to "测试群" --content "开会了" --members "张三" "李四"
    python wx-cli.py get-moments --count 5
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
# 联系人操作命令
# ============================================================

def cmd_get_contact_profile(args):
    """获取联系人资料"""
    weixin = get_weixin()
    profile = weixin.get_contact_profile(args.nickname)
    print(json.dumps(profile, ensure_ascii=False, indent=2))


def cmd_set_contact_remark(args):
    """设置联系人备注"""
    weixin = get_weixin()
    weixin.set_contact_remark(args.nickname, args.remark)
    print(f"已设置 {args.nickname} 的备注为: {args.remark}")


def cmd_add_contact_label(args):
    """添加联系人标签"""
    weixin = get_weixin()
    weixin.add_contact_label(args.nickname, args.labels)
    print(f"已为 {args.nickname} 添加标签: {', '.join(args.labels)}")


def cmd_remove_contact_label(args):
    """移除联系人标签"""
    weixin = get_weixin()
    weixin.remove_contact_label(args.nickname, args.labels)
    print(f"已移除 {args.nickname} 的标签: {', '.join(args.labels)}")


def cmd_set_contact_star(args):
    """设为星标朋友"""
    weixin = get_weixin()
    weixin.set_contact_star(args.nickname)
    print(f"已将 {args.nickname} 设为星标朋友")


def cmd_cancel_contact_star(args):
    """取消星标朋友"""
    weixin = get_weixin()
    weixin.cancel_contact_star(args.nickname)
    print(f"已取消 {args.nickname} 的星标")


def cmd_black_contact(args):
    """加入黑名单"""
    weixin = get_weixin()
    weixin.black_contact(args.nickname)
    print(f"已将 {args.nickname} 加入黑名单")


def cmd_unblack_contact(args):
    """移出黑名单"""
    weixin = get_weixin()
    weixin.unblack_contact(args.nickname)
    print(f"已将 {args.nickname} 移出黑名单")


def cmd_delete_contact(args):
    """删除联系人"""
    weixin = get_weixin()
    weixin.delete_contact(args.nickname)
    print(f"已删除联系人: {args.nickname}")


def cmd_add_friend(args):
    """添加朋友"""
    weixin = get_weixin()
    weixin.add_friend(
        keyword=args.keyword,
        message=args.message,
        remark=args.remark,
        permission=args.permission,
        hide_my_posts=args.hide_my_posts,
        hide_their_posts=args.hide_their_posts,
    )
    print(f"已发送好友申请: {args.keyword}")


def cmd_get_friend_permission(args):
    """获取联系人朋友权限"""
    weixin = get_weixin()
    perm = weixin.get_friend_permission(args.nickname)
    print(json.dumps(perm, ensure_ascii=False, indent=2))


def cmd_set_friend_permission(args):
    """设置联系人朋友权限"""
    weixin = get_weixin()
    weixin.set_friend_permission(
        args.nickname,
        permission=args.permission,
        hide_my_posts=args.hide_my_posts,
        hide_their_posts=args.hide_their_posts,
    )
    print(f"已设置 {args.nickname} 的朋友权限")


# ============================================================
# 群聊操作命令
# ============================================================

def cmd_create_room(args):
    """发起群聊"""
    if len(args.members) < 2:
        print("错误: 发起群聊至少需要两个好友", file=sys.stderr)
        sys.exit(1)
    weixin = get_weixin()
    weixin.create_room(args.members)
    print(f"已发起群聊，成员: {', '.join(args.members)}")


def cmd_set_room_name(args):
    """设置群聊名称"""
    weixin = get_weixin()
    weixin.set_room_name(args.nickname, args.name)
    print(f"已设置群聊 {args.nickname} 的名称为: {args.name}")


def cmd_set_room_announcement(args):
    """设置群公告"""
    weixin = get_weixin()
    weixin.set_room_announcement(args.nickname, args.content)
    print(f"已设置群聊 {args.nickname} 的群公告")


def cmd_add_room_members(args):
    """添加群成员"""
    weixin = get_weixin()
    weixin.add_room_members(args.nickname, args.members)
    print(f"已向群聊 {args.nickname} 添加成员: {', '.join(args.members)}")


def cmd_remove_room_members(args):
    """移除群成员"""
    weixin = get_weixin()
    weixin.remove_room_members(args.nickname, args.members)
    print(f"已从群聊 {args.nickname} 移除成员: {', '.join(args.members)}")


def cmd_exit_room(args):
    """退出群聊"""
    weixin = get_weixin()
    weixin.exit_room(args.nickname)
    print(f"已退出群聊: {args.nickname}")


def cmd_pin_chat(args):
    """置顶会话"""
    weixin = get_weixin()
    weixin.pin_chat(args.nickname)
    print(f"已置顶会话: {args.nickname}")


def cmd_unpin_chat(args):
    """取消置顶"""
    weixin = get_weixin()
    weixin.unpin_chat(args.nickname)
    print(f"已取消置顶: {args.nickname}")


def cmd_mute_chat(args):
    """消息免打扰"""
    weixin = get_weixin()
    weixin.mute_chat(args.nickname)
    print(f"已开启 {args.nickname} 的消息免打扰")


def cmd_unmute_chat(args):
    """取消免打扰"""
    weixin = get_weixin()
    weixin.unmute_chat(args.nickname)
    print(f"已关闭 {args.nickname} 的消息免打扰")


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
# 其他命令
# ============================================================

def cmd_create_note(args):
    """创建笔记"""
    weixin = get_weixin()
    weixin.create_note(args.content)
    print("笔记创建成功")


def cmd_get_self_profile(args):
    """获取当前登录账号资料"""
    weixin = get_weixin()
    profile = weixin.get_self_profile()
    print(json.dumps(profile, ensure_ascii=False, indent=2))


# ============================================================
# 参数解析
# ============================================================

def build_parser():
    parser = argparse.ArgumentParser(
        description="微信自动化命令行工具",
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

    # ---- 联系人操作 ----

    # get-contact-profile
    p = subparsers.add_parser("get-contact-profile", help="获取联系人资料")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_get_contact_profile)

    # set-contact-remark
    p = subparsers.add_parser("set-contact-remark", help="设置联系人备注")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.add_argument("--remark", required=True, help="新备注名")
    p.set_defaults(func=cmd_set_contact_remark)

    # add-contact-label
    p = subparsers.add_parser("add-contact-label", help="添加联系人标签")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.add_argument("--labels", required=True, nargs="+", help="标签名称，空格分隔如 \"朋友\" \"同事\"")
    p.set_defaults(func=cmd_add_contact_label)

    # remove-contact-label
    p = subparsers.add_parser("remove-contact-label", help="移除联系人标签")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.add_argument("--labels", required=True, nargs="+", help="标签名称，空格分隔如 \"朋友\" \"同事\"")
    p.set_defaults(func=cmd_remove_contact_label)

    # set-contact-star
    p = subparsers.add_parser("set-contact-star", help="设为星标朋友")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_set_contact_star)

    # cancel-contact-star
    p = subparsers.add_parser("cancel-contact-star", help="取消星标朋友")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_cancel_contact_star)

    # black-contact
    p = subparsers.add_parser("black-contact", help="加入黑名单")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_black_contact)

    # unblack-contact
    p = subparsers.add_parser("unblack-contact", help="移出黑名单")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_unblack_contact)

    # delete-contact
    p = subparsers.add_parser("delete-contact", help="删除联系人")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_delete_contact)

    # add-friend
    p = subparsers.add_parser("add-friend", help="添加朋友")
    p.add_argument("--keyword", required=True, help="微信号或手机号")
    p.add_argument("--message", default=None, help="申请消息")
    p.add_argument("--remark", default=None, help="备注名")
    p.add_argument("--permission", default=None, choices=["chatonly"], help="朋友权限: chatonly=仅聊天")
    p.add_argument("--hide-my-posts", action="store_true", help="不让对方看我的朋友圈")
    p.add_argument("--hide-their-posts", action="store_true", help="不看对方的朋友圈")
    p.set_defaults(func=cmd_add_friend)

    # get-friend-permission
    p = subparsers.add_parser("get-friend-permission", help="获取联系人朋友权限设置")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_get_friend_permission)

    # set-friend-permission
    p = subparsers.add_parser("set-friend-permission", help="设置联系人朋友权限")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.add_argument("--permission", default="all", choices=["all", "chatonly"], help="权限: all=全部, chatonly=仅聊天")
    p.add_argument("--hide-my-posts", action="store_true", help="不让对方看我的朋友圈")
    p.add_argument("--hide-their-posts", action="store_true", help="不看对方的朋友圈")
    p.set_defaults(func=cmd_set_friend_permission)

    # ---- 群聊操作 ----

    # create-room
    p = subparsers.add_parser("create-room", help="发起群聊")
    p.add_argument("--members", required=True, nargs="+", help="好友昵称列表，至少两个，空格分隔如 \"张三\" \"李四\" \"王五\"")
    p.set_defaults(func=cmd_create_room)

    # set-room-name
    p = subparsers.add_parser("set-room-name", help="设置群聊名称")
    p.add_argument("--nickname", required=True, help="群聊当前名称")
    p.add_argument("--name", required=True, help="新群聊名称")
    p.set_defaults(func=cmd_set_room_name)

    # set-room-announcement
    p = subparsers.add_parser("set-room-announcement", help="设置群公告")
    p.add_argument("--nickname", required=True, help="群聊名称")
    p.add_argument("--content", required=True, help="群公告内容")
    p.set_defaults(func=cmd_set_room_announcement)

    # add-room-members
    p = subparsers.add_parser("add-room-members", help="添加群成员")
    p.add_argument("--nickname", required=True, help="群聊名称")
    p.add_argument("--members", required=True, nargs="+", help="要添加的成员昵称，空格分隔如 \"张三\" \"李四\"")
    p.set_defaults(func=cmd_add_room_members)

    # remove-room-members
    p = subparsers.add_parser("remove-room-members", help="移除群成员")
    p.add_argument("--nickname", required=True, help="群聊名称")
    p.add_argument("--members", required=True, nargs="+", help="要移除的成员昵称，空格分隔如 \"张三\" \"李四\"")
    p.set_defaults(func=cmd_remove_room_members)

    # exit-room
    p = subparsers.add_parser("exit-room", help="退出群聊")
    p.add_argument("--nickname", required=True, help="群聊名称")
    p.set_defaults(func=cmd_exit_room)

    # pin-chat
    p = subparsers.add_parser("pin-chat", help="置顶会话")
    p.add_argument("--nickname", required=True, help="联系人或群聊名称")
    p.set_defaults(func=cmd_pin_chat)

    # unpin-chat
    p = subparsers.add_parser("unpin-chat", help="取消置顶")
    p.add_argument("--nickname", required=True, help="联系人或群聊名称")
    p.set_defaults(func=cmd_unpin_chat)

    # mute-chat
    p = subparsers.add_parser("mute-chat", help="消息免打扰")
    p.add_argument("--nickname", required=True, help="联系人或群聊名称")
    p.set_defaults(func=cmd_mute_chat)

    # unmute-chat
    p = subparsers.add_parser("unmute-chat", help="取消免打扰")
    p.add_argument("--nickname", required=True, help="联系人或群聊名称")
    p.set_defaults(func=cmd_unmute_chat)

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

    # ---- 其他 ----

    # create-note
    p = subparsers.add_parser("create-note", help="创建笔记")
    p.add_argument("--content", required=True, help="笔记内容")
    p.set_defaults(func=cmd_create_note)

    # get-self-profile
    p = subparsers.add_parser("get-self-profile", help="获取当前登录账号资料")
    p.set_defaults(func=cmd_get_self_profile)

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
