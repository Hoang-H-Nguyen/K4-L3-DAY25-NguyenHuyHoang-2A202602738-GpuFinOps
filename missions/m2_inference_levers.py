"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing
from finops import sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = cascade_cost = cache_cost = opt_cost = 0.0
    total_tokens = 0
    reasoning_cost = regular_cost = reasoning_wh = regular_wh = 0.0
    reasoning_count = 0
    request_details = []
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        cascade_cost += pricing.request_cost(inp, out, pin, pout)
        cache_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached)
        cost = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        opt_cost += cost
        is_reasoning = bool(int(num(r["is_reasoning"])))
        wh = sustainability.wh_per_query(inp + out, is_reasoning=is_reasoning)
        if is_reasoning:
            reasoning_count += 1
            reasoning_cost += cost
            reasoning_wh += wh
        else:
            regular_cost += cost
            regular_wh += wh
        request_details.append((is_reasoning, cost, inp, out, cached, is_batch))

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0
    lever_savings = {
        "cascade": base_cost - cascade_cost,
        "cache": cascade_cost - cache_cost,
        "batch": cache_cost - opt_cost,
    }

    # Extension 4: cap reasoning at 5% of requests. The excess is routed to
    # the small model without the 80x reasoning energy multiplier.
    cap_pct = 5.0
    cap_count = int(len(rows) * cap_pct / 100)
    excess = max(0, reasoning_count - cap_count)
    reasoning_rows = [d for d in request_details if d[0]]
    rerouted = sorted(reasoning_rows, key=lambda d: d[1], reverse=True)[:excess]
    cap_cost_savings = cap_wh_savings = 0.0
    sin, sout = MODEL_PRICES["small"]
    for _, old_cost, inp, out, cached, is_batch in rerouted:
        tokens = inp + out
        new_cost = pricing.request_cost(inp, out, sin, sout, min(cached, inp), batch=is_batch)
        cap_cost_savings += max(0.0, old_cost - new_cost)
        cap_wh_savings += sustainability.wh_per_query(tokens, is_reasoning=True) - sustainability.wh_per_query(tokens)

    reasoning = {
        "traffic_pct": reasoning_count / len(rows) * 100 if rows else 0.0,
        "cost_pct": reasoning_cost / opt_cost * 100 if opt_cost else 0.0,
        "energy_pct": reasoning_wh / (reasoning_wh + regular_wh) * 100 if reasoning_wh + regular_wh else 0.0,
        "cost_daily": reasoning_cost, "energy_wh_daily": reasoning_wh,
        "cap_pct": cap_pct, "rerouted_requests": excess,
        "cap_cost_savings_daily": cap_cost_savings, "cap_energy_savings_wh_daily": cap_wh_savings,
    }

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print("lever contribution ($/day): " + ", ".join(f"{k}=${v:.2f}" for k, v in lever_savings.items()))
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print(f"reasoning : {reasoning['traffic_pct']:.1f}% traffic, {reasoning['cost_pct']:.1f}% cost, "
              f"{reasoning['energy_pct']:.1f}% energy")
        print(f"{cap_pct:.0f}% cap    : reroute {excess} requests, save ${cap_cost_savings:.2f}/day "
              f"and {cap_wh_savings:.0f} Wh/day")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "lever_savings_daily": {k: round(v, 2) for k, v in lever_savings.items()},
        "reasoning": {k: round(v, 2) if isinstance(v, float) else v for k, v in reasoning.items()},
    }


if __name__ == "__main__":
    run()
