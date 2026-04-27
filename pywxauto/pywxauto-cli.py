#!/usr/bin/env python3
"""
pywxauto CLI — 微信自动化命令行工具

用法:
    python pywxauto-cli.py <group> <command> [options]

命令组:
    message     消息操作
    session     会话操作
    contact     联系人操作
    moment      朋友圈操作
    other       其他操作

示例:
    python pywxauto-cli.py message send-text --nickname "张三" --content "你好"
    python pywxauto-cli.py session list --all
    python pywxauto-cli.py contact get-profile --nickname "张三"
    python pywxauto-cli.py moment get --count 20
"""

import argparse
import json
import sys

from pywxauto import Weixin


def _wx() -> Weixin:
    return Weixin()


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _print_status(status):
    print(f"发送状态: {status}")


def _ok(label, ok):
    print(f"{label}: {'成功' if ok else '失败'}")


# ============================================================
# message 命令
# ============================================================

def cmd_msg_send_text(args):
    _print_status(_wx().send_text(args.nickname, args.content))

def cmd_msg_send_file(args):
    _print_status(_wx().send_file(args.nickname, args.file))

def cmd_msg_send_at(args):
    _print_status(_wx().send_at(args.nickname, args.content, args.members))

def cmd_msg_send_emotion(args):
    _ok("发送表情", _wx().send_emotion(args.nickname, args.keyword, args.index))

def cmd_msg_send_card(args):
    _ok("发送名片", _wx().send_card(args.nickname, args.share))

def cmd_msg_get(args):
    chat = _wx().open_session_by_search(args.nickname)
    for msg in chat.get_visible_messages():
        print(msg)


# ============================================================
# session 命令
# ============================================================

def cmd_sess_list(args):
    wx = _wx()
    items = wx.session.all() if args.all else wx.session.visible()
    for item in items:
        print(item)

def cmd_sess_open(args):
    _wx().open_session_by_search(args.nickname)
    print(f"已打开会话: {args.nickname}")

def cmd_sess_close(args):
    _wx().close_session(args.nickname)
    print(f"已关闭会话: {args.nickname}")

def cmd_sess_search(args):
    _ok("搜索", _wx().session.search_and_select(args.keyword))

def cmd_sess_pin(args):
    _wx().pin_chat(args.nickname)
    print(f"已置顶: {args.nickname}")

def cmd_sess_unpin(args):
    _wx().unpin_chat(args.nickname)
    print(f"已取消置顶: {args.nickname}")

def cmd_sess_mute(args):
    _wx().mute_chat(args.nickname)
    print(f"已设置免打扰: {args.nickname}")

def cmd_sess_unmute(args):
    _wx().unmute_chat(args.nickname)
    print(f"已取消免打扰: {args.nickname}")

def cmd_sess_delete(args):
    _wx().session.delete(args.nickname)
    print(f"已删除会话: {args.nickname}")


# ============================================================
# contact 命令
# ============================================================

def cmd_ct_get_profile(args):
    _print_json(_wx().get_contact_profile(args.nickname))

def cmd_ct_set_remark(args):
    _wx().set_contact_remark(args.nickname, args.remark)
    print(f"已设置备注: {args.nickname} -> {args.remark}")

def cmd_ct_add_label(args):
    _wx().add_contact_label(args.nickname, args.labels)
    print(f"已添加标签: {args.labels}")

def cmd_ct_remove_label(args):
    _wx().remove_contact_label(args.nickname, args.labels)
    print(f"已移除标签: {args.labels}")

def cmd_ct_star(args):
    _wx().set_contact_star(args.nickname)
    print(f"已星标: {args.nickname}")

def cmd_ct_unstar(args):
    _wx().cancel_contact_star(args.nickname)
    print(f"已取消星标: {args.nickname}")

def cmd_ct_black(args):
    _wx().black_contact(args.nickname)
    print(f"已拉黑: {args.nickname}")

def cmd_ct_unblack(args):
    _wx().unblack_contact(args.nickname)
    print(f"已取消拉黑: {args.nickname}")

def cmd_ct_delete(args):
    _wx().delete_contact(args.nickname)
    print(f"已删除联系人: {args.nickname}")

def cmd_ct_add_friend(args):
    _wx().session.add_friend(args.keyword, message=args.message, remark=args.remark)
    print(f"已发送好友请求: {args.keyword}")

def cmd_ct_recommend(args):
    _ok("推荐名片", _wx().recommend_contact(args.nickname, args.receiver))

def cmd_ct_create_room(args):
    _wx().create_room(args.members)
    print(f"已创建群聊，成员: {args.members}")


# ============================================================
# moment 命令
# ============================================================

def cmd_mom_get(args):
    for item in _wx().moment.get(count=args.count, position=args.position):
        print(item)
        print("---")

def cmd_mom_publish(args):
    _ok("发布朋友圈", _wx().moment.publish_text(args.content))

def cmd_mom_refresh(args):
    _wx().moment.refresh()
    print("已刷新朋友圈")


# ============================================================
# other 命令
# ============================================================

def cmd_other_create_note(args):
    _wx().create_note(args.content)
    print("已创建笔记")

def cmd_other_clear_history(args):
    _wx().clear_chat_history(args.nickname)
    print(f"已清空聊天记录: {args.nickname}")


# ============================================================
# argparse 构建
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="pywxauto-cli",
        description="pywxauto CLI — 微信自动化命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    groups = root.add_subparsers(dest="group", help="命令组")

    # -------------------- message --------------------
    g_msg = groups.add_parser("message", help="消息操作", aliases=["msg"])
    msg_sub = g_msg.add_subparsers(dest="command")

    p = msg_sub.add_parser("send-text", help="发送文本消息")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.add_argument("--content", required=True, help="消息内容")
    p.set_defaults(func=cmd_msg_send_text)

    p = msg_sub.add_parser("send-file", help="发送文件（支持本地路径和URL）")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.add_argument("--file", required=True, help="文件路径或URL")
    p.set_defaults(func=cmd_msg_send_file)

    p = msg_sub.add_parser("send-at", help="群聊 @成员发送消息")
    p.add_argument("--nickname", required=True, help="群聊昵称")
    p.add_argument("--content", required=True, help="消息内容")
    p.add_argument("--members", required=True, nargs="+", help="要@的成员昵称列表")
    p.set_defaults(func=cmd_msg_send_at)

    p = msg_sub.add_parser("send-emotion", help="发送表情")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.add_argument("--keyword", default=None, help="表情关键词（不指定则发送自定义表情）")
    p.add_argument("--index", type=int, default=1, help="表情序号（默认1）")
    p.set_defaults(func=cmd_msg_send_emotion)

    p = msg_sub.add_parser("send-card", help="发送联系人名片")
    p.add_argument("--nickname", required=True, help="接收者昵称")
    p.add_argument("--share", required=True, help="要分享的联系人昵称")
    p.set_defaults(func=cmd_msg_send_card)

    p = msg_sub.add_parser("get", help="获取当前聊天的可见消息")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_msg_get)

    # -------------------- session --------------------
    g_sess = groups.add_parser("session", help="会话操作", aliases=["sess"])
    sess_sub = g_sess.add_subparsers(dest="command")

    p = sess_sub.add_parser("list", help="列出会话列表")
    p.add_argument("--all", action="store_true", help="列出所有会话（滚动加载）")
    p.set_defaults(func=cmd_sess_list)

    p = sess_sub.add_parser("open", help="打开指定会话")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_sess_open)

    p = sess_sub.add_parser("close", help="关闭指定会话")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_sess_close)

    p = sess_sub.add_parser("search", help="搜索会话")
    p.add_argument("--keyword", required=True, help="搜索关键词")
    p.set_defaults(func=cmd_sess_search)

    p = sess_sub.add_parser("pin", help="置顶会话")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_sess_pin)

    p = sess_sub.add_parser("unpin", help="取消置顶会话")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_sess_unpin)

    p = sess_sub.add_parser("mute", help="消息免打扰")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_sess_mute)

    p = sess_sub.add_parser("unmute", help="取消免打扰")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_sess_unmute)

    p = sess_sub.add_parser("delete", help="删除会话")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_sess_delete)

    # -------------------- contact --------------------
    g_ct = groups.add_parser("contact", help="联系人操作", aliases=["ct"])
    ct_sub = g_ct.add_subparsers(dest="command")

    p = ct_sub.add_parser("get-profile", help="获取联系人资料")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_ct_get_profile)

    p = ct_sub.add_parser("set-remark", help="设置联系人备注")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.add_argument("--remark", required=True, help="备注名")
    p.set_defaults(func=cmd_ct_set_remark)

    p = ct_sub.add_parser("add-label", help="添加联系人标签")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.add_argument("--labels", required=True, nargs="+", help="标签列表")
    p.set_defaults(func=cmd_ct_add_label)

    p = ct_sub.add_parser("remove-label", help="移除联系人标签")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.add_argument("--labels", required=True, nargs="+", help="标签列表")
    p.set_defaults(func=cmd_ct_remove_label)

    p = ct_sub.add_parser("star", help="星标联系人")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_ct_star)

    p = ct_sub.add_parser("unstar", help="取消星标")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_ct_unstar)

    p = ct_sub.add_parser("black", help="拉黑联系人")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_ct_black)

    p = ct_sub.add_parser("unblack", help="取消拉黑")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_ct_unblack)

    p = ct_sub.add_parser("delete", help="删除联系人")
    p.add_argument("--nickname", required=True, help="联系人昵称")
    p.set_defaults(func=cmd_ct_delete)

    p = ct_sub.add_parser("add-friend", help="添加好友")
    p.add_argument("--keyword", required=True, help="微信号/手机号/昵称")
    p.add_argument("--message", default=None, help="验证消息")
    p.add_argument("--remark", default=None, help="备注名")
    p.set_defaults(func=cmd_ct_add_friend)

    p = ct_sub.add_parser("recommend", help="推荐联系人名片给他人")
    p.add_argument("--nickname", required=True, help="要推荐的联系人昵称")
    p.add_argument("--receiver", required=True, help="接收推荐的联系人昵称")
    p.set_defaults(func=cmd_ct_recommend)

    p = ct_sub.add_parser("create-room", help="创建群聊")
    p.add_argument("--members", required=True, nargs="+", help="群成员昵称列表")
    p.set_defaults(func=cmd_ct_create_room)

    # -------------------- moment --------------------
    g_mom = groups.add_parser("moment", help="朋友圈操作", aliases=["mom"])
    mom_sub = g_mom.add_subparsers(dest="command")

    p = mom_sub.add_parser("get", help="获取朋友圈动态")
    p.add_argument("--count", type=int, default=10, help="获取条数（默认10）")
    p.add_argument("--position", default="top", choices=["top", "current"], help="起始位置")
    p.set_defaults(func=cmd_mom_get)

    p = mom_sub.add_parser("publish", help="发布朋友圈纯文字")
    p.add_argument("--content", required=True, help="文字内容")
    p.set_defaults(func=cmd_mom_publish)

    p = mom_sub.add_parser("refresh", help="刷新朋友圈")
    p.set_defaults(func=cmd_mom_refresh)

    # -------------------- other --------------------
    g_other = groups.add_parser("other", help="其他操作")
    other_sub = g_other.add_subparsers(dest="command")

    p = other_sub.add_parser("create-note", help="创建笔记")
    p.add_argument("--content", required=True, help="笔记内容")
    p.set_defaults(func=cmd_other_create_note)

    p = other_sub.add_parser("clear-history", help="清空聊天记录")
    p.add_argument("--nickname", required=True, help="联系人/群聊昵称")
    p.set_defaults(func=cmd_other_clear_history)

    return root


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.group:
        parser.print_help()
        sys.exit(0)

    if not hasattr(args, "func"):
        parser.parse_args([args.group, "-h"])
        sys.exit(0)

    try:
        args.func(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
