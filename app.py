import os
import re
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import gradio as gr
from openai import OpenAI
import numpy as np

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
        
        # 设置默认渲染配置
        self.render_config = {
            "pixel_width": 1920,      # 视频宽度
            "pixel_height": 1080,     # 视频高度
            "frame_rate": 60,         # 帧率
            "background_color": "#1C1C1C",  # 深灰色背景
        }
    
    def extract_scene_name(self, code):
        """从代码中提取场景类名"""
        scene_match = re.search(r'class\s+(\w+)\s*\(\s*Scene\s*\)', code)
        if scene_match:
            return scene_match.group(1)
        return "MathScene"
    
    def prepare_code(self, code):
        """准备代码，添加必要的配置"""
        config_code = f"""
# 设置渲染配置
config.pixel_width = {self.render_config['pixel_width']}
config.pixel_height = {self.render_config['pixel_height']}
config.frame_rate = {self.render_config['frame_rate']}
config.background_color = "{self.render_config['background_color']}"

"""
        # 在 imports 后添加配置
        if "from manim import *" in code:
            code = code.replace(
                "from manim import *",
                "from manim import *\n" + config_code
            )
        else:
            code = "from manim import *\n" + config_code + code
        
        return code
    
    def execute(self, code):
        """执行 Manim 代码并返回生成的视频路径"""
        try:
            # 提取场景名
            scene_name = self.extract_scene_name(code)
            
            # 准备代码
            prepared_code = self.prepare_code(code)
            
            # 创建临时 Python 文件
            temp_file = self.temp_dir / "temp_scene.py"
            temp_file.write_text(prepared_code, encoding='utf-8')
            
            # 执行 Manim 命令
            cmd = f"manim -pqh --fps {self.render_config['frame_rate']} {temp_file} {scene_name}"
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

    def set_quality(self, quality_preset="high"):
        """设置渲染质量预设"""
        presets = {
            "low": {
                "pixel_width": 854,
                "pixel_height": 480,
                "frame_rate": 30,
            },
            "medium": {
                "pixel_width": 1280,
                "pixel_height": 720,
                "frame_rate": 30,
            },
            "high": {
                "pixel_width": 1920,
                "pixel_height": 1080,
                "frame_rate": 60,
            },
            "ultra": {
                "pixel_width": 3840,
                "pixel_height": 2160,
                "frame_rate": 60,
            }
        }
        
        if quality_preset in presets:
            self.render_config.update(presets[quality_preset])
        else:
            raise ValueError(f"不支持的质量预设: {quality_preset}")

def extract_manim_code(content):
    """从 AI 响应中提取 Manim 代码"""
    code_match = re.search(r'```python\n(.*?)```', content, re.DOTALL)
    if not code_match:
        raise ValueError("未找到可执行的 Manim 代码")
    return code_match.group(1).strip()

def create_storyboard(concept):
    """根据概念创建动画分镜脚本"""
    prompt = f"""作为数学动画编剧，请为"{concept}"创建一个详细的分镜脚本。
要求：
1. 场景分解：将概念讲解分为3-4个关键场景
2. 视觉设计：描述每个场景的视觉元素和布局
3. 动画节奏：说明动画时长和过渡效果
4. 教学设计：解释每个场景如何帮助理解

请按以下格式输出：
1. 教学目标：[说明这个动画要达到的教学效果]
2. 场景设计：[详细描述每个场景]
3. 视觉风格：[说明整体的色彩和风格]
"""
    
    # 调用 AI 生成分镜脚本
    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def create_animation_code(storyboard):
    """根据分镜脚本生成 Manim 代码"""
    prompt = f"""基于以下分镜脚本，生成对应的 Manim 动画代码：

{storyboard}

要求：
1. 场景设置：
   - 使用 ThreeDScene 作为基类
   - 设置摄像机角度：self.set_camera_orientation(phi=75*DEGREES, theta=-45*DEGREES)
   - 添加三维坐标系作为参考：ThreeDAxes()

2. 三维元素：
   - 使用 Surface 展示曲面
   - 使用 ParametricFunction 创建空间曲线
   - 通过 move_camera 实现动态视角
   - 所有图形都应在三维空间中展示

3. 动画效果：
   - 使用 Create, Write, Transform 等基础动画
   - 通过 move_camera 展示不同视角
   - 控制每个动画在 2-3 秒内完成
   - 避免复杂的材质和渲染效果

4. 代码规范：
   - 添加中文注释说明每个步骤
   - 使用有意义的变量名
   - 避免复杂计算和随机效果
   - 使用标准颜色常量

示例结构：
```python
from manim import *

class MathVisualization(ThreeDScene):
    def construct(self):
        # 设置摄像机
        self.set_camera_orientation(phi=75*DEGREES, theta=-45*DEGREES)
        
        # 创建三维坐标系
        axes = ThreeDAxes()
        self.play(Create(axes))
        
        # 创建三维曲面
        surface = Surface(
            lambda u, v: np.array([u, v, np.sin(u*v)]),
            u_range=[-2, 2],
            v_range=[-2, 2],
            resolution=(30, 30)
        )
        surface.set_color(BLUE)
        
        # 展示动画
        self.play(Create(surface))
        self.move_camera(phi=45*DEGREES, theta=45*DEGREES, run_time=2)
        self.wait()
```
"""
    return prompt

def create_math_visualization_prompt(user_input):
    """生成数学可视化提示"""
    prompt = f"""
请为以下数学概念创建一个教学动画：{user_input}

要求：
1. 动画设计原则：
   - 专注于数学概念的直观解释
   - 使用简洁的几何图形和动画效果
   - 适度使用3D元素增强空间感
   - 避免复杂的材质和渲染效果
   - 控制动画时长在1-2分钟内

2. 动画规范：
   - 场景类必须继承自 Scene
   - 使用基础颜色常量：BLUE, RED, GREEN, YELLOW, WHITE
   - 3D元素仅限于：
     * ThreeDAxes（三维坐标系）
     * Surface（简单曲面）
     * ParametricFunction（参数曲线）
   - 动画方法限制使用：
     * Create, Write, Transform
     * Rotate, Move
     * FadeIn, FadeOut
   - 每个动画片段控制在2-3秒
   
3. 代码要求：
   - 添加中文注释说明每个步骤
   - 使用有意义的变量名
   - 3D场景使用 camera.set_euler_angles(phi, theta, gamma) 设置合适视角
   - 避免复杂的数学计算和随机效果

请按以下格式输出：
1. 教学分析：[简要分析概念的关键点和可视化重点]
2. 动画剧本：[场景描述，动画节奏，视觉重点]
3. Manim代码：[完整的可执行代码]
"""
    return prompt

def process_math_visualization(message, history):
    """处理数学可视化请求"""
    try:
        # 步骤1：扩展用户输入为分镜脚本
        print("正在生成分镜脚本...")
        storyboard = create_storyboard(message)
        print(f"分镜脚本:\n{storyboard}")
        
        # 步骤2：根据分镜脚本生成动画代码
        print("正在生成动画代码...")
        animation_response = create_animation_code(storyboard)
        print(f"动画代码:\n{animation_response}")
        
        # 步骤3：提取并执行代码
        try:
            manim_code = extract_manim_code(animation_response)
            print("提取的 Manim 代码:", manim_code)
            
            executor = ManimExecutor()
            video_path = executor.execute(manim_code)
            
            # 提取教学目标
            goal_match = re.search(r'教学目标：(.*?)场景设计：', storyboard, re.DOTALL)
            teaching_goal = goal_match.group(1).strip() if goal_match else "未找到教学目标"
            
            return f"""教学目标：

{teaching_goal}

动画演示：[video]{video_path}[/video]"""
        
        except Exception as code_error:
            return f"""生成结果：

{storyboard}

动画生成失败：{str(code_error)}"""
            
    except Exception as e:
        return f"错误: {str(e)}"

# 更新界面描述
iface = gr.ChatInterface(
    process_math_visualization,
    title="数学可视化助手",
    description="""
    🔢 输入你想了解的数学概念，AI 将为你：
    1. 创建生动的可视化动画
    2. 提供简明的概念解释
    3. 展示直观的教学演示
    
    💡 示例输入（直接输入即可）：
    - 勾股定理
    - 圆周率
    - 函数极限
    
    🎯 无需输入复杂的公式或详细说明，保持简单即可！
    """,
    theme="soft"
)

if __name__ == "__main__":
    iface.launch() 