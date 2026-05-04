"""
将 pywxauto/wx.py 编译为 .pyd 文件（Cython 编译）

用法:
    python build_pyd.py

前置条件:
    1. pip install cython
    2. 安装 Microsoft Visual C++ Build Tools
       (Visual Studio Installer → "使用 C++ 的桌面开发" 工作负载)
    3. 先运行 python _merge_wx.py 生成合并后的 wx.py

输出:
    编译后的 .pyd 文件会生成在 pywxauto/ 目录下，
    如: pywxauto/wx.cp312-win_amd64.pyd
"""

import os
import shutil
import sys

from Cython.Build import cythonize
from setuptools import Distribution, Extension
from setuptools.command.build_ext import build_ext

# 源文件
SRC = os.path.join("pywxauto", "wx.py")

ext = Extension(
    name="pywxauto.wx",
    sources=[SRC],
)

dist = Distribution({
    "ext_modules": cythonize(
        [ext],
        compiler_directives={
            "language_level": "3",      # Python 3 语法
            "boundscheck": False,       # 关闭边界检查，提升性能
            "wraparound": False,        # 关闭负索引检查
        },
    ),
})

cmd = build_ext(dist)
cmd.ensure_finalized()
cmd.run()

# 把编译产物从 build/ 复制到 pywxauto/ 目录
for root, dirs, files in os.walk("build"):
    for f in files:
        if f.endswith(".pyd") or f.endswith(".so"):
            src_path = os.path.join(root, f)
            dst_path = os.path.join("pywxauto", f)
            shutil.copy2(src_path, dst_path)
            print(f"\n[OK] compile success: {dst_path}")
            print(f"     file size: {os.path.getsize(dst_path) / 1024:.1f} KB")

print("\n[TIP] only .pyd/.so files are needed for distribution, you can remove wx.py source code")
