"""Latih model Decision Tree dari ai/data/dataset.csv.

    python -m ai.train

Hasil: ai/model.joblib (dipakai detector.py) dan ai/report.txt (akurasi,
confusion matrix, aturan pohon, untuk dokumentasi/PPT).
"""
import argparse
import csv
import time
from collections import Counter

import joblib
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.tree import DecisionTreeClassifier, export_text

from ai.features import FEATURES


def load(path: str):
    X, y = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            X.append([float(row[n]) for n in FEATURES])
            y.append(row["label"])
    return np.array(X), np.array(y)


def new_model() -> DecisionTreeClassifier:
    # pohon dangkal: mudah dijelaskan dan tidak terlalu menghafal data
    return DecisionTreeClassifier(max_depth=4, min_samples_leaf=3,
                                  class_weight="balanced", random_state=42)


def train(X, y):
    """Latih, evaluasi, dan kembalikan (model_final, teks_laporan)."""
    counts = Counter(y)
    if len(counts) < 2:
        raise SystemExit("Butuh minimal 2 label berbeda di dataset.")
    min_count = min(counts.values())
    lines = [f"Jumlah data: {len(y)}", "Data per kelas: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    if min_count < 3:
        print("PERINGATAN: ada kelas dengan data < 3 baris. Tambah data supaya evaluasi bermakna.")

    stratify = y if min_count >= 4 else None
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=stratify, random_state=42)
    ev = new_model().fit(Xtr, ytr)
    pred = ev.predict(Xte)
    labels = sorted(counts)
    acc = float((pred == yte).mean())
    lines += ["", f"Data latih/uji: {len(ytr)}/{len(yte)}", f"Akurasi data uji: {acc * 100:.1f}%", "",
              "Laporan per kelas:", classification_report(yte, pred, labels=labels, zero_division=0),
              "Confusion matrix (baris = sebenarnya, kolom = prediksi):", "kelas: " + ", ".join(labels),
              str(confusion_matrix(yte, pred, labels=labels))]
    if min_count >= 2:
        k = min(5, min_count)
        cv = cross_val_score(new_model(), X, y, cv=StratifiedKFold(k, shuffle=True, random_state=42))
        lines += ["", f"Cross-validation {k}-fold: {cv.mean() * 100:.1f}% (+/- {cv.std() * 100:.1f})"]

    final = new_model().fit(X, y)
    imp = sorted(zip(FEATURES, final.feature_importances_), key=lambda p: -p[1])
    lines += ["", "Pentingnya fitur:"] + [f"  {n:<14} {v:.3f}" for n, v in imp]
    lines += ["", "Aturan pohon keputusan:", export_text(final, feature_names=FEATURES)]
    return final, "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ai/data/dataset.csv")
    ap.add_argument("--out", default="ai/model.joblib")
    ap.add_argument("--report", default="ai/report.txt")
    args = ap.parse_args()

    X, y = load(args.data)
    model, report = train(X, y)
    joblib.dump({"model": model, "features": FEATURES, "n_samples": len(y),
                 "trained_at": time.strftime("%Y-%m-%d %H:%M:%S")}, args.out)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\nModel disimpan ke {args.out}, laporan ke {args.report}")


if __name__ == "__main__":
    main()
