import os
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
os.environ["HF_ENDPOINT"] = "https://jnj.artifactrepo.jnj.com/artifactory/api/huggingfaceml/huggingface-co"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HUB_DISABLE_XET"] = "1"

from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "HuggingFaceTB/SmolLM2-360M-Instruct"
TOKEN = os.environ["HF_TOKEN"]
OUTPUT_DIR = Path(__file__).parent / "models" / "SmolVLM-256M-Instruct"


def main():
    from transformers import Idefics3ForConditionalGeneration, AutoProcessor

    print(f"Downloading {MODEL_NAME} to: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading processor...")
    processor = AutoProcessor.from_pretrained(MODEL_NAME, token=TOKEN)
    processor.save_pretrained(OUTPUT_DIR)
    print("  Processor saved.")

    print("Downloading model...")
    model = Idefics3ForConditionalGeneration.from_pretrained(MODEL_NAME, token=TOKEN)
    model.save_pretrained(OUTPUT_DIR)
    print("  Model saved.")

    print(f"\nDone! Model ready at: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
