# @Version  : 1.0
# @Author   : 小野
# @File     : 底漆填写工具.py 主程序入口
# @Time     : 2026/9/30 13:17

import os
import sys

# 强制把工作目录切到 exe 所在目录（或脚本所在目录）
try:
    if getattr(sys, 'frozen', False):
        _base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        _base = os.path.dirname(os.path.abspath(__file__))
    os.chdir(_base)
except Exception:
    pass

from ui_main import run

if __name__ == "__main__":
    run()