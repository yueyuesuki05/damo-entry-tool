@echo off
chcp 65001 >nul
echo === 启动前 ===
echo 当前目录: %cd%
cd /d "D:\PythonProject\damo_tool"
echo 切换后目录: %cd%
echo === 开始运行 ===
"D:\PythonProject\damo_tool\.venv\Scripts\python.exe" "D:\PythonProject\damo_tool\main.py"
echo === 程序已退出 ===
pause