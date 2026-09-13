from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model, dynamic_prompt, ModelRequest
from langchain.tools.tool_node import ToolCallRequest
from typing import Callable
from utils.logger_handler import logger
from utils.prompt_loader import load_report_prompt, load_system_prompts
from langgraph.types import Command
from langgraph.runtime import Runtime
from langchain_core.messages import ToolMessage


@wrap_tool_call
def monitor_tool(
        # 请求的数据封装
        request: ToolCallRequest,
        # 执行的函数本身
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:         # 监控工具的执行
    logger.info(f"[tool monitor] 执行工具：{request.tool_call['name']}")
    logger.info(f"[tool monitor] 执行参数：{request.tool_call['args']}")
    try:
        result = handler(request)
        logger.info(f"[tool monitor] 工具{request.tool_call['name']}调用成功")
        if request.tool_call["name"] == "fill_context_for_report":
            request.runtime.context["report"] = True
        return result
    except Exception as e:
        logger.error(f"[tool monitor] 工具{request.tool_call['name']}调用失败，原因：{str(e)}")
        raise e

@before_model
def log_before_model(
        state: AgentState,      # 记录了整个agent智能体中的状态记录
        runtime: Runtime        # 记录了整个执行过程中的上下文信息
):     # 在模型执行前输出日志
    logger.info(f"[log before model] 即将调用模型，带有{len(state['messages'])}条消息")
    logger.debug(f"[log before model] {type(state['messages'][-1]).__name__} | {state['messages'][-1].content.strip()}")

@dynamic_prompt             # 每次生成提示词之前，调用此函数
def report_prompt_switch(request: ModelRequest): # 动态切换提示词
    is_report = request.runtime.context.get("report", False)
    if is_report:
        return load_report_prompt()

    return load_system_prompts()