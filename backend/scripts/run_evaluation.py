"""CLI script to run offline RAGAS evaluation."""

import asyncio
import argparse
import json
import sys

sys.path.insert(0, ".")


async def main():
    parser = argparse.ArgumentParser(description="Run RAGAS offline evaluation")
    parser.add_argument(
        "--dataset",
        default="app/evaluation/golden_dataset.json",
        help="Path to golden Q&A dataset JSON",
    )
    parser.add_argument(
        "--output",
        default="evaluation_report.json",
        help="Output report path",
    )
    args = parser.parse_args()

    from app.evaluation.ragas_evaluator import run_evaluation

    report = await run_evaluation(
        dataset_path=args.dataset,
        output_path=args.output,
    )

    print("\n=== Evaluation Report ===")
    print(f"Questions: {report['total_questions']}")
    print(f"Metrics: {json.dumps(report['metrics'], indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
