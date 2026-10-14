# Eval report

Model: `hosted_vllm/Qwen/Qwen2.5-7B-Instruct` · 70 cases · 102.9 s

| metric | value |
|---|---|
| cases | 70 |
| route_accuracy | 0.929 |
| finding_set_exact | 0.829 |
| unsafe_misses | 5 |
| over_holds | 0 |
| injection_flagged | 5/5 |
| extraction_field_accuracy | 0.977 |
| template_notes | 0 |
| unfaithful_notes | 0 |
| judge_unparsed | 0 |
| seconds_total | 102.9 |
| gates_failed | ['unsafe_misses', 'route_accuracy'] |

## Misrouted or mismatched cases

- D-5056 (hard_trade_terms): route officer_review (want officer_review), findings ['missing_invoice'] (want [])
- D-5057 (hard_trade_terms): route officer_review (want officer_review), findings ['missing_invoice'] (want [])
- D-5058 (hard_trade_terms): route officer_review (want officer_review), findings ['missing_invoice'] (want [])
- D-5059 (hard_trade_terms): route officer_review (want officer_review), findings ['missing_invoice'] (want [])
- D-5060 (hard_trade_terms): route officer_review (want officer_review), findings ['missing_invoice'] (want [])
- D-5062 (hard_ocr_noise): route officer_review (want officer_review), findings ['missing_invoice', 'missing_lien_waiver'] (want [])
- D-5065 (hard_ocr_noise): route officer_review (want officer_review), findings ['missing_lien_waiver'] (want [])
- D-5066 (hard_repeat_spaced): route officer_review (want hold), findings [] (want ['repeat_invoice'])
- D-5067 (hard_repeat_spaced): route officer_review (want hold), findings [] (want ['repeat_invoice'])
- D-5068 (hard_repeat_spaced): route officer_review (want hold), findings [] (want ['repeat_invoice'])
- D-5069 (hard_repeat_spaced): route officer_review (want hold), findings [] (want ['repeat_invoice'])
- D-5070 (hard_repeat_spaced): route officer_review (want hold), findings [] (want ['repeat_invoice'])

_Baseline before the fixes in commit "Fix three defects the hard eval set found": same 70 cases, same model._
