"""Structural regressions complement the independent runtime frame comparison."""
import copy
import math
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET

from convert_flare import read_flare, to_rml
from geometry import rounded_parameters, sample_rounded_track, cartesian

SOURCE = Path(__file__).resolve().parent / 'sources/loading_world_now.flr'


class ConversionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = SOURCE.read_bytes()
        cls.document = read_flare(cls.data)

    def test_original_animation_contract(self):
        board = self.document['artboards'][0]
        self.assertEqual(board['size'], [1024, 768])
        self.assertEqual(len(board['components']), 698)
        animation, = board['animations']
        self.assertEqual((animation['name'], animation['fps'], animation['duration']),
                         ('Earth Moving', 60, 10))
        self.assertTrue(animation['loop'])
        self.assertEqual([t['component'] for t in animation['tracks']], [13, 130])
        self.assertEqual([k['time'] * 60 for k in animation['tracks'][1]['keys']],
                         [0, 299, 300, 600])

    def test_global_draw_order_is_acyclic_and_complete(self):
        root = ET.fromstring(to_rml(self.document))
        shapes = {s.get('id'): s for s in root.iter('Shape')}
        self.assertEqual(len(shapes), 175)
        expected = sorted((c for c in self.document['artboards'][0]['components']
                           if c['kind'] == 100), key=lambda c: -c['draw_order'])
        first = shapes[f'0:{expected[0]["id"]+1}']
        self.assertIsNone(first.find('DrawRules'))
        for front, back in zip(expected, expected[1:]):
            rule = shapes[f'0:{back["id"]+1}'].find('DrawRules')
            target = rule.find('DrawTarget')
            self.assertEqual(target.get('drawableId'), f'0:{front["id"]+1}')
            self.assertEqual(target.get('placementValue'), 'after')

    def test_state_machine_is_importable_and_animation_keeps_jump(self):
        root = ET.fromstring(to_rml(self.document))
        layer = root.find('.//StateMachineLayer')
        for tag in ['EntryState', 'AnyState', 'ExitState', 'AnimationState']:
            self.assertIsNotNone(layer.find(tag))
        animated = root.findall('.//KeyedObject')
        self.assertEqual([k.get('frame') for k in animated[1].iter('KeyFrameDouble')],
                         ['0', '299', '300', '600'])

    def test_truncated_and_unknown_data_fail(self):
        for data in [self.data[:-1], b'RIVE' + self.data[4:],
                     self.data + struct.pack('<BI', 255, 0)]:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                read_flare(data)

    def test_new_clip_semantics_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'version 23'):
            read_flare(self.data[:5] + struct.pack('<I', 23) + self.data[9:])

    def test_cycle_and_unsupported_clip_group_fail(self):
        for mutation, message in [(lambda b: b['components'][0].update(parent=1), 'Cyclic'),
                                  (lambda b: b['components'][12].update(clips=[10, 123]), 'Multiple clip')]:
            document = copy.deepcopy(self.document)
            mutation(document['artboards'][0])
            with self.assertRaisesRegex(ValueError, message):
                to_rml(document)

    def test_subframe_keys_are_not_silently_quantized(self):
        document = copy.deepcopy(self.document)
        document['artboards'][0]['animations'][0]['tracks'][0]['keys'][0]['time'] = 0.001
        with self.assertRaisesRegex(ValueError, 'Non-integral keyframe'):
            to_rml(document)


class AdditionalAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = SOURCE.parent
        cls.space = read_flare((root / 'Space-Demo.flr').read_bytes())
        cls.logo = read_flare((root / 'flare_flutter_logo_.flr').read_bytes())

    def test_v18_shape_byte_alignment_and_animation_contract(self):
        board = self.space['artboards'][0]
        self.assertEqual(self.space['version'], 18)
        self.assertEqual(board['size'], [818, 463])
        self.assertEqual(len(board['components']), 487)
        self.assertEqual([(c['id'], c['draw_order']) for c in board['components']
                          if c['kind'] == 100][:5], [(3, 1), (6, 2), (9, 3), (14, 4), (17, 15)])
        self.assertEqual([a['name'] for a in board['animations']],
                         ['idle comet', 'idle', 'loading', 'success', 'pull'])

    def test_dynamic_order_matches_source_permutations_without_moving_targets(self):
        for document in (self.space, self.logo):
            root = ET.fromstring(to_rml(document))
            by_id = {e.get('id'): e for e in root.iter() if e.get('id')}
            shapes = {c['id']: c for c in document['artboards'][0]['components'] if c['kind'] == 100}
            # Every possible target is immutable, not another animated shape.
            for target in root.iter('DrawTarget'):
                anchor = by_id[target.get('drawableId')]
                self.assertTrue(anchor.get('name').startswith('Draw rank '))
                self.assertIsNone(anchor.find('DrawRules'))
            for source in document['artboards'][0]['animations']:
                animation = root.find(f'.//LinearAnimation[@name="{source["name"]}"]')
                fps = int(animation.get('fps'))
                for track in source['tracks']:
                    if track['property'] != 7:
                        continue
                    for key in track['keys']:
                        orders = {i: s['draw_order'] for i, s in shapes.items()}
                        orders.update({v['component']: v['order'] for v in key['value']})
                        expected = sorted(orders, key=orders.get)
                        for rank, cid in enumerate(expected, 1):
                            node = by_id[f'0:{cid+1}']
                            rule = node.find('.//DrawRules')
                            keyed = animation.find(f'KeyedObject[@objectId="{rule.get("id")}"]')
                            frame = keyed.find(f'.//KeyFrameId[@frame="{round(key["time"]*fps)}"]')
                            target = by_id[frame.get('value')]
                            self.assertEqual(by_id[target.get('drawableId')].get('name'), f'Draw rank {rank}')

    def test_logo_color_and_paint_opacity_remain_independent(self):
        root = ET.fromstring(to_rml(self.logo))
        self.assertFalse(list(root.iter('LinearGradient')))
        self.assertEqual(len(list(root.iter('SolidColor'))), 3)
        for source in self.logo['artboards'][0]['animations']:
            animation = root.find(f'.//LinearAnimation[@name="{source["name"]}"]')
            self.assertEqual(animation.get('loopValue'), 'oneShot')
            self.assertAlmostEqual(int(animation.get('duration')) / int(animation.get('fps')),
                                   source['duration'], places=6)
            for track in source['tracks']:
                if track['property'] != 28:
                    continue
                fill = root.find(f'.//Fill[@id="0:{track["component"]+1}"]')
                parent = next(s for s in root.iter('Shape') if fill in list(s))
                keyed = animation.find(f'KeyedObject[@objectId="{parent.get("id")}"]/KeyedProperty[@propertyKey="18"]')
                # RML decimal text must round-trip the source float32, not
                # preserve Python's incidental double representation of it.
                self.assertEqual([struct.pack('<f', float(k.get('value'))) for k in keyed],
                                 [struct.pack('<f', k['value']) for k in track['keys']])

    def test_flare_corner_uses_full_edge_clamp_and_point_55_handles(self):
        points = rounded_parameters([0, 0, 7, 10, 0, 0, 10, 10, 0, 0, 10, 0])
        self.assertEqual(points[0][:2], [0, 7])
        self.assertEqual(points[1][:2], [7, 0])
        for actual, expected in zip(cartesian(points[0]), [0, 7, 0, 7, 0, 3.15]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(cartesian(points[1]), [7, 0, 3.15, 0, 7, 0]):
            self.assertAlmostEqual(actual, expected)

    def test_rounded_morph_at_independent_off_grid_times(self):
        keys = [dict(time=0, interpolation=1, value=[0, 0, 0, 10, 0, 0, 10, 10, 0, 0, 10, 0]),
                dict(time=1, interpolation=1, value=[0, 0, 6, 9, 8, 0, 10, 10, 0, 0, 10, 0])]
        baked = sample_rounded_track(keys, 61440)
        self.assertGreater(len(baked), 2)
        self.assertEqual([baked[0]['time'], baked[-1]['time']], [0, 1])
        for time in (.0137, .137, .431, .713, .9971):
            left, right = next((a, b) for a, b in zip(baked, baked[1:]) if a['time'] <= time <= b['time'])
            f = (time-left['time']) / (right['time']-left['time'])
            actual = cartesian([a+(b-a)*f for a, b in zip(left['value'][1], right['value'][1])])
            radius, dx, dy = 6*time, 10-time, 8*time
            length = math.hypot(dx, dy)
            x, y = radius*dx/length, radius*dy/length
            # Analytic Flare exit vertex and its incoming handle on that edge.
            expected = [x, y, x*.45, y*.45, x, y]
            self.assertLess(max(abs(a-b) for a, b in zip(actual, expected)), .001)

    def test_unsupported_static_rounding_fails_instead_of_changing_geometry(self):
        document = copy.deepcopy(self.logo)
        document['artboards'][0]['animations'] = []
        path = next(c for c in document['artboards'][0]['components'] if c['kind'] == 101)
        path['points'][0]['radius'] = 10
        with self.assertRaisesRegex(ValueError, 'Static rounded path'):
            to_rml(document)


if __name__ == '__main__':
    unittest.main()
