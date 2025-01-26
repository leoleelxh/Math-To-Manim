import os
import re
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import gradio as gr
from openai import OpenAI
import numpy as np
from manim import *

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

2. 文字说明系统：
   - 每个场景开始前显示场景标题（中文，优雅的字体）
   - 关键步骤配有解释文字（简洁清晰的说明）
   - 重要公式使用 MathTex 优雅呈现
   - 文字要有适当的显示时长（3-5秒）
   - 文字要有渐入渐出效果
   - 使用 VGroup 组织文字和图形的关联

3. 动画节奏：
   - 场景间要有明确的过渡（淡入淡出）
   - 重要概念讲解时放慢速度（4-6秒）
   - 复杂变换分步展示
   - 关键处添加短暂停顿（self.wait(2)）
   - 总时长控制在 3-5 分钟

4. 三维元素：
   - 使用 Surface 展示曲面
   - 使用 ParametricFunction 创建空间曲线
   - 通过 move_camera 展示多角度视图
   - 所有图形都在三维空间中展示

5. 教学设计：
   - 概念逐层递进
   - 重要内容重复强调
   - 添加直观的类比说明
   - 结合实际应用场景
   - 每个场景结束前总结要点

示例结构：
```python
from manim import *

class MathVisualization(ThreeDScene):
    def construct(self):
        # 设置摄像机
        self.set_camera_orientation(phi=75*DEGREES, theta=-45*DEGREES)
        
        # 创建标题
        title = Text("数学概念可视化", font="SimSun", color=BLUE).scale(1.2)
        subtitle = Text("让抽象变得具体", font="SimSun", color=BLUE_B).scale(0.8)
        title_group = VGroup(title, subtitle).arrange(DOWN)
        
        # 显示标题
        self.play(Write(title_group), run_time=2)
        self.wait(2)
        self.play(FadeOut(title_group))
        
        # 创建三维坐标系
        axes = ThreeDAxes()
        axes_labels = axes.get_axis_labels()
        self.play(Create(axes), Create(axes_labels))
        
        # 创建说明文字
        explanation = Text("观察三维空间中的函数关系", font="SimSun").scale(0.8)
        explanation.to_corner(UL)
        self.play(Write(explanation), run_time=2)
        
        # 创建三维曲面
        surface = Surface(
            lambda u, v: np.array([u, v, np.sin(u*v)]),
            u_range=[-2, 2],
            v_range=[-2, 2],
            resolution=(30, 30)
        )
        surface.set_color(BLUE)
        
        # 添加公式说明
        formula = MathTex(r"z = \sin(xy)").next_to(surface, UP)
        
        # 展示动画
        self.play(
            Create(surface),
            Write(formula),
            run_time=3
        )
        
        # 旋转视角
        self.move_camera(phi=45*DEGREES, theta=45*DEGREES, run_time=3)
        
        # 添加要点总结
        summary = Text("函数在三维空间的几何意义", font="SimSun").scale(0.8)
        summary.to_edge(DOWN)
        self.play(Write(summary))
        self.wait(2)
```

注意事项：
1. 文字要简洁易懂
2. 动画节奏要流畅自然
3. 重要概念要反复强调
4. 场景转换要平滑
5. 保持整体美感
"""
    return prompt

def create_math_visualization_prompt(user_input):
    """生成数学可视化提示"""
    prompt = f"""请为以下数学概念创建一个教学动画：{user_input}

基本要求：
1. 动画设计：
   - 从最简单的形式开始，逐步展示概念的复杂性
   - 使用2D/3D空间展示数学关系，根据概念特点选择合适的维度
   - 动画要素包括：图形、公式、文字说明
   - 每个步骤都要有清晰的解释

2. 动画规范：
   - 场景类根据需要选择 Scene 或 ThreeDScene
   - 动画方法：Create, Write, Transform, FadeIn/Out 等基础方法
   - 动画时长：关键概念4-6秒，过渡2-3秒
   - 总时长控制在3-5分钟
   
3. 代码要求：
   - 添加中文注释说明每个步骤
   - 使用有意义的变量名
   - 确保代码可执行性和复用性
   - 避免不必要的复杂计算

4. 可选功能：
   - 如果概念涉及变化过程，使用 ValueTracker 实现动态变化
   - 如果需要强调某些部分，使用 Indicate 或颜色变化
   - 如果有多个相关概念，使用 VGroup 组织它们的关系
   - 如果需要多视角展示，使用 move_camera（在 ThreeDScene 中）

请按以下格式输出：
1. 教学分析：[分析概念的关键点，确定可视化重点]
2. 动画剧本：[场景描述，动画节奏，重点说明]
3. Manim代码：[完整的可执行代码]
"""
    return prompt

def process_math_visualization(message, history):
    """处理数学可视化请求"""
    try:
        # 生成动画代码
        print("\n1. 开始处理可视化请求...")
        print(f"用户输入: {message}")
        
        print("\n2. 正在生成AI提示...")
        prompt = create_math_visualization_prompt(message)
        print(f"生成的提示内容:\n{prompt}")
        
        print("\n3. 正在调用AI生成代码...")
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        print("\n4. AI响应内容:")
        print("-" * 50)
        print(content)
        print("-" * 50)
        
        # 提取并执行代码
        try:
            print("\n5. 正在提取Manim代码...")
            manim_code = extract_manim_code(content)
            print("\n6. 提取的代码:")
            print("-" * 50)
            print(manim_code)
            print("-" * 50)
            
            print("\n7. 正在执行Manim代码...")
            executor = ManimExecutor()
            video_path = executor.execute(manim_code)
            print(f"\n8. 视频生成成功！保存在: {video_path}")
            
            # 提取教学分析
            print("\n9. 正在提取教学分析...")
            analysis_match = re.search(r'教学分析：(.*?)动画剧本：', content, re.DOTALL)
            teaching_analysis = analysis_match.group(1).strip() if analysis_match else "未找到教学分析"
            print("\n10. 提取的教学分析:")
            print("-" * 50)
            print(teaching_analysis)
            print("-" * 50)
            
            return f"""教学分析：

{teaching_analysis}

动画演示：[video]{video_path}[/video]"""
        
        except Exception as code_error:
            print(f"\n❌ 代码执行失败: {str(code_error)}")
            return f"""生成结果：

{content}

动画生成失败：{str(code_error)}"""
            
    except Exception as e:
        print(f"\n❌ 处理失败: {str(e)}")
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

class FractalTree(Scene):
    def construct(self):
        # 初始化参数
        start_length = 3  # 初始树干长度
        angle = 30*DEGREES  # 分叉角度
        length_ratio = 0.7  # 长度比例
        iterations = 4  # 迭代次数

        # 创建基础树干
        trunk = Line(ORIGIN, UP*start_length, color=BLUE)
        title = Text("分形树 - 第0次迭代", font="SimSun").to_edge(UP)
        self.play(Create(trunk), Write(title))
        self.wait(1)

        # 存储所有分支
        branches = VGroup(trunk)
        all_new_branches = VGroup()

        # 递归生成分形树
        for n in range(1, iterations+1):
            new_branches = VGroup()
            
            # 遍历当前层级的分支
            for branch in branches:
                # 获取当前分支的向量
                branch_vector = branch.get_vector()
                end_point = branch.get_end()
                
                # 创建左分支
                left_branch = Line(
                    start=end_point,
                    end=end_point + rotate_vector(branch_vector*length_ratio, angle),
                    color=GREEN
                )
                
                # 创建右分支
                right_branch = Line(
                    start=end_point,
                    end=end_point + rotate_vector(branch_vector*length_ratio, -angle),
                    color=GREEN
                )
                
                # 添加新分支
                new_branches.add(left_branch, right_branch)
            
            # 更新标题
            new_title = Text(f"分形树 - 第{n}次迭代", font="SimSun").to_edge(UP)
            
            # 创建动画
            self.play(
                Transform(title, new_title),
                LaggedStart(*[Create(b) for b in new_branches], lag_ratio=0.1),
                run_time=2
            )
            
            # 更新分支集合
            all_new_branches.add(new_branches)
            branches = new_branches
            self.wait(0.5)

        # 添加公式
        formula = MathTex(
            r"L_{n} = ", r"r", r" \times L_{n-1}",
            r"\\", r"\theta = 30^\circ"
        ).to_edge(DOWN)
        
        self.play(Write(formula))
        self.wait(1)

        # 添加参数说明
        param_text = Text(
            "r: 长度比例\nθ: 分叉角度",
            font="SimSun",
            color=YELLOW
        ).scale(0.8).next_to(formula, RIGHT)
        
        self.play(Write(param_text))
        self.wait(2) 