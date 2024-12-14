import argparse

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize Multilspy for a language")
    parser.add_argument("lang", type=str, help="The language to initialize Multilspy for")
    args = parser.parse_args()

    print(f"Initializing Multilspy for {args.lang}")
    config = MultilspyConfig.from_dict({"code_language": args.lang})
    logger = MultilspyLogger()
    SyncLanguageServer.create(config, logger, ".")
    print(f"Multilspy for {args.lang} initialized successfully")