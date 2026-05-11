"""
pywxauto 朋友圈接口测试代码

测试前提：
1. 微信已登录并处于主界面
2. 朋友圈中有可见的动态

使用方法：
    python tests/test_moment.py
"""

import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from pywxauto.wx import Weixin, Moment, MomentItem

# ============================================================
# 资源生成
# ============================================================
TMP_DIR = os.path.join(tempfile.gettempdir(), "pywxauto_moment_test")
os.makedirs(TMP_DIR, exist_ok=True)


def gen_image(name: str, color: tuple, size: tuple = (300, 300)) -> str:
    """生成纯色测试图片，返回路径"""
    path = os.path.join(TMP_DIR, name)
    Image.new("RGB", size, color=color).save(path)
    return path


def gen_images(count: int = 3) -> list[str]:
    """生成多张不同颜色的测试图片"""
    colors = [
        (231, 76, 60), (46, 204, 113), (52, 152, 219),
        (155, 89, 182), (241, 196, 15), (230, 126, 34),
        (26, 188, 156), (44, 62, 80), (192, 57, 43),
    ]
    return [gen_image(f"img_{i}.png", colors[i % len(colors)]) for i in range(count)]


def gen_text() -> str:
    """生成带时间戳的测试文案"""
    return f"pywxauto 朋友圈自动化测试 · {time.strftime('%Y-%m-%d %H:%M:%S')}"


def gen_comment() -> str:
    """生成评论内容"""
    return f"自动化测试评论 {time.strftime('%H:%M:%S')}"


# ============================================================
# 测试结果收集
# ============================================================
class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []

    def ok(self, name: str, detail: str = ""):
        self.passed.append(name)
        msg = f"  ✓ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)

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

def test_open_moment(moment: Moment, result: TestResult):
    """打开朋友圈窗口"""
    try:
        moment._open_window()
        assert moment.exists, "窗口未打开"
        result.ok("打开朋友圈窗口")
    except Exception as e:
        result.fail("打开朋友圈窗口", str(e))


def test_window_properties(moment: Moment, result: TestResult):
    """窗口属性读取"""
    try:
        moment._open_window()
        info = f"visible={moment.is_visible}, minimized={moment.is_minimized}"
        result.ok("窗口属性", info)
    except Exception as e:
        result.fail("窗口属性", str(e))


def test_refresh(moment: Moment, result: TestResult):
    """刷新朋友圈"""
    try:
        moment.refresh()
        time.sleep(2)
        result.ok("refresh()")
    except Exception as e:
        result.fail("refresh()", str(e))


def test_get_moments_top(moment: Moment, result: TestResult) -> list[MomentItem]:
    """从顶部获取动态"""
    try:
        moments = moment.get_moments(count=5, position="top")
        assert moments, "未获取到任何动态"
        result.ok("get_moments(top)", f"{len(moments)} 条")
        return moments
    except Exception as e:
        result.fail("get_moments(top)", str(e))
        return []


def test_get_moments_current(moment: Moment, result: TestResult):
    """从当前位置获取动态"""
    try:
        moments = moment.get_moments(count=3, position="current")
        result.ok("get_moments(current)", f"{len(moments)} 条")
    except Exception as e:
        result.fail("get_moments(current)", str(e))


def test_iter_moments(moment: Moment, result: TestResult):
    """生成器逐条获取"""
    try:
        items = list(moment.iter_moments(count=3, position="top"))
        result.ok("iter_moments()", f"迭代 {len(items)} 条")
    except Exception as e:
        result.fail("iter_moments()", str(e))


def test_moment_item_parse(moments: list[MomentItem], result: TestResult):
    """动态条目字段解析"""
    if not moments:
        result.skip("MomentItem 字段", "无数据")
        return
    item = moments[0]
    try:
        assert item.sender, "sender 为空"
        assert item.type, "type 为空"
        d = item.to_dict()
        assert "sender" in d and "type" in d and "content" in d
        s = str(item)
        assert len(s) > 0
        result.ok("MomentItem 字段", f"sender={item.sender!r}, type={item.type!r}")
    except Exception as e:
        result.fail("MomentItem 字段", str(e))


def test_scroll_into_visible(moment: Moment, moments: list[MomentItem], result: TestResult):
    """滚动定位动态"""
    if not moments:
        result.skip("scroll_into_visible()", "无数据")
        return
    try:
        item = moments[-1]
        ok = moment.scroll_into_visible(item)
        assert ok, "返回 False"
        result.ok("scroll_into_visible()", f"定位到 {item.sender!r}")
    except Exception as e:
        result.fail("scroll_into_visible()", str(e))


def test_like(moment: Moment, moments: list[MomentItem], result: TestResult):
    """点赞第一条动态"""
    if not moments:
        result.skip("like()", "无数据")
        return
    try:
        item = moments[0]
        ok = moment.like(item)
        assert ok, "返回 False"
        result.ok("like()", f"点赞 {item.sender!r}")
    except Exception as e:
        result.fail("like()", str(e))


def test_unlike(moment: Moment, moments: list[MomentItem], result: TestResult):
    """取消点赞第一条动态"""
    if not moments:
        result.skip("unlike()", "无数据")
        return
    try:
        item = moments[0]
        ok = moment.unlike(item)
        assert ok, "返回 False"
        result.ok("unlike()", f"取消点赞 {item.sender!r}")
    except Exception as e:
        result.fail("unlike()", str(e))


def test_comment(moment: Moment, moments: list[MomentItem], result: TestResult):
    """评论第一条动态"""
    if not moments:
        result.skip("comment()", "无数据")
        return
    try:
        item = moments[0]
        content = gen_comment()
        ok = moment.comment(item, content)
        assert ok, "返回 False"
        result.ok("comment()", f"评论 {item.sender!r}: {content!r}")
    except Exception as e:
        result.fail("comment()", str(e))


def test_publish_text(moment: Moment, result: TestResult):
    """发布纯文字朋友圈（私密）"""
    try:
        text = gen_text()
        ok = moment.publish(text=text, permission="私密")
        assert ok, "返回 False"
        result.ok("publish(纯文字)", f"内容: {text[:30]}...")
    except Exception as e:
        result.fail("publish(纯文字)", str(e))


def test_publish_single_image(moment: Moment, result: TestResult):
    """发布单图朋友圈（私密）"""
    try:
        text = f"单图测试 {time.strftime('%H:%M:%S')}"
        img = gen_image("single.png", (41, 128, 185))
        ok = moment.publish(text=text, images=[img], permission="私密")
        assert ok, "返回 False"
        result.ok("publish(单图)", f"图片: {img}")
    except Exception as e:
        result.fail("publish(单图)", str(e))


def test_publish_multiple_images(moment: Moment, result: TestResult):
    """发布多图朋友圈（私密）"""
    try:
        text = f"多图测试 {time.strftime('%H:%M:%S')}"
        images = gen_images(3)
        ok = moment.publish(text=text, images=images, permission="私密")
        assert ok, "返回 False"
        result.ok("publish(多图)", f"{len(images)} 张图片")
    except Exception as e:
        result.fail("publish(多图)", str(e))


def test_close_moment(moment: Moment, result: TestResult):
    """关闭朋友圈窗口"""
    try:
        moment.close()
        time.sleep(0.5)
        assert not moment.exists, "窗口未关闭"
        result.ok("close()")
    except Exception as e:
        result.fail("close()", str(e))


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 50)
    print("pywxauto 朋友圈接口测试")
    print("=" * 50)
    print(f"临时资源目录: {TMP_DIR}")
    print()

    # 连接微信
    print("[1/2] 连接微信...")
    try:
        wx = Weixin()
        print(f"  版本: {wx.version}, PID: {wx.pid}, 语言: {wx.language_name}")
    except Exception as e:
        print(f"  连接失败: {e}")
        return

    moment = wx.moment
    result = TestResult()

    print(f"\n[2/2] 执行测试...")
    print("-" * 50)

    # 窗口
    print("\n【窗口操作】")
    test_open_moment(moment, result)
    time.sleep(1)
    test_window_properties(moment, result)

    # 刷新
    print("\n【刷新】")
    test_refresh(moment, result)

    # 获取动态
    print("\n【获取动态】")
    moments = test_get_moments_top(moment, result)
    time.sleep(1)
    test_get_moments_current(moment, result)
    time.sleep(1)
    test_iter_moments(moment, result)
    time.sleep(1)

    # 解析
    print("\n【动态解析】")
    test_moment_item_parse(moments, result)
    if moments:
        print(f"\n  动态列表预览:")
        for i, item in enumerate(moments, 1):
            print(f"    {i}. {item}")
        print()

    # 滚动
    print("\n【滚动定位】")
    test_scroll_into_visible(moment, moments, result)
    time.sleep(1)

    # 互动
    print("\n【互动操作】")
    test_like(moment, moments, result)
    time.sleep(2)
    test_unlike(moment, moments, result)
    time.sleep(2)
    test_comment(moment, moments, result)
    time.sleep(2)

    # 发布（全部私密，不影响真实朋友圈）
    print("\n【发布朋友圈（私密）】")
    test_publish_text(moment, result)
    time.sleep(3)
    test_publish_single_image(moment, result)
    time.sleep(3)
    test_publish_multiple_images(moment, result)
    time.sleep(3)

    # 关闭
    print("\n【关闭窗口】")
    test_close_moment(moment, result)

    # 汇总
    result.summary()

    # 清理临时文件
    import shutil
    try:
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
