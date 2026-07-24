from sentence_transformers import CrossEncoder

model = CrossEncoder('cross-encoder/nli-deberta-v3-base')
pairs = [
    ("A man is playing guitar.", "A man is playing an instrument."), # Entailment
    ("A man is playing guitar.", "A woman is eating a sandwich."),   # Contradiction
    ("A man is playing guitar.", "The man is wearing a red shirt.")  # Neutral
]
scores = model.predict(pairs, apply_softmax=True)
print("Entailment pair:", scores[0])
print("Contradiction pair:", scores[1])
print("Neutral pair:", scores[2])
