from langchain.agents import create_agent
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.agent_tools import rag_summarize,get_user_id,get_user_location,get_current_month,get_weather,generate_external_data,fetch_external_data,fill_context_for_report
from agent.middleware import monitor_tool, log_before_model, report_prompt_switch

class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[rag_summarize,get_user_id,get_user_location,get_current_month,get_weather,generate_external_data,fetch_external_data,fill_context_for_report],
            middleware=[monitor_tool, log_before_model, report_prompt_switch]
        )

    def exec_stream(self, query: str):
        input_dict = {
            "messages":[
                {"role": "user", "content": query}
            ]
        }
        # 第三个参数context就是上下文runtime中的信息，就是切换提示词的标记
        for chunk in self.agent.stream(input_dict, stream_mode="values", context={"report": False}):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"

if __name__ == '__main__':
    res = ReactAgent().exec_stream("给我生成我的使用report")
    for chunk in res:
        print(chunk, end="", flush=True)
