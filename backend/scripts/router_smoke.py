"""Router smoke test — tricky queries for the Supervisor router.

Runs a small hand-picked set of adversarial cross-domain / injury-context
queries through the router_node directly (bypasses API, RateLimiter, DB)
and prints accuracy + confusion matrix + per-query predicted-vs-expected.

Intended as a developer smoke tool for prompt tuning, NOT a CI gate.
The canonical full regression suite lives in the fitcoach-ai-test repo.

Usage (inside backend container):
    docker exec -w /app fitcoach-backend python -m scripts.router_smoke
"""
import asyncio
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.router import router_node  # noqa: E402
from app.agents.state import AgentState  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("router_smoke")

# Hand-picked tricky queries. Each entry covers a specific pattern the
# current prompt fails on. Mix of Chinese and English because the Layer 1
# Golden Set is predominantly English.
SMOKE_QUERIES: list[dict] = [
    # ─── Easy sanity checks (must stay correct) ────────────────────────
    {
        "query": "What is the correct bar position for a low-bar back squat?",
        "expected": "training",
        "pattern": "easy-training-en",
    },
    {
        "query": "增肌期每天要吃多少蛋白质？",
        "expected": "nutrition",
        "pattern": "easy-nutrition-zh",
    },
    {
        "query": "What is the PRICE protocol for acute soft tissue injuries?",
        "expected": "rehab",
        "pattern": "easy-rehab-en",
    },

    # ─── Historical injury + training intent (OLD prompt mis-routes) ──
    {
        "query": "I am a powerlifter with a history of lower back issues. How do I peak safely for a meet?",
        "expected": "training",
        "pattern": "history-injury + peaking → training",
    },
    {
        "query": "我有肩袖旧伤，卧推该怎么调整动作？",
        "expected": "training",
        "pattern": "old-injury + movement-adjustment → training",
    },
    {
        "query": "膝盖以前受伤过，现在想练深蹲进阶该怎么安排？",
        "expected": "training",
        "pattern": "old-injury + progression → training",
    },

    # ─── Current injury / acute / rebuilding → rehab ──────────────────
    {
        "query": "How should I program my bench press to work around a mild pec strain?",
        "expected": "rehab",
        "pattern": "current-strain + program-around → rehab",
    },
    {
        "query": "当前下背痛，还能硬拉吗？",
        "expected": "rehab",
        "pattern": "current-pain + can-I-lift → rehab",
    },
    {
        "query": "I injured my ACL 6 months ago. How do I rebuild my squat strength over 8 weeks?",
        "expected": "rehab",
        "pattern": "injury-rebuild → rehab",
    },
    {
        "query": "膝盖肌腱炎恢复期间，训练量要怎么调？",
        "expected": "rehab",
        "pattern": "rehab-phase + volume → rehab",
    },

    # ─── Training intent despite nutrition/recovery wording ───────────
    {
        "query": "Can I do Starting Strength while eating at a caloric deficit?",
        "expected": "training",
        "pattern": "training-program + diet-context → training",
    },
    {
        "query": "How do I periodize training during a fat loss phase without losing strength?",
        "expected": "training",
        "pattern": "periodization + fat-loss → training",
    },

    # ─── Nutrition intent despite training/recovery context ───────────
    {
        "query": "减脂期要吃多少蛋白质才能保住肌肉？",
        "expected": "nutrition",
        "pattern": "protein-intake + training-goal → nutrition",
    },
    {
        "query": "What protein sources best support tendon healing while I continue to squat?",
        "expected": "nutrition",
        "pattern": "protein-for-healing → nutrition",
    },

    # ─── Rehab-primary with nutrition mention ─────────────────────────
    {
        "query": "I have lower back pain and want to know if creatine can reduce inflammation while I rehab.",
        "expected": "rehab",
        "pattern": "rehab-primary + supplement-question → rehab",
    },

    # ─── Generic training questions with injury-adjacent words ────────
    {
        "query": "Why does my knee cave inward during squats and how do I fix it?",
        "expected": "training",
        "pattern": "form-fault (no pain) → training",
    },
    {
        "query": "How do I progressively overload without getting injured as a beginner?",
        "expected": "training",
        "pattern": "injury-prevention + progression → training",
    },

    # ─── Multi-domain cross (accept valid_agents) ─────────────────────
    {
        "query": "What rep range and what protein intake should a beginner lifter use to build muscle quickly?",
        "expected": "training",  # primary intent: build muscle via rep range
        "pattern": "rep-range + protein → training",
    },
]


async def run_smoke() -> dict:
    preds: list[tuple[dict, str]] = []
    for i, case in enumerate(SMOKE_QUERIES):
        state: AgentState = {"user_query": case["query"]}  # type: ignore[typeddict-item]
        result = await router_node(state)
        pred = result.get("routed_agent", "?")
        preds.append((case, pred))
        mark = "✓" if pred == case["expected"] else "✗"
        logger.info(
            "%s [%d/%d] %-48s  expected=%-9s  got=%-9s  pattern=%s",
            mark,
            i + 1,
            len(SMOKE_QUERIES),
            case["query"][:48],
            case["expected"],
            pred,
            case["pattern"],
        )

    # Metrics
    total = len(preds)
    correct = sum(1 for c, p in preds if p == c["expected"])
    acc = correct / total if total else 0

    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c, p in preds:
        confusion[c["expected"]][p] += 1

    logger.info("")
    logger.info("=" * 72)
    logger.info("Accuracy: %d / %d = %.1f%%", correct, total, 100 * acc)
    logger.info("")
    logger.info("Confusion matrix (rows=expected, cols=predicted):")
    agents = ["training", "rehab", "nutrition"]
    logger.info("           %s", "  ".join(f"{a:>9}" for a in agents))
    for exp in agents:
        row = "  ".join(f"{confusion[exp][p]:>9}" for p in agents)
        logger.info("  %-8s %s", exp, row)
    logger.info("")
    logger.info("Mis-routed cases:")
    for c, p in preds:
        if p != c["expected"]:
            logger.info("  ✗ [%s → %s] %s", c["expected"], p, c["query"])

    return {"accuracy": acc, "correct": correct, "total": total, "predictions": preds}


if __name__ == "__main__":
    asyncio.run(run_smoke())
