import streamlit as st
from agent.react_agent import ReactAgent
from streamlit import session_state
import time

# 标题
st.title("智扫通智能客服")
st.divider()

if "agent" not in st.session_state:
    session_state["agent"] = ReactAgent()

if "message" not in st.session_state:
    st.session_state["message"] = []

# 确保每次刷新页面都能显示历史消息记录
for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

# 用户输入提示词
prompts = st.chat_input()

if prompts:
    st.chat_message("user").write(prompts)
    session_state["message"].append({"role": "user", "content": prompts})

    response_messages = []
    with st.spinner("智能客服思考中"):
        res_stream = session_state["agent"].exec_stream(prompts)

        def capture(generator, cache_list):
            for chunk in generator:
                cache_list.append(chunk)

                for char in chunk:
                    time.sleep(0.01)
                    yield char

        st.chat_message("assistant").write_stream(capture(res_stream, response_messages))
        st.session_state["message"].append({"role": "assistant", "content": response_messages[-1]})
        st.rerun()
