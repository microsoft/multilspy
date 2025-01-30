"""
Multilspy logger module.
"""
import inspect
import json
import logging
from datetime import datetime

class LogLine():
    """
    Represents a line in the Multilspy log
    """

    def __init__(self, time: str, level: str, caller_file: str, caller_name: str, caller_line: int, message: str) -> None:
        self.time = time
        self.level = level
        self.caller_file = caller_file
        self.caller_name = caller_name
        self.caller_line = caller_line
        self.message = message

class MultilspyLogger:
    """
    Logger class
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("multilspy")
        self.logger.setLevel(logging.INFO)

    def log(self, debug_message: str, level: int, sanitized_error_message: str = "") -> None:
        """
        Log the debug and santized messages using the logger
        """

        debug_message = debug_message.replace("'", '"').replace("\n", " ")
        sanitized_error_message = sanitized_error_message.replace("'", '"').replace("\n", " ")

        # Collect details about the callee
        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        caller_file = calframe[1][1].split("/")[-1]
        caller_line = calframe[1][2]
        caller_name = calframe[1][3]

        # Construct the debug log line
        debug_log_line = LogLine(
            time=str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            level=logging.getLevelName(level),
            caller_file=caller_file,
            caller_name=caller_name,
            caller_line=caller_line,
            message=debug_message,
        )

        self.logger.log(
            level=level,
            msg=json.dumps(debug_log_line),
        )
