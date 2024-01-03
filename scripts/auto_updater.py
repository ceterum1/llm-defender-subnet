from argparse import ArgumentParser
import logging
import sys
from time import sleep
import git
import subprocess
import random
import hashlib
from pathlib import Path


logger = logging.getLogger("logger")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler(sys.stdout)
logHandler.setLevel(logging.INFO)
logger.addHandler(logHandler)


def _calculate_hash(file_path):
    # Open the file in binary mode to read its content
    with open(file_path, "rb") as file:
        # Create a hash object (in this case, MD5 hash)
        hash_object = hashlib.md5()

        # Read the file in chunks to handle large files
        for chunk in iter(lambda: file.read(4096), b""):
            hash_object.update(chunk)

    # Return the hexadecimal digest of the hash
    return hash_object.hexdigest()


def run(args):
    """Monitors the given git branch for updates and restart given PM2
    instances if updates are found"""

    while True:
        try:
            should_exit = False
            # Setup git repository objects
            repo = git.Repo()
            origin = repo.remotes.origin

            # Fetch updates from the remote registry
            origin.fetch()

            # Check if there are changes in the remote repository
            if (
                repo.refs[args.branch].commit
                != repo.refs[f"origin/{args.branch}"].commit
            ):
                # Check if auto_updater.py has been changed
                current_hash = _calculate_hash("./scripts/auto_updater.py")
                logger.info("Changes detected in remote branch: %s", args.branch)
                logger.info("Pulling remote branch: %s", args.branch)
                origin.pull(args.branch)
                repo.git.checkout(args.branch)
                logger.info("Checked out to branch: %s", args.branch)

                new_hash = _calculate_hash("./scripts/auto_updater.py")
                if current_hash != new_hash:
                    logger.info(
                        "Auto updater hash has changed. Old hash: %s, new hash: %s. Setting should exit to True.",
                        current_hash,
                        new_hash,
                    )
                    should_exit = True

                # Install package
                run_args = "--install_only 1"
                if args.prepare_miners is True:
                    run_args += " --profile miner"
                subprocess.run(
                    f"bash scripts/run_neuron.sh {run_args}", check=True, shell=True
                )

                logger.info('Installing the new subnet version')
                subprocess.run('pip install -e .', check=True, shell=True)
                
                # Restart pm2 instances
                for instance_name in args.pm2_instance_names:
                    try:
                        sleep_duration = random.randint(15, 90)
                        logger.info(
                            "Sleeping for %s seconds before restart", sleep_duration
                        )
                        sleep(sleep_duration)
                        subprocess.run(
                            f"git checkout {args.branch} && pm2 restart {instance_name}",
                            check=True,
                            shell=True,
                        )
                        logger.info("Restarted PM2 process: %s", instance_name)
                    
                    except subprocess.CalledProcessError as e:
                        logger.error("Unable to restart PM2 instance: %s", e)

                logger.info("All processes have been restarted")
            else:
                logger.info("No changes detected in remote branch: %s", args.branch)

            logger.info("Sleeping for %s seconds.", args.update_interval)
            sleep(int(args.update_interval))

            # Exit the updater and let PM2 restart it if should_exit is True
            if should_exit is True:
                logger.info(
                    "Should exit is True, exiting and letting PM2 restart the updater"
                )
                sys.exit(0)

        except Exception as e:
            logger.error("Error occurred: %s", e)
            raise Exception from e


if __name__ == "__main__":
    parser = ArgumentParser()

    cwd = Path.cwd()
    repo_name = "llm-defender-subnet"

    if cwd.parts[-1] == repo_name:
        parser.add_argument(
            "--pm2_instance_names",
            nargs="+",
            help="List of PM instances to keep up-to-date",
        )
        parser.add_argument("--branch", action="store", help="Git branch to monitor")
        parser.add_argument(
            "--prepare_miners",
            type=bool,
            action="store",
            default=True,
            help="If you're not running miners or you dont want to prepare them, set this to False",
        )
        parser.add_argument(
            "--update_interval",
            action="store",
            help="Interval to check for any new updates",
        )

        args = parser.parse_args()
        run(args)
    else:
        logger.error(
            "Invalid current working directory. You must be in the root of the llm-defender-subnet git repository to run this script. Path: %s",
            cwd,
        )
        raise RuntimeError(
            f"Invalid current path: {cwd}. Expecting the path to end with {repo_name}"
        )
