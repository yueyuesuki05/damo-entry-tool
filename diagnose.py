# @Version  : 1.0
# @Author   : 小野
# @File     : diagnose.py
# @Time     : 2026/10/8 15:20
import sys
import struct
import winreg

print("=" * 60)
print("1. Python 环境")
print("=" * 60)
print(f"Python 版本: {sys.version}")
print(f"Python 位数: {struct.calcsize('P') * 8} 位")
print(f"Python 路径: {sys.executable}")

print()
print("=" * 60)
print("2. pywin32 / pythoncom 检查")
print("=" * 60)
try:
    import win32com
    print(f"win32com 路径: {win32com.__file__}")
except Exception as e:
    print(f"win32com 导入失败: {e}")

try:
    import pythoncom
    print(f"pythoncom 路径: {pythoncom.__file__}")
except Exception as e:
    print(f"pythoncom 导入失败: {e}")

print()
print("=" * 60)
print("3. 注册表检查")
print("=" * 60)


def check_path(root, path):
    try:
        key = winreg.OpenKey(root, path)
        print(f"[✓] 存在: {path}")
        try:
            v, _ = winreg.QueryValueEx(key, None)
            print(f"    默认值 = {v}")
        except Exception:
            pass
        try:
            v, _ = winreg.QueryValueEx(key, "CLSID")
            print(f"    CLSID = {v}")
        except Exception:
            print(f"    CLSID 缺失")
        try:
            v, _ = winreg.QueryValueEx(key, "CurVer")
            print(f"    CurVer = {v}")
        except Exception:
            print(f"    CurVer 缺失")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        print(f"[×] 不存在: {path}")
        return False
    except Exception as e:
        print(f"[!] 出错 {path}: {e}")
        return False


paths_to_check = [
    r"KET.Application",
    r"WOW6432Node\KET.Application",
    r"KET.Application.9",
    r"WOW6432Node\KET.Application.9",
    r"CLSID\{45540001-5750-5300-4B49-4E47534F4655}",
    r"WOW6432Node\CLSID\{45540001-5750-5300-4B49-4E47534F4655}",
    r"CLSID\{45540001-5750-5300-4B49-4E47534F4655}\LocalServer32",
    r"WOW6432Node\CLSID\{45540001-5750-5300-4B49-4E47534F4655}\LocalServer32",
]

for p in paths_to_check:
    check_path(winreg.HKEY_CLASSES_ROOT, p)
    print()

# 搜索所有 KET 相关
print("=" * 60)
print("4. HKEY_CLASSES_ROOT 下所有 KET.* 项")
print("=" * 60)
try:
    hkcr = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
    i = 0
    while True:
        try:
            name = winreg.EnumKey(hkcr, i)
            if name.startswith("KET"):
                print(f"  - {name}")
            i += 1
        except OSError:
            break
    winreg.CloseKey(hkcr)
except Exception as e:
    print(f"枚举失败: {e}")

# 搜索 WOW6432Node 下所有 KET 相关
print()
print("=" * 60)
print("5. HKEY_CLASSES_ROOT\WOW6432Node 下所有 KET.* 项")
print("=" * 60)
try:
    hkcr = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"WOW6432Node")
    i = 0
    while True:
        try:
            name = winreg.EnumKey(hkcr, i)
            if name.startswith("KET"):
                print(f"  - {name}")
            i += 1
        except OSError:
            break
    winreg.CloseKey(hkcr)
except Exception as e:
    print(f"枚举失败: {e}")

input("\n按回车退出...")