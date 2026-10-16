# @Version  : 1.0
# @Author   : 小野
# @File     : test_refresh.py
# @Time     : 2026/10/10 8:36
import sys
import pythoncom
import win32com.client

print("=== 诊断开始 ===", flush=True)

print("1. CoInitialize", flush=True)
pythoncom.CoInitialize()

print("2. 尝试连接 KET.Application", flush=True)
app = None
for prog_id in ["KET.Application", "ET.Application", "WPS.Application"]:
    try:
        app = win32com.client.GetActiveObject(prog_id)
        print(f"   GetActiveObject 成功: {prog_id}", flush=True)
        break
    except Exception as e:
        print(f"   GetActiveObject 失败 {prog_id}: {e}", flush=True)
    try:
        app = win32com.client.Dispatch(prog_id)
        print(f"   Dispatch 成功: {prog_id}", flush=True)
        break
    except Exception as e:
        print(f"   Dispatch 失败 {prog_id}: {e}", flush=True)

if app is None:
    print("!!! 连接全部失败，无法继续", flush=True)
    sys.exit(1)

print("3. 读取 ActiveWorkbook", flush=True)
try:
    wb = app.ActiveWorkbook
    print(f"   wb 对象 = {wb}", flush=True)
    if wb is not None:
        try:
            print(f"   wb.Name = {wb.Name}", flush=True)
        except Exception as e:
            print(f"   读 wb.Name 失败: {e}", flush=True)
except Exception as e:
    print(f"   读 ActiveWorkbook 失败: {e}", flush=True)

print("4. 读取 ActiveSheet", flush=True)
try:
    sh = app.ActiveSheet
    print(f"   sh 对象 = {sh}", flush=True)
    if sh is not None:
        try:
            print(f"   sh.Name = {sh.Name}", flush=True)
        except Exception as e:
            print(f"   读 sh.Name 失败: {e}", flush=True)
except Exception as e:
    print(f"   读 ActiveSheet 失败: {e}", flush=True)

print("=== 诊断结束 ===", flush=True)