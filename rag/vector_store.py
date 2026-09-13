import os.path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.config_handler import chroma_config
from langchain_text_splitters import RecursiveCharacterTextSplitter
from model.factory import chat_model, embed_model
from utils.file_handler import get_file_md5_hex
from utils.path_tool import get_abs_path
from utils.file_handler import listdir_with_allowed_type
from utils.file_handler import pdf_loader, txt_loader
from utils.logger_handler import logger

class VectorStoreSevice(object):
    def __init__(self):
        # 定义向量数据库成员
        self.vector_store = Chroma(
            collection_name=chroma_config["collection_name"],   # 向量数据库名称
            embedding_function=embed_model,                            # 嵌入模型
            persist_directory=chroma_config["persist_directory"],# 向量数据库路径
        )
        # 定义文本分割器成员
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_config["chunk_size"],     #每块最大字符数
            chunk_overlap=chroma_config["chunk_overlap"],#每段之间允许重叠最大字符数
            separators=chroma_config["separators"],     #分割文本的依据符号
            length_function=len                         #统计字符个数的函数，默认使用python自带的len
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_config["k"]})

    def load_document(self):
        """
        从数据文件中读取数据，转为向量存入向量库
        要对文件的md5去重
        :return: None
        """

        def check_md5_hex(md5_for_check: str):
            if not os.path.exists(get_abs_path(chroma_config["md5_hex_store"])):
                # 创建文件
                open(get_abs_path(chroma_config["md5_hex_store"]), "w", encoding="utf-8").close()
                return False

            with open(get_abs_path(chroma_config["md5_hex_store"]), "r", encoding="utf-8") as f:
                for line in f.readlines():
                    line = line.strip()     # 去除前后的空格和回车
                    if line == md5_for_check:
                        return True

            return False    # 表示没被处理过

        def save_md5_hex(md5_for_check: str):
            with open(get_abs_path(chroma_config["md5_hex_store"]), "a", encoding="utf-8") as f:
                f.write(md5_for_check + "\n")

        def get_file_documents(read_file: str):
            if read_file.endswith(".txt"):
                return txt_loader(read_file)

            if read_file.endswith(".pdf"):
                return pdf_loader(read_file)

        allow_file_path = listdir_with_allowed_type(
            get_abs_path(chroma_config["data_path"]),
            tuple(chroma_config["allow_knowledge_file_type"])
        )

        for path in allow_file_path:
            # 获取文件的md5值
            md5_hex = get_file_md5_hex(path)
            if check_md5_hex(md5_hex):
                logger.info(f"[加载知识库]{path}内容已经存在于知识库，跳过")
                continue

            try:
                # 加载知识库分片
                documents: list[Document] = get_file_documents(path)

                if not documents:
                    logger.warning(f"[加载知识库]{path}内没有有效文本内容，跳过")
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[加载知识库]{path}分片后没有有效文本内容，跳过")
                    continue

                # 存入向量库
                self.vector_store.add_documents(split_document)

                # 记录这个文件的md5值，避免重复加载
                save_md5_hex(md5_hex)

                logger.info(f"[加载知识库]{path} 内容已成功加载")
            except Exception as e:
                # exc_info为True为记录详细的报错堆栈，如果为false仅记录错误信息
                logger.error(f"[加载知识库]{path}加载失败, {str(e)}", exc_info=True)
                continue

if __name__ == '__main__':
    vs = VectorStoreSevice()
    vs.load_document()
    retriever = vs.get_retriever()
    res = retriever.invoke("清洁")
    for r in res:
        print(r.page_content)
        print("+" * 20)
