"""
Vue文件注释提取工具
功能：从Vue单文件组件中提取页面注释和组件注释
"""
import re
from typing import Optional


def extract_vue_comments(file_content: str) -> dict:
    """
    提取Vue文件的注释信息
    
    返回: {
        "page_comments": "页面级注释（文件顶部注释）",
        "component_comments": {
            "ComponentName": "组件注释内容",
            ...
        }
    }
    """
    result = {
        "page_comments": "",
        "component_comments": {}
    }
    
    # 1. 提取文件顶部注释（前100行内的注释块）
    result["page_comments"] = _extract_top_comments(file_content)
    
    # 2. 提取组件注释
    result["component_comments"] = _extract_component_comments(file_content)
    
    return result


def _extract_top_comments(content: str, max_lines: int = 100) -> str:
    """
    提取文件顶部注释
    
    策略：
    1. 检查前max_lines行
    2. 提取第一个注释块（/* */ 或 // 或 <!-- -->）
    3. 遇到代码行就停止
    """
    lines = content.split('\n')[:max_lines]
    comments = []
    in_comment = False
    found_code = False
    
    for line in lines:
        stripped = line.strip()
        
        # 跳过空行
        if not stripped:
            if in_comment:
                comments.append('')
            continue
        
        # 如果遇到代码行且还没开始注释，停止
        if found_code and not in_comment:
            break
        
        # 检测多行注释 /* */
        if '/*' in stripped:
            in_comment = True
            # 提取 /* 后的内容
            comment_start = stripped.index('/*') + 2
            if '*/' in stripped[comment_start:]:
                # 单行多行注释 /* ... */
                comment_end = stripped.index('*/', comment_start)
                comment_text = stripped[comment_start:comment_end].strip()
                if comment_text:
                    comments.append(comment_text)
                in_comment = False
                found_code = True
            else:
                # 多行注释开始
                comment_text = stripped[comment_start:].strip()
                if comment_text:
                    comments.append(comment_text)
            continue
        
        if in_comment:
            if '*/' in stripped:
                # 多行注释结束
                comment_end = stripped.index('*/')
                comment_text = stripped[:comment_end].strip()
                if comment_text:
                    comments.append(comment_text)
                in_comment = False
                found_code = True
            else:
                comments.append(stripped)
            continue
        
        # 检测单行注释 //
        if stripped.startswith('//'):
            comment_text = stripped[2:].strip()
            if comment_text:
                comments.append(comment_text)
            continue
        
        # 检测HTML注释 <!-- -->
        if '<!--' in stripped:
            if '-->' in stripped:
                # 单行HTML注释
                start = stripped.index('<!--') + 4
                end = stripped.index('-->', start)
                comment_text = stripped[start:end].strip()
                if comment_text:
                    comments.append(comment_text)
                found_code = True
            else:
                # 多行HTML注释开始
                in_comment = True
                start = stripped.index('<!--') + 4
                comment_text = stripped[start:].strip()
                if comment_text:
                    comments.append(comment_text)
            continue
        
        # 如果遇到非注释代码，标记
        if not in_comment and not stripped.startswith('*'):
            found_code = True
            break
    
    # 清理注释：移除多余的连续空行
    cleaned = []
    prev_empty = False
    for comment in comments:
        is_empty = not comment.strip()
        if is_empty and prev_empty:
            continue
        cleaned.append(comment)
        prev_empty = is_empty
    
    return '\n'.join(cleaned).strip()


def _extract_component_comments(content: str) -> dict:
    """
    提取组件注释
    
    策略：
    1. 查找 export default { name: 'ComponentName' } 或 defineComponent({ name: 'Xxx' })
    2. 提取组件定义前的注释
    3. 也提取 <script> 中组件名称定义前的注释
    """
    component_comments = {}
    
    # 策略1: 匹配 export default 或 defineComponent 前的注释
    # 支持格式：
    # /** 组件说明 */
    # export default { name: 'UserForm' }
    patterns = [
        # JSDoc 注释 + export default
        r'(/\*\*[\s\S]*?\*/)\s*\n\s*export\s+default\s*\{',
        # 单行注释 + export default
        r'(//[^\n]*)\s*\n\s*export\s+default\s*\{',
        # JSDoc 注释 + defineComponent
        r'(/\*\*[\s\S]*?\*/)\s*\n\s*(?:const\s+\w+\s*=\s*)?defineComponent\s*\(',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, content)
        for match in matches:
            comment_block = match.group(1).strip()
            # 清理注释标记
            comment_text = _clean_comment(comment_block)
            
            # 尝试提取组件名称
            # 从后面查找 name: 'Xxx' 或 name: "Xxx"
            after_comment = content[match.end():match.end()+200]
            name_match = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", after_comment)
            
            if name_match:
                component_name = name_match.group(1)
                if comment_text and len(comment_text) > 5:  # 忽略太短的注释
                    component_comments[component_name] = comment_text
    
    # 策略2: 匹配 Vue 3 setup 语法糖中的注释
    # /** 组件说明 */
    # const componentName = defineComponent(...)
    setup_pattern = r'(/\*\*[\s\S]*?\*/)\s*\n\s*const\s+(\w+)\s*=\s*defineComponent'
    matches = re.finditer(setup_pattern, content)
    for match in matches:
        comment_block = match.group(1).strip()
        component_name = match.group(2)
        comment_text = _clean_comment(comment_block)
        
        if comment_text and len(comment_text) > 5:
            component_comments[component_name] = comment_text
    
    return component_comments


def _clean_comment(comment: str) -> str:
    """清理注释标记（/*, */, //, *, <!--, -->）"""
    lines = comment.split('\n')
    cleaned = []
    
    for line in lines:
        # 移除 JSDoc 标记
        line = re.sub(r'^\s*/\*\*?\s*', '', line)
        line = re.sub(r'\*/\s*$', '', line)
        line = re.sub(r'^\s*\*\s*', '', line)
        line = re.sub(r'^\s*//\s*', '', line)
        line = re.sub(r'<!--\s*', '', line)
        line = re.sub(r'\s*-->', '', line)
        
        cleaned.append(line.rstrip())
    
    return '\n'.join(cleaned).strip()


# 测试代码
if __name__ == "__main__":
    test_vue = """
/**
 * 用户表单组件
 * 用于新增和编辑用户信息
 * 
 * @author John Doe
 */
<template>
  <div class="user-form">
    <!-- 表单内容 -->
    <el-form :model="form">
      <el-form-item label="用户名">
        <el-input v-model="form.name" />
      </el-form-item>
    </el-form>
  </div>
</template>

<script>
/**
 * 用户表单逻辑
 * 处理表单验证和提交
 */
export default {
  name: 'UserForm',
  data() {
    return {
      form: {}
    }
  }
}
</script>
"""
    
    result = extract_vue_comments(test_vue)
    print("页面注释:")
    print(result["page_comments"])
    print("\n组件注释:")
    for name, comment in result["component_comments"].items():
        print(f"  {name}: {comment[:50]}...")
