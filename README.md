# <div align="center">🚀 MCP Client For OpenAI-Compatible APIs</div>

<div align="center">

将 MCP 协议接入 OpenAI 兼容的 API，提供 Python 和 Node.js 实现的客户端。

</div>

## 📖 文档

[搞不懂 MCP？那就动手搓一个...]()

## 🔧 快速开始

```bash
# 克隆仓库
git clone https://github.com/hougeai/mcp-client.git
cd mcp-client

# 配置环境变量 
cp .env.template .env

# 配置 MCP 服务器
cp template.mcp_server_config.json mcp_server_config.json
```
### Python 客户端

```bash
# 配置虚拟环境
pip install uv # 安装 uv 命令行工具
uv venv # 创建虚拟环境
source .venv/bin/activate # 激活虚拟环境
uv sync # 安装依赖
# 启动
python mcpclient.py
```
### Node.js 客户端

```bash
# 安装依赖
pnpm install
# 启动
node mcpclient.js
```
## 🔌 MCP 服务器配置

以下资源提供了丰富的MCP工具和服务器:

- [ModelScope](https://modelscope.cn/mcp) - 聚合优质MCP资源，提供免费MCP服务
- [mcp.so](https://mcp.so/zh) - 收集了优秀的 MCP 服务器 和客户端

### 配置示例

```json
{
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/root/projects/"
            ]
        },
        "calculator": {
            "command": "python",
            "args": [
                "tools/calculator.py"
            ]
        },
        "time": {
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                "mcp/time"
            ]
        },
        "amap-maps": {
            "url": "https://mcp.api-inference.modelscope.cn/sse/xxx"
        }
    }
}
```

## 📝 许可证

[MIT License](https://opensource.org/licenses/MIT)