# File: MARK_I/backend_python/api/webhook_executor.py

import asyncio
import httpx
import logging
import time
import uuid
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from api.db_client import supabase_service_client

logger = logging.getLogger(__name__)

class WebhookExecutor:
    """Handles webhook execution with proper error handling and logging"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
    
    async def execute_webhook(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        call_context: Dict[str, Any],
        execution_id: str,
        is_test: bool = False
    ) -> Dict[str, Any]:
        """Execute a webhook and return the result"""
        
        start_time = time.time()
        
        # Ensure execution_id is a valid UUID
        try:
            # Try to parse as UUID, if it fails generate a new one
            uuid.UUID(execution_id)
        except ValueError:
            logger.warning(f"Invalid execution_id '{execution_id}', generating new UUID")
            execution_id = str(uuid.uuid4())
        
        execution_result = {
            "id": execution_id,
            "webhook_id": tool["id"],
            "execution_status": "pending",
            "execution_time_ms": None,
            "http_status_code": None,
            "webhook_response": {},
            "error_message": None,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None
        }
        
        try:
            # Prepare webhook payload
            webhook_payload = {
                "webhook_id": tool["id"],
                "execution_id": execution_id,
                "agent_id": call_context.get("agent_id"),
                "call_id": call_context.get("call_id"),
                "call_context": call_context,
                "parameters": parameters,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "is_test": is_test
            }
            
            # Process JSON body if provided
            if tool.get("json_body"):
                try:
                    # Replace variables in JSON body
                    processed_body = self._replace_variables_in_json(
                        tool["json_body"], 
                        {**call_context, **parameters}
                    )
                    webhook_payload = json.loads(processed_body) if processed_body else webhook_payload
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to process JSON body for tool {tool['id']}: {e}")
                    # Fall back to default payload
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "PAM-Webhook-Agent/1.0",
                **tool.get("webhook_headers", {})
            }
            
            # Make the request
            timeout = tool.get("webhook_timeout_ms", 5000) / 1000.0
            
            response = await self.client.request(
                method=tool["webhook_method"],
                url=tool["webhook_url"],
                json=webhook_payload,
                headers=headers,
                timeout=timeout
            )
            
            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Parse response
            try:
                response_data = response.json() if response.content else {}
            except Exception:
                response_data = {"raw_response": response.text}
            
            # Update execution result
            execution_result.update({
                "execution_status": "success" if response.is_success else "failed",
                "execution_time_ms": execution_time_ms,
                "http_status_code": response.status_code,
                "webhook_response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_data
                },
                "completed_at": datetime.now(timezone.utc)
            })
            
            if not response.is_success:
                execution_result["error_message"] = f"HTTP {response.status_code}: {response.text[:500]}"
            
        except httpx.TimeoutException:
            execution_result.update({
                "execution_status": "timeout",
                "execution_time_ms": int((time.time() - start_time) * 1000),
                "error_message": f"Webhook request timed out after {timeout}s",
                "completed_at": datetime.now(timezone.utc)
            })
            
        except Exception as e:
            execution_result.update({
                "execution_status": "failed",
                "execution_time_ms": int((time.time() - start_time) * 1000),
                "error_message": f"Webhook execution failed: {str(e)}",
                "completed_at": datetime.now(timezone.utc)
            })
            
        finally:
            # Log the execution to database
            await self._log_execution(execution_result, tool, parameters, call_context)
            
        return execution_result
    
    def _replace_variables_in_json(self, json_body: str, variables: Dict[str, Any]) -> str:
        """Replace variables in JSON body template"""
        if not json_body:
            return json_body
            
        # Replace variables with pattern {{variable_name}}
        def replace_var(match):
            var_name = match.group(1)
            return str(variables.get(var_name, match.group(0)))
        
        # Use regex to find and replace variables
        pattern = r'\{\{\s*([^}]+)\s*\}\}'
        processed_json = re.sub(pattern, replace_var, json_body)
        
        return processed_json
    
    def _serialize_for_json(self, obj: Any) -> Any:
        """Recursively serialize objects for JSON storage"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {key: self._serialize_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_for_json(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return self._serialize_for_json(obj.__dict__)
        else:
            return obj
    
    async def _log_execution(
        self,
        execution_result: Dict[str, Any],
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        call_context: Dict[str, Any]
    ):
        """Log execution details to the database"""
        try:
            # Serialize all datetime objects and complex objects
            log_data = {
                "id": execution_result["id"],
                "webhook_id": execution_result["webhook_id"],
                # Make agent_id and call_id completely optional - no foreign key constraints
                "agent_id": call_context.get("agent_id") if call_context.get("agent_id") is not None else None,
                "call_id": call_context.get("call_id") if call_context.get("call_id") is not None else None,
                "execution_context": self._serialize_for_json(call_context),
                "input_parameters": self._serialize_for_json(parameters),
                "webhook_request": self._serialize_for_json({
                    "url": tool["webhook_url"],
                    "method": tool["webhook_method"],
                    "headers": tool.get("webhook_headers", {}),
                    "json_body": tool.get("json_body"),
                    "payload": parameters
                }),
                "webhook_response": self._serialize_for_json(execution_result["webhook_response"]),
                "execution_status": execution_result["execution_status"],
                "execution_time_ms": execution_result["execution_time_ms"],
                "http_status_code": execution_result["http_status_code"],
                "error_message": execution_result["error_message"],
                "created_at": execution_result["created_at"].isoformat() if execution_result["created_at"] else None,
                "completed_at": execution_result["completed_at"].isoformat() if execution_result["completed_at"] else None
            }
            
            result = supabase_service_client.table("webhook_executions").insert(log_data).execute()
            logger.info(f"Successfully logged webhook execution {execution_result['id']}")
            
            # Note: Usage count is automatically incremented by database trigger
            # No need for manual RPC call
                
        except Exception as e:
            logger.error(f"Failed to log webhook execution: {e}")
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Global webhook executor instance
_webhook_executor = None

async def get_webhook_executor() -> WebhookExecutor:
    """Get or create webhook executor instance"""
    global _webhook_executor
    if _webhook_executor is None:
        _webhook_executor = WebhookExecutor()
    return _webhook_executor

async def execute_webhook_with_logging(
    execution_id: str,
    tool: Dict[str, Any],
    parameters: Dict[str, Any],
    call_context: Optional[Dict[str, Any]] = None,
    is_test: bool = False
) -> Dict[str, Any]:
    """Execute webhook with proper logging and error handling"""
    executor = None
    try:
        # Default empty context if none provided
        if call_context is None:
            call_context = {}
        
        logger.info(f"Starting webhook execution for tool {tool.get('id', 'unknown')} with execution_id {execution_id}")
        
        # Create a new executor instance for each execution to avoid shared state issues
        executor = WebhookExecutor()
        result = await executor.execute_webhook(tool, parameters, call_context, execution_id, is_test)
        logger.info(f"Webhook execution completed successfully for execution_id {execution_id}")
        return result
        
    except Exception as e:
        logger.error(f"Webhook execution failed for execution_id {execution_id}: {e}", exc_info=True)
        # Create a basic failure result to ensure logging still works
        failure_result = {
            "id": execution_id,
            "tool_id": tool.get("id", "unknown"),
            "execution_status": "failed",
            "execution_time_ms": 0,
            "http_status_code": None,
            "webhook_response": {},
            "error_message": f"Execution failed: {str(e)}",
            "created_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc)
        }
        # Still try to log the failure
        if executor:
            try:
                await executor._log_execution(failure_result, tool, parameters, call_context or {})
            except Exception as log_error:
                logger.error(f"Failed to log execution failure: {log_error}")
        return failure_result
        
    finally:
        # Always close the HTTP client to prevent resource leaks
        if executor:
            try:
                await executor.close()
                logger.debug(f"HTTP client closed for execution_id {execution_id}")
            except Exception as close_error:
                logger.warning(f"Error closing HTTP client for execution_id {execution_id}: {close_error}")
        
        # Force garbage collection to ensure cleanup
        import gc
        gc.collect() 