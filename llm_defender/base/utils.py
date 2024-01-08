"""
This module implements common classes that are used by one or more core
features and their engines.
"""
import gc
import multiprocessing


class EnginePrompt:
    """
    This class implements a consistent way of representing different
    prompts to be analyzed by the subnet.
    """

    def __init__(self, engine: str, prompt: str, data: dict):
        self.prompt = prompt
        self.engine = engine
        self.data = data

    def get_dict(self) -> dict:
        """
        This function returns dict representation of the class
        """
        return {"engine": self.engine, "prompt": self.prompt, "data": self.data}


class EngineResponse:
    """
    This class implements a consistent way of representing different
    responses produced by the miners.
    """

    def __init__(self, confidence: float, data: dict, name: str):
        self.confidence = confidence
        self.data = data
        self.name = name

    def get_dict(self) -> dict:
        """
        This function returns dict representation of the class
        """
        return {"name": self.name, "confidence": self.confidence, "data": self.data}


def normalize_list(input_list: list) -> list:
    """
    This function normalizes a list so that values are between [0,1] and
    they sum up to 1.
    """
    if len(input_list) > 1:
        min_val = min(input_list)

        if min_val >= 0:
            # If all values are non-negative, simply divide by sum
            sum_vals = sum(input_list)
            normalized_list = [val / sum_vals for val in input_list]
        else:
            # If there are negative values, normalize between abs(min) and max
            abs_min = abs(min_val)
            adjusted_values = [(val + abs_min) for val in input_list]
            sum_adjusted = sum(adjusted_values)
            normalized_list = [val / sum_adjusted for val in adjusted_values]
    else:
        normalized_list = [1.0]

    return normalized_list


def cleanup(variables: list = None):
    """This is a generic cleanup function"""
    if variables:
        for variable in variables:
            variable = None
            del variable

    gc.collect()


def _run_function(result_dict, func, args, kwargs):
    """Helper function for the timeout() function"""
    result = func(*args, **kwargs)
    result_dict["result"] = result


def timeout_decorator(timeout):
    """Uses multiprocessing to create an arbitrary timeout for a
    function call. This function is used for ensuring a stuck function
    call does not block the execution of the neuron script"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            manager = multiprocessing.Manager()
            result = manager.dict()

            process = multiprocessing.Process(
                target=_run_function, args=(result, func, args, kwargs)
            )
            process.start()
            process.join(timeout=timeout)

            if process.is_alive():
                process.terminate()
                process.join()
                raise TimeoutError(
                    f"Function '{func.__name__}' execution timed out after {timeout} seconds."
                )
            return result["result"]

        return wrapper

    return decorator

def validate_miner_blacklist(miner_blacklist) -> bool:
    """The local blacklist must be a JSON array:
    [
        {"hotkey": "5FZV8fBTpEo51pxxPd5AqdpwN3BzK8rxog6VYFiGd6H7pPKY", "reason": "Exploitation"},
        {"hotkey": "5FMjfXzFuW6wLYVGTrvE5Zd66T1dvgv3qKKhWeTFWXoQm3jS", "reason": "Exploitation"}
    ]
    """
    if miner_blacklist:
        return bool(
            isinstance(miner_blacklist, list)
            and all(
                isinstance(item, dict)
                and all(key in item for key in ["hotkey", "reason"])
                for item in miner_blacklist
            )
        )
    return False

def validate_uid(uid):
    """
    This method makes sure that a uid is an int instance 
    between 0 and 256. It also makes sure that boolean 
    inputs are filtered out as non-valid uid's.

    Arguments:
        uid:
            A unique user id that we are checking to make 
            sure is valid. (integer between 0 and 256).

    Returns:
        True:
            uid is valid--it is an integer between 0 and 256, 
            True and False excluded.
        False:
            uid is NOT valid.
    """
    # uid must be an integer instance between 0 and 256
    if not isinstance(uid, int) or isinstance(uid, bool):
        return False
    if uid < 0 or uid > 256:
        return False
    return True