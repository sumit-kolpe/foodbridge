"""Run the full FoodBridge data pipeline end to end:  python scripts/run_pipeline.py"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["01_clean_philly_sites.py", "02_generate_synthetic_raw.py", "03_clean_integrate.py",
         "04_generate_allocations.py", "05_validate_and_summarize.py"]

for step in STEPS:
    print(f"\n=== {step} ===", flush=True)
    if subprocess.run([sys.executable, step], cwd=HERE).returncode:
        sys.exit(f"Pipeline stopped: {step} failed")
print("\nDone. Final CSVs in data/processed/, reports in reports/.")
