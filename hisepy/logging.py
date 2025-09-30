import os
import functools
import logging
import logging.config
import time
import json
import yaml
from dataclasses import dataclass, field
import hisepy.common_utils as cu
from hisepy.upload import get_default_project
from hisepy.auth import ide_instance_guid, HiseUser, instance_account_guid
from typing import Any, Callable, Optional, Dict, Tuple

# Logging Configuration
# Clear prev config
LOGGING_CONFIG = None
PROC_INFO = "/proc/1/fd/1"  # path for container stdout logs
PROC_ERROR = "/proc/1/fd/2"  # path for container stderr logs

# The default logging level is set to 'INFO'
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format':
            '%(asctime)s %(levelname)s [%(name)s:%(lineno)s] %(module)s %(process)d %(thread)d %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
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
    user: str = field(default_factory=lambda: HiseUser().email)
    method_name: str = ""
    ide: str = field(default_factory=ide_instance_guid)
    py_sdk_version: str = field(default_factory=cu.get_sdk_version)
    parameters: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    organization: str = field(default_factory=cu.get_organization)
    account: str = field(default_factory=instance_account_guid)
    project: str = field(default_factory=get_default_project)
    environment_name: str = field(default_factory=cu.get_environment_name)
    time_elapsed: float = None
    message: str = ""
    severity: str = "info"

    def as_dict(self):
        return {
            **self.__dict__,
            "parameters": self.parameters or {
                "args": None,
                "kwargs": None
            },
        }


class ErrorHandler(logging.Handler):
    """Custom logging handler that writes ERROR logs to YAML file."""

    def __init__(self):
        super().__init__(level=logging.ERROR)  # consume only error logs

    # override, as emit is part of logging framework
    def emit(self, record: logging.LogRecord) -> None:
        log_entry = LogEntry(method_name=record.funcName,
                             parameters={
                                 "args": getattr(record, "args", None),
                                 "kwargs": getattr(record, "kwargs", None)
                             },
                             success=False,
                             message=record.getMessage(),
                             time_elapsed=getattr(record, "time_elapsed",
                                                  None),
                             severity="error")
        with open(PROC_ERROR, "a") as f:
            f.write(json.dumps(log_entry.as_dict()) + "\n")
            #yaml.safe_dump([log_entry.as_dict()], f, sort_keys=False)


# attach YAML error handler
if not any(isinstance(h, ErrorHandler) for h in logger.handlers):
    logger.addHandler(ErrorHandler())


def with_logging(func: Callable[..., Any],
                 logger: logging.Logger) -> Callable[..., Any]:
    """Decorate a function with logging and write structured YAML info including success/failure."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        logger.info(f"Calling {func.__name__}")

        # add args/kwargs anytime logging is invoked
        adapter = logging.LoggerAdapter(logger, {
            "args": args,
            "kwargs": kwargs
        })
        success = True
        msg = ""
        try:
            value = func(*args, **kwargs)
            return value
        except Exception as e:
            success = False
            msg = e
            adapter.error(f"Function {func.__name__} raised an exception: {e}")
            raise
        finally:
            time_elapsed = time.time() - start_time
            # --- write structured info to YAML ---
            data = LogEntry(method_name=func.__name__,
                            parameters={
                                "args": args,
                                "kwargs": kwargs
                            },
                            success=success,
                            message=msg,
                            time_elapsed=time_elapsed,
                            severity="info")
            with open(PROC_INFO, "a") as f:
                f.write(json.dumps(data.as_dict()) + "\n")
                #yaml.safe_dump([data.as_dict()], f, sort_keys=False)

            logger.info(
                f"Finished {func.__name__}, success={success}, time_elapsed={time_elapsed:.3f}s"
            )

    return wrapper


with_default_logging = functools.partial(with_logging, logger=logger)
