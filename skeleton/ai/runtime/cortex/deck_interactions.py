"""Model, navigation, and organism interactions used by the operator deck."""
from __future__ import annotations

import random

from skeleton.cortex.dodeca import FACES


class DeckInteractions:
    def _model(self):
        if self.neo is None:
            from skeleton.cortex.live import live_cortex
            self.neo = live_cortex()
        return self.neo

    def _organism(self):
        if not hasattr(self, '_organism_state'):
            from skeleton.distributed.galaxy.system import GalaxySystem
            from skeleton.organism.organismer import Organismer
            self._organism_state = Organismer(root=self.root, galaxy=GalaxySystem(root=self.root))
        return self._organism_state

    def speak(self, stimulus, context=None):
        from skeleton.cortex.refs import reference_scope
        with reference_scope(self.root):
            from skeleton.cortex.antiplag import guard
            from skeleton.cortex.laws import check
            from skeleton.cortex.refs import lookup, record_provenance
            ref = lookup(stimulus)
            model = self._model()
            improvement = None
            if ref:
                record_provenance(ref, action='lookup', root=self.root)
                improvement = model.ascend(stimulus)
                text = str(ref.get('dialect') or ref.get('era') or '')
                guard(text, str(ref['title']))
            else:
                thought = model.think(stimulus, context=context)
                text = str(getattr(getattr(thought, 'amalgam', None), 'text', ''))
            card = check({'kind': 'speak', 'hit': int(ref is not None), 'amalgam': text,
                          'improve': improvement, 'stored_prose': 0, 'law': 'ok'})
            self.last_ref = ref
            self.traces.append(card)
            self.traces[:] = self.traces[-128:]
            return card


    def plan(self, stimulus, *, repair=False):
        from skeleton.cortex.refs import reference_scope
        with reference_scope(self.root):
            from skeleton.cortex.era_bind import resolve
            from skeleton.intelligence.plan_repair import attempt_plan_repair
            from skeleton.organism.quality_state import append_quality
            card = resolve(stimulus)
            quality = self.verify_plan(card, vision=stimulus)
            append_quality({**quality, 'surface': 'plan'}, root=self.root)
            if repair and not quality['accepted']:
                card['repair'] = attempt_plan_repair(card, vision=stimulus, root=self.root)
            card['quality'] = quality
            card['quality_stats'] = self.verifiers['plan'].stats()
            return card


    def pick(self, position):
        if isinstance(position, bool) or not isinstance(position, int) or not 0 <= position < len(FACES):
            raise ValueError('position must identify one of the twelve faces')
        self._position = position
        return {'position': position, 'face': FACES[position], 'seed': self._walk_seed}

    def walk(self, n=1):
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 128:
            raise ValueError('walk length must be between 1 and 128')
        steps = [self.pick(self._navigation.randrange(len(FACES))) for _ in range(n)]
        return {**steps[-1], 'walk': steps}

    def genos(self, stimulus='plan tensor ttk lattice'):
        return self._model().genos(stimulus)

    def galaxy(self, stimulus, *, sleep=False):
        org = self._organism()
        return {**org.galaxy.pulse(stimulus, sleep=sleep), "G": org.G}

    def social(self, stimulus=''):
        from skeleton.research.social.sota import sota_card
        return sota_card(stimulus, G=self._organism().G)

    def organismer(self, stimulus, **kwargs):
        return self._organism().step(stimulus, neo=self._model(), **kwargs)

    def product(self):
        from skeleton.organism.product import product_card
        return product_card(self._organism(), neo=self.neo, deck=self)

    def _init_interactions(self):
        self.last_ref = None
        self.traces = []
        self._walk_seed = 8847291
        self._navigation = random.Random(self._walk_seed)
        self._position = 0
