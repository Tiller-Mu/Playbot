import re

with open('server/app/services/page_component_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 _analyze_with_llm 函数签名，添加注释参数
old_signature = '''    async def _analyze_with_llm(
        self,
        page_name: str,
        page_route: str,
        page_source: str,
        components_summary: str,
        global_rules: str
    ) -> Optional[dict]:
        """使用LLM基于命名推断页面功能（简化版，不传完整代码）"""'''

new_signature = '''    async def _analyze_with_llm(
        self,
        page_name: str,
        page_route: str,
        page_source: str,
        components_summary: str,
        global_rules: str,
        page_comments: str = "",
        component_comments: dict = None
    ) -> Optional[dict]:
        """使用LLM基于命名推断页面功能（简化版，不传完整代码）"""
        if component_comments is None:
            component_comments = {}'''

content = content.replace(old_signature, new_signature)

# 修改Prompt，添加注释信息
old_prompt = '''        prompt = f"""你是一个前端页面分析专家。请根据页面名称和组件列表，推断页面的核心功能。

## 页面信息
- 页面名称: {page_name}
- 路由路径: {page_route}

## 页面使用的组件
{component_list_str}  # 最多15个组件

## 分析任务

根据页面名称和组件名，用**一句话**描述这个页面的核心功能。'''

new_prompt = '''        # 构建页面注释信息
        page_comments_section = ""
        if page_comments:
            page_comments_section = f"""## 页面注释（开发者编写）
{page_comments}

"""
        
        # 构建组件注释信息
        component_comments_section = ""
        if component_comments:
            comp_comments_lines = []
            for comp_name, comp_comment in component_comments.items():
                if comp_comment and len(comp_comment) > 5:
                    comp_comments_lines.append(f"- **{comp_name}**: {comp_comment}")
            if comp_comments_lines:
                component_comments_section = f"""## 组件注释（开发者编写）
{chr(10).join(comp_comments_lines)}

"""
        
        prompt = f"""你是一个前端页面分析专家。请根据页面信息、开发者注释和组件列表，推断页面的核心功能。

## 页面信息
- 页面名称: {page_name}
- 路由路径: {page_route}

{page_comments_section}{component_comments_section}## 页面使用的组件
{component_list_str}  # 最多15个组件

## 分析任务

结合页面名称、开发者注释和组件名，用**一句话**描述这个页面的核心功能。'''

content = content.replace(old_prompt, new_prompt)

with open('server/app/services/page_component_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_component_analyzer.py 已更新，LLM分析时会使用注释信息')
