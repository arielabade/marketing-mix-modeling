"""Load the fitted model and reallocate the budget. No refit."""
import sys
from pathlib import Path
sys.path.insert(0, "src")

import pandas as pd
from pymc_marketing.mmm import MMM

from mmm.model import optimise_budget
from mmm.simulate import simulate, true_roi

frame = simulate()
model = MMM.load("models_mmm.nc")
allocation = optimise_budget(model, frame)

Path("reports").mkdir(exist_ok=True)
allocation.to_csv("reports/budget_allocation.csv", index=False)

pd.set_option("display.width", 200)
print(allocation.to_string(index=False))
print()
print("true ROI ordering, for reference:")
print(true_roi(frame)[["channel", "roi"]].round(4).to_string(index=False))
