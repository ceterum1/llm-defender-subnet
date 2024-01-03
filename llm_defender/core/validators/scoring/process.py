"""This module processes the incoming response from the miner"""
from bittensor import logging
from torch import Tensor
from copy import deepcopy


def validate_response(response: dict) -> bool:
    """This method validates the individual response to ensure it has
    been format correctly

    Arguments:
        response:
            Response received from the miner

    Returns:
        outcome
            An instance of bool depicting the outcome of the validation.
    """
    # Responses without output are not valid
    if not response or isinstance(response, bool):
        logging.trace(f"Received an response without an output: {response}")
        return False

    # Check for type
    if not isinstance(response, dict):
        logging.trace(f"Received an response with incorrect type: {response}")
        return False

    # Check for mandatory keys
    mandatory_keys = [
        "confidence",
        "prompt",
        "engines",
        "synapse_uuid",
        "subnet_version",
    ]
    if not all(key in response for key in mandatory_keys):
        logging.trace(
            f"One or more mandatory keys: {mandatory_keys} missing from response: {response}"
        )
        return False

    # Check that the values are not empty
    for key in mandatory_keys:
        if response[key] is None:
            logging.trace(
                f"One or more mandatory keys: {mandatory_keys} are empty in: {response}"
            )
            return False

    # Check the validity of the confidence score
    if isinstance(response["confidence"], bool) or not isinstance(
        response["confidence"], (float, int)
    ):
        logging.trace(f"Confidence is not correct type: {response}")
        return False

    if not 0.0 <= float(response["confidence"]) <= 1.0:
        logging.trace(f"Confidence is out-of-bounds for response: {response}")
        return False

    # The response has passed the validation
    logging.trace(f"Validation succeeded for response: {response}")
    return True


def assign_score_for_uid(scores: Tensor, uid: int, alpha: float, response_score: float):
    """Assigns a score to an UID

    Arguments:
        scores
            Current Tensor of scores
        uid
            UID of the neuron to set the score for
        alpha
            Scaling factor used for the degradation

    Returns:
        scores
            An updated Tensor of the scores
    """

    # Ensure the alpha is correctly defined
    if alpha >= 1.0 or not isinstance(alpha, float) or isinstance(alpha, bool):
        logging.error(f"Value for alpha is incorrect: {alpha}")
        raise AttributeError(f"Alpha must be below 1.0. Value: {alpha}")

    # Ensure the response score is correctly defined
    if (
        (0.0 > response_score > 1.0)
        or not isinstance(response_score, float)
        or isinstance(response_score, bool)
    ):
        logging.error(f"Value for response_score is incorrect: {response_score}")
        raise AttributeError(
            f"response_score must be in range (0.0, 1.0). Value: {response_score}"
        )

    # Ensure UID is correctly defined
    if (0 > uid > 256) or not isinstance(uid, int):
        logging.error(f"Value for UID is incorrect: {uid}")
        raise AttributeError(f"UID must be in range (0, 256). Value: {uid}")

    # If current score is already at 0.0 we do not need to do anything
    if response_score == 0.0 and scores[uid] == 0.0:
        return scores

    old_score = deepcopy(scores[uid])
    logging.trace(f"Assigning score of 0.0 for UID: {uid}. Current score: {old_score}")
    scores[uid] = alpha * scores[uid] + (1 - alpha) * response_score
    logging.trace(f"Assigned score of 0.0 for UID: {uid}. New score: {scores[uid]}")

    if old_score == scores[uid]:
        logging.error(
            f"Score for UID: {uid} did not change. Old score: {old_score}, new score: {scores[uid]}"
        )
        raise ValueError(
            f"Score for UID: {uid} did not change. Old score: {old_score}, new score: {scores[uid]}"
        )

    return scores, old_score


def get_response_object(
    uid: str, hotkey: str, target: float, prompt: str, synapse_uuid: str
) -> dict:
    """Returns the template for the response object"""

    response = {
        "UID": uid,
        "hotkey": hotkey,
        "target": target,
        "original_prompt": prompt,
        "synapse_uuid": synapse_uuid,
        "response": {},
        "engine_scores": {
            "distance_score": 0.0,
            "speed_score": 0.0,
            "engine_score": 0.0,
            "distance_penalty_multiplier": 0.0,
            "general_penalty_multiplier": 0.0,
            "response_score": 0.0,
        },
        "weight_scores": {
            "new": 0.0,
            "old": 0.0,
            "change": 0.0,
        },
        "engine_data": [],
    }

    return response
