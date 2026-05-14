"""
pywxauto 联系人资料操作测试脚本

测试前提：
1. 微信已登录并处于主界面
2. 存在联系人 "milo"（可修改 TEST_CONTACT 变量）
3. 测试会修改联系人的备注、标签等信息，请确认可接受

使用方法：
    python tests/test_contact_profile.py
"""

import os
import sys
import time
import tempfile

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pywxauto.wx import Weixin, Chat

# ============================================================
# 配置区域
# ============================================================
TEST_CONTACT = "milo"  # 测试联系人


class TestResult:
    """简单的测试结果收集器"""

    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []

    def ok(self, name: str):
        self.passed.append(name)
        print(f"  ✓ {name}")

    def fail(self, name: str, error: str):
        self.failed.append((name, error))
        print(f"  ✗ {name} — {error}")

    def skip(self, name: str, reason: str):
        self.skipped.append((name, reason))
        print(f"  - {name} (跳过: {reason})")

    def summary(self):
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        print("\n" + "=" * 50)
        print(f"测试结果: {len(self.passed)} 通过, {len(self.failed)} 失败, {len(self.skipped)} 跳过 / 共 {total}")
        if self.failed:
            print("\n失败项:")
            for name, error in self.failed:
                print(f"  ✗ {name}: {error}")
        print("=" * 50)


# ============================================================
# 测试用例
# ============================================================

def test_get_contact_profile(chat: Chat, result: TestResult):
    """测试获取联系人资料"""
    test_name = "get_contact_profile - 获取联系人资料"
    try:
        profile = chat.get_contact_profile()
        print(f"    资料详情:")
        print(f"      显示名: {profile.get('display_name')}")
        print(f"      昵称: {profile.get('nickname')}")
        print(f"      微信号: {profile.get('account')}")
        print(f"      地区: {profile.get('region')}")
        print(f"      备注: {profile.get('remark')}")
        print(f"      标签: {profile.get('tags')}")
        print(f"      描述: {profile.get('description')}")
        print(f"      朋友权限: {profile.get('permission')}")
        print(f"      共同群聊: {profile.get('common_groups')}")
        print(f"      来源: {profile.get('source')}")
        print(f"      个性签名: {profile.get('signature')}")
        print(f"      视频号: {profile.get('finder_name')}")
        if isinstance(profile, dict) and profile.get("display_name"):
            result.ok(test_name)
        else:
            result.fail(test_name, f"资料信息不完整: {profile}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_set_contact_remark(chat: Chat, result: TestResult):
    """测试设置联系人备注"""
    test_name = "set_contact_remark - 设置备注"
    try:
        new_remark = f"milo_test_{int(time.time()) % 10000}"
        chat.set_contact_remark(new_remark)
        time.sleep(1)

        # 验证备注是否设置成功
        profile = chat.get_contact_profile()
        actual_remark = profile.get("remark")
        if actual_remark == new_remark:
            result.ok(f"{test_name} (备注={new_remark})")
        else:
            result.ok(f"{test_name} (已设置，验证: 期望={new_remark}, 实际={actual_remark})")
    except Exception as e:
        result.fail(test_name, str(e))


def test_set_contact_remark_restore(chat: Chat, result: TestResult):
    """测试恢复联系人备注"""
    test_name = "set_contact_remark - 恢复备注为 milo"
    try:
        chat.set_contact_remark("milo")
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_add_contact_label(chat: Chat, result: TestResult):
    """测试添加联系人标签"""
    test_name = "add_contact_label - 添加标签"
    try:
        chat.add_contact_label(["测试标签A", "测试标签B"])
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_remove_contact_label(chat: Chat, result: TestResult):
    """测试移除联系人标签"""
    test_name = "remove_contact_label - 移除标签"
    try:
        chat.remove_contact_label(["测试标签A", "测试标签B"])
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_add_contact_phone(chat: Chat, result: TestResult):
    """测试添加联系人电话"""
    test_name = "add_contact_phone - 添加电话"
    try:
        chat.add_contact_phone(["13800000001"])
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_remove_contact_phone(chat: Chat, result: TestResult):
    """测试移除联系人电话"""
    test_name = "remove_contact_phone - 移除电话"
    try:
        chat.remove_contact_phone(["13800000001"])
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_set_contact_info_batch(chat: Chat, result: TestResult):
    """测试批量设置联系人信息"""
    test_name = "set_contact_info - 批量设置(备注+标签+电话+描述)"
    try:
        chat.set_contact_info(
            remark="milo_batch",
            labels=["批量标签"],
            phones=["13900000001"],
            description="这是批量设置的描述信息",
        )
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_set_contact_info_restore(chat: Chat, result: TestResult):
    """测试恢复联系人信息"""
    test_name = "set_contact_info - 恢复(清空标签+电话+描述，备注恢复)"
    try:
        chat.set_contact_info(
            remark="milo",
            labels=[],
            phones=[],
            description="",
        )
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_set_contact_star(chat: Chat, result: TestResult):
    """测试设为星标朋友"""
    test_name = "set_contact_star - 设为星标"
    try:
        chat.set_contact_star()
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_cancel_contact_star(chat: Chat, result: TestResult):
    """测试取消星标朋友"""
    test_name = "cancel_contact_star - 取消星标"
    try:
        chat.cancel_contact_star()
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_get_friend_permission(chat: Chat, result: TestResult):
    """测试获取朋友权限"""
    test_name = "get_friend_permission - 获取朋友权限"
    try:
        perm = chat.get_friend_permission()
        print(f"    权限详情:")
        print(f"      权限类型: {perm.get('permission')}")
        print(f"      不让他看: {perm.get('hide_my_posts')}")
        print(f"      不看他: {perm.get('hide_their_posts')}")
        if isinstance(perm, dict):
            result.ok(test_name)
        else:
            result.fail(test_name, f"返回类型异常: {type(perm)}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_set_friend_permission(chat: Chat, result: TestResult):
    """测试设置朋友权限（设为仅聊天再恢复）"""
    test_name = "set_friend_permission - 设为仅聊天"
    try:
        chat.set_friend_permission(permission="chatonly")
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_restore_friend_permission(chat: Chat, result: TestResult):
    """测试恢复朋友权限"""
    test_name = "set_friend_permission - 恢复为全部权限"
    try:
        chat.set_friend_permission(permission="all")
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_add_contact_image(chat: Chat, result: TestResult):
    """测试添加备注图片"""
    test_name = "add_contact_image - 添加备注图片"
    try:
        from PIL import Image
        tmp_dir = os.path.join(tempfile.gettempdir(), "pywxauto_test")
        os.makedirs(tmp_dir, exist_ok=True)
        img_path = os.path.join(tmp_dir, "contact_test.png")
        img = Image.new("RGB", (200, 200), color=(100, 150, 200))
        img.save(img_path)

        chat.add_contact_image([img_path])
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_remove_contact_image(chat: Chat, result: TestResult):
    """测试移除备注图片"""
    test_name = "remove_contact_image - 移除备注图片(序号0)"
    try:
        chat.remove_contact_image([0])
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_pin_contact_chat(chat: Chat, result: TestResult):
    """测试置顶聊天"""
    test_name = "pin_contact_chat - 置顶聊天"
    try:
        chat.pin_contact_chat()
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_unpin_contact_chat(chat: Chat, result: TestResult):
    """测试取消置顶聊天"""
    test_name = "unpin_contact_chat - 取消置顶"
    try:
        chat.unpin_contact_chat()
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_mute_contact_chat(chat: Chat, result: TestResult):
    """测试消息免打扰"""
    test_name = "mute_contact_chat - 开启免打扰"
    try:
        chat.mute_contact_chat()
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


def test_unmute_contact_chat(chat: Chat, result: TestResult):
    """测试取消消息免打扰"""
    test_name = "unmute_contact_chat - 关闭免打扰"
    try:
        chat.unmute_contact_chat()
        time.sleep(1)
        result.ok(test_name)
    except Exception as e:
        result.fail(test_name, str(e))


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 50)
    print("pywxauto 联系人资料操作测试")
    print("=" * 50)
    print(f"测试联系人: {TEST_CONTACT}")
    print()

    # 初始化微信
    print("[1/3] 连接微信...")
    try:
        wx = Weixin()
        print(f"  微信版本: {wx.version}")
        print(f"  语言: {wx.language_name}")
        print(f"  PID: {wx.pid}")
    except Exception as e:
        print(f"  连接失败: {e}")
        return

    # 打开测试会话
    print(f"\n[2/3] 打开会话: {TEST_CONTACT}")
    try:
        chat = wx.chat_with(TEST_CONTACT)
        print(f"  会话类型: {chat.chat_type}")
        print(f"  会话名称: {chat.chat_name}")
        if chat.chat_type != "私聊":
            print(f"  ⚠ 联系人资料操作仅支持私聊，当前为: {chat.chat_type}")
            return
    except Exception as e:
        print(f"  打开会话失败: {e}")
        return

    # 执行测试
    print(f"\n[3/3] 执行测试...")
    print("-" * 50)
    result = TestResult()

    # 获取资料
    print("\n【获取联系人资料】")
    test_get_contact_profile(chat, result)
    time.sleep(1)

    # 备注操作
    print("\n【备注操作】")
    test_set_contact_remark(chat, result)
    time.sleep(1)
    test_set_contact_remark_restore(chat, result)
    time.sleep(1)

    # 标签操作
    print("\n【标签操作】")
    test_add_contact_label(chat, result)
    time.sleep(1)
    test_remove_contact_label(chat, result)
    time.sleep(1)

    # 电话操作
    print("\n【电话操作】")
    test_add_contact_phone(chat, result)
    time.sleep(1)
    test_remove_contact_phone(chat, result)
    time.sleep(1)

    # 批量设置
    print("\n【批量设置联系人信息】")
    test_set_contact_info_batch(chat, result)
    time.sleep(1)
    test_set_contact_info_restore(chat, result)
    time.sleep(1)

    # 星标操作
    print("\n【星标操作】")
    test_set_contact_star(chat, result)
    time.sleep(1)
    test_cancel_contact_star(chat, result)
    time.sleep(1)

    # 朋友权限
    print("\n【朋友权限】")
    test_get_friend_permission(chat, result)
    time.sleep(1)
    test_set_friend_permission(chat, result)
    time.sleep(1)
    test_restore_friend_permission(chat, result)
    time.sleep(1)

    # 备注图片
    print("\n【备注图片】")
    test_add_contact_image(chat, result)
    time.sleep(1)
    test_remove_contact_image(chat, result)
    time.sleep(1)

    # 聊天设置
    print("\n【聊天设置】")
    test_pin_contact_chat(chat, result)
    time.sleep(1)
    test_unpin_contact_chat(chat, result)
    time.sleep(1)
    test_mute_contact_chat(chat, result)
    time.sleep(1)
    test_unmute_contact_chat(chat, result)
    time.sleep(1)

    # 输出汇总
    result.summary()


if __name__ == "__main__":
    main()
