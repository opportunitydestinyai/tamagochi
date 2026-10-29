#!/usr/bin/env python3
"""Demonstrate local actions/progression using a simulated clock.

Run from the module root: PYTHONPATH=. python3 tests/evolution_scenario.py
The default scenario uses default rules; rounding-edge uses a test configuration.
No bridge event, real user data, external service, or media is used. A supplied
--seed-dir must be a new empty private directory; it is useful for browser tests.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pet.model import ExperienceEngine
from pet.repository import PetRepository
from pet.service import PetEngine


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def next_day(self):
        self.now += timedelta(days=1)


def describe(label, state, *, gained=None):
    keys = ('level', 'xp', 'mood', 'energy', 'happiness', 'curiosity', 'knowledge', 'bond', 'trust')
    result = {key: state[key] for key in keys}
    result['stage'] = state['stage']['name']
    result['specialization'] = state['specialization']
    if gained is not None:
        result['xpAwarded'] = gained
    print(f'{label}: {json.dumps(result, ensure_ascii=False, sort_keys=True)}')


def run(data_dir: Path, target: str):
    data_dir = data_dir.resolve()
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(data_dir.iterdir()):
        raise ValueError('Use um diretório novo e vazio; nenhum banco existente será sobrescrito.')
    # Simulated dates precede real time, so a later browser run can safely
    # reconcile elapsed time. Only rounding-edge uses a test configuration.
    long_levels = {'level10-edge': 10, 'level20-edge': 20, 'level35-edge': 35, 'level50-edge': 50}
    offset = 600 if target in long_levels else (11 if target in ('stage5', 'stage5-edge') else (8 if target == 'rounding-edge' else 2))
    clock = Clock(datetime.now(timezone.utc) - timedelta(days=offset))
    engine = PetEngine(PetRepository(data_dir / 'pet.sqlite3', clock=clock), clock=clock)
    count = 0
    state = engine.snapshot(run_due=False)

    def action(kind, *, meaningful=False, label=None):
        nonlocal count, state
        count += 1
        result = engine.perform_action(kind, f'scenario-action-{count}', meaningful=meaningful)
        state = result['state']
        if label:
            describe(label, state, gained=result['xpAwarded'])
        return result

    def needs_energy(kind):
        cost = -min(0, engine.get_config()['actionEffects'][kind].get('energy', 0))
        if state['energy'] < cost:
            action('REST')

    if target in long_levels:
        # Default rules, actual actions and ledger entries, but simulated days:
        # no real user history and no manually edited XP value.
        target_level = long_levels[target]
        threshold = ExperienceEngine.threshold(target_level, engine.get_config())
        days = 0
        while state['xp'] < threshold - 13:
            days += 1
            for kind in ('REST', *('LEARN',) * 5, *('CREATE',) * 5, *('CHAT',) * 3):
                if state['xp'] >= threshold - 13:
                    break
                old_stage = state['stage']['key']
                needs_energy(kind)
                action(kind, meaningful=(kind == 'CHAT'))
                if state['stage']['key'] != old_stage:
                    print(f"Dia simulado {days}: {state['xp']} XP, nível {state['level']}, estágio {state['stage']['name']}.")
            clock.next_day()
            if days > 600:
                raise AssertionError(f'Não foi possível preparar o cenário simulado de nível {target_level}.')
        with contextlib.closing(engine.repo.connect()) as conn:
            events = conn.execute('SELECT COUNT(*) FROM pet_events').fetchone()[0]
        assert state['level'] == target_level - 1
        assert 0 < threshold - state['xp'] <= 13
        if target_level == 50:
            assert state['stage']['key'] == 'EXPLORER' and events > 10000
        print(f"Histórico simulado: {days} dias, {count} ações, {events} eventos; XP {state['xp']} de {threshold}, nível {state['level']}.")
        return

    if target == 'rounding-edge':
        # A separate configured fixture reaches a wide level interval quickly,
        # using genuine grants/ledger entries rather than editing the state.
        config = engine.get_config()
        config['xpFormula']['scale'] = 1000
        config['xpGains'].update(FIRST_INTERACTION=0, LEARN=100, CREATIVE=95)
        config['xpDailyLimits']['LEARN'] = 10
        config['dailyXpCap'] = 1000
        state = engine.update_config(config)['state']
        print('Cenário de arredondamento com configuração de teste e dias simulados.')
        for _ in range(5):
            for _ in range(10):
                needs_energy('LEARN')
                action('LEARN')
            clock.next_day()
        needs_energy('LEARN')
        action('LEARN')
        needs_energy('CREATE')
        action('CREATE')
        describe('A um XP do nível seguinte', state)
        print('Progresso:', json.dumps(state['progress'], ensure_ascii=False, sort_keys=True))
        assert state['xp'] == 5195 and state['level'] == 3
        assert state['progress']['percent'] == 99.9
        return

    print('Cenário local com regras padrão; o relógio avança de forma simulada.')
    describe('Inicial', state)
    for kind in ('PLAY', 'REST', 'EXPLORE', 'LEARN', 'CREATE'):
        action(kind, label=kind)
    action('CHAT', meaningful=True, label='CHAT significativo')
    for kind in ('LEARN', 'CREATE'):
        for _ in range(4):
            needs_energy(kind)
            action(kind)
    for _ in range(2):
        action('CHAT', meaningful=True)
    describe('Fim do dia simulado 1', state)
    assert state['xp'] == 91

    clock.next_day()
    action('REST')
    action('CHAT', meaningful=True)
    if target == 'level1-edge':
        describe('Nível 1 · antes da transição', state)
        assert state['xp'] == 98 and state['level'] == 1
        return
    action('CHAT', meaningful=True)
    describe('Nível 2 · limiar exato', state)
    print('Progresso no nível 2:', json.dumps(state['progress'], ensure_ascii=False, sort_keys=True))
    assert state['xp'] == 100 and state['level'] == 2
    if target == 'level2':
        return

    # In the same simulated day, reach exactly 150 XP without external events.
    for _ in range(5):
        needs_energy('LEARN')
        action('LEARN')
    needs_energy('CREATE')
    action('CREATE')
    action('CHAT', meaningful=True)  # third and last XP-eligible chat of this day
    describe('Nível 2 · 150 XP acumulados', state)
    print('Progresso intermediário:', json.dumps(state['progress'], ensure_ascii=False, sort_keys=True))
    assert state['xp'] == 150 and state['progress']['intoLevel'] == 50
    if target == 'level2-mid':
        return

    # Complete day 2, then advance one day at a time. Only actions in the local
    # pet UI are used, respecting their energy cost and daily XP limits.
    for _ in range(4):
        needs_energy('CREATE')
        action('CREATE')
    print(f"Dia simulado 2: XP={state['xp']}; nível={state['level']}; estágio={state['stage']['name']}")
    for day in range(3, 20):
        clock.next_day()
        action('REST')  # includes the once-per-day first interaction XP
        for kind in ('LEARN', 'CREATE'):
            for _ in range(5):
                needs_energy(kind)
                action(kind)
                if target == 'stage5-edge' and state['xp'] == 797:
                    describe('Antes da transição para Descoberta', state)
                    assert state['level'] == 4 and state['stage']['key'] == 'AWAKENING'
                    return
                if state['level'] >= 5:
                    break
            if state['level'] >= 5:
                break
        if state['level'] >= 5:
            break
        for _ in range(3):
            action('CHAT', meaningful=True)
        print(f"Dia simulado {day}: XP={state['xp']}; nível={state['level']}; estágio={state['stage']['name']}")
    else:
        raise AssertionError('O estágio de descoberta não foi alcançado dentro do limite do cenário.')

    describe('Evolução para Descoberta', state)
    changes = [event for event in engine.events(limit=500)
               if event['eventType'] == 'PET_EVOLUTION_UNLOCKED' and event['payload'].get('axis') == 'LEVEL']
    assert state['stage']['key'] == 'DISCOVERY'
    assert any(event['payload']['stage'] == 'DISCOVERY' for event in changes)
    print('Evento de evolução:', json.dumps(changes[-1]['payload'], ensure_ascii=False, sort_keys=True))
    print('OK — progressão local com dias simulados e sem evento externo.')


def main():
    parser = argparse.ArgumentParser(description='Cenário descartável de evolução local.')
    parser.add_argument('--seed-dir', type=Path, help='Diretório novo e vazio, para teste de navegador')
    parser.add_argument('--target', choices=('level1-edge', 'level2', 'level2-mid', 'stage5', 'stage5-edge', 'rounding-edge', 'level10-edge', 'level20-edge', 'level35-edge', 'level50-edge'), default='stage5')
    args = parser.parse_args()
    if args.seed_dir:
        run(args.seed_dir, args.target)
    else:
        with tempfile.TemporaryDirectory(prefix='muse-evolution-') as directory:
            run(Path(directory), args.target)


if __name__ == '__main__':
    main()
