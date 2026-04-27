#!/bin/bash

# 1. 更新系統並安裝必要工具
echo "正在更新系統套件..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 2. 加入 Docker 官方 GPG 金鑰
echo "正在加入 Docker 官方 GPG 金鑰..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 3. 設定 Docker 儲存庫 (Repository)
echo "正在設定 Docker 儲存庫..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. 安裝 Docker Engine 與 Compose 插件
echo "正在安裝 Docker 與 Docker Compose..."
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. 將目前使用者加入 docker 群組 (讓你不用一直打 sudo)
echo "正在設定權限..."
sudo usermod -aG docker $USER

echo "------------------------------------------------"
echo "✅ 安裝完成！"
echo "⚠️  請執行以下命令來讓權限生效："
echo "   newgrp docker"
echo "------------------------------------------------"
echo "測試命令: docker compose version"
