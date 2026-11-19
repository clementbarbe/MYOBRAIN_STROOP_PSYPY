#!/usr/bin/env python3
"""Independent numerical audit of the supplied plans, not an SPM estimation.

Three 2-second box regressors convolved with a unit-area double-gamma HRF
(positive shape 6, negative shape 16 / 6, kernel 32 s), oversampled at 10 ms.
Sample at mid-TR, add constant + DCT drift terms (128 s high pass) and whiten
with a specified stationary AR(1) covariance. No motion/physiology/error regressors.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.signal import fftconvolve
from scipy.stats import gamma

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.stroop_designs import DESIGNS, load_design, design_path, acquisition_timing

CONDITIONS = ('congruent', 'incongruent', 'neutral')
CONTRASTS = {'I-C': np.array([-1., 1., 0.]),
             'I-N': np.array([0., 1., -1.]), 'C-N': np.array([1., 0., -1.])}


def regressors(rows, tr, shape=6, dt=.01):
    timing = acquisition_timing(rows, tr)
    n = timing['n_volumes']
    grid = np.arange(0, timing['acquisition_duration'] + 32 + dt, dt)
    htime = np.arange(0, 32 + dt / 2, dt)
    hrf = gamma.pdf(htime, shape) - gamma.pdf(htime, 16) / 6
    hrf /= hrf.sum() * dt
    scans = np.arange(n) * tr + tr / 2
    columns = []
    for condition in CONDITIONS:
        box = np.zeros(len(grid))
        for trial in rows:
            if trial['condition'] == condition:
                a = int(round(trial['onset'] / dt))
                b = int(round((trial['onset'] + trial['duration']) / dt))
                box[a:b] += 1
        response = fftconvolve(box, hrf)[:len(grid)] * dt
        columns.append(np.interp(scans, grid, response))
    return np.column_stack(columns), timing


def model_metrics(task, tr, rho=.3):
    n = len(task)
    # The constant and the low-frequency DCT terms are explicit nuisance columns.
    n_dct = int(np.floor(2 * n * tr / 128))
    nuisance = np.column_stack([np.ones(n)] + [
        np.cos(np.pi * (np.arange(n) + .5) * k / n) for k in range(1, n_dct + 1)])
    full = np.column_stack([task, nuisance])
    whitened = full.copy()
    whitened[1:] = (full[1:] - rho * full[:-1]) / np.sqrt(1 - rho ** 2)
    q, _ = np.linalg.qr(whitened[:, 3:], mode='reduced')
    residual_task = whitened[:, :3] - q @ (q.T @ whitened[:, :3])
    info = residual_task.T @ residual_task
    inverse = np.linalg.inv(info)
    norm = np.sqrt(np.diag(info))
    correlation = info / np.outer(norm, norm)
    vif = np.diag(np.linalg.inv(correlation))
    return {
        'n_scans': n, 'n_columns': full.shape[1],
        'rank': int(np.linalg.matrix_rank(whitened)),
        'residual_task_rank': int(np.linalg.matrix_rank(residual_task)),
        'standardized_task_condition_number': float(np.linalg.cond(residual_task / norm)),
        'residual_task_correlations': correlation.tolist(),
        'vif_C_I_N': vif.tolist(),
        'contrast_variance_factors': {name: float(c @ inverse @ c) for name, c in CONTRASTS.items()},
        'contrast_efficiencies_arbitrary_units': {
            name: float(1 / (c @ inverse @ c)) for name, c in CONTRASTS.items()},
    }, full


def audit(design, tr):
    rows = load_design(design)
    nominal_task, timing = regressors(rows, tr)
    metrics, matrix = model_metrics(nominal_task, tr)
    robust = []
    for shape in (5, 6, 7):
        task, _ = regressors(rows, tr, shape)
        for rho in (.1, .3, .6):
            check, _ = model_metrics(task, tr, rho)
            robust.append({'positive_hrf_shape': shape, 'ar1_rho': rho,
                           'rank': check['rank'], 'n_columns': check['n_columns'],
                           'I-C_variance_factor': check['contrast_variance_factors']['I-C'],
                           'max_vif': max(check['vif_C_I_N'])})
    colors = {condition: dict(Counter(t['ink_color'] for t in rows if t['condition'] == condition))
              for condition in CONDITIONS}
    inc = Counter(f'{t["word"]}:{t["ink_color"]}' for t in rows if t['condition'] == 'incongruent')
    result = {
        'design': design, 'source_file': design_path(design).name,
        'source_sha256': hashlib.sha256(design_path(design).read_bytes()).hexdigest(),
        'counts': dict(Counter(t['condition'] for t in rows)),
        'colors_by_condition': colors, 'incongruent_pairs': dict(inc),
        'timing': timing, 'nominal_model': metrics, 'sensitivity_models': robust,
    }
    return result, matrix


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tr', type=float, default=1.23)
    ap.add_argument('--output', type=Path, default=Path('analysis/glm_audit_2026-11-18'))
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'model': __doc__, 'limitations': [
        'Independent approximation, not a reproduction of SPM microtime/REML estimation.',
        'Not a validation of the claimed 2000-candidate optimization; generator and QC files unavailable.',
        'No observed BOLD noise, motion, physiology or error regressors; no power guarantee.',
    ], 'runs': []}
    for design in DESIGNS:
        result, matrix = audit(design, args.tr)
        report['runs'].append(result)
        np.savez_compressed(args.output / f'{design}_design_matrix.npz', X=matrix,
                            condition_order=np.array(CONDITIONS))
        m = result['nominal_model']
        print(f'{design}: rank {m["rank"]}/{m["n_columns"]}; '
              f'VIF {np.round(m["vif_C_I_N"], 3)}; '
              f'I-C variance {m["contrast_variance_factors"]["I-C"]:.5f}; '
              f'condition number {m["standardized_task_condition_number"]:.3f}')
        print('  residual correlations', np.round(m['residual_task_correlations'], 3).tolist())
    path = args.output / 'glm_audit.json'
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Saved: {path}')


if __name__ == '__main__':
    main()
