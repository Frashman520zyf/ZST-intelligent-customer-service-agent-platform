from langchain_core.documents import Document

from rag.vector_store import VectorStoreSevice
from utils.prompt_loader import load_rag_summarize
from langchain_core.prompts import PromptTemplate
from model.factory import chat_model
from langchain_core.output_parsers import StrOutputParser
"""
    总结服务类：用户提问，将用户提问与参考资料交给模型，让模型总结回复
"""

def print_prompt(prompt):
    print("=" * 40)
    print(prompt.to_string())
    print("=" * 40)
    return prompt

class RagSummarizeSevice(object):
    def __init__(self):
        self.vector_store = VectorStoreSevice()
        self.retriever = self.vector_store.get_retriever()
        self.prompt_template = load_rag_summarize()
        self.prompt_text = PromptTemplate.from_template(self.prompt_template)
        self.model = chat_model
        self.chain = self._init_chain()

    def _init_chain(self):
        return self.prompt_text | print_prompt | self.model | StrOutputParser()

    def retrieve_docs(self, query: str) -> list[Document]:
        return self.retriever.invoke(query)

    def rag_summarize(self, query: str) -> str:
        # 拿到检索的文本
        contents = self.retrieve_docs(query)

        # 拼接文本
        context = ""
        count = 0
        for content in contents:
            count += 1
            context += f"【参考资料{count}】：【内容】：{content.page_content} | 【参考元数据】：{content.metadata} "

        return self.chain.invoke(
            {
                "input": {query},
                "context": context
            }
        )

if __name__ == '__main__':
    res = RagSummarizeSevice().rag_summarize("扫地机器人有什么功能？")
    print(res)
