#!/bin/bash
# MiCodeAgent 每日自动同步脚本
# 每天定时执行：有变更就提交，然后推送到 GitHub

# cron 环境 PATH 很精简，显式补全
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

# 项目目录（含中文路径，务必用绝对路径）
cd /Users/admin/workspace/学习/mewcode || exit 1

# 有未提交变更才 commit，避免「nothing to commit」报错
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "chore: 每日自动同步 $(date '+%Y-%m-%d %H:%M')"
fi

# 推送（失败只记日志，不中断）
git push origin main >> /Users/admin/workspace/学习/mewcode/.micodeagent/sync.log 2>&1
