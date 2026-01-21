# LinYing Bai's Academic Website

**Personal academic portfolio website built with Jekyll and GitHub Pages.**

🌐 **Live Site:** [https://vamperd.github.io/](https://vamperd.github.io/)

## About This Site

This is the personal academic website of LinYing Bai, a third-year undergraduate student at Zhejiang University majoring in Automation. The site showcases research experience, projects, awards, and provides a downloadable CV.

## Site Structure

### Active Pages

- **About** (`/`) - Personal introduction, education background, and research interests
- **Research** (`/research/`) - Research experience including:
  - Humanoid Robot Control with Reinforcement Learning
  - High-Maneuverability Drone Control System
  - Autonomous Navigation System Development
- **Project** (`/project/`) - Engineering projects including:
  - RoboMaster Competition robots
  - Vision-Based Waste Sorting Robot
  - Autonomous Line-Following Robot
- **Award** (`/award/`) - Competition awards and scholarships

### Features

- **LaTeX CV**: Full academic CV with LaTeX source in `files/cv/`
- **PDF Download**: CV available for download from sidebar
- **Responsive Design**: Mobile-friendly layout
- **Clean Navigation**: Focused on essential academic content

## CV Management

### LaTeX Source

The CV is maintained as a LaTeX document in `files/cv/`:

```
files/cv/
├── cv.tex              # Main LaTeX source file
├── cv.pdf              # Compiled PDF (update after editing)
├── citations.bib       # Bibliography (for publications)
├── profile.jpg         # Profile photo
├── Makefile            # Compilation script
└── README.md           # CV-specific documentation
```

### Compiling the CV

```bash
cd files/cv
make                    # Compile PDF
make clean              # Remove intermediate files
make distclean          # Remove all generated files
```

Or manually:
```bash
latexmk -pdf cv.tex
```

### CV Features

- Professional blue section headers
- Integrated profile photo
- Contact information with icons
- Sections: Summary, Education, Honors & Awards, Research Experience, Projects, Skills

## Getting Started

### Prerequisites

- Ruby (>= 2.7)
- Bundler
- Node.js (for JavaScript dependencies)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/NightCat204/NightCat204.github.io.git
   cd NightCat204.github.io
   ```

2. **Install dependencies**
   ```bash
   bundle install
   ```

3. **Run local server**
   ```bash
   bundle exec jekyll serve -l -H localhost
   ```

4. **View site**
   
   Open browser to `http://localhost:4000`

### Updating Content

#### Edit Personal Information

Edit `_config.yml`:
```yaml
author:
  name: "Your Name"
  email: "your.email@example.com"
  github: "yourusername"
  employer: "Your University"
```

#### Update Pages

- **About**: Edit `_pages/about.md`
- **Research**: Edit `_pages/research.md`
- **Projects**: Edit `_pages/project.md`
- **Awards**: Edit `_pages/award.md`

#### Update CV

1. Edit `files/cv/cv.tex`
2. Compile: `cd files/cv && make`
3. Commit updated `cv.pdf`

#### Add Images

Place images in `images/` directory and reference them:
```markdown
![Description](/images/your-image.jpg)
```

## Site Configuration

### Navigation Menu

Edit `_data/navigation.yml` to customize the navigation bar:

```yaml
main:
  - title: "About"
    url: /
  - title: "Research"
    url: /research/
  # Add or remove items as needed
```

### Sidebar

The sidebar includes:
- Profile photo (`images/profile.jpg`)
- Name and affiliation
- Email and GitHub links
- **CV Download link** (automatically added)

Customize in `_includes/author-profile.html`

## Content Not Currently Used

The following template features are disabled but available:

- **Publications** (`_publications/`) - For academic papers
- **Talks** (`_talks/`) - For presentations and seminars  
- **Teaching** (`_teaching/`) - For teaching experience
- **Portfolio** (`_portfolio/`) - For additional projects
- **Blog** (`_posts/`) - For blog posts
- **CV Page** (`_pages/cv.md`) - Web version of CV (PDF preferred)

To enable any of these, uncomment the relevant lines in `_data/navigation.yml`

## Technical Details

### Built With

- **Jekyll** - Static site generator
- **Minimal Mistakes Theme** - Base theme (customized)
- **GitHub Pages** - Hosting
- **Font Awesome** - Icons
- **LaTeX** - CV typesetting

### File Structure

```
├── _config.yml           # Site configuration
├── _data/
│   └── navigation.yml    # Navigation menu
├── _includes/
│   └── author-profile.html  # Sidebar customization
├── _pages/               # Main content pages
│   ├── about.md
│   ├── research.md
│   ├── project.md
│   └── award.md
├── files/
│   └── cv/              # LaTeX CV files
├── images/              # Site images
│   ├── profile.jpg      # Profile photo
│   ├── research_*.jpg   # Research images
│   └── project_*.jpg    # Project images
└── README.md            # This file
```

## Deployment

The site automatically deploys to GitHub Pages when you push to the `master` branch:

1. Make your changes locally
2. Test with `bundle exec jekyll serve`
3. Commit and push:
   ```bash
   git add .
   git commit -m "Update content"
   git push origin master
   ```
4. GitHub Actions will build and deploy (usually within 1-2 minutes)
5. Check status at: Settings → Pages

## Maintenance Notes

### Updating CV

After editing the LaTeX CV:
1. Compile new PDF: `cd files/cv && make`
2. Verify the PDF looks correct
3. Commit both `cv.tex` and `cv.pdf`
4. Push to GitHub

### Adding New Research/Projects

1. Add images to `images/` directory
2. Edit the corresponding markdown file in `_pages/`
3. Follow the existing format for consistency
4. Test locally before pushing

## License

This repository is based on the Academic Pages template, which is © 2016 Michael Rose and released under the MIT License.

Personal content © 2024-2025 Pengyuan Wang

## Contact

- **Email**: 3230104810@zju.edu.cn
- **GitHub**: [@Vamper](https://github.com/Vamperd)
- **Website**: [https://vamperd.github.io](https://vamperd.github.io)

---

*Last updated: October 2025*

## Advanced Usage

### Using Docker

For cross-platform development without installing Ruby:

```bash
chmod -R 777 .
docker compose up
```

Access the site at `http://localhost:4000`

### Using VS Code DevContainer

If using Visual Studio Code:

1. Open the repository in VS Code
2. Press F1 → "DevContainer: Reopen in Container"
3. Site automatically available at `http://localhost:4000`

---

## Credits

This site is based on the [Academic Pages](https://github.com/academicpages/academicpages.github.io) template.
Thanks for Pengyuan Wang's page template [Pengyuan Wang's page](https://github.com/NightCat204/NightCat204.github.io)
