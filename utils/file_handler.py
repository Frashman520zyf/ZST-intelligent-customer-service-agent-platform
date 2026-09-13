import os
import hashlib
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from utils.logger_handler import logger

def get_file_md5_hex(file_path: str):   # 获取文件的MD5十六进制值

    if not os.path.exists(file_path):
        logger.error(f"[md5计算]文件{file_path}不存在")
        return

    if not os.path.isfile(file_path):
        logger.error(f"[md5计算]{file_path}不是文件")
        return

    md5_obj = hashlib.md5()

    chunk_size = 4096   # 4kb分片，避免文件过大爆内存
    try:
        with open(file_path, "rb") as f:    # 必须二进制读取
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)

            md5_hex = md5_obj.hexdigest()
    except Exception as e:
        logger.error(f"[md5计算]{file_path}md5值计算失败，{str(e)}")
        return None

    return md5_hex

def listdir_with_allowed_type(path: str, allowed_types: tuple[str]):    # 返回文件夹内的文件列表
    files = []

    if not os.path.isdir(path):
        logger.error(f"{path}不是文件夹")
        return allowed_types

    for f in os.listdir(path):
        if f.endswith(allowed_types):
            files.append(os.path.join(path, f))

    return tuple(files)

def pdf_loader(file_path: str, pwd=None) -> list[Document]:
     return PyPDFLoader(file_path, pwd, encoding="utf-8").load()

def txt_loader(file_path: str):
    return TextLoader(file_path, encoding="utf-8").load()