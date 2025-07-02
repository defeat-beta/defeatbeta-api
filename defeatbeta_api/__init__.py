import pyfiglet

from defeatbeta_api.__version__ import __version__
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient

_welcome_printed = False
data_update_time = ""

def _print_welcome():
    global _welcome_printed
    global data_update_time
    if not _welcome_printed:
        client = HuggingFaceClient()
        data_update_time = client.get_data_update_time()
        text = "Defeat Beta"
        ascii_lines = pyfiglet.figlet_format(text, font="doom").split('\n')
        ascii_art = '\n'.join(line for line in ascii_lines if line.strip())
        colored_art = "\033[38;5;10m" + ascii_art + "\033[0m"
        print(f"{colored_art}\n"
              f"\033[1;38;5;10m📈:: Data Update Time ::\033[0m\t{data_update_time} \033[1;38;5;10m::\033[0m\n"
              f"\033[1;38;5;10m📈:: Software Version ::\033[0m\t{__version__}      \033[1;38;5;10m::\033[0m")
        _welcome_printed = True

_print_welcome()