"""CLI script to run offline RAG quality evaluation and BM25 ablation comparison."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    parser = argparse.ArgumentParser(description="Run RAG quality evaluation on golden dataset")
    parser.add_argument(
        "--dataset",
        default="app/evaluation/golden_dataset.json",
        help="Path to golden Q&A dataset JSON (default: 52 pairs)",
    )
    parser.add_argument(
        "--output",
        default="app/evaluation/evaluation_report.json",
        help="Output report path",
    )
    parser.add_argument(
        "--disable-bm25",
        action="store_true",
        help="Disable BM25 lexical search (vector-only mode)",
    )
    parser.add_argument(
        "--compare-bm25",
        action="store_true",
        help="Run both Hybrid (BM25 + Vector) and Vector-only to demonstrate BM25 contribution",
    )
    args = parser.parse_args()

    from app.evaluation.ragas_evaluator import run_evaluation

    if args.compare_bm25:
        vector_only = await run_evaluation(
            dataset_path=args.dataset,
            output_path=None,
            bm25_enabled=False,
            record_history=True,
        )
        hybrid = await run_evaluation(
            dataset_path=args.dataset,
            output_path=args.output,
            bm25_enabled=True,
            record_history=True,
        )
        print("\n=== BM25 Contribution Ablation Study (52 Golden Q&A Pairs) ===")
        print(f"Vector-Only (BM25 OFF): {json.dumps(vector_only['metrics'], indent=2)}")
        print(f"Hybrid RRF  (BM25 ON):  {json.dumps(hybrid['metrics'], indent=2)}")
        return

    report = await run_evaluation(
        dataset_path=args.dataset,
        output_path=args.output,
        bm25_enabled=not args.disable_bm25,
        record_history=True,
    )

    m = report["metrics"]
    print("\n=== RAG Quality Evaluation Report ===")
    print(f"Run ID:              {report['run_id']}")
    print(f"Golden Questions:    {report['total_questions']}")
    print(f"BM25 Enabled:        {m['bm25_enabled']}")
    print(f"Faithfulness:        {m['faithfulness']:.4f} ({m['faithfulness'] * 100:.1f}%)")
    print(f"Context Precision:   {m['context_precision']:.4f} ({m['context_precision'] * 100:.1f}%)")
    print(f"Context Recall:      {m['context_recall']:.4f} ({m['context_recall'] * 100:.1f}%)")
    print(f"Latency p50 / p95:   {m['latency_p50_ms']} ms / {m['latency_p95_ms']} ms")
    print(f"Avg Tokens / Answer: {m['avg_tokens_per_answer']}")


if __name__ == "__main__":
    asyncio.run(main())
