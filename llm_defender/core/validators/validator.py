"""Module for prompt-injection neurons for the
llm-defender-subnet.

Long description

Typical example usage:

    foo = bar()
    foo.bar()
"""
import copy
from argparse import ArgumentParser
from typing import Tuple
import torch
from os import path
import bittensor as bt
from llm_defender.base.neuron import BaseNeuron
from llm_defender.base.utils import EnginePrompt
from llm_defender.base import mock_data


class PromptInjectionValidator(BaseNeuron):
    """Summary of the class

    Class description

    Attributes:

    """

    def __init__(self, parser: ArgumentParser):
        super().__init__(parser=parser, profile="validator")

        self.max_engines = 3
        self.timeout = 12
        self.neuron_config = None
        self.wallet = None
        self.subtensor = None
        self.dendrite = None
        self.metagraph = None
        self.scores = None
        self.hotkeys = None

    def apply_config(self, bt_classes) -> bool:
        """This method applies the configuration to specified bittensor classes"""
        try:
            self.neuron_config = self.config(bt_classes=bt_classes)
        except AttributeError as e:
            bt.logging.error(f"Unable to apply validator configuration: {e}")
            raise AttributeError from e
        except OSError as e:
            bt.logging.error(f"Unable to create logging directory: {e}")
            raise OSError from e

        return True

    def validator_validation(self, metagraph, wallet, subtensor) -> bool:
        """This method validates the validator has registered correctly"""
        if wallet.hotkey.ss58_address not in metagraph.hotkeys:
            bt.logging.error(
                f"Your validator: {wallet} is not registered to chain connection: {subtensor}. Run btcli register and try again"
            )
            return False

        return True

    def setup_bittensor_objects(
        self, neuron_config
    ) -> Tuple[bt.wallet, bt.subtensor, bt.dendrite, bt.metagraph]:
        """Setups the bittensor objects"""
        try:
            wallet = bt.wallet(config=neuron_config)
            subtensor = bt.subtensor(config=neuron_config)
            dendrite = bt.dendrite(wallet=wallet)
            metagraph = subtensor.metagraph(neuron_config.netuid)
        except AttributeError as e:
            bt.logging.error(f"Unable to setup bittensor objects: {e}")
            raise AttributeError from e

        self.hotkeys = copy.deepcopy(metagraph.hotkeys)

        return wallet, subtensor, dendrite, metagraph

    def initialize_neuron(self) -> bool:
        """This function initializes the neuron.

        The setup function initializes the neuron by registering the
        configuration.

        Args:
            None

        Returns:
            Bool:
                A boolean value indicating success/failure of the initialization.
        Raises:
            AttributeError:
                AttributeError is raised if the neuron initialization failed
            IndexError:
                IndexError is raised if the hotkey cannot be found from the metagraph
        """
        bt.logging(config=self.neuron_config, logging_dir=self.neuron_config.full_path)
        bt.logging.info(
            f"Initializing validator for subnet: {self.neuron_config.netuid} on network: {self.neuron_config.subtensor.chain_endpoint} with config: {self.neuron_config}"
        )

        # Setup the bittensor objects
        wallet, subtensor, dendrite, metagraph = self.setup_bittensor_objects(
            self.neuron_config
        )

        bt.logging.info(
            f"Bittensor objects initialized:\nMetagraph: {metagraph}\nSubtensor: {subtensor}\nWallet: {wallet}"
        )

        # Validate that the validator has registered to the metagraph correctly
        if not self.validator_validation(metagraph, wallet, subtensor):
            raise IndexError("Unable to find validator key from metagraph")

        # Get the unique identity (UID) from the network
        validator_uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
        bt.logging.info(f"Validator is running with UID: {validator_uid}")

        self.wallet = wallet
        self.subtensor = subtensor
        self.dendrite = dendrite
        self.metagraph = metagraph

        # Read command line arguments and perform actions based on them
        args = self.parser.parse_args()

        if args.load_state:
            self.load_state()
        else:
            # Setup initial scoring weights
            self.scores = torch.zeros_like(metagraph.S, dtype=torch.float32)
            bt.logging.debug(f"Validation weights have been initialized: {self.scores}")

        return True

    def process_responses(
        self, processed_uids: torch.tensor, query: dict, responses: list
    ):
        """
        This function processes the responses received from the miners.
        """

        processed_uids = processed_uids.tolist()

        # Determine target value for scoring
        if query["data"]["isPromptInjection"] is True:
            target = 1.0
        else:
            target = 0.0

        bt.logging.debug(f"Target set to: {target}")

        for i, response in enumerate(responses):
            bt.logging.debug(
                f"Processing response {i} from UID {processed_uids[i]} with content: {response}"
            )
            # Set the score for empty responses to 0
            if not response.output:
                bt.logging.debug(
                    f"Received an empty response from UID {processed_uids[i]}: {response}"
                )
                old_score = copy.deepcopy(self.scores[processed_uids[i]])
                self.scores[processed_uids[i]] = (
                    self.neuron_config.alpha * self.scores[processed_uids[i]]
                    + (1 - self.neuron_config.alpha) * 0.0
                )
                new_score = self.scores[processed_uids[i]]
                bt.logging.info(f'No valid response from UID {processed_uids[i]}. Overall score for the UID {processed_uids[i]}: {new_score} (Change: {new_score - old_score})')
                continue

            response_time = response.dendrite.process_time
            response_score = self.calculate_score(
                response=response.output,
                target=target,
                response_time=response_time,
                hotkey=response.dendrite.hotkey,
            )

            old_score = copy.deepcopy(self.scores[processed_uids[i]])
            self.scores[processed_uids[i]] = (
                self.neuron_config.alpha * self.scores[processed_uids[i]]
                + (1 - self.neuron_config.alpha) * response_score
            )
            new_score = self.scores[processed_uids[i]]

            bt.logging.info(f'Scored the response from UID {processed_uids[i]}: {response_score}. Overall score for the UID {processed_uids[i]}: {new_score} (Change: {new_score - old_score})')

    def calculate_score(
        self, response, target: float, response_time: float, hotkey: str
    ) -> float:
        """This function sets the score based on the response.

        Returns:
            score: An instance of float depicting the score for the
            response
        """

        # Calculate distances to target value for each engine and take the mean
        distances = [
            abs(target - confidence)
            for confidence in [engine["confidence"] for engine in response["engines"]]
        ]
        distance_score = (
            1 - sum(distances) / len(distances) if len(distances) > 0 else 1.0
        )

        # Calculate score for the speed of the response
        bt.logging.debug(
            f"Calculating speed_score for {hotkey} with response_time: {response_time} and timeout {self.timeout}"
        )
        if response_time > self.timeout:
            bt.logging.debug(
                f"Received response time {response_time} larger than timeout {self.timeout}, setting response_time to timeout value"
            )
            response_time = self.timeout

        speed_score = 1.0 - (response_time / self.timeout)

        # Calculate score for the number of engines used
        engine_score = len(response) / self.max_engines

        # Validate individual scores
        if (
            not (0.0 <= distance_score <= 1.0)
            or not (0.0 <= speed_score <= 1.0)
            or not (0.0 <= engine_score <= 1.0)
        ):
            bt.logging.error(
                f"Calculated out-of-bounds individual scores:\nDistance: {distance_score}\nSpeed: {speed_score}\nEngine: {engine_score} for the response: {response} from hotkey: {hotkey}"
            )

            return 0.0

        # Determine final score
        distance_weight = 0.7
        speed_weight = 0.2
        num_engines_weight = 0.1

        bt.logging.debug(
            f"Scores: Distance: {distance_score}, Speed: {speed_score}, Engine: {engine_score}"
        )

        score = (
            distance_weight * distance_score
            + speed_weight * speed_score
            + num_engines_weight * engine_score
        )

        if score > 1.0 or score < 0.0:
            bt.logging.error(
                f"Calculated out-of-bounds score: {score} for the response: {response} from hotkey: {hotkey}"
            )

            return 0.0

        return score

    def penalty(self) -> bool:
        """
        Penalty function.
        """
        return False

    def serve_prompt(self) -> EnginePrompt:
        """Generates a prompt to serve to a miner

        This function selects a random prompt from the dataset to be
        served for the miners connected to the subnet.

        Args:
            None

        Returns:
            prompt: An instance of EnginePrompt
        """

        entry = mock_data.get_prompt()

        prompt = EnginePrompt(
            engine="Prompt Injection",
            prompt=entry["text"],
            data={"isPromptInjection": entry["isPromptInjection"]},
        )

        return prompt

    def save_state(self):
        """Saves the state of the validator to a file."""
        bt.logging.info("Saving validator state.")

        # Save the state of the validator to file.
        torch.save(
            {
                "step": self.step,
                "scores": self.scores,
                "hotkeys": self.hotkeys,
                "last_updated_block": self.last_updated_block
            },
            self.base_path + "/state.pt",
        )

        bt.logging.debug(f'Saved the following state to a file: step: {self.step}, scores: {self.scores}, hotkeys: {self.hotkeys}, last_updated_block: {self.last_updated_block}')

    def load_state(self):
        """Loads the state of the validator from a file."""

        # Load the state of the validator from file.
        state_path = self.base_path + "/state.pt"
        if path.exists(state_path):
            bt.logging.info("Loading validator state.")
            state = torch.load(state_path)
            bt.logging.debug(f'Loaded the following state from file: {state}')
            self.step = state["step"]
            self.scores = state["scores"]
            self.hotkeys = state["hotkeys"]
            self.last_updated_block = state["last_updated_block"]

            bt.logging.info(f'Scores loaded from saved file: {self.scores}')
        else:
            bt.logging.info("Validator state not found. Starting with default values.")
            # Setup initial scoring weights
            self.scores = torch.zeros_like(self.metagraph.S, dtype=torch.float32)
            bt.logging.info(f"Validation weights have been initialized: {self.scores}")

            
