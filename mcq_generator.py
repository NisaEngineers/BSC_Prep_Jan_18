"""
MCQ Generator using Gemma or Qwen text generation models.
Designed to run in Google Colab.

Usage:
  - Set MODEL_ID to a Gemma or Qwen model (see options below).
  - Paste your input text into INPUT_TEXT.
  - (Optional) Provide a custom pattern in QUESTION_PATTERN.
  - Run the script and answer each question interactively.
"""

# ──────────────────────────────────────────────
# 1.  INSTALL DEPENDENCIES  (run once in Colab)
# ──────────────────────────────────────────────
# !pip install -q transformers accelerate bitsandbytes

import re
import json
import textwrap
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

# ──────────────────────────────────────────────
# 2.  CONFIGURATION  – edit these as needed
# ──────────────────────────────────────────────

# --- Model options (pick one) ---
# Qwen  (recommended for Colab free tier – smaller & fast):
MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

# Other options:
# MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
# MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"       # needs ~16 GB VRAM
# MODEL_ID = "google/gemma-2-2b-it"            # requires HF token
# MODEL_ID = "google/gemma-2-9b-it"            # needs ~20 GB VRAM

# --- Number of questions to generate ---
NUM_QUESTIONS = 5

# ──────────────────────────────────────────────
# 3.  INPUT TEXT  – paste the text you want to
#     turn into MCQs here
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
# 4.  OPTIONAL PATTERN  – describe any extra
#     structure you want the questions to follow.
#     Leave empty ("") for the default style.
# ──────────────────────────────────────────────
QUESTION_PATTERN = """
- Focus on factual recall and conceptual understanding.
- Avoid trivial or trick questions.
- Distractors (wrong options) should be plausible but clearly incorrect.
- The difficulty should be appropriate for a high-school or undergraduate level.
"""

# ──────────────────────────────────────────────
# 5.  HELPER FUNCTIONS
# ──────────────────────────────────────────────

def build_prompt(text: str, pattern: str, n: int) -> str:
    """Build the instruction prompt sent to the model."""
    pattern_block = (
        f"\nAdditional requirements for the questions:\n{pattern.strip()}\n"
        if pattern.strip() else ""
    )

    return textwrap.dedent(f"""
        You are an expert educator. Read the following text and generate exactly
        {n} multiple-choice questions (MCQs) that test understanding of the content.
        {pattern_block}
        Return your answer as a **valid JSON array** with no extra text before or
        after it.  Each element must follow this exact schema:

        {{
          "question": "<question text>",
          "options": {{
            "a": "<option A>",
            "b": "<option B>",
            "c": "<option C>",
            "d": "<option D>"
          }},
          "answer": "<correct letter: a | b | c | d>",
          "explanation": "<brief explanation of why the answer is correct>"
        }}

        ===TEXT START===
        {text.strip()}
        ===TEXT END===

        JSON array:
    """).strip()


def load_model(model_id: str):
    """Load the tokenizer and model with optional 4-bit quantisation."""
    print(f"\n⏳  Loading model: {model_id}  …")

    # Use 4-bit quantisation when a CUDA GPU is available to save VRAM.
    use_cuda = torch.cuda.is_available()
    bnb_config = None
    if use_cuda:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto" if use_cuda else None,
        torch_dtype=torch.bfloat16 if use_cuda else torch.float32,
        trust_remote_code=True,
    )
    model.eval()
    print("✅  Model loaded.\n")
    return tokenizer, model


def generate_mcqs(tokenizer, model, prompt: str, max_new_tokens: int = 2048) -> str:
    """Run inference and return the raw model output string."""
    device = next(model.parameters()).device
    messages = [{"role": "user", "content": prompt}]

    # --- tokenise input -------------------------------------------------------
    # apply_chat_template can return either a plain tensor or a BatchEncoding
    # dict depending on the model/version.  We always extract a plain LongTensor.
    try:
        encoded = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        # If it came back as a BatchEncoding / dict, pull out the ids tensor
        if isinstance(encoded, dict):
            input_ids = encoded["input_ids"].to(device)
        else:
            input_ids = encoded.to(device)          # already a tensor
    except Exception:
        # Fallback: plain tokenisation (no chat template)
        input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)

    prompt_len = input_ids.shape[-1]               # save BEFORE generation

    # --- generate -------------------------------------------------------------
    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,          # greedy → deterministic JSON
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )

    # Decode only the newly generated tokens (skip the echoed prompt)
    new_tokens = output_ids[0][prompt_len:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def extract_json(raw: str) -> list:
    """
    Extract and parse the first JSON array found in the model output.
    Falls back to a regex search if the output contains extra prose.
    """
    # Try direct parse first
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Search for the first [...] block in the output
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
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
    """Basic sanity check for a single MCQ dict."""
    required_keys = {"question", "options", "answer", "explanation"}
    if not required_keys.issubset(mcq.keys()):
        print(f"  ⚠️  Question {idx+1} is missing keys – skipping.")
        return False
    if not isinstance(mcq["options"], dict) or not {"a","b","c","d"}.issubset(mcq["options"]):
        print(f"  ⚠️  Question {idx+1} has malformed options – skipping.")
        return False
    if mcq["answer"].lower() not in {"a", "b", "c", "d"}:
        print(f"  ⚠️  Question {idx+1} has an invalid answer key – skipping.")
        return False
    return True


# ──────────────────────────────────────────────
# 6.  QUIZ RUNNER
# ──────────────────────────────────────────────

def print_separator(char="─", width=60):
    print(char * width)


def run_quiz(mcqs: list):
    """Present each MCQ to the user and evaluate their answers."""
    print_separator("═")
    print("🎓  QUIZ TIME!  Answer each question by typing a, b, c, or d.")
    print_separator("═")

    score = 0
    total = len(mcqs)

    for i, mcq in enumerate(mcqs):
        print(f"\nQ{i+1} / {total}: {mcq['question']}\n")
        for letter in ["a", "b", "c", "d"]:
            print(f"  {letter})  {mcq['options'][letter]}")

        # Get a valid answer from the user
        while True:
            raw = input("\nYour answer (a/b/c/d): ").strip().lower()
            if raw in {"a", "b", "c", "d"}:
                break
            print("  Please type a, b, c, or d.")

        correct = mcq["answer"].lower()

        if raw == correct:
            score += 1
            print("\n✅  Correct!\n")
        else:
            print(f"\n❌  Wrong!  The correct answer was ({correct}) "
                  f"{mcq['options'][correct]}")
            print(f"\n💡  Explanation: {mcq['explanation']}\n")

        print_separator()

    # Final score
    print(f"\n🏆  Quiz complete!  You scored {score} / {total}.")
    pct = round(score / total * 100)
    if pct == 100:
        print("    Perfect score – outstanding! 🎉")
    elif pct >= 80:
        print("    Great job! 👍")
    elif pct >= 60:
        print("    Good effort – review the explanations above to improve.")
    else:
        print("    Keep studying – you'll get there! 📚")


# ──────────────────────────────────────────────
# 7.  MAIN
# ──────────────────────────────────────────────

def main():
    # Step 1: Load model
    tokenizer, model = load_model(MODEL_ID)

    # Step 2: Build the prompt
    prompt = build_prompt(INPUT_TEXT, QUESTION_PATTERN, NUM_QUESTIONS)

    # Step 3: Generate MCQs
    print("⚙️   Generating questions …\n")
    raw_output = generate_mcqs(tokenizer, model, prompt)

    # Step 4: Parse the JSON
    try:
        mcqs_raw = extract_json(raw_output)
    except ValueError as e:
        print(f"\n❌  Error parsing model output:\n{e}")
        return

    # Step 5: Validate and filter
    mcqs = [mcq for i, mcq in enumerate(mcqs_raw) if validate_mcq(mcq, i)]

    if not mcqs:
        print("❌  No valid questions were generated. "
              "Try a different model or adjust your input text.")
        return

    print(f"✅  {len(mcqs)} question(s) generated successfully.\n")

    # Step 6: Run the interactive quiz
    run_quiz(mcqs)


if __name__ == "__main__":
    main()
