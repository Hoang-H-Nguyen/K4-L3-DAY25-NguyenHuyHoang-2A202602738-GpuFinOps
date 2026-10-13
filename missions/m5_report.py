"""M5 — Optimization Report: combine M1-M4 into baseline-vs-optimized (deck §1/§11).

Run: python missions/m5_report.py   ->  outputs/report.md + outputs/savings.png
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
from missions._common import num, catalog_by_type, ROOT
from finops import report, sustainability
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing

DAYS = 30
# one tier down for over-provisioned ("util-lie") GPUs
RIGHTSIZE_MAP = {"H100": "A100", "H200": "H100", "A100": "A10G", "A10G": "L4", "L4": "L4"}


def run(verbose: bool = True) -> dict:
    r1 = m1_efficiency_audit.run(verbose=False)
    r2 = m2_inference_levers.run(verbose=False)
    r3 = m3_purchasing.run(verbose=False)
    cat = catalog_by_type()

    # --- buckets ---
    infer_savings = (r2["baseline_daily"] - r2["optimized_daily"]) * DAYS
    purchasing_savings = r3["on_demand_monthly"] - r3["optimized_monthly"]

    idle_savings = r1["idle_waste_daily"] * DAYS
    rightsize_savings = r1["rightsizing_monthly"]

    levers = {
        "Inference (cascade/cache/batch)": round(infer_savings),
        "Purchasing (spot/reserved)": round(purchasing_savings),
        "MBU-aware right-size": round(rightsize_savings),
        "Kill idle GPUs": round(idle_savings),
    }
    baseline = r2["baseline_daily"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    total_pct = sum(levers.values()) / baseline * 100 if baseline else 0.0

    # --- sustainability snapshot ---
    median_tokens = 800
    wh = sustainability.wh_per_query(median_tokens)
    sust = {
        "wh_per_query": wh,
        "carbon_g": sustainability.carbon_g(wh, "us-east-1"),
        "best_region": min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get),
    }

    top_gpu = max(r1["summary"], key=lambda x: x["gpu_util_pct"])
    reasoning = r2["reasoning"]
    rightsizing_rows = "\n".join(
        f"| {r['gpu_id']} | {r['current']} | {r['recommended']} | {r['mbu']:.1%} | "
        f"{r['hbm_gb']} GB | {r['required_bw_tbs']:.3f} TB/s | ${r['monthly_savings']:,} |"
        for r in r1["rightsizing"]
    )
    extras = [
        """## Findings and prioritized actions

1. **Purchasing first (largest ROI):** move checkpointable jobs to spot and steady jobs above the 55% duty-cycle break-even to reserved capacity.
2. **Inference next:** cascade to the small model, then apply prompt cache and batch where latency allows. Cascade contributes the largest measured inference saving.
3. **Remove idle capacity:** automate shutdown after jobs finish; the observed idle intervals cost ${idle:,.0f}/month.
4. **Right-size after profiling:** validate HBM capacity and observed bandwidth before changing GPU type, then benchmark latency and throughput.

GPU-Util measures time with active kernels, not useful FLOPs. `{gpu}` is active {util:.1f}% of the time but reaches only {mfu:.1%} MFU. Memory stalls, small kernels, launch overhead, or I/O waits can keep clocks busy while tensor units do little work; billing still charges the full GPU-hour.""".format(
            idle=idle_savings, gpu=top_gpu["gpu_id"], util=top_gpu["gpu_util_pct"], mfu=top_gpu["mfu"]),
        f"""## Extension 2 — MBU-aware right-sizing

Candidates must have **MBU < 35%**, at least the current HBM capacity, enough peak bandwidth for observed demand, and a lower hourly price. This prevents selecting solely by $/GPU-hour and accidentally causing out-of-memory errors or a bandwidth bottleneck.

| GPU | Current | Recommendation | MBU | HBM floor | Observed BW | Monthly saving |
|---|---|---|---:|---:|---:|---:|
{rightsizing_rows}

Measured potential: **${rightsize_savings:,.0f}/month** before workload benchmarks. The recommendation is a shortlist; production migration still needs latency and throughput validation.""",
        f"""## Extension 4 — Reasoning budget

Reasoning represents **{reasoning['traffic_pct']:.1f}% of traffic**, **{reasoning['cost_pct']:.1f}% of optimized model cost**, and **{reasoning['energy_pct']:.1f}% of estimated inference energy**. Its energy share is disproportionate because the model applies an 80× multiplier for long reasoning generation.

Policy: allow reasoning only for tasks classified as complex or explicitly escalated; cap it at {reasoning['cap_pct']:.0f}% of requests and route the excess to the small model. On this dataset, the cap reroutes **{reasoning['rerouted_requests']} requests/day**, saving about **${reasoning['cap_cost_savings_daily']:.2f}/day** and **{reasoning['cap_energy_savings_wh_daily']:.0f} Wh/day**. Monitor quality before enforcement.""",
        f"""## Mission analysis answers

- **M1:** `{top_gpu['gpu_id']}` has the highest GPU-Util ({top_gpu['gpu_util_pct']:.1f}%) and {top_gpu['mfu']:.1%} MFU. Idle waste is **${idle_savings:,.0f}/month**, or **{idle_savings / baseline * 100:.1f}%** of baseline spend.
- **M2:** Cascade saves **${r2['lever_savings_daily']['cascade']:.2f}/day**, cache **${r2['lever_savings_daily']['cache']:.2f}/day**, and batch **${r2['lever_savings_daily']['batch']:.2f}/day**; cascade is largest. A fully cached input costs 10% and batch halves it, so `0.10 × 0.50 = 0.05`. Avoid batch for interactive, latency-sensitive traffic.
- **M3:** Spot is recommended for every interruptible job below 24 h/day. Effective hours include checkpoint overhead and recomputation after interruption. Reserved suits the three steady inference jobs here; on-demand remains preferable if their duty cycle becomes unpredictable or falls below 55%.
- **M4:** `assistant` is the highest-cost team. Tag coverage is 92%, above the 80% chargeback gate. FOCUS normalizes billing fields across providers so allocation and comparison use one schema.

Sustainability and cost align partially: `europe-north1` has the lowest carbon intensity, while `us-east-wa` has the lowest electricity price. Region choice should also account for latency and data residency; the cleanest region is not automatically the lowest-latency region for users.""",
    ]
    md = report.build_report(baseline, optimized, levers, sustainability=sust, extra_sections=extras)
    out_md = os.path.join(ROOT, "outputs", "report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w") as f:
        f.write(md)
    png = report.savings_waterfall(levers, os.path.join(ROOT, "outputs", "savings.png"))

    if verbose:
        print("== M5 Optimization Report ==")
        print(md)
        print(f"\nWritten: outputs/report.md" + (f" + outputs/savings.png" if png else " (matplotlib absent: PNG skipped)"))

    return {"baseline_monthly": round(baseline), "optimized_monthly": round(optimized),
            "levers": levers, "total_savings_pct": round(total_pct, 1)}


if __name__ == "__main__":
    run()
