# NimbusAI — GPU Cost Optimization Report

- **Period:** monthly
- **Baseline spend:** $27,133
- **Optimized spend:** $13,971
- **Projected savings:** $13,162 (**49%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,212 |
| Purchasing (spot/reserved) | $10,040 |
| MBU-aware right-size | $1,310 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Cheapest+cleanest region: europe-north1

## Findings and prioritized actions

1. **Purchasing first (largest ROI):** move checkpointable jobs to spot and steady jobs above the 55% duty-cycle break-even to reserved capacity.
2. **Inference next:** cascade to the small model, then apply prompt cache and batch where latency allows. Cascade contributes the largest measured inference saving.
3. **Remove idle capacity:** automate shutdown after jobs finish; the observed idle intervals cost $600/month.
4. **Right-size after profiling:** validate HBM capacity and observed bandwidth before changing GPU type, then benchmark latency and throughput.

GPU-Util measures time with active kernels, not useful FLOPs. `gpu-h100-4` is active 98.2% of the time but reaches only 19.4% MFU. Memory stalls, small kernels, launch overhead, or I/O waits can keep clocks busy while tensor units do little work; billing still charges the full GPU-hour.

## Extension 2 — MBU-aware right-sizing

Candidates must have **MBU < 35%**, at least the current HBM capacity, enough peak bandwidth for observed demand, and a lower hourly price. This prevents selecting solely by $/GPU-hour and accidentally causing out-of-memory errors or a bandwidth bottleneck.

| GPU | Current | Recommendation | MBU | HBM floor | Observed BW | Monthly saving |
|---|---|---|---:|---:|---:|---:|
| gpu-h100-4 | H100 | A100 | 20.7% | 80 GB | 0.692 TB/s | $511 |
| gpu-h100-5 | H100 | A100 | 27.1% | 80 GB | 0.908 TB/s | $511 |
| gpu-a10g-0 | A10G | L4 | 23.5% | 24 GB | 0.141 TB/s | $144 |
| gpu-a10g-1 | A10G | L4 | 30.2% | 24 GB | 0.181 TB/s | $144 |

Measured potential: **$1,310/month** before workload benchmarks. The recommendation is a shortlist; production migration still needs latency and throughput validation.

## Extension 4 — Reasoning budget

Reasoning represents **8.4% of traffic**, **16.5% of optimized model cost**, and **94.0% of estimated inference energy**. Its energy share is disproportionate because the model applies an 80× multiplier for long reasoning generation.

Policy: allow reasoning only for tasks classified as complex or explicitly escalated; cap it at 5% of requests and route the excess to the small model. On this dataset, the cap reroutes **81 requests/day**, saving about **$1.20/day** and **14314 Wh/day**. Monitor quality before enforcement.

## Mission analysis answers

- **M1:** `gpu-h100-4` has the highest GPU-Util (98.2%) and 19.4% MFU. Idle waste is **$600/month**, or **2.2%** of baseline spend.
- **M2:** Cascade saves **$37.40/day**, cache **$1.20/day**, and batch **$1.79/day**; cascade is largest. A fully cached input costs 10% and batch halves it, so `0.10 × 0.50 = 0.05`. Avoid batch for interactive, latency-sensitive traffic.
- **M3:** Spot is recommended for every interruptible job below 24 h/day. Effective hours include checkpoint overhead and recomputation after interruption. Reserved suits the three steady inference jobs here; on-demand remains preferable if their duty cycle becomes unpredictable or falls below 55%.
- **M4:** `assistant` is the highest-cost team. Tag coverage is 92%, above the 80% chargeback gate. FOCUS normalizes billing fields across providers so allocation and comparison use one schema.

Sustainability and cost align partially: `europe-north1` has the lowest carbon intensity, while `us-east-wa` has the lowest electricity price. Region choice should also account for latency and data residency; the cleanest region is not automatically the lowest-latency region for users.

_Figures are June-2026 as-of snapshots; re-baseline before acting._