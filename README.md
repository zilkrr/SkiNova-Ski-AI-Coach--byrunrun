# SkiNova 智能滑雪AI教练系统
## 项目简介
本项目基于FastAPI搭建后端服务，结合MediaPipe Pose计算机视觉模型，实现滑雪视频上传、人体骨骼关键点提取，自动计算膝关节角度、身体前倾角，生成姿态打分与训练诊断建议，同时包含滑雪教练智能匹配推荐功能。

## 技术栈
- 后端框架：FastAPI
- 视觉识别：OpenCV + MediaPipe Pose
- 语言：Python
- 前端页面：HTML

## 文件说明
1. main.py：后端全部接口（视频姿态分析+教练推荐）
2. index.html：前端简易上传页面
3. requirements.txt：项目依赖库

## 运行方式
1. 安装依赖
pip install -r requirements.txt
2. 启动后端服务
uvicorn main:app --reload
3. 打开html页面即可上传视频进行动作分析
