# ComfyUI-BeautifulWorkflows

> **注意：这不是 ComfyUI 的插件，不需要安装到 ComfyUI 中。**
> 这是一个独立的命令行工具，在 ComfyUI 外部运行，用于批量美化工作流 JSON 文件。

> **Note: This is NOT a ComfyUI plugin/extension.** It runs as a standalone Python CLI tool outside of ComfyUI to batch-process workflow JSON files.

---

## 功能 / Features

- **布局美化** - 按节点类型分列排列，自动对齐
- **分组着色** - 为 Loader、Sampler、Conditioning 等类别自动创建彩色分组
- **去重节点** - 检测并删除重复节点，自动重接线路
- **去除广告** - 删除工作流中的广告链接和垃圾信息
- **注入说明** - 在工作流中插入作者信息、使用说明
- **LLM 命名** - 通过 Ollama（本地 AI）自动生成描述性文件名

---

## 用法 / Usage

### 环境要求
- Python 3.10+
- [Ollama](https://ollama.ai)（可选，用于 AI 命名，无则使用规则命名）

### 批量处理 inputs/ 目录下所有工作流
```bash
python beautify.py
```

### 处理单个文件
```bash
python beautify.py inputs/my_workflow.json -o outputs/result.json
```

### 对比 LLM 命名模型效果
```bash
python beautify.py --compare-models
```

---

## 目录结构 / Directory Structure

```
beautify.py          # CLI 入口
config.py            # 节点分类、颜色、广告关键词配置
layout.py            # 列式布局算法
grouping.py          # 节点分类 + Group 创建
cleaner.py           # 广告清除 + 节点去重
notes.py             # 说明注释节点生成
llm.py               # Ollama 集成（命名 + 模型对比）
inputs/              # 放入待处理的工作流 JSON + user_info.md
outputs/             # 输出美化后的工作流
```

---

## 配置作者信息

编辑 `inputs/user_info.md`：

```markdown
# Workflow Title
Author: Your Name
Website: https://example.com
Description: What this workflow does

## Footer
Custom credits text
```

---

## 节点颜色方案 / Color Scheme

| 类别 | 颜色 |
|------|------|
| Loader | 蓝色 `#2b5278` |
| Conditioning | 绿色 `#3f7a3f` |
| ControlNet | 青色 `#2d6b6b` |
| Sampler | 紫色 `#6b3fa0` |
| Latent / VAE | 琥珀 `#7a6b3f` |
| Image | 棕色 `#a0522d` |
| Utility | 灰色 `#555555` |

---

## ❤️ 支持与关注 / Support & Follow

> 开源代码可以免费，但显卡、电费、服务器和咖啡豆暂时还没学会开源。

你好，我是**赛博迪克朗**。我平时给 AI 喂提示词、给 ComfyUI 接管线，也负责修复那些“昨天明明还能跑”的神秘问题。教程里看起来三分钟解决的事，背后往往是三十次失败和一句又一句“这不应该啊”。

如果这个项目帮你少踩了一个坑、少重装了一次环境，那些和报错窗口深情对视的夜晚就算没有白熬。欢迎通过下面的方式支持和关注：

- [💙 支付宝 / Alipay](https://github.com/whmc76/.github/blob/main/SUPPORT.md#alipay)
- [🌍 PayPal](https://paypal.me/CyberDickLang)
- [📺 哔哩哔哩 / Bilibili](https://space.bilibili.com/339984)
- [▶️ YouTube](https://www.youtube.com/@CyberDickLang)

抖音、小红书、快手、今日头条、微信视频号、X：搜索全网统一名称 **“赛博迪克朗”**。

**不赞助也完全没关系。** 使用、Star、反馈、分享，甚至一句“这东西真能用”，都是继续更新的动力。谢谢你让这个项目不只是躺在我的硬盘里感动自己。
