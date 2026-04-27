FROM node:20-slim

WORKDIR /app

# 1. 複製 package.json
COPY frontend/package.json ./

# 2. 使用快一點的鏡像站並安裝 (加上 --prefer-offline 盡量使用本地快取)
RUN npm config set registry https://registry.npmmirror.com && \
    npm install --prefer-offline --no-audit --progress=false

# 3. 複製其餘程式碼
COPY frontend/ ./

# 啟動開發伺服器
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
