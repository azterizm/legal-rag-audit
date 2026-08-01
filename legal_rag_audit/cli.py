import argparse
import asyncio
import logging
import sys

from legal_rag_audit.config import AuditConfig
from legal_rag_audit.corpus_loader import CorpusError
from legal_rag_audit.runner import TestRunner

def main():
    parser = argparse.ArgumentParser(description="Legal RAG Audit Tool")
    parser.add_argument("-c", "--config", required=True, help="Path to config.yaml")
    parser.add_argument("-o", "--output", default="report", help="Base name for output report files")
    parser.add_argument("--skip-upload", action="store_true", help="Skip uploading the corpus, use local files for tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    
    file_handler = logging.FileHandler(".legal_rag_audit.log", mode='a')
    console_handler = logging.StreamHandler()
    
    logging.basicConfig(
        level=log_level, 
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[file_handler, console_handler]
    )

    try:
        config = AuditConfig.load_from_yaml(args.config)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        sys.exit(1)

    runner = TestRunner(config, skip_upload=args.skip_upload)

    # Run the async runner loop
    try:
        report = asyncio.run(runner.run_all())
    except CorpusError as e:
        # A setup problem, not a finding. No report is written — a report produced from
        # a corpus we could not verify would describe the corpus, not the target.
        logging.error(f"Corpus setup failed, aborting before any result is written:\n{e}")
        sys.exit(2)
    
    import os
    
    output_base = args.output
    out_dir = os.path.dirname(output_base)
    if not out_dir:
        out_dir = "reports"
        output_base = os.path.join(out_dir, output_base)
        
    os.makedirs(out_dir, exist_ok=True)
    
    # Save reports
    json_path = f"{output_base}.json"
    md_path = f"{output_base}.md"
    
    report.save_json(json_path)
    report.save_markdown(md_path)
    
    logging.info(f"Report saved to {json_path} and {md_path}")
    
    # Exit with code 1 if failed
    if report.summary["verdict"] == "FAIL":
        sys.exit(1)
        
if __name__ == "__main__":
    main()
