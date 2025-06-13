import os
import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.websocket import websocket_client

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class MCPClient:
    def __init__(self, stream=False):
        # 初始化会话和客户端对象
        self.session_list: List[ClientSession] = []
        self.available_tools: List = []
        self.tool_session_map: Dict = {}
        self.exit_stack = AsyncExitStack() # 退出堆栈
        self.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL")) 
        self.model = os.getenv("MODEL_NAME", "qwen-plus")
        self.stream = stream
        self.mcp_server_config = self.parse_mcp_server("../mcp_server_config.json")
        
    def parse_mcp_server(self, config_path: str):
        with open(config_path, "r") as f:
            config = json.load(f)
        return config['mcpServers']
    
    def get_response(self, messages: list):
        response = self.openai.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=[tool for tools in self.available_tools for tool in tools],
            stream=self.stream
        )
        if self.stream:
            return self._handle_stream_response(response)
        else:
            return self._handle_nonstream_response(response)
    
    def _handle_stream_response(self, response):
        content = ''
        tool_function = {}
        for chunk in response:
            print(chunk)
            tool_calls = chunk.choices[0].delta.tool_calls
            if tool_calls:
                tool_call = tool_calls[0]
                if tool_call.id:
                    tool_function = {
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments if tool_call.function.arguments else ''
                        }
                    }
                elif tool_call.function.arguments:
                    tool_function["function"]["arguments"] += tool_call.function.arguments
            delta = chunk.choices[0].delta.content
            if delta:
                content += delta
        tool_functions = [tool_function] if tool_function else []
        return tool_functions, self._create_response(content, tool_functions)
    
    def _handle_nonstream_response(self, response):
        content = response.choices[0].message.content
        tool_functions = []
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            for tool_call in tool_calls:
                tool_functions.append({
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })
        return tool_functions, self._create_response(content, tool_functions)
            
    def _create_response(self, full_content: str, tool_functions: list):
        if not tool_functions:
            return [{
                "role": "assistant",
                "content": full_content,
            }]
        
        return [{
            "role": "assistant",
            "content": None,  # tool_calls 消息时 content 必须为 null
            "tool_calls": [{
                "id": tool_function["id"],
                "type": tool_function["type"],
                "function": tool_function["function"]
            } for tool_function in tool_functions]
        }]
    
    def get_tools(self, response):
        available_tools = [{ 
            "type":"function",
            "function":{
                "name": tool.name,
                "description": tool.description, # 工具描述
                "parameters": tool.inputSchema  # 工具输入模式
            }
        } for tool in response.tools]
        return available_tools

    async def connect_stdio_server(self, server_name: str):
        """连接到 stdio MCP 服务器"""
        server = self.mcp_server_config[server_name]
        # 创建 StdioServerParameters 对象
        server_params = StdioServerParameters(
            command=server['command'],
            args=server['args'],
            env=server.get('env', None),
        )
        # 使用 stdio_client 创建与服务器的 stdio 传输
        read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        # 创建 ClientSession 对象，用于与服务器通信
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        # 初始化会话
        await session.initialize()
        # 列出可用工具
        response = await session.list_tools()
        tools = self.get_tools(response)
        print(tools)
        return session, tools
    
    async def connect_sse_server(self, server_name: str):
        """连接到 sse MCP 服务器"""
        server = self.mcp_server_config[server_name]
        try:
            read, write, _ = await self.exit_stack.enter_async_context(streamablehttp_client(server['url']))
        except Exception as e:
            print(f"Failed to connect to streamable server {server['url']}: {e}")
            read, write = await self.exit_stack.enter_async_context(sse_client(server['url']))
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        response = await session.list_tools()
        tools = self.get_tools(response)
        # print(tools)
        return session, tools

    async def connect_websocket_server(self, server_name: str):
        """连接到 websocket MCP 服务器"""
        server = self.mcp_server_config[server_name]
        read, write = await self.exit_stack.enter_async_context(websocket_client(server['url']))
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        response = await session.list_tools()
        tools = self.get_tools(response)
        return session, tools
    
    async def connect_server(self):
        for sever_name in self.mcp_server_config:
            server = self.mcp_server_config[sever_name]
            if server.get('type') == 'websocket':
                session, tools = await self.connect_websocket_server(sever_name)
            elif server.get('url'):
                session, tools = await self.connect_sse_server(sever_name)
            else:
                session, tools = await self.connect_stdio_server(sever_name)
            self.session_list.append(session)
            self.available_tools.append(tools)
        # 构建 tool name 到 session 的映射
        self.tool_session_map = {
            tool['function']['name']: session for session, tools in zip(self.session_list, self.available_tools) for tool in tools
        }

    async def process_query(self, query):
        # 创建消息列表
        messages = [{"role": "user", "content": query}]
        while True:
            tool_functions, response = self.get_response(messages)
            messages.extend(response)
            if not tool_functions:
                break
            for tool_functions in tool_functions:
                tool_call_id = tool_functions['id']
                tool_name = tool_functions['function']['name']
                try:
                    tool_args = json.loads(tool_functions['function']['arguments'])
                except:
                    tool_args = {}
                session = self.tool_session_map[tool_name]
                result = await session.call_tool(tool_name, tool_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps({
                        "result": [content.text for content in result.content],
                        "meta": str(result.meta),
                        "isError": str(result.isError)
                    })
                })
        return messages
 
    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose() 

async def test_single_server():
    try:
        client = MCPClient()
        session, tools = await client.connect_stdio_server(server_name='calculator')
        # session, tools = await client.connect_websocket_server(server_name='amap-maps')
        print(tools)
        # res = await session.call_tool("get_current_time", {"timezone": "UTC"})
        # print(res.content)
    finally:
        await client.cleanup()

async def main():
    try:
        client = MCPClient(stream=True)
        await client.connect_server()
        # messages = await client.process_query("现在北京时间几点，天气怎么样")
        messages = await client.process_query("半径是8，计算圆的面积")
        print(messages)
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    # asyncio.run(test_single_server())
    asyncio.run(main())