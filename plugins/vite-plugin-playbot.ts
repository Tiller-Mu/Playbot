import fs from 'fs';
import path from 'path';

/**
 * Playbot 录制组件探测器 Vite 插件 (用于测试流水线构建)
 * 
 * 作用:
 * 在编译期间 (针对 Vue 3)，自动扫描所有的 .vue 文件并在其 template 内的最外层节点(或所有顶级节点)
 * 注入 `data-playbot-component` 属性。
 * 即使进行了代码混淆或生产环境打包，该属性也会保留在生成的 HTML 节点上，
 * 以便 Playbot 录制探针反向关联原生 DOM 与源码组件层级。
 */
export default function playbotComponentInjector() {
  return {
    name: 'vite-plugin-playbot-injector',
    // 强制在 vue 核心编译之前执行
    enforce: 'pre' as const,

    transform(code: string, id: string) {
      if (!id.endsWith('.vue')) {
        return null;
      }

      // 获取相对于项目根目录的路径（保证平台的一致性）
      let relativePath = path.relative(process.cwd(), id).replace(/\\/g, '/');
      // 抹平一些可能的前缀，通常展示 src/components/...
      
      // 我们需要将该标识注入到 template 的第一层 HTML 标签中
      const templateMatch = code.match(/<template[^>]*>/);
      
      if (!templateMatch) {
         return null;
      }
      
      const templateStart = templateMatch.index! + templateMatch[0].length;
      const beforeTemplate = code.slice(0, templateStart);
      const templateContent = code.slice(templateStart);
      
      // 使用正则查找紧接着 template 后面的各种原生 HTML tag 并注入标识
      // 例如 <div class="xxx"> -> <div data-playbot-component="src/components/MyComp.vue" class="xxx">
      // 注意: Vue 3 支持 Fragment(多根节点), 所以我们全局替换 templateContent 里所有的一级标签 (启发式)
      
      // 粗略启发式注入（匹配不在已关闭标签内的开标签）- 这里用一个简单替换演示
      const newTemplateContent = templateContent.replace(
        /(<[a-zA-Z0-9-]+)(?=[^>]*>)/, 
        `$1 data-playbot-component="${relativePath}"`
      );
      
      console.log(`\x1b[32m[Playbot Plugin] ✅ 成功着色组件: ${relativePath}\x1b[0m`);
      
      return {
        code: beforeTemplate + newTemplateContent,
        map: null // 此行允许跳过 sourcemap 挂载，如果在深层打包通常需要配合生成
      };
    }
  };
}
