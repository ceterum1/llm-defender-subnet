import bittensor as bt
from llm_defender.base.utils import validate_uid

def _check_prompt_response_mismatch(
    uid, response, prompt, penalty_name="Prompt/Response mismatch"
):
    penalty = 0.0
    if response["prompt"] != prompt:
        penalty = 20.0
    bt.logging.trace(
        f"Applied penalty score '{penalty}' from rule '{penalty_name}' for UID: '{uid}'"
    )
    return penalty


def _check_confidence_validity(uid, response, penalty_name="Confidence out-of-bounds"):
    penalty = 0.0
    if response["confidence"] > 1.0 or response["confidence"] < 0.0:
        penalty = 20.0
    bt.logging.trace(
        f"Applied penalty score '{penalty}' from rule '{penalty_name}' for UID: '{uid}'"
    )
    return penalty


def _check_confidence_history(
    uid, miner_responses, penalty_name="Suspicious confidence history"
):
    total_confidence = 0
    count = 0
    penalty = 0.0
    for entry in miner_responses:
        if (
            "response" in entry
            and isinstance(entry["response"], dict)
            and "confidence" in entry["response"]
        ):
            total_confidence += entry["response"]["confidence"]
            count += 1

    average_confidence = total_confidence / count if count > 0 else 0

    if average_confidence >= 0.45 and average_confidence <= 0.55:
        penalty += 7
    elif average_confidence < 0.45 and average_confidence >= 0.35:
        penalty += 4
    elif average_confidence < 0.35:
        penalty += 6
    elif average_confidence > 0.9:
        penalty += 4

    bt.logging.trace(
        f"Applied penalty score '{penalty}' from rule '{penalty_name}' for UID: '{uid}'. Average confidence: '{average_confidence}'"
    )

    return penalty

def check_penalty(uid, miner_responses, response, prompt):
    """This function checks the total penalty score within duplicate
    category"""
    if not validate_uid(uid) or not miner_responses or not response or not prompt:
        # Apply penalty if invalid values are provided to the function
        return 10.0

    if len(miner_responses) < 50:
        # Apply base penalty if we do not have a sufficient number of responses to process
        bt.logging.trace(f'Applied base penalty for UID: {uid} because of insufficient number of responses: {len(miner_responses)}')
        return 5

    penalty = 0.0
    penalty += _check_prompt_response_mismatch(uid, response, prompt)
    penalty += _check_confidence_validity(uid, response)
    penalty += _check_confidence_history(uid, miner_responses)

    return penalty
