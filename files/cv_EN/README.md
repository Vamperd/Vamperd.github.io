# Pengyuan Wang - Academic CV (LaTeX)

这个目录包含 Pengyuan Wang 学术简历的完整 LaTeX 源码和编译后的 PDF。

## 文件说明

- **`cv.tex`** - LaTeX 主文件，包含所有简历内容和格式设置
- **`cv.pdf`** - 编译后的 PDF 文件（可直接下载）
- **`profile.jpg`** - 个人证件照（3cm 宽度）
- **`citations.bib`** - BibTeX 参考文献数据库（目前未使用，为将来出版物预留）
- **`Makefile`** - 编译脚本，用于自动化 PDF 生成
- **`README.md`** - 本文档

## 当前 CV 内容

### 个人信息
- **姓名**: Pengyuan Wang
- **身份**: Undergraduate, Zhejiang University, Robotics Engineering
- **邮箱**: wpy.wangpengyuan@gmail.com
- **电话**: (+86) 18858112270
- **网站**: https://nightcat204.github.io
- **GitHub**: @NightCat204

### CV 章节结构

1. **Summary** - 个人简介和研究兴趣
   - 浙江大学机器人工程专业本科三年级
   - 研究方向：Legged Robot, Reinforcement Learning
   
2. **Education** - 教育背景
   - 浙江大学，机器人工程学士学位（2023-2027）
   - 导师：Prof. Qiuguo Zhu
   
3. **Honors & Awards** - 荣誉奖项
   - RoboMaster 全国赛一等奖（2024 全国前四，2025 全国前八）
   - 浙江大学机器人竞赛一等奖（2024 亚军）
   - 浙江大学三等奖学金（2024, 2025）
   
4. **Research Experience** - 研究经历
   - 人形机器人强化学习控制（2025.03 - 至今）
   - 高机动无人机控制系统（2025.07 - 2025.09）
   - 自主导航系统开发（2024.07 - 2024.08）
   
5. **Projects** - 项目经历
   - RoboMaster 竞赛步兵和无人机控制系统（2023.10 - 2025.08）
   - 基于视觉的垃圾分类机器人（2024.08 - 2024.09）
   - 中控杯自主循迹机器人（2024.03 - 2024.05）
   
6. **Skills** - 技能
   - 编程语言：C/C++, Python, MATLAB
   - 机器人工具：ROS, Gazebo, RViz, IsaacGym
   - 控制理论：PID, LQR, MPC
   - 机器学习：Reinforcement Learning (PPO), PyTorch
   - 嵌入式系统：STM32, Jetson ORIN NX, Embedded Linux

## 特色设计

### 视觉设计
- ✅ **蓝色章节标题** - 专业的深蓝色 (RGB: 0, 102, 204)
- ✅ **个人照片** - 右上角 3cm 证件照
- ✅ **清晰布局** - 姓名左对齐，联系方式两行排列
- ✅ **图标增强** - Font Awesome 图标美化联系方式

### 内容组织
- ✅ **教育和荣誉前置** - 在研究经历之前展示
- ✅ **项目链接** - 链接到个人网站的详细页面
- ✅ **时间倒序** - 最新经历在前

## 编译 PDF

### 方法一：使用 Make（推荐）

确保系统已安装 `make` 和完整的 LaTeX 发行版（TeX Live 或 MiKTeX）：

```bash
cd files/cv
make          # 编译生成 cv.pdf
make clean    # 清理中间文件（.aux, .log, .out 等）
make distclean # 清理所有文件（包括 PDF）
```

### 方法二：使用 latexmk

```bash
cd files/cv
latexmk -pdf cv.tex
```

### 方法三：手动编译

```bash
pdflatex cv.tex
# 如果使用参考文献：
# biber cv
# pdflatex cv.tex
pdflatex cv.tex
```

**注意**：
- 中间文件（.aux, .log, .bcf, .out, .run.xml, .synctex.gz）会被 `.gitignore` 自动忽略
- 只需提交 `cv.tex`, `cv.pdf`, `profile.jpg`, `citations.bib` 等源文件

## 在线编辑（可选）

如果不想在本地安装 LaTeX：

### Overleaf
1. 访问 [Overleaf](https://www.overleaf.com/)
2. 创建新项目，上传所有文件（cv.tex, profile.jpg, citations.bib）
3. 在线编辑并实时预览
4. 下载编译后的 PDF

## 更新 CV 内容

### 修改个人信息

编辑 `cv.tex` 中的标题部分（约第 144-152 行）：

```latex
\begin{tabularx}{\linewidth}{@{} X r @{}}
\Huge{你的姓名} & \multirow{8}{*}{\includegraphics[width=3cm]{profile.jpg}} \\[3pt]
\normalsize{\textit{你的身份}} & \\
\normalsize{\textit{你的学校和专业}} & \\[10pt]
\href{mailto:your.email@example.com}{...} \ $|$ \ 
\href{tel:+861234567890}{...} & \\[3pt]
\href{https://yourwebsite.com}{...} \ $|$ \ 
\href{https://github.com/yourusername}{...} & \\
\end{tabularx}
```

### 修改各章节内容

**Summary**（个人简介）:
```latex
\section{Summary}
在这里写你的个人简介和研究兴趣...
```

**Education**（教育背景）:
```latex
\section{Education}
\begin{tabularx}{\linewidth}{@{}l X@{}}	
2023 - 2027 & 学位 at \textbf{大学名称} \\
& 学院名称 \\
& Advisor: 导师姓名 \\
\end{tabularx}
```

**Research Experience**（研究经历）:
```latex
\begin{joblong}{项目标题}{时间段}
\item 研究内容描述第一点
\item 研究内容描述第二点
\item 获得的技能和成果
\end{joblong}
```

**Projects**（项目经历）:
```latex
\begin{tabularx}{\linewidth}{ @{}l r@{} }
\textbf{项目名称} & \hfill \href{链接}{时间段} \\[3.75pt]
\multicolumn{2}{@{}X@{}}{项目详细描述...}  \\
\end{tabularx}
```

### 添加/修改照片

1. 将新照片命名为 `profile.jpg`（或修改 cv.tex 中的文件名）
2. 建议尺寸：证件照规格，宽度会自动调整为 3cm
3. 替换文件后重新编译

### 调整颜色

当前章节标题使用蓝色，如需修改（约第 81 行）：

```latex
% 修改为其他颜色
\definecolor{sectioncolor}{RGB}{0, 102, 204}  % 当前蓝色
% \definecolor{sectioncolor}{RGB}{0, 128, 0}  % 绿色
% \definecolor{sectioncolor}{RGB}{139, 0, 0}  % 深红色
```

### 添加出版物（未来）

当有学术出版物时，在 `citations.bib` 中添加：

```bibtex
@article{wang2025robotics,
    title = {Your Paper Title},
    author = {Wang, Pengyuan and Coauthor, Name},
    journal = {Journal Name},
    year = {2025},
    volume = {1},
    pages = {1--10}
}
```

然后取消 cv.tex 中的注释（约第 239-243 行）：

```latex
\section{Publications}
\begin{refsection}[citations.bib]
\nocite{*}
\printbibliography[heading=none]
\end{refsection}
```

## 在个人网站中使用

### 当前配置

CV PDF 可以通过以下方式访问：

1. **边栏下载链接** - 所有页面的左侧边栏底部都有 "Download CV" 链接
   - 文件位置：`_includes/author-profile.html`
   - 链接到：`/files/cv/cv.pdf`

2. **直接 URL 访问**
   - https://nightcat204.github.io/files/cv/cv.pdf

### 更新流程

每次修改 CV 后：

1. 编辑 `cv.tex` 文件
2. 编译生成新的 `cv.pdf`：`make`
3. 检查 PDF 内容是否正确
4. 提交到 Git：
   ```bash
   git add cv.tex cv.pdf
   git commit -m "Update CV"
   git push
   ```
5. 等待 GitHub Pages 部署（约 1-2 分钟）
6. 访问网站验证新 CV

## 技术细节

### LaTeX 包依赖

- `tabularx` - 灵活的表格布局
- `multirow` - 多行单元格（用于照片）
- `fontawesome5` - 图标字体
- `xcolor` - 颜色支持
- `titlesec` - 自定义章节格式
- `hyperref` - 超链接支持
- `graphicx` - 图片插入
- `biblatex` - 参考文献管理（可选）

### 文件编码

- 使用 UTF-8 编码
- 支持中英文混排（如需要可启用 XeLaTeX）

### 布局设置

- 纸张：A4
- 字体大小：12pt
- 页边距：通过 `geometry` 包设置为 0.9 倍
- 章节标题：Large 字体，蓝色，带下划线

## 常见问题

### Q: 照片和文字重叠怎么办？

A: 调整 `\multirow` 的行数（当前为 8）：
```latex
\multirow{8}{*}{\includegraphics[width=3cm]{profile.jpg}}
% 增加数字以增加照片占用的行数
```

### Q: 如何修改章节标题颜色？

A: 修改 `\definecolor{sectioncolor}` 的 RGB 值：
```latex
\definecolor{sectioncolor}{RGB}{0, 102, 204}  % 蓝色
```

### Q: 编译时出现错误？

A: 常见解决方法：
1. 确保安装了完整的 LaTeX 发行版
2. 删除所有中间文件：`make clean` 或手动删除 .aux, .log 等
3. 检查特殊字符是否正确转义（如 &, %, # 等）
4. 确保 `profile.jpg` 文件存在

### Q: 如何改变 PDF 文件名？

A: 修改 `Makefile` 中的 `NAME` 变量，或直接重命名编译后的文件。

## 版本历史

- **2025.10** - 添加蓝色章节标题，个人照片集成
- **2025.10** - 初始版本，基于 autoCV 模板定制

## 参考资源

- **模板来源**: [autoCV](https://github.com/jitinnair1/autoCV) - MIT License
- **LaTeX 文档**: [Overleaf Documentation](https://www.overleaf.com/learn)
- **Font Awesome**: [fontawesome.com](https://fontawesome.com/)

## 维护者

**Pengyuan Wang**
- Email: wpy.wangpengyuan@gmail.com
- GitHub: [@NightCat204](https://github.com/NightCat204)
- Website: [nightcat204.github.io](https://nightcat204.github.io)

---

*Last updated: October 2025*

