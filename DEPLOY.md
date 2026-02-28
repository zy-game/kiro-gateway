# Kiro Gateway 部署指南

## 📋 部署到 139.155.78.241

### 1️⃣ 准备工作

#### 1.1 确保服务器已安装 Docker

```bash
# SSH 连接到服务器
ssh root@139.155.78.241

# 检查 Docker 是否已安装
docker --version
docker-compose --version

# 如果未安装，执行以下命令安装
curl -fsSL https://get.docker.com | sh
```

#### 1.2 创建项目目录

```bash
# 在服务器上创建项目目录
mkdir -p /opt/kiro-gateway
cd /opt/kiro-gateway
```

### 2️⃣ 上传项目文件

#### 方式 1: 使用 SCP（推荐）

在本地 Windows 机器上执行：

```powershell
# 压缩项目文件（排除不必要的文件）
cd E:\kiro-gateway
tar -czf kiro-gateway.tar.gz `
  --exclude='.git' `
  --exclude='__pycache__' `
  --exclude='*.pyc' `
  --exclude='node_modules' `
  --exclude='accounts.db' `
  --exclude='debug_logs' `
  .

# 上传到服务器
scp kiro-gateway.tar.gz root@139.155.78.241:/opt/kiro-gateway/

# SSH 到服务器解压
ssh root@139.155.78.241
cd /opt/kiro-gateway
tar -xzf kiro-gateway.tar.gz
rm kiro-gateway.tar.gz
```

#### 方式 2: 使用 Git（如果服务器可以访问 GitHub）

```bash
# 在服务器上
cd /opt/kiro-gateway
git clone https://github.com/jwadow/kiro-gateway.git .
```

### 3️⃣ 配置环境变量

```bash
# 复制生产环境配置
cp .env.production .env

# 编辑配置文件
nano .env
```

**必须修改的配置：**

```bash
# 1. 设置 API 密钥（用于访问网关）
PROXY_API_KEY="your-secure-api-key-here"

# 2. 设置 Kiro 认证信息
REFRESH_TOKEN="your_kiro_refresh_token_here"

# 3. 设置 JWT 密钥（用于 Web UI 登录）
JWT_SECRET_KEY="your-random-secret-key-at-least-32-characters-long"
```

### 4️⃣ 部署服务

```bash
# 给部署脚本添加执行权限
chmod +x deploy.sh

# 执行部署
./deploy.sh
```

或者手动执行：

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 5️⃣ 验证部署

#### 5.1 检查容器状态

```bash
docker-compose ps
```

应该看到容器状态为 `Up`。

#### 5.2 检查健康状态

```bash
curl http://localhost:8000/health
```

应该返回：

```json
{
  "status": "healthy",
  "version": "..."
}
```

#### 5.3 访问 Web 管理界面

浏览器访问：`http://139.155.78.241:8000/admin`

默认登录：
- 用户名: `admin`
- 密码: `admin123`

**⚠️ 重要：首次登录后请立即修改密码！**

### 6️⃣ 配置防火墙（如果需要）

```bash
# 开放 8000 端口
firewall-cmd --permanent --add-port=8000/tcp
firewall-cmd --reload

# 或者使用 iptables
iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

### 7️⃣ 设置开机自启动

Docker Compose 已配置 `restart: unless-stopped`，容器会自动重启。

如果需要确保 Docker 服务开机启动：

```bash
systemctl enable docker
```

### 8️⃣ 日常运维

#### 查看日志

```bash
# 实时查看日志
docker-compose logs -f

# 查看最近 100 行日志
docker-compose logs --tail=100

# 查看特定服务日志
docker-compose logs kiro-gateway
```

#### 重启服务

```bash
docker-compose restart
```

#### 停止服务

```bash
docker-compose down
```

#### 更新服务

```bash
# 拉取最新代码
git pull

# 或者重新上传文件

# 重新构建并启动
docker-compose up -d --build
```

#### 备份数据库

```bash
# 备份 accounts.db
docker cp kiro-gateway:/app/accounts.db ./accounts.db.backup

# 或者直接复制（如果挂载了卷）
cp accounts.db accounts.db.backup
```

### 9️⃣ 故障排查

#### 容器无法启动

```bash
# 查看详细日志
docker-compose logs

# 检查配置文件
cat .env

# 检查端口占用
netstat -tlnp | grep 8000
```

#### 无法访问服务

```bash
# 检查容器是否运行
docker-compose ps

# 检查防火墙
firewall-cmd --list-ports

# 检查端口监听
netstat -tlnp | grep 8000

# 测试本地访问
curl http://localhost:8000/health
```

#### 认证失败

```bash
# 检查环境变量
docker-compose exec kiro-gateway env | grep REFRESH_TOKEN

# 重新设置环境变量后重启
docker-compose restart
```

### 🔟 性能优化

#### 调整资源限制

编辑 `docker-compose.yml`：

```yaml
deploy:
  resources:
    limits:
      cpus: '4'        # 根据服务器配置调整
      memory: 2G
    reservations:
      cpus: '1'
      memory: 512M
```

#### 启用日志轮转

```bash
# 编辑 docker-compose.yml，添加日志配置
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 1️⃣1️⃣ 安全建议

1. **修改默认密码**
   - 首次登录后立即修改 admin 密码

2. **使用强密钥**
   - `PROXY_API_KEY`: 至少 32 字符
   - `JWT_SECRET_KEY`: 至少 32 字符

3. **限制访问**
   - 如果不需要公网访问，使用防火墙限制 IP

4. **定期备份**
   - 定期备份 `accounts.db`

5. **监控日志**
   - 定期检查 `debug_logs/` 目录

### 1️⃣2️⃣ 监控和告警

#### 使用 Docker 健康检查

```bash
# 查看健康状态
docker inspect --format='{{.State.Health.Status}}' kiro-gateway
```

#### 设置监控脚本

```bash
# 创建监控脚本
cat > /opt/kiro-gateway/monitor.sh << 'EOF'
#!/bin/bash
if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "Kiro Gateway is down! Restarting..."
    cd /opt/kiro-gateway
    docker-compose restart
fi
EOF

chmod +x /opt/kiro-gateway/monitor.sh

# 添加到 crontab（每 5 分钟检查一次）
crontab -e
# 添加：
# */5 * * * * /opt/kiro-gateway/monitor.sh
```

### 1️⃣3️⃣ 常用命令速查

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 查看状态
docker-compose ps

# 进入容器
docker-compose exec kiro-gateway bash

# 更新并重启
docker-compose up -d --build

# 清理旧镜像
docker image prune -a
```

### 📞 支持

如有问题，请查看：
- GitHub Issues: https://github.com/jwadow/kiro-gateway/issues
- 项目文档: README.md

---

**部署完成后，记得测试以下功能：**

✅ Web 管理界面登录  
✅ 添加账号  
✅ 生成 API 令牌  
✅ 刷新用量  
✅ 查看请求日志  
✅ API 调用测试
