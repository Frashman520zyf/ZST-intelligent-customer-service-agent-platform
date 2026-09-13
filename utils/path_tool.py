"""
为整个工程提供统一的绝对路径
"""
import os.path


def get_project_root() -> str:
    """
    获取工程所在的根目录
    :return: 字符串根目录
    """
    # 当前文件的绝对路径
    current_file = os.path.abspath(__file__)
    # 先获取当前文件所在文件夹目录绝对路径
    current_dir = os.path.dirname(current_file)
    # 获取工程根目录
    root_dir = os.path.dirname(current_dir)

    return root_dir

def get_abs_path(relative_path: str) -> str:
    """
    传入相对路径，返回绝对路径
    :param relative_path:
    :return:
    """
    project_root = get_project_root()
    return os.path.join(project_root, relative_path)


if __name__ == '__main__':
    print(get_abs_path("prompts/main_prompt.txt"))