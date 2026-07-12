---
layout: profile-page
title: "构建"
permalink: /zh/build/
lang: zh
alternate_url: /project/
kicker: "构建 / 从模型到机器"
lead: "控制、感知、硬件和团队执行必须同时面对真实约束的系统工作。"
---

## 自主哨兵机器人控制系统

<div class="case-note"><strong>RoboMaster · 2024 年 10 月–2025 年 8 月</strong><br>自主哨兵机器人的系统架构与控制工作。</div>

<img src="/images/project_sentry.png" alt="自主哨兵机器人" width="300" style="float:right; margin:0 0 1rem 1.2rem;">

负责从电路设计、焊接等硬件基础到高层软件实现的系统架构，构建低延迟的自主主控指令执行系统。在实机上部署 PID 与 LQR 控制，建立状态空间模型，抑制粗精双云台的动态振荡并改善跟踪精度。

<div style="clear:both"></div>

## 视觉制导飞镖系统

<div class="case-note"><strong>RoboMaster · 2025 年 8 月至今</strong><br>精确制导飞镖平台的制导、导航与控制。</div>

<img src="/images/project_dart.png" alt="视觉制导飞镖系统" width="300" style="float:right; margin:0 0 1rem 1.2rem;">

参与飞镖系统的 GNC 架构，覆盖硬件集成与计算机视觉部署，建立自主目标获取的实时闭环。系统采用气动控制与比例导航，实现从静态开环弹道向末端主动制导的转换；平台正在继续整合主动涵道风扇推进与双目 VIO。

<div style="clear:both"></div>

## HW-Components 通用机器人控制库

<div class="case-note"><strong>2024 年 10 月至今 · 核心贡献者</strong><br>面向竞赛机器人的通信、调度与能量管理组件。</div>

构建高性能通信框架，借助 C++ 模板元编程实现协议 ID 的自动分配；实现多频率调度与顺序发送，并开发基于能量模型的扭矩调节算法，以适应超级电容状态与竞赛功率限制。
