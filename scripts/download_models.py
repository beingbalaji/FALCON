"""Download and cache the open models once (about 800 MB), so the first check is fast."""
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from falxon.config import settings

for name in (settings.nli_model, settings.rerank_model):
    print(f"Fetching {name} …")
    AutoTokenizer.from_pretrained(name)
    AutoModelForSequenceClassification.from_pretrained(name)
print("Models ready.")
