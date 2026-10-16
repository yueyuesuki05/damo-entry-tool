# @Version  : 1.0
# @Author   : 小野
# @File     : test_com.py
# @Time     : 2026/10/8 16:20
import win32com.client

tests = [
    ("Scripting.FileSystemObject", "系统文件对象"),
    ("WScript.Shell", "Windows 脚本外壳"),
    ("Shell.Application", "系统外壳"),
    ("KET.Application", "WPS 表格"),
]

for prog_id, name in tests:
    try:
        obj = win32com.client.Dispatch(prog_id)
        print(f"[✓] {name} ({prog_id}) 连接成功")
    except Exception as e:
        print(f"[×] {name} ({prog_id}) 连接失败: {e}")