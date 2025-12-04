import os
import functools
import logging
import logging.config
import time
import json
import yaml
import inspect
from dataclasses import dataclass, field
import hisepy.common_utils as cu
from hisepy.auth import ide_instance_guid, IDEInstance, HiseUser, instance_account_guid, debug, TEST_IDE_GUID
from typing import Any, Callable, Optional, Dict, Tuple

# Logging Configuration
# Clear prev config
LOGGING_CONFIG = None
PROC_INFO = "/proc/1/fd/1"  # path for container stdout logs
PROC_ERROR = "/proc/1/fd/2"  # path for container stderr logs


LEVEL_COLORS = {
    "INFO": "\033[32m",    # Green
    "WARNING": "\033[33m", # Yellow
    "ERROR": "\033[31m",   # Red
}

class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[41m",  # Red background (optional)
    }
    RESET = "\033[0m"

    def format(self, record):
        asctime = self.formatTime(record, self.datefmt)
        color = self.LEVEL_COLORS.get(record.levelno, "")
        
        prefix = f"{color}{asctime} {record.levelname}{self.RESET}"

        # replace only the start of the formatted string 
        msg = f"[{record.name}:{record.lineno}] {record.module} {record.process} {record.thread} {record.getMessage()}"
        return f"{prefix} {msg}"

# The default logging level is set to 'INFO'
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            '()': ColorFormatter, # color scheme according to LEVEL COLORS
            'format': '%(asctime)s %(levelname)s [%(name)s:%(lineno)s] %(module)s %(process)d %(thread)d %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
            'stream': 'ext://sys.stdout',  # Force stdout (no red background in JupyterLab)
        },
    },
    'loggers': {
        '': {
            'level': 'INFO',
            'handlers': [
                'console',
            ],
        },
    },
})

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    timestamp: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    user: str = field(default_factory=lambda: HiseUser().email
                      ) if not debug else "testuser@alleninstitute.org"
    method_name: str = ""
    ide: str = field(default_factory=ide_instance_guid)
    sdk_version: str = field(default_factory=cu.get_sdk_version)
    parameters: dict[str, any] = field(default_factory=dict)
    success: bool = True
    organization: str = field(default_factory=cu.get_organization)
    account: str = field(default_factory=instance_account_guid)
    project: str = field(default_factory=IDEInstance().get_default_project
                         ) if not debug() else TEST_IDE_GUID
    environment_name: str = field(default_factory=cu.get_environment_name)
    time_elapsed: float = None
    message: str = ""
    severity: str = "info"
    language: str = "python"

    def as_dict(self):
        return {**self.__dict__}


class ErrorHandler(logging.Handler):
    """Custom logging handler that writes ERROR logs to ide-container logs"""

    def __init__(self):
        super().__init__(level=logging.ERROR)  # consume only error logs

    # override, as emit is part of logging framework
    def emit(self, record: logging.LogRecord) -> None:
        log_entry = LogEntry(method_name=getattr(record, "method_name", None),
                             parameters=getattr(record, "parameters", None),
                             success=False,
                             message=record.getMessage(),
                             time_elapsed=getattr(record, "time_elapsed",
                                                  None),
                             severity="error")
        with open(PROC_ERROR, "a") as f:
            f.write(json.dumps(log_entry.as_dict()) + "\n")


# attach YAML error handler
if not any(isinstance(h, ErrorHandler) for h in logger.handlers):
    logger.addHandler(ErrorHandler())


def safe_serialize(obj):
    """Convert non-serializable objects (e.g. Plotly, torch, numpy) into readable placeholders."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        if hasattr(obj, "__class__"):
            return f"<non-serializable: {obj.__class__.__name__}>"
        return str(obj)


def with_logging(func: Callable[..., Any],
                 logger: logging.Logger) -> Callable[..., Any]:
    """Decorate a function with logging and write structured YAML info including success/failure."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        # safely log args
        parameters = {k: safe_serialize(v) for k, v in bound.arguments.items()}

        # add args/kwargs anytime logging is invoked
        adapter = logging.LoggerAdapter(
            logger, {
                "parameters": parameters,
                "method_name": func.__name__,
                "time_elapsed": time.time() - start_time
            })

        # allow runtime overrides 
        adapter.extra["_override"] = {} 

        # temporarily replace global logger reference in the target module
        # (so logger.error(), logger.info() inside the function use the adapter)
        original_logger = func.__globals__.get("logger", None)
        func.__globals__["logger"] = adapter

        success = True
        msg = ""
        try:
            adapter.info(f"Calling {func.__name__}")
            value = func(*args, **kwargs)
            return value
        except Exception as e:
            success = False
            msg = e

            # this will be the prefix for all metric log queries
            # send extra params so error handler can log info correctly
            adapter.error(f"Function {func.__name__} raised an exception: {e}",
                          exc_info=True)
            raise
        finally:
            # extract override fields
            override = adapter.extra.get("_override", {})



            time_elapsed = time.time() - start_time
            data = LogEntry(method_name=override.get("method_name", func.__name__),
                            parameters=parameters,
                            success=success,
                            message=str(msg),
                            time_elapsed=time_elapsed,
                            severity="info")
            with open(PROC_INFO, "a") as f:
                f.write(json.dumps(data.as_dict()) + "\n")

            # always restore the original logger
            if original_logger is not None:
                func.__globals__["logger"] = original_logger

            adapter.info(
                f"Finished {func.__name__}, success={success}, time_elapsed={time_elapsed:.3f}s"
            )

    return wrapper


with_default_logging = functools.partial(with_logging, logger=logger)
