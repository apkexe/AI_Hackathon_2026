"""
RAG Quality Evaluator for CitizenGov.

Reads questions from eval/questions.csv, sends each to the RAG pipeline,
then uses the LLM to score the answer against the expected answer (1-5).

Usage:
    python eval/evaluate_rag.py
    python eval/evaluate_rag.py --output eval/results.csv
"""
import argparse
import csv
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_ingestion.embeddings import VectorStore
from app.watchdog.agent import call_llm
from app.prompts.templates import RAG_SYSTEM_PROMPT, format_contracts_as_context
from app.rag.query_analyzer import analyze_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rag_evaluator")

EVAL_SYSTEM_PROMPT = """You are an impartial evaluator comparing an AI assistant's answer against a reference answer.

Score the AI answer from 1 to 5:
- 5: Perfect — all key facts match the reference, numbers are correct or very close, no hallucinations.
- 4: Good — main facts are correct, minor omissions or rounding differences.
- 3: Acceptable — partially correct, some key facts present but missing important details.
- 2: Poor — mostly wrong or very incomplete, but shows some relevant knowledge.
- 1: Fail — completely wrong, irrelevant, or hallucinated.

RULES:
- Focus on factual accuracy, not writing style.
- If the AI answer says "I don't have enough data" but the reference has a clear answer, score 2 max.
- Small rounding differences in numbers (e.g., €1.33B vs €1.34B) are acceptable for score 5.
- The AI answer does NOT need to match the reference word-for-word.

Output ONLY a JSON object with exactly these keys:
{"score": <1-5>, "reasoning": "<one sentence explaining the score>"}
"""


def ask_rag(question: str, vs: VectorStore) -> str:
    """Run the full RAG pipeline for a single question."""
    analysis = analyze_query(question)
    filters = analysis.get("filters", {})
    semantic_query = analysis.get("semantic_query", question)

    try:
        relevant_contracts = vs.hybrid_search(
            query=semantic_query,
            where_filters=filters if filters else None,
            n_results=20,
        )
    except Exception:
        relevant_contracts = vs.search_contracts(question, n_results=10)

    if not relevant_contracts:
        return "Δεν βρέθηκαν σχετικά αποτελέσματα."

    relevant_contracts = vs.rerank_results(relevant_contracts, question, top_k=10)
    context_text = format_contracts_as_context(relevant_contracts)
    user_prompt = f"Context:\n{context_text}\n\nQuestion: {question}"

    return call_llm(RAG_SYSTEM_PROMPT, user_prompt)


def score_answer(question: str, expected: str, actual: str) -> dict:
    """Use the LLM to score the actual answer against the expected one."""
    user_prompt = (
        f"Question: {question}\n\n"
        f"Reference Answer: {expected}\n\n"
        f"AI Answer: {actual}\n\n"
        f"Score the AI answer (1-5):"
    )
    raw = call_llm(EVAL_SYSTEM_PROMPT, user_prompt)

    import json
    try:
        result = json.loads(raw.strip())
        return {"score": int(result["score"]), "reasoning": result["reasoning"]}
    except Exception:
        logger.warning(f"Failed to parse eval response: {raw}")
        return {"score": 0, "reasoning": f"Parse error: {raw[:200]}"}


def main():
    parser = argparse.ArgumentParser(description="CitizenGov RAG Evaluator")
    parser.add_argument("--input", default=os.path.join(os.path.dirname(__file__), "questions.csv"))
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "results.csv"))
    args = parser.parse_args()

    # Load questions
    with open(args.input, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        questions = list(reader)

    logger.info(f"Loaded {len(questions)} questions from {args.input}")

    vs = VectorStore()
    results = []

    for i, row in enumerate(questions):
        question = row["question"]
        expected = row["expected_answer"]
        logger.info(f"[{i+1}/{len(questions)}] {question[:80]}...")

        # Get RAG answer
        try:
            actual = ask_rag(question, vs)
        except Exception as e:
            logger.error(f"  RAG failed: {e}")
            actual = f"ERROR: {e}"

        logger.info(f"  RAG answer: {actual[:120]}...")

        # Score it
        try:
            eval_result = score_answer(question, expected, actual)
        except Exception as e:
            logger.error(f"  Scoring failed: {e}")
            eval_result = {"score": 0, "reasoning": f"Scoring error: {e}"}

        score = eval_result["score"]
        reasoning = eval_result["reasoning"]
        logger.info(f"  Score: {score}/5 — {reasoning}")

        results.append({
            "question": question,
            "expected_answer": expected,
            "actual_answer": actual,
            "score": score,
            "reasoning": reasoning,
        })

        time.sleep(1)  # Rate limiting

    # Write results
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["question", "expected_answer", "actual_answer", "score", "reasoning"])
        writer.writeheader()
        writer.writerows(results)

    # Summary
    scores = [r["score"] for r in results if r["score"] > 0]
    avg = sum(scores) / len(scores) if scores else 0
    dist = {s: scores.count(s) for s in range(1, 6)}

    logger.info("=" * 60)
    logger.info(f"EVALUATION COMPLETE — {len(results)} questions")
    logger.info(f"Average Score: {avg:.2f}/5")
    logger.info(f"Distribution: {dist}")
    logger.info(f"Results saved to {args.output}")
    logger.info("=" * 60)

    print(f"\nAverage Score: {avg:.2f}/5")
    print(f"Distribution: 5={dist.get(5,0)} | 4={dist.get(4,0)} | 3={dist.get(3,0)} | 2={dist.get(2,0)} | 1={dist.get(1,0)}")


if __name__ == "__main__":
    main()
