import argparse
import asyncio
import logging
import sys

from legal_rag_audit.config import AuditConfig
from legal_rag_audit.runner import TestRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    parser = argparse.ArgumentParser(description="Legal RAG Audit Tool")
    parser.add_argument("-c", "--config", required=True, help="Path to config.yaml")
    parser.add_argument("-o", "--output", default="report", help="Base name for output report files")
    
    args = parser.parse_args()

    try:
        config = AuditConfig.load_from_yaml(args.config)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        sys.exit(1)

    runner = TestRunner(config)
    
    # Run the async runner loop
    report = asyncio.run(runner.run_all())
    
    # Save reports
    json_path = f"{args.output}.json"
    md_path = f"{args.output}.md"
    
    report.save_json(json_path)
    report.save_markdown(md_path)
    
    logging.info(f"Report saved to {json_path} and {md_path}")
    
    # Exit with code 1 if failed
    if report.summary["verdict"] == "FAIL":
        sys.exit(1)
        
if __name__ == "__main__":
    main()
