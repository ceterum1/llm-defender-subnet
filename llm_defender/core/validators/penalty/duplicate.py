import bittensor as bt
from llm_defender.base.utils import validate_uid


def _calculate_duplicate_percentage(
    uid, miner_responses, engine, penalty_name="Duplicate percentage"
):
    penalty = 0.0
    # Isolate engine-specific data
    engine_data = [
        entry
        for item in miner_responses
        for entry in item.get("engine_data", [])
        if entry.get("name") == engine
    ]
    if not engine_data:
        return penalty

    # Calculate duplicate percentage
    engine_data_str = [str(entry) for entry in engine_data]
    duplicates = {entry: engine_data_str.count(entry) for entry in engine_data_str}
    if not duplicates:
        return penalty
    duplicate_percentage = (len(engine_data) - len(duplicates)) / len(engine_data)

    if not duplicate_percentage:
        return penalty

    if engine == "engine:yara":
        if duplicate_percentage > 0.95:
            penalty += 0.25
    elif engine == "engine:vector_search":
        if duplicate_percentage > 0.15:
            penalty += 0.5
    elif engine == "engine:text_classification":
        if duplicate_percentage > 0.5:
            if duplicate_percentage > 0.95:
                penalty += 1.0
            elif duplicate_percentage > 0.9:
                penalty += 0.66
            elif duplicate_percentage > 0.8:
                penalty += 0.33
            else:
                penalty += 0.15
    bt.logging.trace(
        f"Applied penalty score '{penalty}' from rule '{penalty_name}' for UID: '{uid}'. Duplicate % for {engine}: {duplicate_percentage}"
    )

    return penalty


def _find_identical_reply(
    uid, miner_responses, response, engine, penalty_name="Identical replies"
):
    """Applies penalty if identical replies are found"""
    penalty = 0.0
    engine_response = [data for data in response["engines"] if data["name"] == engine]
    if not engine_response:
        return penalty
    if len(engine_response) > 0:
        if any(
            engine_response == entry
            for item in miner_responses
            for entry in item.get("engine_data", [])
        ):
            penalty += 0.25

        bt.logging.trace(
            f"Applied penalty score '{penalty}' from rule '{penalty_name}' for UID: '{uid}'"
        )
    return penalty


def check_penalty(uid, miner_responses, response):
    """This function checks the total penalty score within duplicate category"""
    if not validate_uid(uid) or not miner_responses or not response:
        # Apply penalty if invalid values are provided to the function
        return 20.0

    penalty = 0.0
    for engine in ["engine:text_classification", "engine:yara", "engine:vector_search"]:
        penalty += _find_identical_reply(uid, miner_responses, response, engine)
        penalty += _calculate_duplicate_percentage(uid, miner_responses, engine)

    return penalty
