"""
Playbot 全栈服务启动器
功能：同时启动前端和后端服务，分别打开独立控制台窗口
使用方法：python start.py
"""
import subprocess
import sys
import time
import os
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def kill_process_by_port(port):
    """根据端口号终止进程"""
    try:
        result = subprocess.run(
            f'netstat -ano | findstr :{port}',
            capture_output=True, text=True, shell=True
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if 'LISTENING' in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                    print(f"   ✓ 已终止端口 {port} 上的进程 PID: {pid}")
    except Exception as e:
        print(f"   ⚠ 终止进程时出错: {e}")


def start_backend():
    """启动后端服务"""
    print("\n" + "=" * 60)
    print("🚀 启动后端服务")
    print("=" * 60)
    
    server_dir = Path(__file__).parent / "server"
    port = 8004
    
    # 检查并清理端口
    print(f"\n📡 检查端口 {port}...")
    result = subprocess.run(
        f'netstat -ano | findstr :{port}',
        capture_output=True, text=True, shell=True
    )
    
    if 'LISTENING' in result.stdout:
        print(f"   ⚠ 端口 {port} 已被占用，正在清理...")
        kill_process_by_port(port)
        time.sleep(1)
    
    # 使用Python 3.14启动后端
    print(f"   ✓ 启动后端服务 (端口: {port}, Python 3.14)")
    
    # 使用python命令（py命令可能失效）
    cmd = f'python -m uvicorn app.main:app --reload --port {port}'
    
    # 使用start命令确保弹出新窗口，改用 powershell 获得极大默认缓冲区（3000行+）
    subprocess.Popen(
        f'start "Playbot Backend" powershell -NoExit -Command "{cmd}"',
        cwd=server_dir,
        shell=True
    )
    
    print("   ✓ 后端服务已启动（新窗口）")


def start_frontend():
    """启动前端服务"""
    print("\n" + "=" * 60)
    print("🎨 启动前端服务")
    print("=" * 60)
    
    client_dir = Path(__file__).parent / "client"
    port = 5174
    
    # [模拟自动化构建注入] 将测试环境用的 Vite Plugin 注入到 target 项目中
    vite_config_path = client_dir / "vite.config.ts"
    try:
        content = vite_config_path.read_text(encoding='utf-8')
        if 'playbotComponentInjector' not in content:
            print(f"   ✓ [CI/CD阶段] 正在自动化挂载 playbot 组件侦测插件...")
            import_stmt = "import playbotComponentInjector from '../plugins/vite-plugin-playbot';\n"
            new_content = import_stmt + content
            new_content = new_content.replace('plugins: [vue()]', 'plugins: [vue(), playbotComponentInjector()]')
            vite_config_path.write_text(new_content, encoding='utf-8')
    except Exception as e:
        print(f"   ⚠ 注入测试构建片段失败: {e}")
    
    # 检查并清理端口
    print(f"\n📡 检查端口 {port}...")
    result = subprocess.run(
        f'netstat -ano | findstr :{port}',
        capture_output=True, text=True, shell=True
    )
    
    if 'LISTENING' in result.stdout:
        print(f"   ⚠ 端口 {port} 已被占用，正在清理...")
        kill_process_by_port(port)
        time.sleep(1)
    
    # 启动前端（新窗口，使用 PowerShell 获取大缓冲区）
    print(f"   ✓ 启动前端服务 (端口: {port})")
    
    subprocess.Popen(
        'start "Playbot Frontend" powershell -NoExit -Command "npm run dev"',
        cwd=client_dir,
        shell=True
    )
    
    print("   ✓ 前端服务已启动（新窗口）")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🎯 Playbot 全栈服务启动器")
    print("=" * 60)
    print("\n📋 启动计划:")
    print("   1. 后端服务 (FastAPI + Uvicorn)")
    print("      - 地址: http://localhost:8004")
    print("      - 特性: 自动热更新")
    print("   2. 前端服务 (Vue3 + Vite)")
    print("      - 地址: http://localhost:5174")
    print("      - 特性: 自动热更新")
    print("\n⏳ 正在启动服务...\n")
    
    try:
        # 启动后端
        start_backend()
        
        # 等待一下，让后端先启动
        time.sleep(2)
        
        # 启动前端
        start_frontend()
        
        # 等待服务启动
        time.sleep(3)
        
        print("\n" + "=" * 60)
        print("✅ 所有服务已启动完成！")
        print("=" * 60)
        print("\n🌐 访问地址:")
        print("   • 前端: http://localhost:5174")
        print("   • 后端API: http://localhost:8004")
        print("   • API文档: http://localhost:8004/docs")
        print("\n💡 提示:")
        print("   • 两个服务分别在独立的控制台窗口运行")
        print("   • 关闭窗口即可停止对应服务")
        print("   • 代码修改后会自动热更新")
        print("\n🛑 按 Ctrl+C 退出此启动器（不影响已启动的服务）\n")
        
        # 保持脚本运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 启动器已退出")
        print("ℹ️  已启动的服务仍在运行，请手动关闭窗口停止服务")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
