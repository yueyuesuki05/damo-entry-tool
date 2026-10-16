# @Version  : 1.0
# @Author   : 小野
# @File     : test_active.py
# @Time     : 2026/10/9 16:45
import win32com.client

print("--- 测试 Dispatch ---")
try:
    app = win32com.client.Dispatch("KET.Application")
    wb = app.ActiveWorkbook
    print(f"Dispatch 成功")
    print(f"ActiveWorkbook = {wb.Name if wb else '无'}")
except Exception as e:
    print(f"Dispatch 失败: {e}")

print("--- 测试 GetActiveObject ---")
try:
    app = win32com.client.GetActiveObject("KET.Application")
    wb = app.ActiveWorkbook
    print(f"GetActiveObject 成功")
    print(f"ActiveWorkbook = {wb.Name if wb else '无'}")
except Exception as e:
    print(f"GetActiveObject 失败: {e}")