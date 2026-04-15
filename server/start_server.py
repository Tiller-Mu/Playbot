"""
后端服务自动重启脚本
功能：启动后端服务，并在检测到Python文件变化时自动重启
使用方法：python start_server.py
"""
import subprocess
import sys
import time
import os
from pathlib import Path
import signal


def get_python_files(directory):
    """获取目录下所有Python文件的最后修改时间"""
    python_files = {}
    for path in Path(directory).rglob("*.py"):
        python_files[str(path)] = path.stat().st_mtime
    return python_files


def kill_process_by_port(port):
    """根据端口号终止进程"""
    try:
        # Windows系统
        result = subprocess.run(
            f'netstat -ano | findstr :{port}',
            capture_output=True, text=True, shell=True
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if 'LISTENING' in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True)
                    print(f"已终止端口 {port} 上的进程 PID: {pid}")
    except Exception as e:
        print(f"终止进程时出错: {e}")


def start_server():
    """启动后端服务"""
    print("=" * 60)
    print("Playbot 后端服务启动器")
    print("=" * 60)
    
    server_dir = Path(__file__).parent
    port = 8003
    
    # 检查端口是否被占用
    result = subprocess.run(
        f'netstat -ano | findstr :{port}',
        capture_output=True, text=True, shell=True
    )
    
    if 'LISTENING' in result.stdout:
        print(f"\n⚠️  端口 {port} 已被占用，正在清理...")
        kill_process_by_port(port)
        time.sleep(2)
    
    print(f"\n🚀 启动后端服务 (端口: {port})")
    print("📝 按 Ctrl+C 停止服务")
    print("=" * 60)
    
    try:
        # 启动Uvicorn服务
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", str(port)],
            cwd=server_dir,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        
        # 等待进程结束
        process.wait()
        
    except KeyboardInterrupt:
        print("\n\n🛑 正在停止服务...")
        process.terminate()
        process.wait()
        print("✅ 服务已停止")
    except Exception as e:
        print(f"\n❌ 服务启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    start_server()
