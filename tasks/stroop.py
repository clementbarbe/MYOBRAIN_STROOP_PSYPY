"""Stroop task driven by the supplied A/B/C/D schedules."""

from __future__ import annotations

import hashlib
import json

from psychopy import visual

from config.constants import PROJECT_ROOT, TTL_START_EXP
from config.stroop_designs import design_for_subject, load_design
from config.stroop_training import (
    training_trials, assess_training, DISCOVERY_DURATION, PHASES,
)
from core.exceptions import TaskError
from tasks.base import BaseTask
from tasks.registry import register_task


@register_task('stroop')
class StroopTask(BaseTask):
    TASK_NAME = 'stroop'

    def _setup_stimuli(self) -> None:
        cfg = self.task_config
        self.training = self.design_id == 'training'
        self._word_stim = visual.TextStim(
            self.win, text='', height=cfg['stimulus']['word_height'],
            pos=(0, 0), bold=True, font='monospace',
        )
        self._color_rgb = cfg['colors']
        key_source = 'response_keys_fmri' if self.settings.mode == 'fmri' else 'response_keys_pc'
        self._color_to_key = cfg[key_source]
        self._key_to_color = {key: color for color, key in self._color_to_key.items()}
        self._valid_keys = list(self._key_to_color)
        self._ttl = cfg['ttl_codes']
        self._training_view = None
        self._current_training_phase = None
        self._discovery_presses = []
        self._training_report = None
        if self.training:
            from tasks.button_box import ButtonBoxView
            self._training_view = ButtonBoxView(self.win, self._color_to_key, self._color_rgb)
        self._feedback = visual.TextStim(self.win, text='', height=0.07, wrapWidth=1.7)
        self._feedback_until = 0.0

    def prepare(self) -> None:
        """Read the fixed schedule before waiting for the scanner."""
        if not self.training and self.design_id != design_for_subject(self.settings.participant_id):
            raise TaskError('Le design ne correspond pas au numéro d’inclusion du sujet.')
        try:
            trials = (training_trials(design_for_subject(self.settings.participant_id))
                      if self.training else load_design(self.design_id))
        except (OSError, ValueError, KeyError) as error:
            raise TaskError(str(error)) from error
        if len(trials) != self.block_sequence[0]['n_trials']:
            raise TaskError('Le nombre d’essais ne correspond pas au design.')
        self._prepared = [trials]
        self._schedule = trials
        last = trials[-1]
        self._schedule_end = last['fixation_onset'] + last['fixation_after_sec']
        self._final_rest_duration = (0.0 if self.training else
                                     float(self.task_config.get('final_rest_duration', 10.0)))
        self._run_end = self._schedule_end + self._final_rest_duration
        self._write_design_sidecar()
        self.logger.ok(f'Design {self.design_id} : {len(trials)} essais, {self._run_end:.2f}s')

    def _write_design_sidecar(self, **kwargs) -> None:
        source = None if self.training else PROJECT_ROOT / f'stroop_design_{self.design_id}.tsv'
        payload = {
            'subject': self.settings.participant_id,
            'run': self.settings.run, 'design_id': self.design_id,
            'training': self.training,
            'source_file': source.name if source else None,
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest() if source else None,
            'duration': self._run_end, 'response_keys': self._color_to_key,
            'schedule_duration': self._schedule_end,
            'final_rest_duration': self._final_rest_duration,
            'planned_final_rest_onset': self._schedule_end if not self.training else None,
            'response_window': 'stimulus presentation only',
            'schedule': self._schedule,
            'training_accuracy_threshold': (self.task_config['training']['accuracy_threshold']
                                            if self.training else None),
            'color_hints_during_acquisition': False,
        }
        stem = self.settings.base_name(self.TASK_NAME, self.design_id)
        path = self.settings.task_dir(self.TASK_NAME) / f'{stem}_design.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

    def _get_instruction_text(self) -> str:
        keys = '\n'.join(f'{color.upper()} → {key.upper()}'
                         for color, key in self._color_to_key.items())
        if self.training:
            return (
                'ENTRAÎNEMENT — environ 3 minutes\n\n'
                'Découverte du boîtier : appuyez sur les boutons.\n'
                '1. Répondez à des pastilles, avec rappel des touches.\n'
                '2. Même exercice sans rappel.\n'
                '3. Répondez à la couleur de l’encre des mots.\n\n'
                f'{keys}\n\n'
                'Un bilan permettra de vérifier les acquis.\n\n'
                f'{self.ADVANCE_PROMPT}'
            )
        return (
            f'STROOP — Sujet {self.settings.participant_id} / Design {self.design_id}\n\n'
            'Indiquez la COULEUR DE L’ENCRE. Ignorez le sens du mot.\n\n'
            f'{keys}\n\n'
            'Répondez pendant l’affichage du mot,\nle plus vite et précisément possible.\n'
            'Pendant la tâche, aucun indice de couleur ne sera affiché.\n\n'
            f'{self.ADVANCE_PROMPT}'
        )

    def wait_for_trigger(self) -> None:
        if not self.training:
            super().wait_for_trigger()
            return
        # Practice uses the selected response buttons, without a scanner pulse.
        self.clock.reset()
        self.flush_keyboard()
        self.hardware.send_trigger(TTL_START_EXP)

    def _draw_interval(self, next_onset: float | None) -> None:
        if (self.training and self._current_training_phase != 'stroop'
                and self.clock.time < self._feedback_until):
            self._feedback.draw()
        else:
            self._fixation.draw()
        if self.training and self._current_training_phase == 'guided_mapping':
            self._training_view.draw_box(self.clock.time)

    def _run_discovery(self) -> None:
        self.flush_keyboard()
        checked = set()
        while self.clock.time < DISCOVERY_DURATION - self.scanner.frame_duration / 2:
            for key in self.get_keys(key_list=self._valid_keys + ['r']):
                self._training_view.flash(key.name, self.clock.time)
                self._discovery_presses.append({'key': key.name, 'time': key.rt,
                                                'active': key.name in self._valid_keys})
                if key.name in self._valid_keys:
                    checked.add(key.name)
            self._training_view.draw_discovery(
                self.clock.time, checked, DISCOVERY_DURATION - self.clock.time)
            self.win.flip()

    def _begin_training_phase(self, trial: dict) -> None:
        phase = trial['training_phase']
        if phase == self._current_training_phase:
            return
        self._wait_until(trial['phase_instruction_onset'], lambda: self._draw_interval(None))
        self._feedback_until = 0.0
        self._current_training_phase = phase
        self._wait_until(trial['onset'],
                         lambda: self._training_view.draw_phase_instruction(phase))

    def _draw_trial(self, trial: dict) -> None:
        if trial.get('stimulus_kind') == 'patch':
            self._training_view.patch.draw()
        else:
            self._word_stim.draw()
        if trial.get('show_mapping', False):
            self._training_view.draw_box(self.clock.time)

    def _wait_until(self, deadline: float, draw) -> None:
        """Absolute deadlines prevent cumulative drift from trial to trial."""
        frame = self.scanner.frame_duration
        while self.clock.time < deadline - frame / 2:
            draw()
            self.win.flip()
            self.get_keys(key_list=[])

    def run_rest(self, label='', duration=None) -> None:
        # Preserve all TSV fixations, then keep fixation for the extra RUN rest.
        if self.training and label == 'initial':
            self._run_discovery()
        if label == 'final':
            self._wait_until(self._run_end, lambda: self._draw_interval(None))

    def run_trial(self, trial_data, block_idx, trial_idx, block_def, **kwargs) -> dict:
        trial = trial_data
        if self.training:
            self._begin_training_phase(trial)
        onset, offset = trial['onset'], trial['fixation_onset']
        ink, condition = trial['ink_color'], trial['condition']
        correct_key = self._color_to_key[ink]
        self._word_stim.text = trial['word']
        self._word_stim.color = self._color_rgb[ink]
        if trial.get('stimulus_kind') == 'patch':
            self._training_view.patch.fillColor = self._color_rgb[ink]
        self._wait_until(onset, lambda: self._draw_interval(onset))
        if self.clock.time >= offset:
            raise TaskError(f'Retard de présentation : essai {trial["trial"]} dépassé.')
        # Poll pending pulses/escape before clearing old participant responses.
        self.get_keys(key_list=[])
        self.flush_keyboard()
        self._draw_trial(trial)
        self.win.flip()
        actual_onset = self.clock.time
        self.hardware.send_trigger(self._ttl.get(f'stim_{condition}', self._ttl['stim_neutral']))
        self.hardware.send_eyetracker_message(
            f'STIM_{condition}_{trial["trial"]}_t{actual_onset:.4f}'
        )
        response = None
        rt = None
        response_deadline = offset

        def poll_response():
            nonlocal response, rt
            keys = self.get_keys(key_list=self._valid_keys + (['r'] if trial.get('show_mapping') else []))
            for key in keys:
                if trial.get('show_mapping'):
                    self._training_view.flash(key.name, self.clock.time)
                if key.name not in self._valid_keys:
                    continue
                # Keyboard.rt shares the experiment clock; use the event time,
                # so a late poll never turns a pre-onset press into a response.
                timestamp = key.rt
                if response is None and actual_onset <= timestamp < response_deadline:
                    response = key.name
                    rt = timestamp - actual_onset
                    code = 'response_correct' if response == correct_key else 'response_incorrect'
                    self.hardware.send_trigger(self._ttl[code])

        while self.clock.time < offset - self.scanner.frame_duration / 2:
            poll_response()
            self._draw_trial(trial)
            self.win.flip()
        poll_response()
        next_onset = (self._schedule[trial_idx + 1]['onset']
                      if trial_idx + 1 < len(self._schedule) else None)
        self._draw_interval(next_onset)
        self.win.flip()
        actual_offset = self.clock.time
        response_deadline = actual_offset
        # Retrieve presses from the final displayed frame before the next
        # fixation poll can discard them.
        poll_response()
        correct = response == correct_key
        if trial.get('show_feedback', False):
            # The memory stage gives correctness feedback, without a key hint.
            self._feedback.text = ('Correct !' if correct else
                                   'Pas de réponse' if response is None else 'Incorrect')
            self._feedback.color = 'white' if correct else 'yellow'
            self._feedback_until = actual_offset + 0.9
        record = self._base_record(block_idx, trial_idx, block_def)
        record.update({
            'onset': round(actual_onset, 6), 'duration': round(actual_offset - actual_onset, 6),
            'condition': condition, 'trial_type': condition, 'stimulus': trial['stimulus'],
            'word': trial['word'], 'ink_color': ink, 'correct_response': correct_key,
            'response': response, 'correct': int(correct),
            'RT': round(rt, 6) if rt is not None else None,
            'responded': int(response is not None),
            'is_error': int(response is not None and not correct), 'is_miss': int(response is None),
            'response_color': self._key_to_color.get(response), 'correct_color': ink,
            'variant': trial['variant'], 'training': int(self.training),
            'training_phase': trial.get('training_phase', 'acquisition'),
            'stimulus_kind': trial.get('stimulus_kind', 'word'),
            'mapping_visible': int(trial.get('show_mapping', False)),
            'feedback_enabled': int(trial.get('show_feedback', False)),
            'source_trial': trial.get('source_trial'),
            'temporal_window': trial['temporal_window'], 'is_long_null': trial['is_long_null'],
            'previous_condition': trial['previous_condition'], 'transition': trial['transition'],
            'planned_onset': onset, 'planned_duration': trial['duration'],
            'onset_error': round(actual_onset - onset, 6),
            'fixation_onset': round(actual_offset, 6),
            'planned_fixation_onset': offset, 'fixation_after_sec': trial['fixation_after_sec'],
        })
        self.logger.log(
            f'Essai {trial["trial"]} | {condition} | {trial["stimulus"]} | '
            f't={actual_onset:.4f} | réponse={response} | correct={int(correct)}'
        )
        return record

    def _print_task_stats(self) -> None:
        records = self.data_writer.records
        if not self.training:
            from dataio.stroop_summary import format_stroop_summary
            summary = format_stroop_summary(
                records, self.settings.participant_id, self.design_id,
                sum(block['n_trials'] for block in self.block_sequence),
            )
            for line in summary.splitlines():
                self.logger.log(line)
            return
        correct = sum(row['correct'] for row in records)
        self.logger.ok(f'Stroop : {correct}/{len(records)} réponses correctes')
        if self.training:
            self._training_report = assess_training(
                records, self._discovery_presses, self._color_to_key,
                self.task_config['training']['accuracy_threshold'],
            )
            stem = self.settings.base_name(self.TASK_NAME, self.design_id)
            path = self.settings.task_dir(self.TASK_NAME) / f'{stem}_training_report.json'
            path.write_text(json.dumps(self._training_report, indent=2, ensure_ascii=False),
                            encoding='utf-8')
            self.logger.ok(f'Bilan entraînement : {path.name}')

    def _show_end_screen(self) -> None:
        if not self.training or not self._training_report or not self._training_report['complete']:
            super()._show_end_screen()
            return
        report = self._training_report
        lines = ['BILAN DE L’ENTRAÎNEMENT', '']
        for phase, title in zip(PHASES, ('Avec rappel', 'Sans rappel', 'Stroop')):
            result = report['phases'][phase]
            lines.append(f'{title} : {result["correct"]}/{result["n_trials"]} '
                         f'({result["accuracy"]:.0%})')
        lines += ['', 'Acquis vérifiés' if report['acquired'] else
                  'À reprendre : les associations ou la consigne sont à revoir.',
                  '', 'Seuil pratique : au moins '
                  f'{report["accuracy_threshold"]:.0%} sans rappel et en Stroop,',
                  'avec chaque couleur réussie et les trois boutons vérifiés.',
                  '', self.ADVANCE_PROMPT]
        self.show_text_and_wait('\n'.join(lines))
