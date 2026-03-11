# Kiro Gateway

OpenAI 兼容的 Kiro API 网关服务，支持多账户管理和负载均衡。

## 功能特性

- 🔄 OpenAI API 兼容接口
- 👥 多账户管理和自动负载均衡
- 🔐 JWT 认证和权限管理
- 📊 Web 管理界面
- 🚀 流式响应支持
- 🧠 扩展思考模式（Extended Thinking）
- 🔧 灵活的配置选项

## 快速开始

### 方式一：Docker 部署（推荐）

#### 前置要求

- Docker 20.10+
- Docker Compose 2.0+

#### 部署步骤

1. **克隆项目**

```bash
git clone https://github.com/jwadow/kiro-gateway.git
cd kiro-gateway
```

2. **启动服务**

```bash
docker-compose -f docker-compose.production.yml up -d
```

3. **查看日志**

```bash
docker-compose -f docker-compose.production.yml logs -f
```

4. **访问服务**

- API 端点: `http://localhost:8000`
- 管理界面: `http://localhost:8000/admin`
- API 文档: `http://localhost:8000/docs`
- 健康检查: `http://localhost:8000/health`

默认管理员账户：
- 用户名: `admin`
- 密码: `admin123`

⚠️ **首次登录后请立即修改密码！**

#### 停止服务

```bash
docker-compose -f docker-compose.production.yml down
```

#### 更新服务

```bash
git pull
docker-compose -f docker-compose.production.yml up -d --build
```

---

### 方式二：本地部署

#### 前置要求

- Python 3.10+
- pip

#### 部署步骤

1. **克隆项目**

```bash
git clone https://github.com/jwadow/kiro-gateway.git
cd kiro-gateway
```

2. **创建虚拟环境（推荐）**

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

3. **安装依赖**

```bash
pip install -r requirements.txt
```

4. **启动服务**

```bash
# 使用默认配置（0.0.0.0:8000）
python main.py

# 自定义端口
python main.py --port 9000

# 仅本地访问
python main.py --host 127.0.0.1 --port 8000

# 或使用环境变量
SERVER_PORT=9000 python main.py
```

5. **访问服务**

服务启动后，访问地址同 Docker 部署方式。

#### 停止服务

按 `Ctrl+C` 停止服务。

---

## 配置说明

### 必需配置

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `PROXY_API_KEY` | 网关访问密码 | `my-secure-password` |
| 认证方式（四选一） | | |
| `KIRO_CREDS_FILE` | Kiro IDE 凭证文件路径 | `~/.aws/sso/cache/kiro-auth-token.json` |
| `REFRESH_TOKEN` | Kiro 刷新令牌 | `your_refresh_token` |
| `KIRO_CLI_DB_FILE` | kiro-cli 数据库路径 | `~/.local/share/kiro-cli/data.sqlite3` |

### 可选配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `SERVER_HOST` | 服务监听地址 | `0.0.0.0` |
| `SERVER_PORT` | 服务端口 | `8000` |
| `KIRO_REGION` | AWS 区域 | `us-east-1` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `VPN_PROXY_URL` | 代理服务器地址 | 空 |
| `FAKE_REASONING` | 启用扩展思考模式 | `true` |
| `TRUNCATION_RECOVERY` | 启用截断恢复 | `true` |

完整配置说明请参考 `.env.example` 文件。

---

## 使用示例

### OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-proxy-api-key",  # .env 中的 PROXY_API_KEY
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="claude-sonnet-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

### cURL

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-proxy-api-key" \
  -d '{
    "model": "claude-sonnet-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

## 管理界面

访问 `http://localhost:8000/admin` 进入 Web 管理界面。

功能包括：
- 账户管理（添加/删除/编辑 Kiro 账户）
- 配额监控
- 账户状态查看
- 负载均衡配置

---

## 常见问题

### 1. 端口被占用

修改 `.env` 文件中的 `SERVER_PORT`，或使用命令行参数：

```bash
python main.py --port 9000
```

### 2. 无法连接到 Kiro API

- 检查网络连接
- 如果在中国大陆，配置 `VPN_PROXY_URL`
- 验证认证凭证是否有效

### 3. Docker 容器无法访问本地文件

如果使用本地凭证文件（如 `KIRO_CREDS_FILE`），需要在 `docker-compose.production.yml` 中添加卷挂载：

```yaml
volumes:
  - ~/.aws:/home/kiro/.aws:ro
```

### 4. 查看详细日志

```bash
# Docker
docker-compose -f docker-compose.production.yml logs -f

# 本地部署
# 修改 .env 中的 LOG_LEVEL=DEBUG
```

---

## 开发

### 运行测试

```bash
pytest
```

### 代码检查

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行测试
pytest tests/
```

---

## 许可证

本项目采用 [GNU Affero General Public License v3.0](LICENSE) 许可证。

---

## 贡献

欢迎提交 Issue 和 Pull Request！

项目地址: https://github.com/jwadow/kiro-gateway

---

## 支持

- 📖 [完整文档](.env.example)
- 🐛 [问题反馈](https://github.com/jwadow/kiro-gateway/issues)
- 💬 [讨论区](https://github.com/jwadow/kiro-gateway/discussions)
