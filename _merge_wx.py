"""
将 pywxauto 包的所有模块合并为单个 wx.py 文件。

合并顺序按依赖关系排列，去除模块间的 import 语句，
保留对外部库的 import。

合并后的代码中：
- _state.background 直接引用顶层变量 background
- input_wm.xxx() 直接调用同文件中的函数
- input_wx.xxx() 直接调用同文件中的函数
- 各模块的类和函数都在同一命名空间
"""

import os
import re

# 按依赖顺序排列的源文件
SOURCE_FILES = [
    'pywxauto/_state.py',
    'pywxauto/exceptions.py',
    'pywxauto/pim.py',
    'pywxauto/input_wm.py',
    'pywxauto/utils.py',
    'pywxauto/capture.py',
    'pywxauto/input_wx.py',
    'pywxauto/messages.py',
    'pywxauto/windows.py',
    'pywxauto/session.py',
    'pywxauto/friend_circle.py',
    'pywxauto/file_manager.py',
    'pywxauto/chat.py',
    'pywxauto/core.py',
]


def is_internal_import(line: str) -> bool:
    """判断是否是内部导入行"""
    stripped = line.strip()
    if stripped.startswith('from pywxauto'):
        return True
    if stripped.startswith('import pywxauto'):
        return True
    return False


def read_file_content(filepath: str) -> str:
    """读取文件内容"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def remove_internal_imports(content: str) -> str:
    """移除内部导入语句（包括多行导入）"""
    lines = content.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过 from __future__ import annotations
        if stripped == 'from __future__ import annotations':
            i += 1
            continue

        # 跳过 if TYPE_CHECKING: ... pass 块
        if stripped == 'if TYPE_CHECKING:':
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if s == 'pass' or s == '':
                    i += 1
                else:
                    # 如果下一行不是缩进的，退出
                    if not lines[i].startswith(' ') and not lines[i].startswith('\t'):
                        break
                    i += 1
            continue

        # 检查内部导入
        if is_internal_import(line):
            # 多行导入
            if '(' in stripped and ')' not in stripped:
                while i < len(lines) and ')' not in lines[i]:
                    i += 1
                i += 1  # 跳过包含 ) 的行
            else:
                i += 1
            continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def remove_external_imports(content: str, collected_imports: set) -> str:
    """移除外部导入语句（已统一放在文件顶部）"""
    lines = content.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过空行
        if not stripped:
            result.append(line)
            i += 1
            continue

        # 检查是否是顶层 import/from 语句
        if (stripped.startswith('import ') or stripped.startswith('from ')) and not line.startswith(' ') and not line.startswith('\t'):
            # 跳过 try/except 块中的导入（如 wcocr）
            if i > 0 and lines[i-1].strip() in ('try:', 'except ImportError:', 'except Exception:'):
                result.append(line)
                i += 1
                continue

            # 多行导入
            if '(' in stripped and ')' not in stripped:
                full_import = stripped
                i += 1
                while i < len(lines) and ')' not in lines[i]:
                    full_import += ' ' + lines[i].strip()
                    i += 1
                if i < len(lines):
                    full_import += ' ' + lines[i].strip()
                    i += 1
                # 不添加到结果（已在顶部）
                continue

            # 单行导入
            if stripped in collected_imports:
                i += 1
                continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def collect_external_imports(filepath: str) -> set:
    """收集文件中的外部库导入语句"""
    imports = set()
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_try_block = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == 'try:':
            in_try_block = True
            i += 1
            continue
        if stripped.startswith('except'):
            in_try_block = False
            i += 1
            continue

        # 跳过内部导入
        if is_internal_import(line):
            if '(' in stripped and ')' not in stripped:
                while i < len(lines) and ')' not in lines[i]:
                    i += 1
            i += 1
            continue

        # 跳过 try 块中的导入（特殊处理）
        if in_try_block:
            i += 1
            continue

        # 收集外部导入
        if not line.startswith(' ') and not line.startswith('\t'):
            if stripped.startswith('import ') or stripped.startswith('from '):
                if stripped == 'from __future__ import annotations':
                    i += 1
                    continue
                if 'TYPE_CHECKING' in stripped:
                    i += 1
                    continue
                imports.add(stripped)

        i += 1

    return imports


def apply_namespace_fixes(content: str) -> str:
    """
    修复合并后的命名空间引用。
    
    - _state.background -> background (顶层变量)
    
    input_wm 和 input_wx 的引用保持不变，
    通过在合并文件中创建命名空间模拟类来解决。
    """
    # _state.background -> background
    content = content.replace('_state.background', 'background')
    
    return content


def build_merged_file() -> str:
    """构建合并后的文件内容"""

    # 收集所有外部导入
    all_imports = set()
    for filepath in SOURCE_FILES:
        all_imports |= collect_external_imports(filepath)

    # 分类导入
    stdlib_modules = {
        'ctypes', 'fnmatch', 'functools', 'glob', 'io', 'json',
        'logging', 'os', 'random', 're', 'struct', 'tempfile',
        'threading', 'time', 'urllib', 'enum', 'typing', 'subprocess',
        'dataclasses', 'datetime', 'queue',
    }

    stdlib_imports = set()
    third_party_imports = set()

    for imp in all_imports:
        # 提取模块名
        if imp.startswith('import '):
            module = imp.split()[1].split('.')[0]
        else:  # from xxx import ...
            module = imp.split()[1].split('.')[0]

        if module in stdlib_modules:
            stdlib_imports.add(imp)
        else:
            third_party_imports.add(imp)

    # 构建文件头
    header = '"""\npywxauto - 微信自动化库（单文件合并版）\n\n将所有模块合并为单个文件，便于编译为 .pyd。\n"""\n\nfrom __future__ import annotations\n\n'

    # 构建导入区
    import_section = '\n'.join(sorted(stdlib_imports)) + '\n\n'
    import_section += '\n'.join(sorted(third_party_imports)) + '\n\n'

    # wcocr 特殊处理（try/except）
    import_section += 'try:\n    from pywxauto import wcocr\nexcept ImportError:\n    wcocr = None\n\n'

    # 构建各模块内容
    module_sections = []
    for filepath in SOURCE_FILES:
        module_name = os.path.splitext(os.path.basename(filepath))[0]

        content = read_file_content(filepath)

        # 移除内部导入
        content = remove_internal_imports(content)

        # 移除外部导入（已统一在顶部）
        content = remove_external_imports(content, all_imports)

        # 修复命名空间引用
        content = apply_namespace_fixes(content)

        # 清理多余空行
        while '\n\n\n\n' in content:
            content = content.replace('\n\n\n\n', '\n\n\n')

        content = content.strip()
        if not content:
            continue

        section = f'\n# {"=" * 70}\n# 模块: {module_name}\n# {"=" * 70}\n\n{content}\n'
        module_sections.append(section)

    result = header + import_section + '\n'.join(module_sections) + '\n'
    
    # 最终修复：移除 wcocr 相关的 try/except 块（已在顶部处理）
    result = result.replace(
        "try:\n    from pywxauto import wcocr\nexcept ImportError:\n    wcocr = None\n\n\n# ---- 常量 ----",
        "# ---- 常量 ----"
    )
    # 处理 try 块中导入被移除后残留的空 try/except
    result = result.replace(
        "try:\nexcept ImportError:\n    wcocr = None",
        ""
    )

    # 在 input_wm 模块内容之后插入命名空间模拟类
    input_wm_shim = '''

# ---- input_wm 命名空间（供其他模块通过 input_wm.xxx 调用） ----
class _InputWmNamespace:
    """模拟 input_wm 模块命名空间，使 input_wm.xxx() 调用方式继续工作"""
    minimize_window = staticmethod(minimize_window)
    maximize_window = staticmethod(maximize_window)
    restore_window = staticmethod(restore_window)
    close_window = staticmethod(close_window)
    focus_window = staticmethod(focus_window)
    activate_window = staticmethod(activate_window)
    deactivate_window = staticmethod(deactivate_window)
    move_window = staticmethod(move_window)
    resize_window = staticmethod(resize_window)
    show_window = staticmethod(show_window)
    hide_window = staticmethod(hide_window)
    toggle_window = staticmethod(toggle_window)
    click_window = staticmethod(click_window)
    double_click_window = staticmethod(double_click_window)
    right_click_window = staticmethod(right_click_window)
    middle_click_window = staticmethod(middle_click_window)
    scroll_window = staticmethod(scroll_window)
    key_down_window = staticmethod(key_down_window)
    key_up_window = staticmethod(key_up_window)
    key_press_window = staticmethod(key_press_window)
    key_hotkey_window = staticmethod(key_hotkey_window)
    key_type_window = staticmethod(key_type_window)

input_wm = _InputWmNamespace()
'''

    # 在 input_wm 模块结束、utils 模块开始之前插入
    result = result.replace(
        '\n# ======================================================================\n# 模块: utils\n# ======================================================================',
        input_wm_shim + '\n# ======================================================================\n# 模块: utils\n# ======================================================================'
    )

    # 在 input_wx 模块内容之后插入命名空间模拟类
    # 需要在 messages 模块之前
    input_wx_shim = '''

# ---- input_wx 命名空间（供其他模块通过 input_wx.xxx 调用） ----
class _InputWxNamespace:
    """模拟 input_wx 模块命名空间，使 input_wx.xxx() 调用方式继续工作"""
    focus = staticmethod(focus)
    click = staticmethod(click)
    send_keys = staticmethod(send_keys)
    move_to = staticmethod(move_to)
    scroll_at = staticmethod(scroll_at)
    send_shortcut = staticmethod(send_shortcut)
    select_all = staticmethod(select_all)
    copy = staticmethod(copy)
    paste = staticmethod(paste)

input_wx = _InputWxNamespace()
'''

    result = result.replace(
        '\n# ======================================================================\n# 模块: messages\n# ======================================================================',
        input_wx_shim + '\n# ======================================================================\n# 模块: messages\n# ======================================================================'
    )

    # 添加别名（原代码中通过 import as 创建的别名）
    result = result.replace(
        "def rand_ratio() -> float:\n    \"\"\"返回 0.2~0.6 之间的随机比例，用于模拟人类点击偏移\"\"\"\n    return random.uniform(0.2, 0.6)\n",
        "def rand_ratio() -> float:\n    \"\"\"返回 0.2~0.6 之间的随机比例，用于模拟人类点击偏移\"\"\"\n    return random.uniform(0.2, 0.6)\n\n# 别名（原模块间 import as 的兼容）\n_is_url = is_url\n_download_to_temp = download_to_temp\n_rand_ratio = rand_ratio\n",
        1  # 只替换第一次出现（utils 模块中的）
    )

    # MSG_CLASS_TO_EVENT 别名
    result = result.replace(
        "    OtherMessage: Event.OTHER,\n}\n",
        "    OtherMessage: Event.OTHER,\n}\n\n_MSG_CLASS_TO_EVENT = MSG_CLASS_TO_EVENT\n",
        1
    )

    return result


if __name__ == '__main__':
    output = build_merged_file()
    output_path = os.path.join('pywxauto', 'wx.py')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)

    lines = output.count('\n')
    size = len(output.encode('utf-8'))
    print(f'[OK] 合并完成: {output_path}')
    print(f'     {lines} 行, {size / 1024:.1f} KB')
