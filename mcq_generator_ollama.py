"""
MCQ Generator using Ollama (Qwen / Gemma / any local model).
Designed to run in Google Colab.

Colab setup (run these cells first):
──────────────────────────────────────
Cell 1 – install & start Ollama:
  !curl -fsSL https://ollama.com/install.sh | sh
  !nohup ollama serve &> ollama.log &
  import time; time.sleep(3)          # wait for server to start

Cell 2 – pull a model (pick one):
  !ollama pull qwen2.5:1.5b            # ~1 GB  – fastest
  # !ollama pull qwen2.5:3b            # ~2 GB
  # !ollama pull qwen2.5:7b            # ~5 GB  – best quality
  # !ollama pull gemma2:2b             # ~1.6 GB

Cell 3 – run this script:
  !python mcq_generator_ollama.py
──────────────────────────────────────
"""

import re
import json
import textwrap
import urllib.request
import urllib.error

# ──────────────────────────────────────────────
# CONFIGURATION  – edit these as needed
# ──────────────────────────────────────────────

# Must match the tag you pulled with `ollama pull`
MODEL    = "qwen2.5:1.5b"   # change to qwen2.5:3b / qwen2.5:7b / gemma2:2b etc.
OLLAMA_URL = "http://localhost:11434/api/chat"

NUM_QUESTIONS = 5

# ──────────────────────────────────────────────
# INPUT TEXT  – paste the text you want quizzed
# ──────────────────────────────────────────────
INPUT_TEXT = """
Photosynthesis is the process used by plants, algae, and certain bacteria to
harness energy from sunlight and turn it into chemical energy. During
photosynthesis, plants absorb carbon dioxide (CO2) from the air through tiny
pores called stomata and water (H2O) from the soil through their roots.
Using the energy from sunlight, the plant converts these raw materials into
glucose (C6H12O6) and oxygen (O2). The overall chemical equation is:
  6CO2 + 6H2O + light energy → C6H12O6 + 6O2
Photosynthesis occurs mainly in the chloroplasts, where the green pigment
chlorophyll absorbs light energy. The process has two main stages: the
light-dependent reactions (which capture solar energy and produce ATP and
NADPH) and the Calvin cycle (which uses that energy to fix CO2 into glucose).
"""

# ──────────────────────────────────────────────
# OPTIONAL PATTERN  – leave empty "" to skip
# ──────────────────────────────────────────────
QUESTION_PATTERN = """
- Focus on factual recall and conceptual understanding.
- Avoid trivial or trick questions.
- Distractors (wrong options) should be plausible but clearly incorrect.
- Difficulty: high-school or undergraduate level.
"""

# ──────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────

def build_prompt(text: str, pattern: str, n: int) -> str:
    pattern_block = (
        f"\nAdditional requirements:\n{pattern.strip()}\n"
        if pattern.strip() else ""
    )
    return textwrap.dedent(f"""
        You are an expert educator. Read the text below and generate exactly
        {n} multiple-choice questions (MCQs) that test understanding of it.
        {pattern_block}
        Return ONLY a valid JSON array – no markdown fences, no extra text.
        Each element must follow this exact schema:
        {{
          "question": "<question text>",
          "options": {{"a": "...", "b": "...", "c": "...", "d": "..."}},
          "answer": "<a | b | c | d>",
          "explanation": "<why the answer is correct>"
        }}

        ===TEXT===
        {text.strip()}
        ===END===
    """).strip()


def chat(prompt: str) -> str:
    """Send a single-turn chat request to the local Ollama server."""
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0,       # greedy → deterministic JSON
            "num_predict": 2048,
        },
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
            return body["message"]["content"]
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_URL}.\n"
            "Make sure you ran:  !nohup ollama serve &> ollama.log &\n"
            f"Original error: {e}"
        )


def extract_json(raw: str) -> list:
    """Parse the first JSON array from the model output."""
    raw = raw.strip()

    # Strip optional markdown code fences the model might still add
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # Direct parse
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: grab the first [...] block
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Could not parse a JSON array from the model output.\n"
        f"Raw output (first 800 chars):\n{raw[:800]}"
    )


def validate_mcq(mcq: dict, idx: int) -> bool:
    required = {"question", "options", "answer", "explanation"}
    if not required.issubset(mcq):
        print(f"  ⚠️  Q{idx+1} missing keys – skipping.")
        return False
    if not isinstance(mcq["options"], dict) or not {"a","b","c","d"}.issubset(mcq["options"]):
        print(f"  ⚠️  Q{idx+1} malformed options – skipping.")
        return False
    if mcq["answer"].lower() not in {"a","b","c","d"}:
        print(f"  ⚠️  Q{idx+1} invalid answer key – skipping.")
        return False
    return True


# ──────────────────────────────────────────────
# QUIZ RUNNER
# ──────────────────────────────────────────────

def sep(char="─", w=60):
    print(char * w)


def run_quiz(mcqs: list):
    sep("═")
    print("🎓  QUIZ TIME!  Type a, b, c, or d to answer each question.")
    sep("═")

    score = 0
    for i, mcq in enumerate(mcqs):
        print(f"\nQ{i+1}/{len(mcqs)}: {mcq['question']}\n")
        for letter in "abcd":
            print(f"  {letter})  {mcq['options'][letter]}")

        while True:
            ans = input("\nYour answer (a/b/c/d): ").strip().lower()
            if ans in "abcd" and len(ans) == 1:
                break
            print("  Please type a, b, c, or d.")

        correct = mcq["answer"].lower()
        if ans == correct:
            score += 1
            print("\n✅  Correct!\n")
        else:
            print(f"\n❌  Wrong!  Correct answer: ({correct}) {mcq['options'][correct]}")
            print(f"💡  {mcq['explanation']}\n")
        sep()

    print(f"\n🏆  Score: {score}/{len(mcqs)}")
    pct = score / len(mcqs) * 100
    if pct == 100:  print("    Perfect! 🎉")
    elif pct >= 80: print("    Great job! 👍")
    elif pct >= 60: print("    Good effort – review the explanations above.")
    else:           print("    Keep studying! 📚")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    print(f"🤖  Model : {MODEL}")
    print(f"📋  Generating {NUM_QUESTIONS} questions …\n")

    prompt    = build_prompt(INPUT_TEXT, QUESTION_PATTERN, NUM_QUESTIONS)
    raw       = chat(prompt)

    try:
        mcqs_raw = extract_json(raw)
    except ValueError as e:
        print(f"❌  {e}")
        return

    mcqs = [m for i, m in enumerate(mcqs_raw) if validate_mcq(m, i)]
    if not mcqs:
        print("❌  No valid questions generated. Try a larger model.")
        return

    print(f"✅  {len(mcqs)} question(s) ready.\n")
    run_quiz(mcqs)


if __name__ == "__main__":
    main()
