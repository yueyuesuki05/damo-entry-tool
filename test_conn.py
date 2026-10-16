import win32com.client
import pythoncom

pythoncom.CoInitialize()

# 测试 1：Dispatch（会尝试启动新实例）
print("--- 测试 Dispatch ---")
for prog_id in ["KET.Application", "ET.Application", "WPS.Application"]:
    try:
        app = win32com.client.Dispatch(prog_id)
        print(f"Dispatch 成功: {prog_id}")
        break
    except Exception as e:
        print(f"Dispatch 失败 {prog_id}: {e}")

# 测试 2：用 clsid 直接查找
print("--- 测试 GetActiveObject 每个 ProgID ---")
for prog_id in ["KET.Application", "ET.Application", "WPS.Application"]:
    try:
        app = win32com.client.GetActiveObject(prog_id)
        print(f"GetActiveObject 成功: {prog_id}")
    except Exception as e:
        print(f"GetActiveObject 失败 {prog_id}: {e}")