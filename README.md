# Marketing Mix Modeling

A Bayesian MMM with adstock and saturation — and, unusually, a way to tell whether it worked.

---

## 1. Business problem

A business spends across TV, search, social and affiliate, and wants to know how much revenue each
channel actually caused, so the next unit of budget goes to the right place.

The difficulty is structural: incremental contribution is never observed. On real data an MMM's
output can be inspected but not scored. Everyone sees the same decomposition chart and nobody can say
whether it is right.

---

## 2. Key results

**The model is fitted against a process whose true parameters are written down**, so its estimates can
be checked against an answer key rather than against intuition.

| Channel | True ROI | Estimated ROI | Error | True rank | Estimated rank |
| --- | --- | --- | --- | --- | --- |
| tv | 0.717 | 1.012 | +41.2% | 1 | 2 |
| search | 0.689 | 0.812 | +17.9% | 2 | 3 |
| social | 0.389 | 0.324 | −16.7% | 3 | 4 |
| **affiliate** | **0.173** | **1.271** | **+636.5%** | **4** | **1** |

Read the overall numbers and the model looks broken: ROI rank correlation of **−0.200**, mean absolute
ROI error of **0.396**. It places the worst channel first.

**Drop the one channel it could never have measured and the picture inverts:**

| | Including affiliate | Excluding affiliate |
| --- | --- | --- |
| ROI rank correlation | −0.200 | **1.000** |
| Mean absolute ROI error | 0.396 | **0.161** |
| Mean relative ROI error | — | 25.3% |

**The ordering is perfect for every channel that carries signal.** The ranking collapses because of a
single channel, and a diagnostic computed *before* fitting says which one:

| Channel | Share of revenue | Signal-to-noise |
| --- | --- | --- |
| tv | 22.6% | 0.88 |
| search | 14.5% | 0.45 |
| social | 6.2% | 0.30 |
| **affiliate** | **1.2%** | **0.04** |

Affiliate's weekly contribution varies by about **4% of the weekly revenue noise**. There is no
information in the data about its ROI, so the model returns something close to its prior — and
returns it with the same confident posterior interval as everything else.

### What the error costs, concretely

Feeding the fitted model into the budget optimiser makes the consequence unambiguous:

| Channel | True ROI rank | Current weekly | Recommended | Change |
| --- | --- | --- | --- | --- |
| tv | 1 | 26,174 | 17,893 | **−31.6%** |
| search | 2 | 20,974 | 17,893 | −14.7% |
| social | 3 | 12,121 | 17,893 | +47.6% |
| **affiliate** | **4 (worst)** | 5,590 | 11,181 | **+100%, at the bound** |

**The optimiser doubles spend on the worst channel**, and only the 200% cap stops it going further.
The three measurable channels converge to near-equal spend, which is the optimiser correctly
equalising marginal returns — the machinery works. It is fed one number it should never have been
given.

**The decision this supports.** Before trusting any MMM, compute the signal-to-noise ratio per
channel. A channel below roughly 0.1 cannot be measured by this method at this sample size, and it
should be **pinned to its current spend and excluded from the optimisation**, not argued about in a
meeting. Measuring a small channel needs a geo experiment or a holdout test, not a bigger model.

**On the sampler, and why it is the same finding.** The first fit, at the default `target_accept`,
produced **93 divergences**. Raising it to 0.95 cut them to **22**. Divergences mean the chains could
not explore parts of the posterior, so the intervals are not trustworthy.

Tuning the sampler further would be treating the symptom. A parameter the likelihood carries no
information about is pinned only by its prior, which leaves a flat ridge in the posterior that NUTS
cannot traverse — and the unmeasurable channel is exactly such a parameter. **The divergences and the
636% ROI error on affiliate have the same cause.** The fix is to take the channel out of the model,
not to make the sampler work harder at exploring a direction the data never constrained.

---

## 3. Data

**SIMULATED, deliberately, and no real company's data appears anywhere in this repository.**

The generating process is in [`src/mmm/config.py`](src/mmm/config.py): per-channel adstock rates,
saturation steepness, peak contribution, the weekly media plan, and a baseline with trend,
seasonality and noise.

| | |
| --- | --- |
| Period | 104 weeks (two years), weekly |
| Channels | tv, search, social, affiliate |
| Media share of revenue | 44% — the rest is baseline the model must not claim |
| Baseline | intercept + linear trend + yearly seasonality + Gaussian noise |

The model receives exactly what a client's data team can hand over: dates, weekly spend per channel,
weekly revenue. It never sees the adstock rates, the saturation curves, the baseline, or the
per-channel contributions.

The baseline carries trend and seasonality on purpose. Without them, the test would be a softball: a
model that attributes seasonal strength to whichever channel happened to spend during it would still
look accurate.

---

## 4. Approach

**Geometric adstock, then logistic saturation**, matching the simulation's functional form. If the
simulation used a different form, "recovery" would be measuring specification error rather than
estimation quality — a separate and more pessimistic experiment.

**Yearly seasonality in the model**, because it is in the business. Omitting it is the most common way
an MMM flatters a channel: spend concentrated in the strong season gets credited with the season.

**Signal-to-noise as a pre-fit diagnostic.** Computed here from the simulation's true contributions.
The real-world equivalent is the ratio of a channel's spend variation to unexplained revenue variance,
and it answers the question that should be asked before fitting: is there enough signal for the model
to say anything, or will it return the prior dressed as a finding?

**Rank correlation rather than exact rank matching.** The decision is where the next pound goes, so
what matters is whether the ordering survives, not whether each channel lands on its exact position.

**Bounded budget optimisation.** An unconstrained optimiser will move 90% of spend into one channel.
No media team implements that, and the saturation curve is least trustworthy exactly where no data was
observed, so each channel is bounded to between 40% and 200% of its current spend.

---

## 5. Business metrics

```
adstock(spend, alpha)   carryover: each week keeps a decaying share of earlier spend
saturation(x, lambda)   (1 - exp(-lambda*x)) / (1 + exp(-lambda*x))
contribution            beta * saturation(adstock(spend))
ROI                     incremental contribution / spend
signal_to_noise         sd(weekly contribution) / sd(weekly revenue noise)
```

| Assumption | Value |
| --- | --- |
| Carryover (adstock alpha) | tv 0.70 · social 0.35 · search 0.15 · affiliate 0.05 |
| Budget bounds | 40% to 200% of current channel spend |
| Optimisation horizon | 13 weeks |

---

## 6. Limitations and next steps

- **The data is simulated.** No conclusion about any real channel's ROI can be drawn from this. What
  transfers is the method and the diagnostic, not the numbers.
- **The model knows the right functional form.** The simulation and the model share geometric adstock
  and logistic saturation, so this measures estimation under a correct specification. Real campaigns
  do not come with their functional form attached, and a mis-specification study would give a harsher
  and more honest number.
- **25% average ROI error on the identifiable channels is not precision.** It is enough to rank
  channels and to size a reallocation; it is not enough to defend a claim like "TV returns exactly
  0.72". Note the direction: both large channels are over-estimated, which is what happens when the
  unmeasurable channel absorbs variance the model then has to redistribute.
- **Correlation is not causation, even here.** An MMM infers from observed covariation. It cannot
  separate a channel that drives demand from one that is switched on when demand is already rising.
  Only a geo holdout or a randomised experiment can, which is what
  [ab-testing-toolkit](https://github.com/arielabade/ab-testing-toolkit) addresses.
- **Twenty-two divergences remain**, and raising `target_accept` again would not be the right answer:
  the ridge comes from a parameter the data does not identify. Dropping affiliate from the model, or
  giving it a tightly informative prior, is the principled fix.
- **Next step:** run the same recovery test with a mis-specified saturation curve, and report how much
  of the 25% error is estimation versus specification. That is the number a practitioner actually
  needs, and this result is its optimistic floor.

---

## 7. How to run

```bash
git clone https://github.com/arielabade/marketing-mix-modeling
cd marketing-mix-modeling

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python run_fit.py        # simulate, fit, and score recovery against the truth
python run_optimise.py   # reallocate the budget using the fitted curves
pytest                   # 13 tests
```

Sampling takes several minutes: four chains, 2,000 tuning steps, `target_accept = 0.95`.

### Layout

```
src/mmm/config.py     the known generating process and the optimisation bounds
src/mmm/simulate.py   adstock, saturation, and the dataset
src/mmm/model.py      the MMM, ROI recovery, signal-to-noise, budget optimisation
tests/                adstock and saturation properties, and the diagnostic
reports/              roi_recovery.csv, signal_to_noise.csv, budget_allocation.csv
```
