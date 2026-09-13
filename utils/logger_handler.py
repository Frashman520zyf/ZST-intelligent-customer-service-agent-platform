"""
日志配置模块

本模块基于 Python 标准库 logging 封装了一个方便获取 logger 的函数。
可以把日志想象成程序的“日记”：程序在运行过程中，把一些重要信息
（比如出错、警告、调试细节）记录下来，方便以后排查问题。

主要功能：
- 同时输出日志到控制台和文件
- 控制台默认只显示 INFO 及以上级别，文件默认记录 DEBUG 及以上级别
- 日志文件按天生成，存放在项目根目录的 logs 文件夹下
- 统一日志格式，包含时间、logger 名称、级别、文件名、行号和消息
"""

import logging
from utils.path_tool import get_abs_path
import os
from datetime import datetime

# 日志保存的根目录
# get_abs_path 是自定义工具函数，把相对路径转成绝对路径，避免路径出错
LOG_ROOT = get_abs_path("logs")

# 确保日志的目录存在
# exist_ok=True 表示如果目录已存在也不会报错
os.makedirs(LOG_ROOT, exist_ok=True)

# 日志的格式配置  error info debug
# 定义日志的输出格式。每个 %(...)s 是一个占位符：
#   %(asctime)s   ：时间，如 2025-03-21 10:30:45,123
#   %(name)s      ：logger 的名字（比如 "agent"）
#   %(levelname)s ：日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
#   %(filename)s  ：产生日志的文件名
#   %(lineno)d    ：行号
#   %(message)s   ：日志内容
# 最终格式类似：2025-03-21 10:30:45,123 - agent - INFO - main.py:20 - 信息日志
DEFAULT_LOG_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)


def get_logger(
        name: str = "agent",
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        log_file=None,
) -> logging.Logger:
    """
    获取一个配置好的 logger 对象。

    参数：
        name          : logger 的名字，不同名字的 logger 可以独立配置，默认 "agent"
        console_level : 输出到控制台的日志最低级别，默认 INFO
                        （即 INFO、WARNING、ERROR、CRITICAL 会显示，DEBUG 不显示）
        file_level    : 写入文件的日志最低级别，默认 DEBUG（所有级别都写入文件）
        log_file      : 日志文件路径，如果不传就自动生成

    返回：
        配置好的 logging.Logger 对象
    """
    logger = logging.getLogger(name)
    # 设置这个 logger 的总开关为 DEBUG，意味着所有级别的日志都会交给后面的 handler 处理。
    # 真正的过滤在 handler 上做。
    logger.setLevel(logging.DEBUG)

    # 避免重复添加 Handler
    # 如果这个 logger 已经有 handler 了，直接返回，避免重复添加导致日志重复输出。
    # 因为 getLogger 同名返回的是同一个对象。
    if logger.handlers:
        return logger

    # 控制台Handler
    # StreamHandler 把日志输出到控制台（终端）
    console_handler = logging.StreamHandler()
    # 设置控制台只显示 console_level 及以上级别的日志
    console_handler.setLevel(console_level)
    # 应用上面定义的格式
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)

    logger.addHandler(console_handler)

    # 文件Handler
    if not log_file:        # 日志文件的存放路径
        # 如果没有指定 log_file，就自动生成一个，比如 logs/agent_20250321.log，按天分文件
        log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

    # FileHandler 把日志写入文件，encoding='utf-8' 防止中文乱码
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    # 设置文件记录 file_level 及以上级别的日志
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)

    logger.addHandler(file_handler)

    return logger


# 快捷获取日志器
# 在模块级别创建一个默认名为 "agent" 的 logger，
# 方便其他文件 from this_module import logger 直接使用。
logger = get_logger()


if __name__ == '__main__':
    # 当直接运行这个文件时，会记录四条不同级别的日志。
    # 因为控制台级别是 INFO，所以控制台会显示 INFO、ERROR、WARNING，但不会显示 DEBUG。
    # 因为文件级别是 DEBUG，所以文件里会记录全部四条。
    logger.info("信息日志")
    logger.error("错误日志")
    logger.warning("警告日志")
    logger.debug("调试日志")