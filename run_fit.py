import json, sys
from pathlib import Path
sys.path.insert(0, "src")
import pandas as pd
from mmm.simulate import simulate, true_roi
from mmm.config import BASELINE
from mmm.model import fit, recovery_report, rank_agreement, roi_rank_correlation, signal_to_noise

frame = simulate()
Path("data").mkdir(exist_ok=True)
frame.to_parquet("data/simulated_mmm.parquet", index=False)

model = fit(frame)
report = recovery_report(model, frame, true_roi(frame))
Path("reports").mkdir(exist_ok=True)
report.to_csv("reports/roi_recovery.csv", index=False)

pd.set_option("display.width", 220)
print(report[["channel","spend","true_roi","estimated_roi","roi_error","roi_error_pct","true_rank","estimated_rank"]].round(4).to_string(index=False))
print()
snr = signal_to_noise(frame, BASELINE.noise_sd)
snr.to_csv("reports/signal_to_noise.csv", index=False)
print()
print(snr.round(4).to_string(index=False))
print()
print("rank agreement (exact): %.2f" % rank_agreement(report))
print("ROI rank correlation  : %.3f" % roi_rank_correlation(report))
print("mean absolute ROI error: %.4f" % report.roi_error.abs().mean())

identifiable = report[report.channel != "affiliate"]
print()
print("--- excluindo o canal nao identificavel (affiliate, SNR 0.03):")
print("ROI rank correlation  : %.3f" % roi_rank_correlation(identifiable))
print("mean absolute ROI error: %.4f" % identifiable.roi_error.abs().mean())
print("mean ROI error pct    : %.1f%%" % (100*identifiable.roi_error_pct.abs().mean()))
model.save("models_mmm.nc")
