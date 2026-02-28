#!/bin/bash
# Kiro Gateway 部署脚本

set -e

echo "🚀 开始部署 Kiro Gateway..."

# 停止并删除旧容器
echo "📦 停止旧容器..."
docker-compose down || true

# 构建新镜像
echo "🔨 构建 Docker 镜像..."
docker-compose build

# 启动容器
echo "▶️  启动容器..."
docker-compose up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查容器状态
echo "✅ 检查容器状态..."
docker-compose ps

# 查看日志
echo "📋 最近日志："
docker-compose logs --tail=20

echo ""
echo "✨ 部署完成！"
echo "🌐 访问地址: http://139.155.78.241:8000"
echo "🔐 管理后台: http://139.155.78.241:8000/admin"
echo "📊 健康检查: http://139.155.78.241:8000/health"
echo ""
echo "查看日志: docker-compose logs -f"
echo "停止服务: docker-compose down"
