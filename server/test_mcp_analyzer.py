"""测试MCP页面分析器 - 验证LLM连接和分析流程"""
import asyncio
import logging
import json
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_llm_connection():
    """测试LLM连接"""
    from app.services.llm_service import get_llm_client, llm_chat_json
    
    print("=" * 60)
    print("测试1: LLM连接测试")
    print("=" * 60)
    
    try:
        client, model = await get_llm_client()
        print(f"✓ LLM客户端创建成功")
        print(f"  - 模型: {model}")
        print(f"  - Endpoint: {client.base_url}")
        
        # 测试简单对话
        response = await llm_chat_json(
            messages=[
                {"role": "system", "content": "你是一个助手"},
                {"role": "user", "content": "回复OK表示正常"}
            ],
            temperature=0.1,
            max_tokens=100
        )
        
        print(f"✓ LLM响应成功: {response[:50]}...")
        return True
        
    except Exception as e:
        print(f"✗ LLM连接失败: {e}")
        return False


async def test_component_analyzer():
    """测试组件分析器"""
    from app.services.component_analyzer import analyze_components
    
    print("\n" + "=" * 60)
    print("测试2: 静态组件分析")
    print("=" * 60)
    
    # 使用测试项目路径
    test_repo = Path("d:/dpProject/Playbot/workspace/repos/150a351f-3a27-40ad-8a73-8a1885f28391")
    
    if not test_repo.exists():
        print(f"✗ 测试项目不存在: {test_repo}")
        return None
    
    print(f"项目路径: {test_repo}")
    
    try:
        result = await analyze_components(str(test_repo))
        
        print(f"✓ 组件分析成功")
        print(f"  - 框架: {result['framework']}")
        print(f"  - 总组件数: {len(result['components'])}")
        print(f"  - 页面组件: {len(result['page_components'])}")
        print(f"  - 普通组件: {len(result['common_components'])}")
        print(f"  - 入口点: {result['entry_points']}")
        
        # 显示前5个组件
        print(f"\n前5个组件:")
        for i, comp in enumerate(result['components'][:5], 1):
            print(f"  {i}. {comp['name']} ({comp['type']}) - {comp['file_path']}")
        
        return result
        
    except Exception as e:
        print(f"✗ 组件分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_page_analyzer(components_info: dict):
    """测试页面分析器"""
    from app.services.page_component_analyzer import PageComponentAnalyzer
    
    print("\n" + "=" * 60)
    print("测试3: 页面级MCP分析")
    print("=" * 60)
    
    if not components_info:
        print("✗ 缺少组件信息，跳过测试")
        return
    
    test_repo = Path("d:/dpProject/Playbot/workspace/repos/150a351f-3a27-40ad-8a73-8a1885f28391")
    page_components = components_info.get('page_components', [])
    
    if not page_components:
        print("✗ 没有页面组件，跳过测试")
        return
    
    # 测试第一个页面
    test_page = page_components[0]
    print(f"测试页面: {test_page['name']}")
    print(f"路由: {test_page.get('route', 'N/A')}")
    print(f"文件: {test_page['file_path']}")
    
    try:
        analyzer = PageComponentAnalyzer(repo_path=str(test_repo))
        
        result = await analyzer.analyze_page(
            page_component=test_page,
            components_list=components_info['components'],
            global_rules=""
        )
        
        if result:
            print(f"✓ 页面分析成功")
            print(f"  - 页面名称: {result.get('title', 'N/A')}")
            print(f"  - 检测到的组件数: {len(result.get('detected_components', []))}")
            print(f"  - 组件列表: {result.get('detected_components', [])}")
            print(f"  - 交互元素数: {len(result.get('interactive_elements', []))}")
            print(f"  - 弹窗数: {len(result.get('modals', []))}")
            print(f"  - 表单数: {len(result.get('forms', []))}")
            
            # 显示完整的JSON结果
            print(f"\n完整分析结果:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"✗ 页面分析失败，返回None")
        
    except Exception as e:
        print(f"✗ 页面分析失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("MCP页面分析器 - 完整测试")
    print("=" * 60 + "\n")
    
    # 测试1: LLM连接
    llm_ok = await test_llm_connection()
    
    if not llm_ok:
        print("\n⚠ LLM连接失败，请先配置LLM设置")
        return
    
    # 测试2: 组件分析
    components_info = await test_component_analyzer()
    
    # 测试3: 页面分析
    await test_page_analyzer(components_info)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
