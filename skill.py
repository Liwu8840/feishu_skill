# coding: utf-8
"""
飞书 AI 文件夹文档管理技能

支持能力：
1. list_folder_docs: 列出 AI 文件夹下的所有文档
2. create_doc: 在 AI 文件夹下创建新文档
3. write_doc: 向指定文档写入文本（默认追加）
4. get_doc_content: 查看文档文本内容
5. get_doc_outline: 查看文档目录（标题结构）
6. self_test: 自检（鉴权、列文档、可选写入测试）

鉴权模式：
- 个人版优先：传 access_token（或 FEISHU_ACCESS_TOKEN）
- 企业版兼容：传 app_id + app_secret（或 FEISHU_APP_ID/FEISHU_APP_SECRET）
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://open.feishu.cn/open-apis"
HEADING_TYPE_MAP = {
    3: 1,
    4: 2,
    5: 3,
    6: 4,
    7: 5,
    8: 6,
}
DOC_TYPES = {"doc", "docx", "wiki"}


def _json_result(ok: bool, action: str, data: Optional[Dict[str, Any]] = None, error: str = "") -> str:
    return json.dumps(
        {
            "ok": ok,
            "action": action,
            "data": data or {},
            "error": error,
        },
        ensure_ascii=False,
    )


def _request_json(
    method: str,
    path: str,
    token: str = "",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = BASE_URL + path
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if query:
            url = f"{url}?{query}"

    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        raise RuntimeError(f"HTTP {e.code}: {raw or str(e)}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _extract_elements_text(elements: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for el in elements or []:
        text_run = el.get("text_run") or {}
        content = text_run.get("content")
        if content:
            parts.append(str(content))
    return "".join(parts).strip()


def _block_text(block: Dict[str, Any]) -> str:
    # 常见富文本块字段：paragraph / heading1..heading6
    for key in [
        "paragraph",
        "heading1",
        "heading2",
        "heading3",
        "heading4",
        "heading5",
        "heading6",
    ]:
        node = block.get(key) or {}
        elements = node.get("elements") or []
        text = _extract_elements_text(elements)
        if text:
            return text
    return ""


def _get_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = _request_json(
        method="POST",
        path="/auth/v3/tenant_access_token/internal",
        body={"app_id": app_id, "app_secret": app_secret},
    )
    if resp.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {resp.get('msg', 'unknown error')}")
    token = resp.get("tenant_access_token")
    if not token:
        raise RuntimeError("获取 tenant_access_token 失败: 返回中无 tenant_access_token")
    return token


def _list_folder_docs(token: str, folder_token: str, page_size: int = 100, max_items: int = 500) -> Dict[str, Any]:
    if not folder_token:
        raise RuntimeError("缺少 ai_folder_token/folder_token")

    size = max(1, min(int(page_size or 100), 200))
    limit = max(1, int(max_items or 500))

    items: List[Dict[str, Any]] = []
    page_token = ""

    while True:
        resp = _request_json(
            method="GET",
            path="/drive/v1/files",
            token=token,
            params={
                "folder_token": folder_token,
                "page_size": size,
                "page_token": page_token or None,
                "order_by": "EditedTime",
                "direction": "DESC",
            },
        )
        if resp.get("code") != 0:
            raise RuntimeError(f"查询文件失败: {resp.get('msg', 'unknown error')}")

        data = resp.get("data") or {}
        files = data.get("files") or []
        for f in files:
            file_type = (f.get("type") or "").lower()
            if file_type not in DOC_TYPES:
                continue
            items.append(
                {
                    "name": f.get("name"),
                    "type": f.get("type"),
                    "token": f.get("token"),
                    "url": f.get("url"),
                    "owner_id": (f.get("owner_id") or {}).get("id"),
                    "modified_time": f.get("modified_time"),
                }
            )
            if len(items) >= limit:
                break

        has_more = bool(data.get("has_more"))
        page_token = data.get("next_page_token") or ""
        if len(items) >= limit or not has_more or not page_token:
            break

    return {
        "folder_token": folder_token,
        "count": len(items),
        "items": items,
    }


def _create_doc(token: str, title: str, folder_token: str) -> Dict[str, Any]:
    if not title:
        raise RuntimeError("create_doc 缺少必填参数 title")
    if not folder_token:
        raise RuntimeError("create_doc 需要 ai_folder_token/folder_token")

    resp = _request_json(
        method="POST",
        path="/docx/v1/documents",
        token=token,
        body={"title": title, "folder_token": folder_token},
    )
    if resp.get("code") != 0:
        raise RuntimeError(f"创建文档失败: {resp.get('msg', 'unknown error')}")

    doc = (resp.get("data") or {}).get("document") or {}
    return {
        "document_id": doc.get("document_id"),
        "title": doc.get("title"),
        "url": doc.get("url"),
        "revision_id": doc.get("revision_id"),
        "folder_token": folder_token,
    }


def _write_doc(token: str, document_id: str, content: str, index: int = -1) -> Dict[str, Any]:
    if not document_id:
        raise RuntimeError("write_doc 缺少必填参数 document_id")
    if not content:
        raise RuntimeError("write_doc 缺少必填参数 content")

    resp = _request_json(
        method="POST",
        path=f"/docx/v1/documents/{document_id}/blocks/{document_id}/children",
        token=token,
        body={
            "index": int(index) if index is not None else -1,
            "children": [
                {
                    "block_type": 2,
                    "paragraph": {
                        "elements": [{"text_run": {"content": content}}],
                    },
                }
            ],
        },
    )
    if resp.get("code") != 0:
        raise RuntimeError(f"写入文档失败: {resp.get('msg', 'unknown error')}")

    children = ((resp.get("data") or {}).get("children") or [])
    return {
        "document_id": document_id,
        "written_content_length": len(content),
        "new_blocks": children,
    }


def _get_block_children(token: str, document_id: str, block_id: str) -> List[Dict[str, Any]]:
    page_token = ""
    children: List[Dict[str, Any]] = []

    while True:
        resp = _request_json(
            method="GET",
            path=f"/docx/v1/documents/{document_id}/blocks/{block_id}/children",
            token=token,
            params={
                "page_size": 200,
                "page_token": page_token or None,
            },
        )
        if resp.get("code") != 0:
            raise RuntimeError(f"读取文档块失败: {resp.get('msg', 'unknown error')}")

        data = resp.get("data") or {}
        part = data.get("items") or data.get("children") or []
        children.extend(part)

        has_more = bool(data.get("has_more"))
        page_token = data.get("page_token") or data.get("next_page_token") or ""
        if not has_more or not page_token:
            break

    return children


def _collect_document_blocks(token: str, document_id: str, max_blocks: int = 2000) -> List[Dict[str, Any]]:
    # 从 root block（document_id）开始做 DFS，收集全部块
    stack = [document_id]
    blocks: List[Dict[str, Any]] = []
    visited = set()

    while stack and len(blocks) < max_blocks:
        parent_id = stack.pop()
        for block in _get_block_children(token, document_id, parent_id):
            bid = block.get("block_id")
            if not bid or bid in visited:
                continue
            visited.add(bid)
            blocks.append(block)
            stack.append(bid)
            if len(blocks) >= max_blocks:
                break

    return blocks


def _get_doc_content(token: str, document_id: str, max_blocks: int = 2000, max_chars: int = 20000) -> Dict[str, Any]:
    if not document_id:
        raise RuntimeError("get_doc_content 缺少必填参数 document_id")

    blocks = _collect_document_blocks(token, document_id, max_blocks=max_blocks)
    lines: List[str] = []
    total_chars = 0

    for block in blocks:
        text = _block_text(block)
        if not text:
            continue
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        piece = text[:remaining]
        lines.append(piece)
        total_chars += len(piece)

    return {
        "document_id": document_id,
        "block_count": len(blocks),
        "text_length": total_chars,
        "content": "\n".join(lines),
        "truncated": total_chars >= max_chars,
    }


def _get_doc_outline(token: str, document_id: str, max_blocks: int = 2000) -> Dict[str, Any]:
    if not document_id:
        raise RuntimeError("get_doc_outline 缺少必填参数 document_id")

    blocks = _collect_document_blocks(token, document_id, max_blocks=max_blocks)
    outline: List[Dict[str, Any]] = []

    for block in blocks:
        block_type = int(block.get("block_type") or 0)
        level = HEADING_TYPE_MAP.get(block_type)
        if not level:
            continue
        outline.append(
            {
                "level": level,
                "text": _block_text(block),
                "block_id": block.get("block_id"),
            }
        )

    return {
        "document_id": document_id,
        "heading_count": len(outline),
        "outline": outline,
    }


def _self_test(token: str, folder_token: str, run_write_test: bool) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    docs = _list_folder_docs(token=token, folder_token=folder_token, page_size=20, max_items=20)
    checks.append({"step": "list_folder_docs", "ok": True, "doc_count": docs.get("count", 0)})

    if not run_write_test:
        return {
            "mode": "read_only",
            "folder_token": folder_token,
            "checks": checks,
            "message": "基础连通性测试通过（鉴权+列文档）。",
        }

    title = f"codex_test_{int(time.time())}"
    created = _create_doc(token=token, title=title, folder_token=folder_token)
    checks.append({"step": "create_doc", "ok": True, "document_id": created.get("document_id")})

    doc_id = created.get("document_id") or ""
    sample = f"self_test_write_{int(time.time())}"
    _write_doc(token=token, document_id=doc_id, content=sample, index=-1)
    checks.append({"step": "write_doc", "ok": True, "written": sample})

    content = _get_doc_content(token=token, document_id=doc_id, max_blocks=300, max_chars=4000)
    found = sample in (content.get("content") or "")
    checks.append({"step": "get_doc_content", "ok": found})

    outline = _get_doc_outline(token=token, document_id=doc_id, max_blocks=300)
    checks.append({"step": "get_doc_outline", "ok": True, "heading_count": outline.get("heading_count", 0)})

    return {
        "mode": "write",
        "folder_token": folder_token,
        "created_document_id": doc_id,
        "checks": checks,
        "message": "写入链路测试完成。",
    }


def run(**kwargs) -> str:
    action = (kwargs.get("action") or kwargs.get("操作") or "").strip()
    access_token = (kwargs.get("access_token") or os.getenv("FEISHU_ACCESS_TOKEN") or "").strip()
    app_id = (kwargs.get("app_id") or os.getenv("FEISHU_APP_ID") or "").strip()
    app_secret = (kwargs.get("app_secret") or os.getenv("FEISHU_APP_SECRET") or "").strip()

    folder_token = (
        kwargs.get("ai_folder_token")
        or kwargs.get("folder_token")
        or os.getenv("FEISHU_AI_FOLDER_TOKEN")
        or ""
    ).strip()

    page_size = kwargs.get("page_size") or 100
    max_items = kwargs.get("max_items") or 500
    title = (kwargs.get("title") or "").strip()
    document_id = (kwargs.get("document_id") or "").strip()
    content = kwargs.get("content") or ""
    index = kwargs.get("index") if kwargs.get("index") is not None else -1
    max_blocks = kwargs.get("max_blocks") or 2000
    max_chars = kwargs.get("max_chars") or 20000
    run_write_test = _to_bool(kwargs.get("run_write_test"), default=False)

    allowed_actions = {
        "list_folder_docs",
        "create_doc",
        "write_doc",
        "get_doc_content",
        "get_doc_outline",
        "self_test",
    }

    if not action:
        return _json_result(False, "unknown", error="缺少必填参数 action")
    if action not in allowed_actions:
        return _json_result(False, action, error=f"action 不支持，请使用: {', '.join(sorted(allowed_actions))}")

    try:
        if access_token:
            token = access_token
        else:
            if not app_id or not app_secret:
                return _json_result(
                    False,
                    action,
                    error=(
                        "缺少鉴权信息。请提供 access_token（个人版推荐）"
                        "或 app_id/app_secret（企业版），也可使用环境变量。"
                    ),
                )
            token = _get_tenant_access_token(app_id, app_secret)

        if action == "list_folder_docs":
            data = _list_folder_docs(token=token, folder_token=folder_token, page_size=int(page_size), max_items=int(max_items))
            return _json_result(True, action, data=data)

        if action == "create_doc":
            data = _create_doc(token=token, title=title, folder_token=folder_token)
            return _json_result(True, action, data=data)

        if action == "write_doc":
            data = _write_doc(token=token, document_id=document_id, content=str(content), index=int(index))
            return _json_result(True, action, data=data)

        if action == "get_doc_content":
            data = _get_doc_content(token=token, document_id=document_id, max_blocks=int(max_blocks), max_chars=int(max_chars))
            return _json_result(True, action, data=data)

        if action == "get_doc_outline":
            data = _get_doc_outline(token=token, document_id=document_id, max_blocks=int(max_blocks))
            return _json_result(True, action, data=data)

        if not folder_token:
            raise RuntimeError("self_test 需要 ai_folder_token/folder_token 或 FEISHU_AI_FOLDER_TOKEN")
        data = _self_test(token=token, folder_token=folder_token, run_write_test=run_write_test)
        return _json_result(True, action, data=data)

    except Exception as e:
        logger.error("feishu_ai_docs_manager 执行失败: %s", e, exc_info=True)
        return _json_result(False, action, error=str(e))


if __name__ == "__main__":
    print(run(action="self_test", run_write_test=False))
