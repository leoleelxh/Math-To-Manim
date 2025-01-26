import os
import re
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import gradio as gr
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI client with DeepSeek base URL
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# Verify API key is present
if not os.getenv("DEEPSEEK_API_KEY"):
    raise ValueError("DEEPSEEK_API_KEY environment variable is not set. Please check your .env file.")

class ManimExecutor:
    """Manim 代码执行器"""
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "math_to_manim"
        self.output_dir = Path("static/animations")
        
        # 创建必要的目录
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_scene_name(self, code):
        """从代码中提取场景类名"""
        scene_match = re.search(r'class\s+(\w+)\s*\(\s*Scene\s*\)', code)
        if scene_match:
            return scene_match.group(1)
        return "MathScene"
    
    def execute(self, code):
        """执行 Manim 代码并返回生成的视频路径"""
        try:
            # 提取场景名
            scene_name = self.extract_scene_name(code)
            
            # 创建临时 Python 文件
            temp_file = self.temp_dir / "temp_scene.py"
            temp_file.write_text(code, encoding='utf-8')
            
            # 执行 Manim 命令
            cmd = f"manim -pqh {temp_file} {scene_name}"
            result = subprocess.run(
                cmd, 
                shell=True, 
                check=True,
                capture_output=True,
                text=True
            )
            
            # 查找生成的视频文件
            video_files = list(self.temp_dir.glob("*.mp4"))
            if not video_files:
                raise Exception("未找到生成的视频文件")
            
            # 移动视频到输出目录
            video_file = video_files[0]
            output_file = self.output_dir / f"{scene_name}_{video_file.name}"
            video_file.rename(output_file)
            
            return str(output_file)
        except subprocess.CalledProcessError as e:
            error_msg = f"Manim 执行错误:\n{e.stderr}"
            raise Exception(error_msg)
        except Exception as e:
            raise Exception(f"动画生成失败: {str(e)}")

def extract_manim_code(content):
    """从 AI 响应中提取 Manim 代码"""
    code_match = re.search(r'```python\n(.*?)```', content, re.DOTALL)
    if not code_match:
        raise ValueError("未找到可执行的 Manim 代码")
    return code_match.group(1).strip()

def create_math_visualization_prompt(user_input):
    """创建数学可视化的提示词"""
    return f"""作为专业的数学教育动画设计师，请针对以下数学概念创建教学动画：

{user_input}

请按照以下步骤设计：

1. 教学分析
- 概念的核心要点是什么？
- 学生可能遇到的难点是什么？
- 如何通过可视化帮助理解？

2. 动画剧本
- 设计循序渐进的场景
- 描述每个场景的具体动画效果
- 说明动画如何帮助理解概念

3. Manim代码
- 生成完整的、可直接执行的代码
- 必须包含以下imports:
  from manim import *
- 场景类必须继承自Scene类
- 添加详细的中文注释
- 确保代码完整且可执行
- 使用 -pqh 质量设置

请按以下格式回复：
1. 教学分析：[详细分析]
2. 动画剧本：[分场景描述]
3. Manim代码：
```python
[完整代码]
```
"""

def format_latex(text):
    """Format inline LaTeX expressions for proper rendering in Gradio."""
    # Replace single dollar signs with double for better display
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        # Skip lines that already have double dollars
        if '$$' in line:
            formatted_lines.append(line)
            continue
            
        # Format single dollar expressions
        in_math = False
        new_line = ''
        for i, char in enumerate(line):
            if char == '$' and (i == 0 or line[i-1] != '\\'):
                in_math = not in_math
                new_line += '$$' if in_math else '$$'
            else:
                new_line += char
        formatted_lines.append(new_line)
    
    return '\n'.join(formatted_lines)

def process_math_visualization(message, history):
    """处理数学可视化请求"""
    try:
        # 构建消息历史
        messages = []
        for human, assistant in history:
            messages.append({"role": "user", "content": human})
            if assistant:
                messages.append({"role": "assistant", "content": assistant})
        
        # 使用教学设计提示词
        formatted_message = create_math_visualization_prompt(message)
        messages.append({"role": "user", "content": formatted_message})
        
        # 调用 DeepSeek API
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=messages
        )
        
        # 获取响应内容
        content = response.choices[0].message.content
        
        # 提取并执行 Manim 代码
        try:
            manim_code = extract_manim_code(content)
            executor = ManimExecutor()
            video_path = executor.execute(manim_code)
            
            # 格式化输出内容
            formatted_content = format_latex(content)
            
            return f"""🎓 生成结果：

{formatted_content}

🎥 动画已生成：[video]{video_path}[/video]"""
        
        except Exception as code_error:
            # 如果代码执行失败，仍然显示分析结果
            formatted_content = format_latex(content)
            return f"""🎓 生成结果：

{formatted_content}

❌ 动画生成失败：{str(code_error)}"""
            
    except Exception as e:
        return f"错误: {str(e)}"

# Create Gradio interface with markdown enabled
iface = gr.ChatInterface(
    process_math_visualization,
    title="数学可视化助手",
    description="""
    🔢 输入数学概念或公式，AI 将：
    1. 分析教学重点
    2. 设计可视化方案
    3. 生成动画代码
    4. 渲染教学视频
    
    示例输入：
    - 勾股定理可视化
    - 函数极限的概念
    - 圆周率π的几何意义
    """,
    theme="soft"
)

if __name__ == "__main__":
    iface.launch() 