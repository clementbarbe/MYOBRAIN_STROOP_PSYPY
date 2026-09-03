"""
Stroop Color-Word Task (French) — manual response.

COLOR GUIDE VISIBILITY RULE
---------------------------
The 3 colored circles (response guide) are visible ONLY during:
    - the ITI following a stimulus
    - the rest periods between blocks

They are ALWAYS hidden during:
    - the pre-stimulus fixation
    - the stimulus presentation itself
    - the last `indicator_hide_lead` seconds before any stimulus onset

This guarantees the guide is never on screen when the participant is
preparing or executing a colour decision, avoiding any visual priming
of the response mapping.

Because the projected next-stimulus time is recomputed on every frame,
the rule holds for both fixed-ITI (block) and jittered-ITI (event) designs.

Stimuli:
    Congruent   : ROUGE in red, BLEU in blue, VERT in green
    Incongruent : ROUGE in blue, ROUGE in green, BLEU in red ... (6 pairs)
    Neutral     : abstract French words (IDEE, CAUSE, ORDRE...) in color
                  -> forces lexical reading without chromatic conflict

Trial timing:
    Block designs : 500ms fixation + 1200ms word + 300ms ITI = 2.0s
    Event design  : 500ms fixation + 1200ms word + jittered ITI (1.5-4.5s)

Randomisation (within block):
    - Ink colors balanced
    - No >2 consecutive same ink color
    - No >2 consecutive same word
    - Incongruent blocks: 6 word/ink pairs balanced
    - Event design: never 2 consecutive trials of the same type
"""

from __future__ import annotations

import random
from collections import defaultdict

from psychopy import visual

from tasks.base import BaseTask
from tasks.registry import register_task
from tasks.utils.sequence import desequence
from utils.console import SYM_OK, SYM_ERR


@register_task('stroop')
class StroopTask(BaseTask):
    """Stroop Color-Word fMRI task."""

    TASK_NAME = 'stroop'

    # ═════════════════════════════════════════════════════════════════
    # SETUP
    # ═════════════════════════════════════════════════════════════════

    def _setup_stimuli(self) -> None:
        stim_cfg = self.task_config.get('stimulus', {})

        self._word_stim = visual.TextStim(
            self.win, text='', color='white',
            height=stim_cfg.get('word_height', 0.15),
            pos=(0, 0), bold=True, font='monospace',
        )

        # ── Colors ───────────────────────────────────────────────────
        colors_cfg = self.task_config.get('colors', {})
        self._color_rgb = {
            'rouge': colors_cfg.get('rouge', [1.0, -1.0, -1.0]),
            'bleu':  colors_cfg.get('bleu',  [-1.0, -1.0, 1.0]),
            'vert':  colors_cfg.get('vert',  [-1.0, 0.8, -1.0]),
        }
        self._ink_colors = list(self._color_rgb.keys())

        # ── Words ────────────────────────────────────────────────────
        cw = self.task_config.get('color_words', {})
        self._color_words = {
            'rouge': cw.get('rouge', 'ROUGE'),
            'bleu':  cw.get('bleu',  'BLEU'),
            'vert':  cw.get('vert',  'VERT'),
        }
        self._neutral_words = self.task_config.get(
            'neutral_words',
            ['IDEE', 'ACTE', 'FAIT', 'AVIS', 'SENS', 'ETAT',
             'CAUSE', 'ORDRE', 'THEME', 'DEBUT', 'TERME', 'DROIT'],
        )

        pairs_cfg = self.task_config.get('incongruent_pairs', [])
        if pairs_cfg:
            self._inc_pairs = [(p['word'], p['ink']) for p in pairs_cfg]
        else:
            self._inc_pairs = [
                (self._color_words[w], i)
                for w in self._ink_colors
                for i in self._ink_colors if w != i
            ]

        # ── Response keys ────────────────────────────────────────────
        key_src = ('response_keys_fmri' if self.settings.mode == 'fmri'
                   else 'response_keys_pc')
        keys_cfg = self.task_config.get(key_src, {})
        self._color_to_key = {
            'rouge': keys_cfg.get('rouge', 'left'),
            'bleu':  keys_cfg.get('bleu',  'down'),
            'vert':  keys_cfg.get('vert',  'right'),
        }
        self._key_to_color = {v: k for k, v in self._color_to_key.items()}
        self._valid_keys = list(self._color_to_key.values())

        # ── Colored circle guide ─────────────────────────────────────
        self._indicators = []
        self._hide_lead = float(
            self.task_config.get('indicator_hide_lead', 2.0)
        )
        # Absolute clock time of the next stimulus onset.
        # None  -> no upcoming stimulus (guide may stay visible)
        # float -> guide hides when (value - now) <= _hide_lead
        self._next_stim_time: float | None = None
        # Master switch used to force the guide off (final rest, etc.)
        self._guide_enabled = True

        if self.task_config.get('show_indicators', True):
            radius = self.task_config.get('indicator_radius', 0.028)
            ind_y = self.task_config.get('indicator_y', -0.82)
            spacing = self.task_config.get('indicator_spacing', 0.22)
            order = self.task_config.get(
                'indicator_order', ['rouge', 'bleu', 'vert']
            )
            n = len(order)
            x0 = -spacing * (n - 1) / 2.0
            for i, c in enumerate(order):
                self._indicators.append(visual.Circle(
                    self.win,
                    radius=radius,
                    fillColor=self._color_rgb[c],
                    lineColor=self._color_rgb[c],
                    pos=(x0 + i * spacing, ind_y),
                    edges=64,
                ))
            self._log_guide_visibility()

        self._ttl = self.task_config.get('ttl_codes', {})

    def _log_guide_visibility(self) -> None:
        """Report when the colour guide will actually be on screen."""
        fix = self.design.get('fixation_duration', 0.5)
        rest = self.design.get('rest_duration', 7.0)
        paradigm = self.design.get('paradigm', 'block')

        if paradigm == 'event':
            iti_min = self.design.get('iti_min', 1.5)
            iti_max = self.design.get('iti_max', 4.5)
            vis_min = max(0.0, iti_min + fix - self._hide_lead)
            vis_max = max(0.0, iti_max + fix - self._hide_lead)
            iti_txt = f"ITI: {vis_min:.1f}-{vis_max:.1f}s visible"
        else:
            iti = self.design.get('iti_duration', 0.3)
            vis = max(0.0, iti + fix - self._hide_lead)
            iti_txt = (
                f"ITI: {vis:.1f}s visible"
                if vis > 0 else "ITI: jamais visible (fenetre trop courte)"
            )

        rest_vis = max(0.0, rest - self._hide_lead - fix)
        self.logger.log(
            f"Guide couleur | hide_lead={self._hide_lead}s | "
            f"{iti_txt} | Rest: {rest_vis:.1f}s visible"
        )

    # ═════════════════════════════════════════════════════════════════
    # GUIDE DRAWING
    # ═════════════════════════════════════════════════════════════════

    def _guide_visible(self) -> bool:
        """
        Decide whether the colour guide should be drawn on this frame.

        Returns False if:
            - the guide is disabled or not configured
            - a stimulus is due in less than `_hide_lead` seconds
        """
        if not self._indicators or not self._guide_enabled:
            return False
        if self._next_stim_time is None:
            return True
        return (self._next_stim_time - self.clock.time) > self._hide_lead

    def _draw_guide(self) -> None:
        """Draw the 3 colored circles if the visibility rule allows it."""
        if self._guide_visible():
            for c in self._indicators:
                c.draw()

    # ═════════════════════════════════════════════════════════════════
    # DISPLAY OVERRIDES
    # ═════════════════════════════════════════════════════════════════

    def show_fixation(self, duration: float) -> None:
        """
        Fixation with guide handled by the visibility rule.

        Used by the base class for rest periods and pre-block fixation.
        """
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
        """
        Rest period. The guide is shown, then hidden `_hide_lead` seconds
        before the first stimulus of the upcoming block.
        """
        dur = (duration if duration is not None
               else self.design.get('rest_duration', 7.0))

        if label == 'final':
            # No stimulus will follow — keep the screen clean.
            self._guide_enabled = False
            self._next_stim_time = None
        else:
            instr = self.design.get('instruction_duration', 0.0)
            pre_fix = self.design.get('pre_block_fixation', 0.0)
            fix = self.design.get('fixation_duration', 0.5)
            self._next_stim_time = (
                self.clock.time + dur + instr + pre_fix + fix
            )

        super().run_rest(label=label, duration=dur)

        self._next_stim_time = None

    # ═════════════════════════════════════════════════════════════════
    # INSTRUCTIONS
    # ═════════════════════════════════════════════════════════════════

    def _get_instruction_text(self) -> str:
        total = sum(b.get('n_trials', 0) for b in self.block_sequence)
        n_blocs = len(self.block_sequence)
        k_r = self._color_to_key['rouge'].upper()
        k_b = self._color_to_key['bleu'].upper()
        k_v = self._color_to_key['vert'].upper()

        return (
            f"Stroop — Denomination de couleur\n\n"
            f"Design : {self.design.get('name', '')}\n"
            f"{n_blocs} bloc(s), {total} essais\n\n"
            f"Repondez a la COULEUR DE L'ENCRE.\n"
            f"Ignorez ce que le mot dit !\n\n"
            f"  ROUGE  ->  [{k_r}]  (index)\n"
            f"  BLEU   ->  [{k_b}]  (majeur)\n"
            f"  VERT   ->  [{k_v}]  (annulaire)\n\n"
            f"Un rappel (3 cercles colores) apparait\n"
            f"entre les essais et pendant les pauses.\n"
            f"Il disparait avant chaque mot.\n\n"
            f"Repondez le plus VITE et PRECISEMENT possible.\n\n"
            f"Appuyez sur une touche pour continuer..."
        )

    def _get_block_instruction(self, block_idx: int,
                               block_def: dict) -> str | None:
        if self.design.get('instruction_duration', 0.0) <= 0:
            return None
        n = len(self.block_sequence)
        return (
            f"Bloc {block_idx + 1}/{n}\n\n"
            f"Nommez la COULEUR DE L'ENCRE"
        )

    # ═════════════════════════════════════════════════════════════════
    # TRIAL GENERATION
    # ═════════════════════════════════════════════════════════════════

    def generate_trials(self, block_def: dict) -> list:
        """
        Return list of (word, ink_color, trial_type, iti) tuples.

        Block designs use a fixed ITI.
        Event design uses a jittered ITI per trial.
        """
        condition = block_def['condition']
        n = block_def['n_trials']
        paradigm = self.design.get('paradigm', 'block')

        # ── Build trial content ──────────────────────────────────────
        if condition == 'neutral':
            trials = self._gen_neutral(n)
        elif condition == 'congruent':
            trials = self._gen_congruent(n)
        elif condition == 'incongruent':
            trials = self._gen_incongruent(n)
        elif condition == 'mixed':
            trials = self._gen_mixed(n)
        else:
            trials = self._gen_neutral(n)

        # ── Order constraints ────────────────────────────────────────
        if condition == 'mixed':
            trials = self._no_repeat_type(trials)
            trials = self._soft_desequence_color(trials, max_c=2)
        else:
            trials = self._double_desequence(trials, max_c=2)

        # ── Attach ITIs ──────────────────────────────────────────────
        if paradigm == 'event':
            from tasks.utils.sequence import generate_jittered_isis
            itis = generate_jittered_isis(
                n,
                self.design.get('iti_min', 1.5),
                self.design.get('iti_max', 4.5),
            )
        else:
            itis = [self.design.get('iti_duration', 0.3)] * n

        return [(t[0], t[1], t[2], iti) for t, iti in zip(trials, itis)]

    # ── Content generators ───────────────────────────────────────────

    def _gen_congruent(self, n: int) -> list:
        """Balanced congruent trials: each ink color equally often."""
        trials = []
        per, rem = divmod(n, 3)
        for i, c in enumerate(self._ink_colors):
            cnt = per + (1 if i < rem else 0)
            trials.extend([(self._color_words[c], c, 'congruent')] * cnt)
        random.shuffle(trials)
        return trials

    def _gen_incongruent(self, n: int) -> list:
        """Balanced incongruent: 6 word/ink pairs equally distributed."""
        trials = []
        n_pairs = len(self._inc_pairs)
        per, rem = divmod(n, n_pairs)
        for i, (w, ink) in enumerate(self._inc_pairs):
            cnt = per + (1 if i < rem else 0)
            trials.extend([(w, ink, 'incongruent')] * cnt)
        random.shuffle(trials)
        return trials

    def _gen_neutral(self, n: int) -> list:
        """Balanced neutral: abstract words, ink colors equally distributed."""
        trials = []
        per, rem = divmod(n, 3)
        pool = list(self._neutral_words)
        random.shuffle(pool)
        k = 0
        for i, c in enumerate(self._ink_colors):
            cnt = per + (1 if i < rem else 0)
            for _ in range(cnt):
                trials.append((pool[k % len(pool)], c, 'neutral'))
                k += 1
        random.shuffle(trials)
        return trials

    def _gen_mixed(self, n: int) -> list:
        """Equal mix of the 3 trial types (event-related design)."""
        per, rem = divmod(n, 3)
        n_neu = per + (1 if rem > 0 else 0)
        n_con = per + (1 if rem > 1 else 0)
        n_inc = n - n_neu - n_con
        return (
            self._gen_neutral(n_neu)
            + self._gen_congruent(n_con)
            + self._gen_incongruent(n_inc)
        )

    # ── Ordering constraints ─────────────────────────────────────────

    def _no_repeat_type(self, trials: list) -> list:
        """
        Reorder so that no two consecutive trials share the same trial_type.
        Greedy construction from type pools (feasible when balanced).
        """
        pools = defaultdict(list)
        for t in trials:
            pools[t[2]].append(t)
        for p in pools.values():
            random.shuffle(p)

        result = []
        last_type = None

        for _ in range(len(trials)):
            candidates = [k for k, v in pools.items() if v and k != last_type]
            if not candidates:
                candidates = [k for k, v in pools.items() if v]
                if not candidates:
                    break
            chosen = max(candidates, key=lambda k: len(pools[k]))
            result.append(pools[chosen].pop())
            last_type = chosen

        return result

    def _soft_desequence_color(self, trials: list, max_c: int = 2) -> list:
        """
        Avoid >max_c consecutive identical ink colors WITHOUT breaking
        the trial-type alternation (swap only between same-type trials).
        """
        for _ in range(80):
            ok = True
            for i in range(max_c, len(trials)):
                window = [trials[j][1] for j in range(i - max_c, i + 1)]
                if len(set(window)) == 1:
                    ok = False
                    cands = [
                        k for k in range(len(trials))
                        if trials[k][2] == trials[i][2]
                        and trials[k][1] != trials[i][1]
                    ]
                    if cands:
                        s = random.choice(cands)
                        trials[i], trials[s] = trials[s], trials[i]
                    break
            if ok:
                break
        return trials

    def _double_desequence(self, trials: list, max_c: int = 2) -> list:
        """No >max_c consecutive same ink color AND same word."""
        trials = desequence(
            trials, key_func=lambda t: t[1], max_consecutive=max_c
        )
        for _ in range(50):
            ok = True
            for i in range(max_c, len(trials)):
                w = [trials[j][0] for j in range(i - max_c, i + 1)]
                if len(set(w)) == 1:
                    ok = False
                    cands = [
                        k for k in range(i + 1, len(trials))
                        if trials[k][0] != trials[i][0]
                    ]
                    if cands:
                        s = random.choice(cands)
                        trials[i], trials[s] = trials[s], trials[i]
                    break
            if ok:
                break
        return trials

    # ═════════════════════════════════════════════════════════════════
    # TRIAL EXECUTION
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

        # ── Phase 1: Fixation — guide always hidden ──────────────────
        # The stimulus is imminent (fix_dur < hide_lead in every design),
        # so we force the guide off for the whole fixation window.
        self._next_stim_time = self.clock.time + fix_dur
        self._fixation.draw()
        self.win.flip()
        fix_onset = self.clock.time
        deadline = fix_onset + fix_dur
        while self.clock.time < deadline:
            self._fixation.draw()
            self.win.flip()
            self.get_keys(key_list=[])

        # ── Phase 2: Colored word — guide always hidden ──────────────
        self._word_stim.text = word
        self._word_stim.color = self._color_rgb[ink_color]
        self._word_stim.draw()
        self.win.flip()
        stim_onset = self.clock.time

        ttl_code = self._ttl.get(f'stim_{trial_type}', 0)
        if ttl_code:
            self.hardware.send_trigger(ttl_code)
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
                    ttl_r = self._ttl.get(
                        'response_correct' if response_color == ink_color
                        else 'response_incorrect', 0
                    )
                    if ttl_r:
                        self.hardware.send_trigger(ttl_r)
            self._word_stim.draw()
            self.win.flip()

        # ── Phase 3: ITI — guide visible under the hide_lead rule ────
        iti_onset = self.clock.time
        iti_end = iti_onset + iti_dur
        is_last = (trial_idx >= block_def['n_trials'] - 1)

        if is_last:
            # A rest period follows; run_rest will set its own estimate.
            self._next_stim_time = None
        else:
            self._next_stim_time = iti_end + fix_dur

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
                    ttl_r = self._ttl.get(
                        'response_correct' if response_color == ink_color
                        else 'response_incorrect', 0
                    )
                    if ttl_r:
                        self.hardware.send_trigger(ttl_r)
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
        record = self._base_record(block_idx, trial_idx, block_def)
        record.update({
            'paradigm': self.design.get('paradigm', 'block'),
            'block_condition': block_def['condition'],
            'n_trials_in_block': block_def['n_trials'],
            'word': word,
            'ink_color': ink_color,
            'trial_type': trial_type,
            'correct_key': correct_key,
            'correct_color': ink_color,
            'responded': int(responded),
            'response_key': response_key or '',
            'response_direction': response_color or '',
            'response_color': response_color or '',
            'rt': round(rt, 4) if rt is not None else -1,
            'is_correct': int(is_correct),
            'is_error': int(responded and not is_correct),
            'is_miss': int(not responded),
            'fixation_onset': round(fix_onset, 4),
            'stim_onset': round(stim_onset, 4),
            'iti_onset': round(iti_onset, 4),
            'fixation_duration': fix_dur,
            'stim_duration': stim_dur,
            'iti_duration': round(iti_dur, 4),
            'guide_shown_in_iti': int(guide_shown),
        })

        self._print_trial(
            block_idx, trial_idx, word, ink_color, trial_type,
            responded, is_correct, rt, stim_onset,
        )
        return record

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
            rt_s = f"{rt * 1000:5.0f}ms" if rt and rt > 0 else "    - "
        print(
            f"  B{bi:02d} T{ti:02d} | t={onset:8.3f}s | "
            f"{tt} | {word:>6s} [{ink[:3]}] | {tag} {sym} | {rt_s}"
        )

    def _print_task_stats(self) -> None:
        records = self.data_writer.records
        if not records:
            return

        total = len(records)
        correct = sum(r['is_correct'] for r in records)
        errors = sum(r.get('is_error', 0) for r in records)
        misses = sum(r.get('is_miss', 0) for r in records)

        print(f"\n{'=' * 60}")
        print(f"  STROOP - {correct}/{total} ({100 * correct / total:.1f}%)")
        print(f"  Correct={correct}  Erreurs={errors}  Miss={misses}")

        n_guide = sum(r.get('guide_shown_in_iti', 0) for r in records)
        print(f"  Guide couleur affiche pendant {n_guide}/{total} ITI")
        print(f"  {'-' * 54}")

        by_type = defaultdict(list)
        for r in records:
            by_type[r['trial_type']].append(r)

        rt_by = {}
        for tt in ['congruent', 'incongruent', 'neutral']:
            recs = by_type.get(tt, [])
            if not recs:
                continue
            n = len(recs)
            acc = 100 * sum(r['is_correct'] for r in recs) / n
            rts = [r['rt'] for r in recs if r['rt'] > 0 and r['is_correct']]
            mean = sum(rts) / len(rts) if rts else 0
            rt_by[tt] = mean
            if rts:
                s = sorted(rts)
                mid = len(s) // 2
                med = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
                med_s = f"{med * 1000:.0f}ms"
            else:
                med_s = "-"
            mean_s = f"{mean * 1000:.0f}ms" if rts else "-"
            err = sum(r.get('is_error', 0) for r in recs)
            mis = sum(r.get('is_miss', 0) for r in recs)
            print(
                f"  {tt:12s}: {acc:5.1f}% ({n:3d}) | "
                f"Mean={mean_s:>6s} Med={med_s:>6s} | "
                f"Err={err:2d} Miss={mis:2d}"
            )

        con = rt_by.get('congruent', 0)
        inc = rt_by.get('incongruent', 0)
        neu = rt_by.get('neutral', 0)
        print(f"  {'-' * 54}")
        if inc > 0 and con > 0:
            print(f"  Interference (INC-CON): {(inc - con) * 1000:+.0f}ms")
        if inc > 0 and neu > 0:
            print(f"  Interference (INC-NEU): {(inc - neu) * 1000:+.0f}ms")
        if neu > 0 and con > 0:
            print(f"  Facilitation (CON-NEU): {(con - neu) * 1000:+.0f}ms")

        by_ink = defaultdict(list)
        for r in records:
            by_ink[r['ink_color']].append(r)
        if len(by_ink) > 1:
            print(f"  {'-' * 54}")
            for c in sorted(by_ink):
                recs = by_ink[c]
                n = len(recs)
                acc = 100 * sum(r['is_correct'] for r in recs) / n
                rts = [r['rt'] for r in recs
                       if r['rt'] > 0 and r['is_correct']]
                rt_s = f"{sum(rts) / len(rts) * 1000:.0f}ms" if rts else "-"
                print(f"  ink={c:6s}: {acc:5.1f}% ({n}) | RT={rt_s}")

        print(f"{'=' * 60}\n")