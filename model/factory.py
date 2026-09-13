from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.language_models import BaseChatModel

from utils.config_handler import rag_config
from langchain_core.embeddings import Embeddings
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi


class BaseModelFactory(ABC):
    @abstractmethod
    def generater(self) -> Optional[Embeddings | BaseChatModel]:
        pass

class ChatModelFactory(BaseModelFactory):
    def generater(self) -> Optional[Embeddings | BaseChatModel]:
        return ChatTongyi(model=rag_config["chat_model"])

class EmbeddingsModelFactory(BaseModelFactory):
    def generater(self) -> Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=rag_config["embedding_model"])

chat_model = ChatModelFactory().generater()
embed_model = EmbeddingsModelFactory().generater()