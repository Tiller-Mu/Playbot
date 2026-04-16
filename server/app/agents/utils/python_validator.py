import ast
from typing import Tuple, Optional

def validate_python_code(code_str: str) -> Tuple[bool, Optional[str]]:
    """
    静态校验 Python 代码的语法合法性。
    不实际执行，不消耗运算资源且无比安全。
    :param code_str: Python 代码全文
    :return: (是否通过, 错误栈详细说明)
    """
    if not code_str or not str(code_str).strip():
        return False, "代码为空"
        
    try:
        # 去掉 Markdown 的包装符号（如果有的话）
        clean_code = code_str.strip()
        if clean_code.startswith("```"):
            lines = clean_code.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_code = "\n".join(lines).strip()
            
        # 针对潜在缩进问题进行统一约束
        ast.parse(clean_code)
        return True, None
    except SyntaxError as e:
        error_msg = f"SyntaxError 语法错误: {e.msg} (第 {e.lineno} 行)"
        return False, error_msg
    except Exception as e:
        return False, f"未知的解析异常: {str(e)}"
