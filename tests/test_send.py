"""
pywxauto 发送接口测试代码

测试前提：
1. 微信已登录并处于主界面
2. 存在一个可用的聊天对象（默认使用"文件传输助手"）
3. 测试图片/文件路径需要根据实际环境修改

使用方法：
    python tests/test_send.py
"""

import os
import sys
import time
import tempfile

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pywxauto.wx import (
    Weixin, Chat, SeparateChat, MessageStatus,
    Event, Message, TextMessage, FileMessage, ImageMessage,
)

# ============================================================
# 配置区域 - 根据实际环境修改
# ============================================================
TEST_CONTACT = "文件传输助手"  # 测试聊天对象（建议用文件传输助手，不打扰他人）
TEST_GROUP = None  # 测试群聊名称，None 则跳过群聊相关测试
TEST_IMAGE_PATH = None  # 测试图片路径，None 则自动生成临时图片
TEST_FILE_PATH = None  # 测试文件路径，None 则自动生成临时文件
TEST_VIDEO_PATH = None  # 测试视频路径，None 则跳过视频发送测试
TEST_IMAGE_URL = "https://www.python.org/static/community_logos/python-logo.png"  # 测试网络图片


def create_temp_image() -> str:
    """创建临时测试图片"""
    from PIL import Image
    tmp_dir = os.path.join(tempfile.gettempdir(), "pywxauto_test")
    os.makedirs(tmp_dir, exist_ok=True)
    img_path = os.path.join(tmp_dir, "test_image.png")
    img = Image.new("RGB", (200, 200), color=(73, 109, 137))
    img.save(img_path)
    return img_path


def create_temp_file() -> str:
    """创建临时测试文件"""
    tmp_dir = os.path.join(tempfile.gettempdir(), "pywxauto_test")
    os.makedirs(tmp_dir, exist_ok=True)
    file_path = os.path.join(tmp_dir, "test_file.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("这是 pywxauto 发送接口测试文件\n")
        f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return file_path


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


def test_send_text(chat: Chat, result: TestResult):
    """测试发送文本消息"""
    test_name = "send_text - 基本文本"
    try:
        content = f"pywxauto 测试消息 {time.strftime('%H:%M:%S')}"
        status = chat.send_text(content)
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态异常: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_text_with_timeout(chat: Chat, result: TestResult):
    """测试发送文本消息（带超时等待）"""
    test_name = "send_text - 带超时检测"
    try:
        content = f"超时检测测试 {time.strftime('%H:%M:%S')}"
        status = chat.send_text(content, timeout=5)
        if status == MessageStatus.SENT:
            result.ok(test_name)
        elif status == MessageStatus.UNKNOWN:
            result.ok(test_name + " (状态未知但未报错)")
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_text_multiline(chat: Chat, result: TestResult):
    """测试发送多行文本"""
    test_name = "send_text - 多行文本"
    try:
        content = "第一行\n第二行\n第三行"
        status = chat.send_text(content)
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_text_emoji(chat: Chat, result: TestResult):
    """测试发送含 emoji 的文本"""
    test_name = "send_text - 含 emoji"
    try:
        content = "测试 emoji 🎉🚀✅"
        status = chat.send_text(content)
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_text_long(chat: Chat, result: TestResult):
    """测试发送长文本"""
    test_name = "send_text - 长文本"
    try:
        content = "长文本测试" * 50  # 250 字符
        status = chat.send_text(content)
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_file(chat: Chat, file_path: str, result: TestResult):
    """测试发送文件"""
    test_name = "send_file - 本地文件"
    try:
        status = chat.send_file(file_path)
        if status in (MessageStatus.SENT, MessageStatus.SENDING, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_file_with_timeout(chat: Chat, file_path: str, result: TestResult):
    """测试发送文件（带超时等待传输完成）"""
    test_name = "send_file - 带超时检测"
    try:
        status = chat.send_file(file_path, timeout=10)
        if status == MessageStatus.SENT:
            result.ok(test_name)
        elif status in (MessageStatus.SENDING, MessageStatus.UNKNOWN):
            result.ok(test_name + " (仍在传输或状态未知)")
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_file_multiple(chat: Chat, result: TestResult):
    """测试发送多个文件"""
    test_name = "send_file - 多文件"
    try:
        tmp_dir = os.path.join(tempfile.gettempdir(), "pywxauto_test")
        os.makedirs(tmp_dir, exist_ok=True)
        files = []
        for i in range(2):
            path = os.path.join(tmp_dir, f"multi_test_{i}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"多文件测试 #{i}\n")
            files.append(path)

        status = chat.send_file(files)
        if status in (MessageStatus.SENT, MessageStatus.SENDING, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_image(chat: Chat, image_path: str, result: TestResult):
    """测试发送图片"""
    test_name = "send_image - 本地图片"
    try:
        status = chat.send_image(image_path)
        if status in (MessageStatus.SENT, MessageStatus.SENDING, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_image_url(chat: Chat, result: TestResult):
    """测试发送网络图片"""
    test_name = "send_image - 网络 URL"
    try:
        status = chat.send_image(TEST_IMAGE_URL)
        if status in (MessageStatus.SENT, MessageStatus.SENDING, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_image_multiple(chat: Chat, result: TestResult):
    """测试发送多张图片"""
    test_name = "send_image - 多张图片"
    try:
        from PIL import Image
        tmp_dir = os.path.join(tempfile.gettempdir(), "pywxauto_test")
        os.makedirs(tmp_dir, exist_ok=True)
        images = []
        for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
            path = os.path.join(tmp_dir, f"multi_img_{i}.png")
            img = Image.new("RGB", (100, 100), color=color)
            img.save(path)
            images.append(path)

        status = chat.send_image(images)
        if status in (MessageStatus.SENT, MessageStatus.SENDING, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_video(chat: Chat, video_path: str, result: TestResult):
    """测试发送视频"""
    test_name = "send_video - 本地视频"
    if not video_path:
        result.skip(test_name, "未配置 TEST_VIDEO_PATH")
        return
    try:
        status = chat.send_video(video_path, timeout=30)
        if status in (MessageStatus.SENT, MessageStatus.SENDING, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_emotion_search(chat: Chat, result: TestResult):
    """测试搜索发送表情"""
    test_name = "send_emotion - 搜索表情"
    try:
        status = chat.send_emotion(keyword="你好", index=1)
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_emotion_custom(chat: Chat, result: TestResult):
    """测试发送自定义表情"""
    test_name = "send_emotion - 自定义表情"
    try:
        status = chat.send_emotion(keyword=None, index=1)
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_at(chat: Chat, result: TestResult):
    """测试发送 @消息（仅群聊）"""
    test_name = "send_at - @所有人"
    if chat.chat_type != "群聊":
        result.skip(test_name, "当前非群聊")
        return
    try:
        status = chat.send_at("测试@消息", at_members=["所有人"])
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_text_with_reply(chat: Chat, result: TestResult):
    """测试引用回复消息"""
    test_name = "send_text - 引用回复"
    try:
        # 先获取最新消息
        messages = chat.get_visible_messages()
        if not messages:
            result.skip(test_name, "消息列表为空")
            return

        # 找到最后一条非系统消息
        target_msg = None
        for msg in reversed(messages):
            if not isinstance(msg, Message):
                continue
            if msg.sender_type.value != "system":
                target_msg = msg
                break

        if not target_msg:
            result.skip(test_name, "未找到可引用的消息")
            return

        status = chat.send_text("这是引用回复测试", reply_to=target_msg)
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_get_visible_messages(chat: Chat, result: TestResult):
    """测试获取可见消息列表"""
    test_name = "get_visible_messages"
    try:
        messages = chat.get_visible_messages()
        if isinstance(messages, list):
            result.ok(f"{test_name} (获取到 {len(messages)} 条消息)")
        else:
            result.fail(test_name, f"返回类型异常: {type(messages)}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_chat_properties(chat: Chat, result: TestResult):
    """测试聊天属性"""
    test_name = "chat 属性"
    try:
        name = chat.chat_name
        chat_type = chat.chat_type
        if name and chat_type:
            result.ok(f"{test_name} (name={name!r}, type={chat_type!r})")
        else:
            result.fail(test_name, f"name={name!r}, type={chat_type!r}")
    except Exception as e:
        result.fail(test_name, str(e))


def test_send_collection(chat: Chat, result: TestResult):
    """测试发送收藏"""
    test_name = "send_collection"
    try:
        # 收藏内容因人而异，这里用一个通用关键词尝试
        status = chat.send_collection("测试")
        if status in (MessageStatus.SENT, MessageStatus.UNKNOWN):
            result.ok(test_name)
        else:
            result.fail(test_name, f"状态: {status.value}")
    except Exception as e:
        # 收藏为空时会抛异常，属于正常情况
        if "未找到匹配" in str(e) or "搜索后未找到" in str(e):
            result.skip(test_name, "收藏中无匹配内容")
        else:
            result.fail(test_name, str(e))


def main():
    print("=" * 50)
    print("pywxauto 发送接口测试")
    print("=" * 50)
    print(f"测试对象: {TEST_CONTACT}")
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
    except Exception as e:
        print(f"  打开会话失败: {e}")
        return

    # 准备测试资源
    image_path = TEST_IMAGE_PATH or create_temp_image()
    file_path = TEST_FILE_PATH or create_temp_file()
    print(f"  测试图片: {image_path}")
    print(f"  测试文件: {file_path}")

    # 执行测试
    print(f"\n[3/3] 执行测试...")
    print("-" * 50)
    result = TestResult()

    # 基础属性测试
    print("\n【聊天属性】")
    test_chat_properties(chat, result)
    test_get_visible_messages(chat, result)

    # 文本发送测试
    print("\n【文本消息】")
    test_send_text(chat, result)
    time.sleep(1)
    test_send_text_with_timeout(chat, result)
    time.sleep(1)
    test_send_text_multiline(chat, result)
    time.sleep(1)
    test_send_text_emoji(chat, result)
    time.sleep(1)
    test_send_text_long(chat, result)
    time.sleep(1)

    # 文件发送测试
    print("\n【文件消息】")
    test_send_file(chat, file_path, result)
    time.sleep(2)
    test_send_file_with_timeout(chat, file_path, result)
    time.sleep(2)
    test_send_file_multiple(chat, result)
    time.sleep(2)

    # 图片发送测试
    print("\n【图片消息】")
    test_send_image(chat, image_path, result)
    time.sleep(2)
    test_send_image_url(chat, result)
    time.sleep(2)
    test_send_image_multiple(chat, result)
    time.sleep(2)

    # 视频发送测试
    print("\n【视频消息】")
    test_send_video(chat, TEST_VIDEO_PATH, result)
    time.sleep(2)

    # 表情发送测试
    print("\n【表情消息】")
    test_send_emotion_search(chat, result)
    time.sleep(2)
    test_send_emotion_custom(chat, result)
    time.sleep(2)

    # 收藏发送测试
    print("\n【收藏消息】")
    test_send_collection(chat, result)
    time.sleep(2)

    # 引用回复测试
    print("\n【引用回复】")
    test_send_text_with_reply(chat, result)
    time.sleep(1)

    # @消息测试（仅群聊）
    if TEST_GROUP:
        print(f"\n【群聊测试】(群: {TEST_GROUP})")
        try:
            group_chat = wx.chat_with(TEST_GROUP)
            test_send_at(group_chat, result)
        except Exception as e:
            result.fail("打开群聊", str(e))

    # 输出汇总
    result.summary()


if __name__ == "__main__":
    main()
