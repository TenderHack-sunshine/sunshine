# Error Analysis

Generated from:

- `artifacts/rule_based/test_false_positives_top20.csv`
- `artifacts/rubert_tiny_toxicity/test_false_positives_top20.csv`
- `artifacts/rubert_tiny_toxicity/test_false_negatives_top20.csv`
- `artifacts/fine_tuned_rubert_tiny2/test_false_negatives_top20.csv`

The fine-tuned model has 0 test false positives, so false-positive analysis uses the available baseline errors. The rule-based model has 0 test false negatives. The toxicity baseline has 17 test false negatives and the fine-tuned model has 18 test false negatives; together this gives 35 false-negative examples for analysis.

## False Positives

20 rule-based false positives:

- 13 `hard_negative_emotional_or_insult`
- 4 `gibberish_keyboard_smash`
- 3 `clean_support`
- Main transformations: `natural_paraphrase`, `uppercase_or_emphasis`, `gibberish_suffix`, `pure_gibberish`

20 toxicity-baseline false positives:

- 15 `hard_negative_emotional_or_insult`
- 5 `gibberish_keyboard_smash`
- Main transformations: `uppercase_or_emphasis`, `pure_gibberish`, `gibberish_suffix`, `gibberish_prefix`, `gibberish_with_support_context`, `natural_paraphrase`

Interpretation:

- Both baselines confuse emotional aggression, insults, shouting, and noisy keyboard-like text with actual obscene lexemes.
- Rule-based threshold selection under the required recall constraint selects threshold `0.0`, causing every clean test example to be classified positive.
- The toxicity model is sensitive to general toxicity, not only obscenity, which explains many hard-negative false positives.

## False Negatives

17 toxicity-baseline false negatives:

- 14 `obscenity_obfuscated`
- 3 `obscenity_with_gibberish_noise`
- Main transformations: `spaced_letters`, `alternate_spelling`, `masked_symbols`, `gibberish_suffix`, `gibberish_inside_context`

18 fine-tuned false negatives:

- 18 `obscenity_with_gibberish_noise`
- Main transformations: `gibberish_prefix`, `gibberish_inside_context`, `gibberish_after_obscenity`

Interpretation:

- The toxicity baseline misses separated letters and masked or alternate spellings.
- The fine-tuned model handles explicit, masked, mixed-alphabet, and spaced examples well, but misses cases where random noise surrounds or interrupts the obscene lexeme.
- The selected fine-tuned threshold maximizes precision under the validation recall constraint, so remaining test false negatives are the expected tradeoff for zero false positives on this test split.
