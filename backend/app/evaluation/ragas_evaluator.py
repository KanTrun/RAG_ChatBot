"""RAGAS offline evaluation runner."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_evaluation(
    dataset_path: str = "app/evaluation/golden_dataset.json",
    output_path: str | None = None,
) -> dict:
    """Run RAGAS evaluation against a golden dataset.

    Returns dict with metric scores.
    """
    # Load dataset
    data_file = Path(dataset_path)
    if not data_file.exists():
        raise FileNotFoundError(f"Golden dataset not found: {dataset_path}")

    with open(data_file) as f:
        dataset = json.load(f)

    questions = dataset.get("questions", [])
    if not questions:
        raise ValueError("Empty golden dataset")

    logger.info(f"Running evaluation on {len(questions)} questions")

    # Collect results by running each question through the RAG pipeline
    results = []
    for item in questions:
        query = item["question"]
        ground_truth = item["ground_truth"]

        # Import here to avoid circular deps
        from app.services.embedding_service import get_embedding_service
        from app.services.retrieval_service import RetrievalService

        # For evaluation, we'd need a DB session - this is a CLI script
        # Placeholder: actual implementation requires async DB session setup
        results.append(
            {
                "question": query,
                "ground_truth": ground_truth,
                "answer": "",  # filled by actual pipeline run
                "contexts": [],  # filled by actual pipeline run
            }
        )

    # Compute metrics using RAGAS (when available)
    metrics = _compute_ragas_metrics(results)

    # Output report
    report = {
        "total_questions": len(questions),
        "metrics": metrics,
        "results": results[:5],  # sample
    }

    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Evaluation report saved to {output_path}")

    return report


def _compute_ragas_metrics(results: list[dict]) -> dict:
    """Compute RAGAS metrics. Graceful fallback if ragas not installed."""
    try:
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            faithfulness,
        )
        from datasets import Dataset

        dataset = Dataset.from_list(results)
        score = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision],
        )
        return {k: round(v, 4) for k, v in score.items()}

    except ImportError:
        logger.warning("RAGAS not installed — returning placeholder metrics")
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
            "note": "Install ragas package: pip install ragas",
        }
