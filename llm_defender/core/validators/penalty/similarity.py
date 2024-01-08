import bittensor as bt
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np
from llm_defender.base.utils import validate_uid


def _check_response_history(
    uid, miner_responses, engine, penalty_name="High-similarity score"
):
    """Checks the response history to determine the similarity of engine responses"""
    # Isolate engine-specific data
    penalty = 0.0
    engine_data = [
        entry
        for item in miner_responses
        for entry in item.get("engine_data", [])
        if entry.get("name") == engine
    ]
    if not engine_data:
        return penalty

    # Calculate duplicsate percentage
    engine_data_str = [str(entry["data"]) for entry in engine_data]

    # Create a CountVectorizer to convert text to word count vectors
    vectorizer = CountVectorizer()

    # Fit and transform the documents into vectors
    vectorized_docs = vectorizer.fit_transform(engine_data_str)

    # Calculate pairwise cosine similarity for all combinations of documents
    cosine_sim_matrix = cosine_similarity(vectorized_docs)

    # Exclude self-similarity values (diagonal) and compute average
    mask = np.triu(np.ones(cosine_sim_matrix.shape), k=1).astype(bool)
    similarities = cosine_sim_matrix[mask]

    if len(similarities) == 0:
        return penalty

    average_similarity = similarities.mean()
    bt.logging.trace(f"Average similarity: {average_similarity}")

    if average_similarity > 0.9:
        penalty += 1.0
    elif average_similarity > 0.8:
        penalty += 0.66
    elif average_similarity > 0.7:
        penalty += 0.33
    elif average_similarity > 0.6:
        penalty += 0.10

    bt.logging.trace(
        f"Applied penalty score '{penalty}' from rule '{penalty_name}' for UID: '{uid}' for engine: '{engine}'. Average similarity: '{average_similarity}'"
    )
    return penalty


def check_penalty(uid, miner_responses):
    """This function checks the total penalty score within similarity
    category"""
    penalty = 0.0

    if not validate_uid(uid) or not miner_responses:
        # Apply penalty if invalid values are provided to the function
        return 20.0

    for engine in ["engine:text_classification", "engine:yara", "engine:vector_search"]:
        penalty += _check_response_history(uid, miner_responses, engine)

    return penalty
