"""
MCQ Generator using Google Gemini API (new google-genai SDK).
Designed to run in Google Colab.

Colab setup:
──────────────────────────────────────
Cell 1 – install the NEW SDK:
  !pip install -q google-genai

Cell 2 – add your key in Colab Secrets (🔑 left sidebar)
  Name: GEMINI_API_KEY

Cell 3 – run:
  !python mcq_generator_gemini.py

Free key → https://aistudio.google.com/app/apikey
──────────────────────────────────────
"""

import re
import json
import textwrap
import os
import time

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise SystemExit("❌  Run:  !pip install -q google-genai  then restart the runtime.")

# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────

# Paste your key here OR store it in Colab Secrets as GEMINI_API_KEY
GEMINI_API_KEY = ""

# Model options (free tier):
#   "gemini-2.0-flash-lite"   ← most generous free quota  ✅ recommended
#   "gemini-2.0-flash"        ← fast, slightly lower free quota
#   "gemini-1.5-flash"        ← older but very stable
MODEL = "gemini-2.0-flash-lite"

NUM_QUESTIONS = 5

# Retry settings for 429 / quota errors
MAX_RETRIES = 4          # number of retry attempts
RETRY_WAIT  = 30         # seconds to wait between retries (if no hint in error)

# ──────────────────────────────────────────────
# INPUT TEXT
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
# OPTIONAL PATTERN  – leave "" to skip
# ──────────────────────────────────────────────
QUESTION_PATTERN = """
- Focus on factual recall and conceptual understanding.
- Avoid trivial or trick questions.
- Distractors (wrong options) should be plausible but clearly incorrect.
- Difficulty: high-school or undergraduate level.
"""

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def resolve_api_key() -> str:
    """Try hardcoded constant → Colab Secrets → environment variable."""
    if GEMINI_API_KEY:
        return GEMINI_API_KEY
    try:
        from google.colab import userdata
        key = userdata.get("GEMINI_API_KEY")
        if key:
            return key
    except Exception:
        pass
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    raise SystemExit(
        "❌  No API key found.\n"
        "    1) Add GEMINI_API_KEY in Colab Secrets (🔑 left sidebar)\n"
        "    2) OR paste it into GEMINI_API_KEY at the top of this script.\n"
        "    Free key → https://aistudio.google.com/app/apikey"
    )


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


def call_gemini(client: genai.Client, prompt: str) -> str:
    """
    Call the Gemini API with automatic retry on 429 quota errors.
    Parses the retry-delay hint from the error message when available.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=2048,
                ),
            )
            return response.text

        except Exception as e:
            err = str(e)
            is_quota = "429" in err or "quota" in err.lower() or "rate" in err.lower()

            if is_quota and attempt < MAX_RETRIES:
                # Read the suggested wait time from the error if present
                wait = RETRY_WAIT
                m = re.search(r"retry in ([\d.]+)s", err, re.IGNORECASE)
                if m:
                    wait = int(float(m.group(1))) + 2   # small buffer
                print(f"  ⏳  Quota limit hit – waiting {wait}s "
                      f"(attempt {attempt}/{MAX_RETRIES}) …")
                time.sleep(wait)
            else:
                raise   # non-quota error or retries exhausted


def extract_json(raw: str) -> list:
    raw = raw.strip()
    # Strip markdown fences the model might add despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: find the first [...] block
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
            if ans in {"a","b","c","d"}:
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
    api_key = resolve_api_key()
    client  = genai.Client(api_key=api_key)

    print(f"🤖  Model  : {MODEL}")
    print(f"📋  Generating {NUM_QUESTIONS} questions …\n")

    prompt = build_prompt(INPUT_TEXT, QUESTION_PATTERN, NUM_QUESTIONS)

    try:
        raw = call_gemini(client, prompt)
    except Exception as e:
        print(f"❌  Gemini API error: {e}")
        return

    try:
        mcqs_raw = extract_json(raw)
    except ValueError as e:
        print(f"❌  {e}")
        return

    mcqs = [m for i, m in enumerate(mcqs_raw) if validate_mcq(m, i)]
    if not mcqs:
        print("❌  No valid questions generated.")
        return

    print(f"✅  {len(mcqs)} question(s) ready.\n")
    run_quiz(mcqs)


if __name__ == "__main__":
    main()
