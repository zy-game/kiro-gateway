# Kiro Gateway - 快速部署命令

## 🚀 一键部署到 139.155.78.241

### 步骤 1: 在本地打包项目

```powershell
# 在 Windows PowerShell 中执行
cd E:\kiro-gateway

# 创建压缩包（排除不必要的文件）
$exclude = @('.git', '__pycache__', '*.pyc', 'node_modules', 'accounts.db', 'debug_logs', '*.tar.gz')
tar -czf kiro-gateway.tar.gz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='accounts.db' --exclude='debug_logs' .
```

### 步骤 2: 上传到服务器

```powershell
# 上传文件
scp kiro-gateway.tar.gz root@139.155.78.241:/tmp/
```

### 步骤 3: 在服务器上部署

```bash
# SSH 连接到服务器
ssh root@139.155.78.241

# 执行以下命令
cd /opt
mkdir -p kiro-gateway
cd kiro-gateway
tar -xzf /tmp/kiro-gateway.tar.gz
rm /tmp/kiro-gateway.tar.gz

# 配置环境变量
cp .env.production .env
nano .env  # 编辑配置文件

# 启动服务
chmod +x deploy.sh
./deploy.sh
```

### 步骤 4: 验证部署

```bash
# 检查容器状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 测试健康检查
curl http://localhost:8000/health

# 在浏览器访问
# http://139.155.78.241:8000/admin
# 用户名: admin
# 密码: admin123
```

## 📝 必须修改的配置

编辑 `.env` 文件，修改以下内容：

```bash
# 1. API 密钥（用于访问网关 API）
PROXY_API_KEY="your-secure-api-key-here"

# 2. Kiro 认证信息（从你的 Kiro IDE 获取）
REFRESH_TOKEN="your_kiro_refresh_token_here"

# 3. JWT 密钥（用于 Web UI 登录，随机生成）
JWT_SECRET_KEY="$(openssl rand -base64 32)"
```

## 🔧 常用运维命令

```bash
# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 更新服务
docker-compose up -d --build

# 备份数据库
docker cp kiro-gateway:/app/accounts.db ./accounts.db.backup.$(date +%Y%m%d)

# 查看容器资源使用
docker stats kiro-gateway
```

## 🐛 故障排查

```bash
# 容器无法启动
docker-compose logs

# 检查端口占用
netstat -tlnp | grep 8000

# 检查防火墙
firewall-cmd --list-ports

# 重新构建镜像
docker-compose build --no-cache
docker-compose up -d
```

## 🔐 安全检查清单

- [ ] 修改了 PROXY_API_KEY
- [ ] 修改了 JWT_SECRET_KEY
- [ ] 修改了 admin 默认密码
- [ ] 配置了防火墙规则
- [ ] 设置了日志轮转
- [ ] 配置了定期备份

## 📊 监控检查

```bash
# 检查服务健康状态
curl http://localhost:8000/health

# 检查容器健康状态
docker inspect --format='{{.State.Health.Status}}' kiro-gateway

# 查看最近的请求日志
docker-compose exec kiro-gateway ls -lh debug_logs/
```

## 🔄 更新流程

```bash
# 1. 备份数据库
docker cp kiro-gateway:/app/accounts.db ./accounts.db.backup

# 2. 停止服务
docker-compose down

# 3. 更新代码（重新上传或 git pull）

# 4. 重新构建并启动
docker-compose up -d --build

# 5. 验证
docker-compose logs -f
curl http://localhost:8000/health
```

## 📞 快速联系

- 项目地址: https://github.com/jwadow/kiro-gateway
- 问题反馈: https://github.com/jwadow/kiro-gateway/issues
