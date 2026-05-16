FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package.json ./
RUN npm config set registry https://registry.npmmirror.com && \
    npm install --prefer-offline --no-audit --progress=false
COPY frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
