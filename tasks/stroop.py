"""
Stroop Color-Word Task (French) — manual response.

SEQUENCE CONSTRUCTION
---------------------
The whole run is built BEFORE the scanner trigger, in three steps:

 1. Run-level balanced pools
       ink colours .............. equal counts across the run (+/-1)
       incongruent word/ink ..... the 6 pairs equally used (+/-1)
       neutral words ............ the 12 abstract words equally used (+/-1)
 2. Deal the pools to the blocks
 3. Enforce ordering constraints inside each block
       no more than 2 consecutive identical ink colours
       no more than 2 consecutive identical words
       event design: never 2 consecutive trials of the same type

Every constraint is then re-checked by tasks.utils.validation and the
report is written to <stem>_design.json. Nothing is generated during
the run itself, so no CPU spike can perturb the timing.

COLOR GUIDE
-----------
The 3 coloured circles appear only during the ITI and the rest periods,
and always vanish `indicator_hide_lead` seconds before a stimulus.
"""

from __future__ import annotations

import random
from collections import defaultdict

from psychopy import visual

from tasks.base import BaseTask
from tasks.registry import register_task
from tasks.utils.pools import (
    balanced_pool, deal_to_blocks, enforce_max_run,
    interleave_no_repeat, counts, max_run_length,
)
from tasks.utils.validation import (
    ValidationReport, check_balanced, check_max_run, check_exact,
)
from utils.console import SYM_OK, SYM_ERR

MAX_SAME_COLOR = 2
MAX_SAME_WORD = 2


@register_task('stroop')
class StroopTask(BaseTask):
    """Stroop Color-Word fMRI task."""

    TASK_NAME = 'stroop'
    PREGENERATE_TRIALS = True          # build everything before the trigger

    # ═════════════════════════════════════════════════════════════════
    # SETUP
    # ═════════════════════════════════════════════════════════════════

    def _setup_stimuli(self) -> None:
        cfg = self.task_config
        stim_cfg = cfg.get('stimulus', {})

        self._word_stim = visual.TextStim(
            self.win, text='', color='white',
            height=stim_cfg.get('word_height', 0.15),
            pos=(0, 0), bold=True, font='monospace',
        )

        colors = cfg.get('colors', {})
        self._color_rgb = {
            'rouge': colors.get('rouge', [1.0, -1.0, -1.0]),
            'bleu':  colors.get('bleu',  [-1.0, -1.0, 1.0]),
            'vert':  colors.get('vert',  [-1.0, 0.8, -1.0]),
        }
        self._ink_colors = list(self._color_rgb.keys())

        cw = cfg.get('color_words', {})
        self._color_words = {
            'rouge': cw.get('rouge', 'ROUGE'),
            'bleu':  cw.get('bleu',  'BLEU'),
            'vert':  cw.get('vert',  'VERT'),
        }
        self._neutral_words = list(cfg.get('neutral_words', [
            'IDEE', 'ACTE', 'FAIT', 'AVIS', 'SENS', 'ETAT',
            'CAUSE', 'ORDRE', 'THEME', 'DEBUT', 'TERME', 'DROIT',
        ]))

        pairs = cfg.get('incongruent_pairs', [])
        self._inc_pairs = (
            [(p['word'], p['ink']) for p in pairs] if pairs else
            [(self._color_words[w], i)
             for w in self._ink_colors
             for i in self._ink_colors if w != i]
        )

        key_src = ('response_keys_fmri' if self.settings.mode == 'fmri'
                   else 'response_keys_pc')
        keys = cfg.get(key_src, {})
        self._color_to_key = {
            'rouge': keys.get('rouge', 'left'),
            'bleu':  keys.get('bleu',  'down'),
            'vert':  keys.get('vert',  'right'),
        }
        self._key_to_color = {v: k for k, v in self._color_to_key.items()}
        self._valid_keys = list(self._color_to_key.values())

        # ── Colour guide ─────────────────────────────────────────────
        self._indicators = []
        self._hide_lead = float(cfg.get('indicator_hide_lead', 2.0))
        self._next_stim_time: float | None = None
        self._guide_enabled = True

        if cfg.get('show_indicators', True):
            r = cfg.get('indicator_radius', 0.028)
            y = cfg.get('indicator_y', -0.82)
            sp = cfg.get('indicator_spacing', 0.22)
            order = cfg.get('indicator_order', ['rouge', 'bleu', 'vert'])
            x0 = -sp * (len(order) - 1) / 2.0
            for i, c in enumerate(order):
                self._indicators.append(visual.Circle(
                    self.win, radius=r, edges=64,
                    fillColor=self._color_rgb[c],
                    lineColor=self._color_rgb[c],
                    pos=(x0 + i * sp, y),
                ))

        self._ttl = cfg.get('ttl_codes', {})

    # ═════════════════════════════════════════════════════════════════
    # SEQUENCE CONSTRUCTION — run level, before the trigger
    # ═════════════════════════════════════════════════════════════════

    def build_all_trials(self) -> list[list]:
        """
        Build the complete run.

        Returns one list of trial tuples per block:
            (word, ink_color, trial_type, iti)
        """
        rng = self._rng
        paradigm = self.design.get('paradigm', 'block')

        if paradigm == 'event':
            blocks = self._build_event(rng)
        else:
            blocks = self._build_blocked(rng)

        self._attach_itis(blocks, rng)
        return blocks

    # ── Blocked designs ──────────────────────────────────────────────

    def _build_blocked(self, rng: random.Random) -> list[list]:
        """One condition per block; pools balanced across the whole run."""
        # Group block indices by condition
        by_cond: dict[str, list[int]] = defaultdict(list)
        for i, b in enumerate(self.block_sequence):
            by_cond[b['condition']].append(i)

        out: list[list] = [[] for _ in self.block_sequence]

        for cond, idxs in by_cond.items():
            sizes = [self.block_sequence[i]['n_trials'] for i in idxs]
            total = sum(sizes)
            pool = self._condition_pool(cond, total, rng)
            for i, chunk in zip(idxs, deal_to_blocks(pool, sizes)):
                out[i] = self._order_block(chunk, rng)

        return out

    def _condition_pool(self, cond: str, n: int,
                        rng: random.Random) -> list:
        """Balanced pool of (word, ink, type) for one condition."""
        if cond == 'congruent':
            inks = balanced_pool(self._ink_colors, n, rng)
            return [(self._color_words[c], c, 'congruent') for c in inks]

        if cond == 'incongruent':
            pairs = balanced_pool(self._inc_pairs, n, rng)
            return [(w, ink, 'incongruent') for (w, ink) in pairs]

        if cond == 'neutral':
            inks = balanced_pool(self._ink_colors, n, rng)
            words = balanced_pool(self._neutral_words, n, rng)
            rng.shuffle(words)
            return [(w, c, 'neutral') for w, c in zip(words, inks)]

        raise ValueError(f"Unknown condition '{cond}'")

    def _order_block(self, trials: list, rng: random.Random) -> list:
        """Apply the two run-length constraints inside a block."""
        trials = list(trials)
        rng.shuffle(trials)
        enforce_max_run(trials, key=lambda t: t[1],
                        max_run=MAX_SAME_COLOR, rng=rng)
        enforce_max_run(trials, key=lambda t: t[0],
                        max_run=MAX_SAME_WORD, rng=rng)
        # Re-check colour: the word pass may have broken it
        enforce_max_run(trials, key=lambda t: t[1],
                        max_run=MAX_SAME_COLOR, rng=rng)
        return trials

    # ── Event-related design ─────────────────────────────────────────

    def _build_event(self, rng: random.Random) -> list[list]:
        """Single pseudo-block, all conditions interleaved."""
        n = self.block_sequence[0]['n_trials']
        per, rem = divmod(n, 3)
        n_neu = per + (1 if rem > 0 else 0)
        n_con = per + (1 if rem > 1 else 0)
        n_inc = n - n_neu - n_con

        trials = (
            self._condition_pool('neutral', n_neu, rng)
            + self._condition_pool('congruent', n_con, rng)
            + self._condition_pool('incongruent', n_inc, rng)
        )

        # Never two consecutive trials of the same type
        trials = interleave_no_repeat(trials, key=lambda t: t[2], rng=rng)

        # Then relax the colour runs, without breaking the type alternation
        enforce_max_run(trials, key=lambda t: t[1],
                        max_run=MAX_SAME_COLOR, rng=rng,
                        protect=lambda t: t[2])
        return [trials]

    # ── ITIs ─────────────────────────────────────────────────────────

    def _attach_itis(self, blocks: list[list], rng: random.Random) -> None:
        """Append the ITI to every trial tuple, in place."""
        if self.design.get('paradigm') == 'event':
            lo = self.design.get('iti_min', 1.5)
            hi = self.design.get('iti_max', 4.5)
            for b, trials in enumerate(blocks):
                # Stratified jitter: shuffled quantiles, mean guaranteed
                n = len(trials)
                steps = [lo + (hi - lo) * (i + 0.5) / n for i in range(n)]
                rng.shuffle(steps)
                blocks[b] = [
                    (w, c, t, round(iti, 4))
                    for (w, c, t), iti in zip(trials, steps)
                ]
        else:
            iti = self.design.get('iti_duration', 0.3)
            for b, trials in enumerate(blocks):
                blocks[b] = [(w, c, t, iti) for (w, c, t) in trials]

    # ═════════════════════════════════════════════════════════════════
    # VALIDATION
    # ═════════════════════════════════════════════════════════════════

    def validate_sequence(self, blocks: list[list]) -> ValidationReport:
        """Verify balance and ordering; also fill the descriptive summary."""
        rep = ValidationReport()
        flat = [t for b in blocks for t in b]

        words = [t[0] for t in flat]
        inks = [t[1] for t in flat]
        types = [t[2] for t in flat]

        # ── Totals ───────────────────────────────────────────────────
        expected = sum(b['n_trials'] for b in self.block_sequence)
        check_exact(rep, 'total trial count', len(flat), expected)
        check_exact(rep, 'block count', len(blocks), len(self.block_sequence))

        # ── Run-level balance ────────────────────────────────────────
        check_balanced(rep, 'trial types balanced (run)', types, tolerance=1)
        check_balanced(rep, 'ink colours balanced (run)', inks, tolerance=1)

        inc = [t for t in flat if t[2] == 'incongruent']
        if inc:
            check_balanced(rep, 'incongruent pairs balanced',
                           [(t[0], t[1]) for t in inc], tolerance=1)
        neu = [t for t in flat if t[2] == 'neutral']
        if neu:
            check_balanced(rep, 'neutral words balanced',
                           [t[0] for t in neu], tolerance=1)

        # ── Semantic correctness of each trial type ──────────────────
        bad_con = [t for t in flat
                   if t[2] == 'congruent' and t[0] != self._color_words[t[1]]]
        check_exact(rep, 'congruent word==ink', len(bad_con), 0)

        bad_inc = [t for t in flat
                   if t[2] == 'incongruent' and t[0] == self._color_words[t[1]]]
        check_exact(rep, 'incongruent word!=ink', len(bad_inc), 0)

        color_set = set(self._color_words.values())
        bad_neu = [t for t in flat if t[2] == 'neutral' and t[0] in color_set]
        check_exact(rep, 'neutral words are non-colour', len(bad_neu), 0)

        # ── Ordering, per block ──────────────────────────────────────
        worst_c = max((max_run_length([t[1] for t in b]) for b in blocks),
                      default=0)
        worst_w = max((max_run_length([t[0] for t in b]) for b in blocks),
                      default=0)
        rep.add('max consecutive same ink (per block)',
                worst_c <= MAX_SAME_COLOR,
                f"{worst_c} (max {MAX_SAME_COLOR})")
        rep.add('max consecutive same word (per block)',
                worst_w <= MAX_SAME_WORD,
                f"{worst_w} (max {MAX_SAME_WORD})")

        if self.design.get('paradigm') == 'event':
            check_max_run(rep, 'max consecutive same trial type',
                          types, max_allowed=1)

        # ── Per-block balance inside blocked designs ─────────────────
        if self.design.get('paradigm') != 'event':
            mono = all(len(set(t[2] for t in b)) == 1 for b in blocks if b)
            rep.add('one condition per block', mono,
                    'each block is pure' if mono else 'mixed block found')

        # ── Descriptive summary for the sidecar ──────────────────────
        rep.summary = {
            'n_trials': len(flat),
            'n_blocks': len(blocks),
            'trials_per_block': [len(b) for b in blocks],
            'trial_type_counts': counts(types),
            'ink_colour_counts': counts(inks),
            'word_counts': counts(words),
            'incongruent_pair_counts': counts(
                [f"{t[0]}/{t[1]}" for t in inc]) if inc else {},
            'neutral_word_counts': counts(
                [t[0] for t in neu]) if neu else {},
            'max_consecutive_same_ink': worst_c,
            'max_consecutive_same_word': worst_w,
            'max_consecutive_same_type': max_run_length(types),
            'iti_mean': round(
                sum(t[3] for t in flat) / len(flat), 4) if flat else 0,
            'iti_min': min((t[3] for t in flat), default=0),
            'iti_max': max((t[3] for t in flat), default=0),
        }
        return rep

    # ═════════════════════════════════════════════════════════════════
    # GUIDE
    # ═════════════════════════════════════════════════════════════════

    def _guide_visible(self) -> bool:
        if not self._indicators or not self._guide_enabled:
            return False
        if self._next_stim_time is None:
            return True
        return (self._next_stim_time - self.clock.time) > self._hide_lead

    def _draw_guide(self) -> None:
        if self._guide_visible():
            for c in self._indicators:
                c.draw()

    def show_fixation(self, duration: float) -> None:
        deadline = self.clock.time + duration
        self._fixation.draw()
        self._draw_guide()
        self.win.flip()
        while self.clock.time < deadline:
            self._fixation.draw()
            self._draw_guide()
            self.win.flip()
            self.get_keys(key_list=[])

    def run_rest(self, label: str = '', duration: float | None = None) -> None:
        dur = (duration if duration is not None
               else self.design.get('rest_duration', 7.0))
        if label == 'final':
            self._guide_enabled = False
            self._next_stim_time = None
        else:
            self._next_stim_time = (
                self.clock.time + dur
                + self.design.get('instruction_duration', 0.0)
                + self.design.get('pre_block_fixation', 0.0)
                + self.design.get('fixation_duration', 0.5)
            )
        super().run_rest(label=label, duration=dur)
        self._next_stim_time = None

    # ═════════════════════════════════════════════════════════════════
    # INSTRUCTIONS
    # ═════════════════════════════════════════════════════════════════

    def _get_instruction_text(self) -> str:
        total = sum(b.get('n_trials', 0) for b in self.block_sequence)
        k_r = self._color_to_key['rouge'].upper()
        k_b = self._color_to_key['bleu'].upper()
        k_v = self._color_to_key['vert'].upper()
        return (
            f"Stroop — Denomination de couleur\n\n"
            f"Design : {self.design.get('name', '')}\n"
            f"{len(self.block_sequence)} bloc(s), {total} essais\n\n"
            f"Repondez a la COULEUR DE L'ENCRE.\n"
            f"Ignorez ce que le mot dit !\n\n"
            f"  ROUGE  ->  [{k_r}]  (index)\n"
            f"  BLEU   ->  [{k_b}]  (majeur)\n"
            f"  VERT   ->  [{k_v}]  (annulaire)\n\n"
            f"Un rappel (3 cercles colores) apparait entre\n"
            f"les essais. Il disparait avant chaque mot.\n\n"
            f"Repondez le plus VITE et PRECISEMENT possible.\n\n"
            f"Appuyez sur une touche pour continuer..."
        )

    def _get_block_instruction(self, block_idx: int,
                               block_def: dict) -> str | None:
        if self.design.get('instruction_duration', 0.0) <= 0:
            return None
        return (f"Bloc {block_idx + 1}/{len(self.block_sequence)}\n\n"
                f"Nommez la COULEUR DE L'ENCRE")

    # ═════════════════════════════════════════════════════════════════
    # TRIAL
    # ═════════════════════════════════════════════════════════════════

    def run_trial(self, trial_data, block_idx: int, trial_idx: int,
                  block_def: dict, **kwargs) -> dict:
        word, ink_color, trial_type, iti_dur = trial_data

        fix_dur = self.design.get('fixation_duration', 0.5)
        stim_dur = self.design.get('stim_duration', 1.2)
        correct_key = self._color_to_key[ink_color]

        self.flush_keyboard()
        responded = False
        rt = None
        response_key = None
        response_color = None
        guide_shown = False

        # ── Fixation — guide forced off ──────────────────────────────
        self._next_stim_time = self.clock.time + fix_dur
        self._fixation.draw()
        self.win.flip()
        fix_onset = self.clock.time
        deadline = fix_onset + fix_dur
        while self.clock.time < deadline:
            self._fixation.draw()
            self.win.flip()
            self.get_keys(key_list=[])

        # ── Stimulus — guide forced off ──────────────────────────────
        self._word_stim.text = word
        self._word_stim.color = self._color_rgb[ink_color]
        self._word_stim.draw()
        self.win.flip()
        stim_onset = self.clock.time

        code = self._ttl.get(f'stim_{trial_type}', 0)
        if code:
            self.hardware.send_trigger(code)
        self.hardware.send_eyetracker_message(
            f"STIM_{trial_type[:3].upper()}_{word}_{ink_color}_"
            f"B{block_idx}_T{trial_idx}_t{stim_onset:.3f}"
        )

        deadline = stim_onset + stim_dur
        while self.clock.time < deadline:
            if not responded:
                keys = self.get_keys(key_list=self._valid_keys)
                if keys:
                    responded = True
                    rt = self.clock.time - stim_onset
                    response_key = keys[0].name
                    response_color = self._key_to_color.get(response_key)
                    t = self._ttl.get(
                        'response_correct' if response_color == ink_color
                        else 'response_incorrect', 0)
                    if t:
                        self.hardware.send_trigger(t)
            self._word_stim.draw()
            self.win.flip()

        # ── ITI — guide allowed ──────────────────────────────────────
        iti_onset = self.clock.time
        iti_end = iti_onset + iti_dur
        last = (trial_idx >= block_def['n_trials'] - 1)
        self._next_stim_time = None if last else iti_end + fix_dur

        self._fixation.draw()
        if self._guide_visible():
            guide_shown = True
            self._draw_guide()
        self.win.flip()

        while self.clock.time < iti_end:
            if not responded:
                keys = self.get_keys(key_list=self._valid_keys)
                if keys:
                    responded = True
                    rt = self.clock.time - stim_onset
                    response_key = keys[0].name
                    response_color = self._key_to_color.get(response_key)
                    t = self._ttl.get(
                        'response_correct' if response_color == ink_color
                        else 'response_incorrect', 0)
                    if t:
                        self.hardware.send_trigger(t)
            else:
                self.get_keys(key_list=[])
            self._fixation.draw()
            if self._guide_visible():
                guide_shown = True
                self._draw_guide()
            self.win.flip()

        self._next_stim_time = None
        is_correct = (response_color == ink_color) if responded else False

        # ── Record ───────────────────────────────────────────────────
        rec = self._base_record(block_idx, trial_idx, block_def)
        rec.update({
            # BIDS events.tsv core columns
            'onset': round(stim_onset, 4),
            'duration': stim_dur,
            'trial_type': trial_type,
            # Condition
            'block_condition': block_def['condition'],
            'n_trials_in_block': block_def['n_trials'],
            'word': word,
            'ink_color': ink_color,
            # Response
            'correct_color': ink_color,
            'correct_key': correct_key,
            'responded': int(responded),
            'response_key': response_key if responded else None,
            'response_color': response_color if responded else None,
            'rt': round(rt, 4) if (responded and rt is not None) else None,
            'is_correct': int(is_correct),
            'is_error': int(responded and not is_correct),
            'is_miss': int(not responded),
            # Timing detail
            'fixation_onset': round(fix_onset, 4),
            'stim_onset': round(stim_onset, 4),
            'iti_onset': round(iti_onset, 4),
            'fixation_duration': fix_dur,
            'stim_duration': stim_dur,
            'iti_duration': round(iti_dur, 4),
            'guide_shown_in_iti': int(guide_shown),
        })

        self._print_trial(block_idx, trial_idx, word, ink_color,
                          trial_type, responded, is_correct, rt, stim_onset)
        return rec

    # ═════════════════════════════════════════════════════════════════
    # CONSOLE
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    def _print_trial(bi, ti, word, ink, ttype, responded, correct, rt, onset):
        tt = ttype[:3].upper()
        if not responded:
            tag, sym, rt_s = 'MISS', SYM_ERR, "    - "
        elif correct:
            tag, sym, rt_s = 'OK  ', SYM_OK, f"{rt * 1000:5.0f}ms"
        else:
            tag, sym = 'ERR ', SYM_ERR
            rt_s = f"{rt * 1000:5.0f}ms" if rt else "    - "
        print(f"  B{bi:02d} T{ti:02d} | t={onset:8.3f}s | {tt} | "
              f"{word:>6s} [{ink[:3]}] | {tag} {sym} | {rt_s}")

    def _print_task_stats(self) -> None:
        recs = self.data_writer.records
        if not recs:
            return

        total = len(recs)
        correct = sum(r['is_correct'] for r in recs)
        errors = sum(r['is_error'] for r in recs)
        misses = sum(r['is_miss'] for r in recs)

        print(f"\n{'=' * 62}")
        print(f"  STROOP — design {self.design_id} | "
              f"{self.design.get('name', '')}")
        print(f"  {correct}/{total} corrects ({100 * correct / total:.1f}%) | "
              f"Err={errors}  Miss={misses}")
        print(f"  {'-' * 56}")

        by_type = defaultdict(list)
        for r in recs:
            by_type[r['trial_type']].append(r)

        rt_med = {}
        for tt in ['congruent', 'incongruent', 'neutral']:
            rs = by_type.get(tt, [])
            if not rs:
                continue
            n = len(rs)
            acc = 100 * sum(r['is_correct'] for r in rs) / n
            rts = [r['rt'] for r in rs if r['is_correct'] and r['rt']]
            if rts:
                s = sorted(rts)
                m = len(s) // 2
                med = s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2
                rt_med[tt] = med
                mean = sum(rts) / len(rts)
                rt_txt = f"Med={med * 1000:4.0f}ms Mean={mean * 1000:4.0f}ms"
            else:
                rt_txt = "Med=   -  Mean=   -"
            print(f"  {tt:12s}: {acc:5.1f}% ({n:3d} essais) | {rt_txt} | "
                  f"Err={sum(r['is_error'] for r in rs):2d} "
                  f"Miss={sum(r['is_miss'] for r in rs):2d}")

        con, inc, neu = (rt_med.get(k, 0) for k in
                         ('congruent', 'incongruent', 'neutral'))
        print(f"  {'-' * 56}")
        if inc and con:
            print(f"  Interference (INC-CON): {(inc - con) * 1000:+5.0f}ms")
        if inc and neu:
            print(f"  Interference (INC-NEU): {(inc - neu) * 1000:+5.0f}ms")
        if con and neu:
            print(f"  Facilitation (NEU-CON): {(neu - con) * 1000:+5.0f}ms")

        by_ink = defaultdict(list)
        for r in recs:
            by_ink[r['ink_color']].append(r)
        print(f"  {'-' * 56}")
        for c in sorted(by_ink):
            rs = by_ink[c]
            acc = 100 * sum(r['is_correct'] for r in rs) / len(rs)
            rts = [r['rt'] for r in rs if r['is_correct'] and r['rt']]
            rt_s = f"{sum(rts) / len(rts) * 1000:4.0f}ms" if rts else "   -"
            print(f"  encre {c:6s}: {acc:5.1f}% ({len(rs):3d}) | RT={rt_s}")

        print(f"{'=' * 62}\n")