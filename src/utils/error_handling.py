"""
错误处理和恢复机制模块

提供稳健的API调用、错误处理和恢复策略
"""
import logging
import time
import functools
from typing import Callable, Any, Optional, Tuple
from datetime import datetime, timedelta
import traceback
from enum import Enum
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import signal
import threading
from src.utils.logging_config import setup_logger

logger = setup_logger('error_handling')

class ErrorCategory(Enum):
    NETWORK_ERROR = "network_error"
    API_RATE_LIMIT = "api_rate_limit"
    DATA_INTEGRITY = "data_integrity"
    TIMEOUT_ERROR = "timeout_error"
    AUTHENTICATION_ERROR = "authentication_error"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorRecoveryAction:
    should_retry: bool
    delay_before_retry: float  # seconds
    fallback_strategy: Optional[str]  # name of fallback method
    log_level: int  # logging level for this error
    error_category: ErrorCategory


class ErrorHandler:
    """增强的错误处理器"""

    def __init__(self):
        self.error_stats = {}  # Track error statistics
        self.last_error_time = {}  # Track when errors occurred
        self.circuit_breaker_states = {}  # Circuit breaker tracking

    def categorize_error(self, error: Exception, context: str = "") -> ErrorCategory:
        """根据错误类型和上下文进行分类"""
        error_msg = str(error).lower()

        if isinstance(error, (requests.ConnectionError, requests.Timeout)):
            return ErrorCategory.NETWORK_ERROR
        elif isinstance(error, requests.exceptions.ReadTimeout):
            return ErrorCategory.TIMEOUT_ERROR
        elif "429" in error_msg or "rate limit" in error_msg or "too many requests" in error_msg:
            return ErrorCategory.API_RATE_LIMIT
        elif "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg:
            return ErrorCategory.AUTHENTICATION_ERROR
        elif "500" in error_msg or "502" in error_msg or "503" in error_msg or "504" in error_msg:
            return ErrorCategory.SERVER_ERROR
        elif "400" in error_msg:
            return ErrorCategory.CLIENT_ERROR
        else:
            return ErrorCategory.UNKNOWN_ERROR

    def get_recovery_action(self, error: Exception, attempt: int, max_retries: int, context: str = "") -> ErrorRecoveryAction:
        """根据错误情况制定恢复策略"""
        category = self.categorize_error(error, context)

        # 记录错误统计
        if context not in self.error_stats:
            self.error_stats[context] = {"total": 0, "category_counts": {}}
        self.error_stats[context]["total"] += 1
        self.error_stats[context]["category_counts"][category.value] = self.error_stats[context]["category_counts"].get(category.value, 0) + 1

        # 基于错误类型和尝试次数制定恢复策略
        if category in [ErrorCategory.NETWORK_ERROR, ErrorCategory.TIMEOUT_ERROR, ErrorCategory.SERVER_ERROR]:
            # 这些错误通常可以重试
            should_retry = attempt < max_retries
            delay = min(2 ** attempt, 30)  # 指数退避，最多30秒
            fallback = None if should_retry else "fallback_cache"

            return ErrorRecoveryAction(
                should_retry=should_retry,
                delay_before_retry=delay,
                fallback_strategy=fallback,
                log_level=logging.WARNING if attempt < max_retries else logging.ERROR,
                error_category=category
            )

        elif category == ErrorCategory.API_RATE_LIMIT:
            # API限流，需要更长的延迟
            should_retry = attempt < max_retries
            delay = 60 * (attempt + 1)  # 递增分钟级延迟
            fallback = "reduce_frequency" if should_retry else "fallback_cache"

            return ErrorRecoveryAction(
                should_retry=should_retry,
                delay_before_retry=delay,
                fallback_strategy=fallback,
                log_level=logging.WARNING,
                error_category=category
            )

        elif category == ErrorCategory.AUTHENTICATION_ERROR:
            # 认证错误，通常不应该重试
            return ErrorRecoveryAction(
                should_retry=False,
                delay_before_retry=0,
                fallback_strategy="renew_auth_token",
                log_level=logging.ERROR,
                error_category=category
            )

        elif category == ErrorCategory.DATA_INTEGRITY:
            # 数据完整性错误，可能需要从备份获取
            should_retry = False
            fallback = "use_backup_data"

            return ErrorRecoveryAction(
                should_retry=should_retry,
                delay_before_retry=0,
                fallback_strategy=fallback,
                log_level=logging.WARNING,
                error_category=category
            )

        else:
            # 其他错误
            should_retry = attempt < max_retries
            delay = 2 ** attempt

            return ErrorRecoveryAction(
                should_retry=should_retry,
                delay_before_retry=delay,
                fallback_strategy="fallback_cache" if not should_retry else None,
                log_level=logging.WARNING if attempt < max_retries else logging.ERROR,
                error_category=category
            )

    def handle_error(self, error: Exception, context: str = "", attempt: int = 0, max_retries: int = 3):
        """处理错误并执行恢复动作"""
        recovery_action = self.get_recovery_action(error, attempt, max_retries, context)

        # 记录错误
        log_method = {
            logging.DEBUG: logger.debug,
            logging.INFO: logger.info,
            logging.WARNING: logger.warning,
            logging.ERROR: logger.error,
            logging.CRITICAL: logger.critical,
        }.get(recovery_action.log_level, logger.error)

        log_method(f"[{context}] Error occurred (attempt {attempt + 1}/{max_retries}): {error}")
        log_method(f"[{context}] Error category: {recovery_action.error_category.value}")

        # 执行恢复动作
        if recovery_action.delay_before_retry > 0:
            logger.info(f"[{context}] Waiting {recovery_action.delay_before_retry}s before retry...")
            time.sleep(recovery_action.delay_before_retry)

        return recovery_action


# 全局错误处理器实例
error_handler = ErrorHandler()


def robust_api_call(max_retries: int = 3, fallback_func: Optional[Callable] = None):
    """
    装饰器：提供健壮的API调用机制
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            context = f"{func.__module__}.{func.__name__}"
            last_error = None

            for attempt in range(max_retries + 1):  # 包含首次尝试
                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        return result
                except Exception as e:
                    last_error = e
                    recovery_action = error_handler.handle_error(e, context, attempt, max_retries)

                    if not recovery_action.should_retry:
                        break

            # 如果所有重试都失败且有备用函数，则使用备用函数
            if fallback_func:
                try:
                    logger.info(f"[{context}] All retries failed, using fallback function")
                    return fallback_func(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"[{context}] Fallback function also failed: {fallback_error}")

            # 如果还是失败，抛出最后一个错误
            if last_error:
                raise last_error
            else:
                raise Exception(f"API call failed after {max_retries} retries: {context}")

        return wrapper
    return decorator


def circuit_breaker(failure_threshold: int = 5, recovery_timeout: int = 60):
    """
    熔断器装饰器：防止连续失败
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_key = f"{func.__module__}.{func.__name__}"

            # 检查是否处于熔断状态
            now = datetime.now()
            circuit_state = error_handler.circuit_breaker_states.get(func_key)

            if circuit_state:
                if now < circuit_state['recovery_time']:
                    # 熔断器开启，直接返回或抛出异常
                    logger.warning(f"Circuit breaker OPEN for {func_key}, skipping call")
                    raise Exception(f"Circuit breaker OPEN for {func_key}")
                else:
                    # 熔断器半开状态，允许一次试探
                    error_handler.circuit_breaker_states[func_key]['state'] = 'HALF_OPEN'

            try:
                result = func(*args, **kwargs)

                # 成功，重置熔断器状态
                if func_key in error_handler.circuit_breaker_states:
                    del error_handler.circuit_breaker_states[func_key]

                return result

            except Exception as e:
                # 失败，更新熔断器状态
                if func_key not in error_handler.circuit_breaker_states:
                    error_handler.circuit_breaker_states[func_key] = {
                        'failures': 0,
                        'state': 'CLOSED',
                        'recovery_time': None
                    }

                state = error_handler.circuit_breaker_states[func_key]
                state['failures'] += 1

                if state['failures'] >= failure_threshold:
                    state['state'] = 'OPEN'
                    state['recovery_time'] = now + timedelta(seconds=recovery_timeout)
                    logger.error(f"Circuit breaker TRIPPED for {func_key}")

                raise e

        return wrapper
    return decorator


def timeout_handler(timeout_seconds: int):
    """
    超时处理器装饰器
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 创建自定义异常类
            class TimeoutError(Exception):
                pass

            # 仅在支持signal的平台上使用（Unix系统）
            if hasattr(signal, 'SIGALRM'):
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Function {func.__name__} timed out after {timeout_seconds} seconds")

                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout_seconds)

                try:
                    result = func(*args, **kwargs)
                    signal.alarm(0)  # 取消闹钟
                    return result
                finally:
                    signal.signal(signal.SIGALRM, old_handler)  # 恢复原处理函数
            else:
                # Windows平台的替代实现（使用线程）
                import threading
                result_container = [None]
                exception_container = [None]

                def target():
                    try:
                        result_container[0] = func(*args, **kwargs)
                    except Exception as e:
                        exception_container[0] = e

                thread = threading.Thread(target=target)
                thread.daemon = True
                thread.start()
                thread.join(timeout=timeout_seconds)

                if thread.is_alive():
                    raise TimeoutError(f"Function {func.__name__} timed out after {timeout_seconds} seconds")

                if exception_container[0]:
                    raise exception_container[0]

                return result_container[0]

        return wrapper
    return decorator


# 数据质量验证工具
def validate_data_quality(data, required_fields=None, min_length=None, validator_func=None):
    """
    验证数据质量
    """
    if data is None:
        return False, "Data is None"

    if required_fields:
        if isinstance(data, dict):
            missing_fields = [field for field in required_fields if field not in data or data[field] is None]
            if missing_fields:
                return False, f"Missing required fields: {missing_fields}"
        elif isinstance(data, (list, tuple)):
            if len(data) == 0:
                return False, "Data is empty list/tuple"

    if min_length is not None:
        if hasattr(data, '__len__') and len(data) < min_length:
            return False, f"Data length {len(data)} is less than minimum {min_length}"

    if validator_func and callable(validator_func):
        try:
            is_valid = validator_func(data)
            if not is_valid:
                return False, "Custom validation failed"
        except Exception as e:
            return False, f"Validation function raised exception: {e}"

    return True, "Data quality validation passed"


def resilient_data_fetcher(primary_func, fallback_funcs=None, validation_rules=None):
    """
    具有弹性的数据获取器
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            context = f"{func.__module__}.{func.__name__}"

            # 首先尝试主函数
            try:
                result = primary_func(*args, **kwargs)
                is_valid, validation_msg = validate_data_quality(result, required_fields=validation_rules.get('required_fields', None) if validation_rules else None,
                                                                min_length=validation_rules.get('min_length', None) if validation_rules else None,
                                                                validator_func=validation_rules.get('validator_func', None) if validation_rules else None)
                if is_valid:
                    logger.info(f"[{context}] Primary data source succeeded")
                    return result
                else:
                    logger.warning(f"[{context}] Primary result failed validation: {validation_msg}")
            except Exception as e:
                logger.warning(f"[{context}] Primary data source failed: {e}")

            # 如果主函数失败或数据不合格，尝试备用函数
            if fallback_funcs:
                for i, fallback_func in enumerate(fallback_funcs):
                    try:
                        logger.info(f"[{context}] Trying fallback source #{i+1}")
                        result = fallback_func(*args, **kwargs)
                        is_valid, validation_msg = validate_data_quality(result, required_fields=validation_rules.get('required_fields', None) if validation_rules else None,
                                                                       min_length=validation_rules.get('min_length', None) if validation_rules else None,
                                                                       validator_func=validation_rules.get('validator_func', None) if validation_rules else None)
                        if is_valid:
                            logger.info(f"[{context}] Fallback source #{i+1} succeeded")
                            return result
                        else:
                            logger.warning(f"[{context}] Fallback #{i+1} result failed validation: {validation_msg}")
                    except Exception as e:
                        logger.warning(f"[{context}] Fallback source #{i+1} failed: {e}")
                        continue

            # 所有尝试都失败
            raise Exception(f"All data sources failed for {context}")

        return wrapper
    return decorator


# 示例使用
if __name__ == "__main__":
    # 示例：使用错误处理装饰器
    @robust_api_call(max_retries=3)
    def example_api_call():
        # 模拟一个可能失败的API调用
        import random
        if random.random() < 0.7:  # 70%的几率失败
            raise requests.ConnectionError("Simulated connection error")
        return {"result": "success", "data": [1, 2, 3]}

    try:
        result = example_api_call()
        print("Success:", result)
    except Exception as e:
        print("Failed after retries:", e)