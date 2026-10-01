"""Start the local demo; never binds to a public network interface."""
import argparse
from pathlib import Path
from triage import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sutra local customer-support triage")
    parser.add_argument("--port", type=int, default=8106)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent / "instance")
    parser.add_argument("--training-data", type=Path, help="Optional validated local training JSON; never downloads data")
    parser.add_argument("--no-demo", action="store_true", help="Leave a new database empty")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    application = create_app({"DATA_DIR": str(args.data_dir.resolve()), "SEED_DEMO": not args.no_demo, "TRAINING_DATA": args.training_data})
    application.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)
