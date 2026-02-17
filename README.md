# feishu_ai_docs_manager

## 简介

用于操作 **AI 文件夹** 下的飞书文档，支持：

- 列出 AI 文件夹下所有文档
- 在 AI 文件夹下创建文档
- 向文档写入内容
- 查看文档内容
- 查看文档目录（标题结构）
- 自检测试是否连通成功

## 文件说明

- `manifest.json`: 技能声明
- `schema.json`: 输入输出参数定义
- `skill.py`: 执行逻辑
- `tool.json`: Tool Calling 描述

## 使用前准备

1. 在飞书开放平台创建应用并开通文档相关权限。
2. 获取 `app_id`、`app_secret`。
3. 获取 AI 文件夹 `folder_token`。
4. 建议配置环境变量：

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
export FEISHU_AI_FOLDER_TOKEN="fldcnxxxx"
```

## Action 列表

- `list_folder_docs`: 列 AI 文件夹下文档
- `create_doc`: 在 AI 文件夹创建文档
- `write_doc`: 写入文档
- `get_doc_content`: 查看文档内容
- `get_doc_outline`: 查看文档目录
- `self_test`: 自检（可选写入测试）

## 调用示例

### 1) 列出 AI 文件夹文档

```json
{
  "action": "list_folder_docs",
  "ai_folder_token": "fldcnxxxx",
  "page_size": 100,
  "max_items": 500
}
```

### 2) 在 AI 文件夹创建文档

```json
{
  "action": "create_doc",
  "ai_folder_token": "fldcnxxxx",
  "title": "测试-需求文档"
}
```

### 3) 写入文档

```json
{
  "action": "write_doc",
  "document_id": "doxcnxxxx",
  "content": "这是自动写入内容",
  "index": -1
}
```

### 4) 查看文档内容

```json
{
  "action": "get_doc_content",
  "document_id": "doxcnxxxx"
}
```

### 5) 查看文档目录

```json
{
  "action": "get_doc_outline",
  "document_id": "doxcnxxxx"
}
```

### 6) 自检（只读）

```json
{
  "action": "self_test",
  "ai_folder_token": "fldcnxxxx",
  "run_write_test": false
}
```

### 7) 自检（创建+写入链路）

```json
{
  "action": "self_test",
  "ai_folder_token": "fldcnxxxx",
  "run_write_test": true
}
```

## 返回格式

统一返回 JSON 字符串：

- `ok`: 是否成功
- `action`: 执行动作
- `data`: 成功数据
- `error`: 失败信息
