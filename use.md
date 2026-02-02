# 代码库使用文档

本文档旨在为你提供一份关于管理和更新个人主页的详细指南。该网站基于 **Jekyll** 构建，使用了一个专为学术展示优化的主题（Academic Pages）。

## 1. 快速参考：常用任务

| 任务 | 需要修改的文件/目录 |
|------|--------------------------|
| **更新个人信息** (姓名, 简介, 社交链接) | `_config.yml` |
| **更新主页内容** (介绍文字) | `_pages/about.md` |
| **添加论文/出版物** | `_publications/` (新建 `.md` 文件) 或使用 `markdown_generator/` 自动生成 |
| **添加博客文章** | `_posts/` (新建 `YYYY-MM-DD-标题.md`) |
| **更新简历 (CV)** | `_pages/cv.md` (网页文字版) & `files/` (PDF 下载版) |
| **添加演讲/报告** | `_talks/` |
| **上传图片/PDF** | `images/` 或 `files/` |

---

## 2. 全局配置 (`_config.yml`)
这是**最重要的控制文件**。它定义了全局设置。修改此文件通常需要重启本地服务器才能看到效果。

*   **站点设置**: 修改 `title` (标题), `description` (描述), `url` (网址)。
*   **作者档案 (Author Profile)**: 在 `author:` 字段下，你可以更新：
    *   `name` (姓名), `bio` (个人简介), `location` (地点), `email` (邮箱)。
    *   `social` (社交链接): 填写 GitHub, LinkedIn, Google Scholar 等平台的用户名或链接，侧边栏会自动显示对应图标。
*   **导航栏**: 虽然配置通常在 `_data/navigation.yml` 中，但也可能在 `_config.yml` 中找到相关设置。

---

## 3. 内容管理

### 主页 (`_pages/about.md`)
这个文件控制你 landing page（落地页）的内容（因为它的头部包含 `permalink: /`）。
*   **修改正文**: 使用标准 Markdown 语法撰写。
*   **Front Matter (头部元数据)**: 保持 `author_profile: true` 以显示侧边栏的头像和个人信息。

### 论文/出版物 (`_publications/`)
每一篇论文都是一个独立的 Markdown 文件。
*   **命名规范**: `YYYY-MM-DD-论文标题.md`。
*   **Front Matter (元数据)**:
    *   `title`: 论文标题。
    *   `collection`: 必须保留为 `publications`。
    *   `category`: 分类，例如 `manuscripts` (期刊论文), `conferences` (会议论文)。
    *   `venue`: 发表地点 (例如 "ICCV 2023")。
    *   `paperurl` / `slidesurl`: 链接到 PDF 文件 (建议先将 PDF 上传到 `files/` 目录)。
    *   `citation`: 该论文的引用格式 (HTML 字符串)。
*   **正文内容**: 文件的正文部分可以放置摘要或论文的详细介绍。

### 博客文章 (`_posts/`)
*   **命名规范**: `YYYY-MM-DD-你的标题.md`。
*   **Front Matter**:
    *   `title`: 文章标题。
    *   `date`: 发布日期。
    *   `tags`: 标签列表。

### 简历 / CV (`_pages/cv.md` 和 `files/`)
*   **网页版**: 编辑 `_pages/cv.md` 来更新显示在网页上的 HTML 文本版简历。
*   **下载版 PDF**: 
    1.  将新的简历 PDF 文件放入 `files/` 目录 (例如 `files/cv.pdf`)。
    2.  在 `_config.yml` 或 `_pages/about.md` 中链接它，例如 `[下载 CV](/files/cv.pdf)`。

### 演讲 / Talks (`_talks/`)
结构类似论文。
*   **Front Matter**: 包含 `type` (类型，如 Seminar, Conference), `location` (地点), 和 `venue` (场合)。

---

## 4. 进阶：自动化脚本 (`markdown_generator/`)
这个文件夹包含 Python 脚本，用于自动生成论文和演讲的 Markdown 文件，如果你有大量的发表记录，这会非常有用。

*   **`publications.py`**: 读取 `publications.tsv` (Tab 分隔值文件) 或 BibTeX 文件，并在 `_publications/` 中生成 `.md` 文件。
*   **`talks.py`**: 读取 `talks.tsv` 并在 `_talks/` 中生成文件。
*   **如何使用**:
    1.  更新源数据 (`.tsv` 表格或 `.bib` 文件)。
    2.  运行 Python 脚本 (例如 `python publications.py`)。
    3.  脚本会覆盖或创建 `../_publications` 目录下的文件。

---

## 5. 目录结构总结

*   **`_data/`**: 存放结构化数据文件 (例如导航菜单)。
*   **`_includes/`**: 可复用的 HTML 片段 (页头、页脚、侧边栏)。编辑 `archive-single.html` 可以修改列表项的显示样式。
*   **`_layouts/`**: 页面 HTML 模版 (例如 `default.html`, `single.html`)。
*   **`_sass/`**: CSS 样式源文件。在这里修改配色、字体或间距。
*   **`assets/`**: 编译后的 CSS/JS 资源。
*   **`images/`**: 存放个人头像、博客配图等。
*   **`files/`**: 存放 PDF 文件 (论文、幻灯片、CV)。

## 6. 小贴士
*   **本地测试**: 使用 `bundle exec jekyll serve` 在本地预览更改，然后再推送到 GitHub。
*   **图片引用**: 在 Markdown 中引用图片时，使用绝对路径 `![Alt Text](/images/filename.jpg)`。注意开头的斜杠。
