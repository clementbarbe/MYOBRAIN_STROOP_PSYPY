"""Response-key validation shared by the task and the hardware check."""

from config.constants import ADVANCE_KEY, QUIT_KEY


def response_keys(config: dict, mode: str, trigger_key: str) -> dict:
    mapping = config.get(f'response_keys_{mode}', {})
    if set(mapping) != {'rouge', 'bleu', 'vert'}:
        raise ValueError(f'response_keys_{mode} doit définir rouge, bleu et vert.')
    values = list(mapping.values())
    if any(not isinstance(key, str) or not key.strip() or key != key.strip().lower() for key in values):
        raise ValueError('Les touches doivent être des noms PsychoPy en minuscules ; '
                         'mettre les chiffres entre guillemets, par exemple "1".')
    if len(set(values)) != 3:
        raise ValueError('Chaque couleur doit avoir une touche différente.')
    if not isinstance(trigger_key, str) or not trigger_key.strip() or trigger_key != trigger_key.strip().lower():
        raise ValueError('trigger_key doit être un nom de touche PsychoPy en minuscules, par exemple "t" ou "5".')
    if trigger_key in (ADVANCE_KEY, QUIT_KEY):
        raise ValueError('Le trigger ne peut pas utiliser la touche de validation ou de sortie.')
    conflicts = set(values) & {trigger_key, ADVANCE_KEY, QUIT_KEY}
    if conflicts:
        raise ValueError(f'Touche de réponse réservée au trigger/contrôle : {sorted(conflicts)}')
    return dict(mapping)
