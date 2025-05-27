const { OpenAI } = require('openai');
const path = require('path');
const fs = require('fs');
const { Client } = require("@modelcontextprotocol/sdk/client/index.js");
const { StdioClientTransport } = require("@modelcontextprotocol/sdk/client/stdio.js");
const { StreamableHTTPClientTransport } = require("@modelcontextprotocol/sdk/client/streamableHttp.js");
const { SSEClientTransport } = require("@modelcontextprotocol/sdk/client/sse.js");

require('dotenv').config({ path: path.join(__dirname, '../.env') });

class MCPClient {
  constructor(stream = false) {
    this.clients = [];
    this.availableTools = [];
    this.toolClientMap = {};
    this.openai = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
      baseURL: process.env.OPENAI_BASE_URL
    });
    this.model = process.env.MODEL_NAME;
    this.stream = stream;
    this.config = this.parseConfig(
      path.join(__dirname, '../mcp_server_config.json')
    );
  }
  
  parseConfig(configPath) {
    const raw = fs.readFileSync(configPath);
    return JSON.parse(raw).mcpServers;
  }
  
  async handleStreamResponse(response) {
    let content = '';
    let toolFunction = {};
    try {
      for await (const chunk of response) {
        const toolCalls = chunk.choices[0]?.delta?.tool_calls;
        if (toolCalls) {
          const toolCall = toolCalls[0];
          if (toolCall.id) {
            toolFunction = {
              id: toolCall.id,
              type: toolCall.type,
              function: {
                name: toolCall.function?.name || '',
                arguments: toolCall.function?.arguments || ''
              }
            };
          } else if (toolCall.function?.arguments) {
            toolFunction.function.arguments += toolCall.function.arguments;
          }
        }
        const delta = chunk.choices[0]?.delta?.content;
        if (delta) {
          content += delta;
        }
      }
      const toolFunctions = toolFunction.id ? [toolFunction] : [];
      return {
        tool_functions: toolFunctions,
        response: this.createResponse(content, toolFunctions)
      };
    } catch (error) {
      console.error('Stream processing error:', error);
      throw error;
    }
  }
  
  handleNonStreamResponse(response) {
    // console.log(response);
    const content = response.choices[0]?.message?.content || '';
    const toolFunctions = [];
    
    const toolCalls = response.choices[0]?.message?.tool_calls;
    if (toolCalls) {
      for (const toolCall of toolCalls) {
        toolFunctions.push({
          id: toolCall.id,
          type: toolCall.type,
          function: {
            name: toolCall.function.name,
            arguments: toolCall.function.arguments
          }
        });
      }
    }
    return {
      tool_functions: toolFunctions,
      response: this.createResponse(content, toolFunctions)
    };
  }
  
  createResponse(content, toolFunctions) {
    return [{
      role: 'assistant',
      content: content,
      tool_calls: toolFunctions
    }];
  }

  async getResponse(messages) {
    const response = await this.openai.chat.completions.create({
      model: this.model,
      messages: messages,
      tools: this.availableTools.flat(),
      stream: this.stream
    });
    
    if (this.stream) {
      return this.handleStreamResponse(response);
    } else {
      return this.handleNonStreamResponse(response);
    }

  }
  
  async connectServer() {
    for (const [serverName, server] of Object.entries(this.config)) {
      const client = new Client({name: serverName, version: "0.1.0"});
      if (server.url) {
        // SSE连接
        const baseUrl = new URL(server.url);
        try {
          const transport = new StreamableHTTPClientTransport(baseUrl);
          await client.connect(transport);
        } catch (e) {
          console.error("Failed to connect to streamable server");
          const transport = new SSEClientTransport(baseUrl);
          await client.connect(transport);
        }
      } else {
        // Stdio连接
        const transport = new StdioClientTransport({
          command: server.command,
          args: server.args,
          env: server.env
        });
        await client.connect(transport);
      }
      const response = await client.listTools();
      const tools = response.tools.map(tool => ({
        type: "function",
        function: {
          name: tool.name,
          description: tool.description,
          parameters: tool.inputSchema
        }
      }));
      this.clients.push(client);
      this.availableTools.push(tools);
    }
    // 构建tool到client的映射
    this.clients.forEach((client, idx) => {
      this.availableTools[idx].forEach(tool => {
        this.toolClientMap[tool.function.name] = client;
      });
    });
    console.log("Connected to all servers");
  }

  async processQuery(query) {
    // 创建消息列表
    const messages = [{role: "user", content: query}];
    while (true) {
      const {tool_functions, response} = await this.getResponse(messages);
      messages.push(...response);
      if (!tool_functions || tool_functions.length === 0) {
        break;
      }
      for (const tool_call of tool_functions) {
        const tool_call_id = tool_call.id;
        const tool_name = tool_call.function.name;
        let tool_args = {};
        
        try {
          tool_args = JSON.parse(tool_call.function.arguments);
        } catch (e) {
          console.error("Failed to parse tool arguments:", e);
        }
        console.log("Tool call:", tool_name, "Tool args:", tool_args);
        const client = this.toolClientMap[tool_name];
        const result = await client.callTool({name: tool_name, arguments: tool_args});
        
        messages.push({
          role: "tool",
          tool_call_id,
          content: JSON.stringify({
            result: result.content.map(c => c.text),
            meta: String(result.meta),
            isError: String(result.isError)
          })
        });
      }
    }
    return messages;
  }
  
}

async function test() {
  const client = new MCPClient(false);
  try {
    await client.connectServer();
    const res = await client.processQuery("现在北京时间几点");
    console.log(res);
  } catch (e) {
    console.error(e);
  }
}

if (require.main === module) {
  test();
}