from utils.config_handler import prompt_config
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

def load_system_prompts():
    try:
        system_prompt_path = get_abs_path(prompt_config["main_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_system_prompts]在yaml配置项中没有main_prompt_path")
        raise e

    try:
        return open(system_prompt_path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_system_prompts]解析系统提示词出错，{str(e)}")
        raise e

def load_rag_summarize():
    try:
        system_prompt_path = get_abs_path(prompt_config["rag_summarize_path"])
    except KeyError as e:
        logger.error(f"[load_rag_summarize]在yaml配置项中没有rag_summarize_path")
        raise e

    try:
        return open(system_prompt_path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_rag_summarize]解析系统提示词出错，{str(e)}")
        raise e

def load_report_prompt():
    try:
        system_prompt_path = get_abs_path(prompt_config["report_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_report_prompt]在yaml配置项中没有report_prompt_path")
        raise e

    try:
        return open(system_prompt_path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_report_prompt]解析系统提示词出错，{str(e)}")
        raise e

if __name__ == '__main__':
    print(load_report_prompt())
