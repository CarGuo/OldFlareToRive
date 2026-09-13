#!/usr/bin/env python3
"""Flare vector runtime export -> RML, with explicit unsupported-feature errors.

2026-09-13: Recover legacy vector assets without rasterizing animation frames.
Binary layouts follow the pinned Flare-Flutter readers in validation/vendor;
RML properties were checked against Rive CLI 1.0.2's schema.
This implements the feature subset exercised by the three supplied assets, not a claim
of universal Flare support. Unknown blocks/properties are errors. Bytes beyond
ActorAnimation.read's runtime fields are retained verbatim in the source report.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

from geometry import rounded_parameters, sample_rounded_track, MORPH_SUBDIVISIONS


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, size):
        end = self.offset + size
        if end > len(self.data):
            raise ValueError(f"Truncated Flare block at {self.offset}")
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def number(self, fmt):
        value = struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite numeric value')
        return value

    def u8(self): return self.number('B')
    def u16(self): return self.number('H')
    def u32(self): return self.number('I')
    def f32(self): return self.number('f')
    def f64(self): return self.number('d')
    def vector(self, n): return [self.f32() for _ in range(n)]
    def string(self): return self.take(self.u32()).decode('utf-8')

    def boolean(self):
        value = self.u8()
        if value not in (0, 1):
            raise ValueError(f'Invalid boolean: {value}')
        return bool(value)

    def block(self):
        kind, length = self.u8(), self.u32()
        return kind, Reader(self.take(length))

    def blocks(self):
        while self.offset < len(self.data):
            yield self.block()

    def end(self):
        if self.offset != len(self.data):
            raise ValueError(f'Unconsumed block bytes: {len(self.data)-self.offset}')


NODE_TYPES = {2: 'Node', 100: 'Shape', 101: 'Path', 108: 'Ellipse', 109: 'Rectangle'}
# Flare PropertyTypes -> Rive Node property keys (rive schema Node).
NUMERIC_PROPERTIES = {1: 13, 2: 14, 3: 16, 4: 17, 5: 15, 6: 18}


def read_component(kind, r, index, version):
    c = {'id': index, 'kind': kind, 'name': r.string(), 'parent': r.u16()}
    if kind in NODE_TYPES:
        c.update(zip(('x', 'y', 'rotation', 'scaleX', 'scaleY', 'opacity'), r.vector(6)))
        c['collapsed'] = r.boolean()
        c['clips'] = []
        for _ in range(r.u8()):
            clip = r.u16()
            if version >= 23 and not r.boolean():
                raise ValueError('Subtractive clips are not implemented')
            c['clips'].append(clip)
    if kind == 100:
        c['visible'] = r.boolean()
        # 2026-09-13: pre-v21 Shape.read consumed a reserved blend byte.
        # Upstream 80d0ee9 stopped consuming it, shifting v18 drawOrder.
        # See Flare-Flutter 446f5c7:flare_dart/lib/actor_shape.dart:55-65.
        blend = r.u8()
        c['legacy_blend_byte'] = blend if version < 21 else None
        c['blend'] = blend if version >= 21 else 3
        c['draw_order'] = r.u16()
        if c['blend'] != 3:
            raise ValueError(f'Unsupported blend mode {c["blend"]}')
        if version >= 22 and r.boolean():
            raise ValueError('Stroke-transform semantics are not implemented')
    elif kind == 101:
        if r.u8():
            raise ValueError('Skinned paths are not implemented')
        c['visible'], c['closed'] = r.boolean(), r.boolean()
        c['points'] = []
        for _ in range(r.u16()):
            point = {'type': r.u8(), 'position': r.vector(2)}
            if point['type'] == 0:
                point['radius'] = r.f32()
            elif point['type'] in (1, 2, 3):
                point['in'], point['out'] = r.vector(2), r.vector(2)
            else:
                raise ValueError(f'Unknown point type {point["type"]}')
            c['points'].append(point)
    elif kind in (108, 109):
        c['width'], c['height'] = r.f32(), r.f32()
        if kind == 109:
            c['radius'] = r.f32()
    elif kind == 102:
        c['opacity'], c['color'], c['fill_rule'] = r.f32(), r.vector(4), r.u8()
        if c['fill_rule'] not in (0, 1):
            raise ValueError('Unknown fill rule')
    elif kind in (104, 106):
        c['opacity'] = r.f32()
        c['stops'] = [r.vector(5) for _ in range(r.u8())]
        c['start'], c['end'] = r.vector(2), r.vector(2)
        if kind == 106:
            c['secondary_radius_scale'] = r.f32()
        c['fill_rule'] = r.u8()
        if c['fill_rule'] not in (0, 1):
            raise ValueError('Unknown fill rule')
    elif kind != 2:
        raise ValueError(f'Unsupported component type {kind}: {c["name"]}')
    r.end()
    return c


def read_animation(r, components):
    a = {'name': r.string(), 'fps': r.u8(), 'duration': r.f32(), 'loop': r.boolean(), 'tracks': []}
    for _ in range(r.u16()):
        component = r.u16()
        for _ in range(r.u16()):
            kind, p = r.block()
            if kind not in {*NUMERIC_PROPERTIES, 7, 19, 20, 28}:
                raise ValueError(f'Unsupported animated property {kind}')
            track = {'component': component, 'property': kind, 'keys': []}
            for _ in range(p.u16()):
                key = {'time': p.f64(), 'interpolation': p.u8() if kind != 7 else 0}
                if key['interpolation'] == 2:
                    key['bezier'] = p.vector(4)
                elif key['interpolation'] not in (0, 1):
                    raise ValueError('Unknown interpolation')
                if kind == 7:
                    key['value'] = [{'component': p.u16(), 'order': p.u16()}
                                    for _ in range(p.u16())]
                elif kind == 19:
                    c = components[component - 1]
                    if c['kind'] != 101:
                        raise ValueError('Vertex animation targets a non-path')
                    key['value'] = p.vector(sum(3 if v['type'] == 0 else 6 for v in c['points']))
                elif kind == 20:
                    key['value'] = p.vector(4)
                else:
                    key['value'] = p.f32()
                track['keys'].append(key)
            p.end()
            a['tracks'].append(track)
    # 2026-09-13: The pinned ActorAnimation.read returns after keyed components.
    # Some exports contain a trailer the runtime never reads. Preserve it as
    # opaque provenance; do not invent playback semantics for editor metadata.
    a['runtime_unread_tail_hex'] = r.take(len(r.data) - r.offset).hex()
    r.end()
    return a


def read_flare(data):
    r = Reader(data)
    if r.take(5) != b'FLARE':
        raise ValueError('Expected a binary FLARE runtime file')
    version = r.u32()
    if not 18 <= version < 23:
        raise ValueError(f'Unsupported Flare version {version}')
    boards = []
    for kind, group in r.blocks():
        if kind != 115:
            raise ValueError(f'Unsupported root block {kind}')
        count = group.u16()
        for board_kind, b in group.blocks():
            if board_kind != 114:
                raise ValueError(f'Unsupported artboard block {board_kind}')
            board = {'name': b.string(), 'translation': b.vector(2), 'size': b.vector(2),
                     'origin': b.vector(2), 'clip': b.boolean(), 'color': b.vector(4),
                     'components': [], 'animations': []}
            for block_kind, block in b.blocks():
                if block_kind == 1:
                    num = block.u16()
                    board['components'] = [read_component(k, p, i, version)
                                           for i, (k, p) in enumerate(block.blocks(), 1)]
                    if len(board['components']) != num:
                        raise ValueError('Component count mismatch')
                elif block_kind == 8:
                    num = block.u16()
                    for k, p in block.blocks():
                        if k != 7:
                            raise ValueError(f'Unsupported animation block {k}')
                        board['animations'].append(read_animation(p, board['components']))
                    if len(board['animations']) != num:
                        raise ValueError('Animation count mismatch')
                else:
                    raise ValueError(f'Unsupported artboard content {block_kind}')
            boards.append(board)
        if len(boards) != count:
            raise ValueError('Artboard count mismatch')
    if len(boards) != 1:
        raise ValueError('This converter currently requires exactly one artboard')
    return {'version': version, 'artboards': boards}


def element(parent, tag, **attrs):
    def text(value):
        if isinstance(value, bool): return str(value).lower()
        if isinstance(value, float): return format(value, '.10g')
        return str(value)
    return ET.SubElement(parent, tag, {k: text(v) for k, v in attrs.items()})


def color_hex(color, opacity=1):
    rgba = [math.floor(v * 255 + 0.5) for v in (*color[:3], color[3] * opacity)]
    if any(v < 0 or v > 255 for v in rgba):
        raise ValueError('Color outside supported range')
    return ''.join(f'{v:02X}' for v in (rgba[3], *rgba[:3]))


def ellipse_points(width, height):
    # Flare ActorEllipse uses 0.55, not Rive's ellipse approximation. Emit the
    # original cubic geometry to preserve the silhouette, including clip masks.
    x, y = width / 2, height / 2
    return [{'type': 2, 'position': p, 'in': i, 'out': o} for p, i, o in (
        ((0, -y), (-x*.55, -y), (x*.55, -y)),
        ((x, 0), (x, -y*.55), (x, y*.55)),
        ((0, y), (x*.55, y), (-x*.55, y)),
        ((-x, 0), (-x, y*.55), (-x, -y*.55))) ]


def rectangle_points(c):
    x, y = c['width'] / 2, c['height'] / 2
    radius = min(c['radius'], x, y)
    corners = [(-x, -y), (x, -y), (x, y), (-x, y)]
    if radius <= 0:
        return [dict(type=0, position=p, radius=0) for p in corners]
    # Flare's rounded vertices use 0.55 as well; Rive's native rounded
    # rectangle has different handles. Preserve the original cubic outline.
    points = []
    for i, p in enumerate(corners):
        def towards(q, distance):
            dx, dy = q[0] - p[0], q[1] - p[1]
            length = math.hypot(dx, dy)
            return [p[0] + distance * dx / length, p[1] + distance * dy / length]
        before, after = corners[i-1], corners[(i+1) % 4]
        a, z = towards(before, radius), towards(after, radius)
        points.extend([{'type': 2, 'position': a, 'in': a, 'out': towards(before, radius*.45)},
                       {'type': 2, 'position': z, 'in': towards(after, radius*.45), 'out': z}])
    return points


def to_rml(document):
    b = document['artboards'][0]
    if b['origin'] != [0.0, 0.0]:
        raise ValueError('Non-zero artboard origin is not implemented')
    root = ET.Element('Rive', version='1', kind='fragment')
    root.append(ET.Comment('Generated by convert_flare.py; edit the converter, not this file.'))
    style_id = len(b['components']) + 2
    next_id = style_id + 1
    def allocate():
        nonlocal next_id
        result = f'0:{next_id}'
        next_id += 1
        return result
    art = element(root, 'Artboard', id='0:1', name=b['name'], width=b['size'][0],
                  height=b['size'][1], clip=b['clip'], styleId=f'0:{style_id}')
    element(art, 'LayoutComponentStyle', id=f'0:{style_id}')
    # FlutterActorArtboard.draw ignores the editor background color. Keep the
    # runtime asset transparent; its editor color remains in source.json.
    components = {c['id']: c for c in b['components']}
    children = {i: [] for i in (0, *components)}
    for c in components.values():
        if c['parent'] not in children:
            raise ValueError(f'Missing parent {c["parent"]}')
        children[c['parent']].append(c['id'])
    visiting, visited = set(), set()
    def validate_tree(i):
        if i in visiting:
            raise ValueError('Cyclic component hierarchy')
        if i in visited:
            return
        visiting.add(i)
        for child in children[i]: validate_tree(child)
        visiting.remove(i)
        visited.add(i)
    for i in children: validate_tree(i)
    for c in components.values():
        if c['kind'] != 100:
            continue
        ancestor = c['parent']
        while ancestor:
            if components[ancestor]['kind'] == 100:
                raise ValueError('Nested drawables need separate DrawRules scope handling')
            ancestor = components[ancestor]['parent']
    def rid(i): return f'0:{i+1}'
    def order(i):
        own = [components[i]['draw_order']] if components[i]['kind'] == 100 else []
        return max(own + [order(j) for j in children[i]], default=-1)
    for ids in children.values():
        ids.sort(key=order, reverse=True)
    emitted = {}
    paint_targets, opacity_targets, vertex_targets = {}, {}, {}
    drawables = {}
    animated_opacity = {t['component'] for a in b['animations'] for t in a['tracks']
                        if t['property'] == 28}
    rounded_morphs = {t['component'] for a in b['animations'] for t in a['tracks']
                      if t['property'] == 19 and any(any(v != 0 for v in k['value'][2::3]) for k in t['keys'])}

    def emit(parent, i):
        c = components[i]
        common = {'id': rid(i), 'name': c['name']}
        if c['kind'] in NODE_TYPES:
            common.update({k: c[k] for k in ('x', 'y', 'rotation', 'scaleX', 'scaleY', 'opacity')})
            if c['collapsed']:
                common['opacity'] = 0
        kind = c['kind']
        if kind in (102, 104, 106):
            p = components[c['parent']]
            node = element(parent, 'Fill', **common, fillRule=('evenOdd', 'nonZero')[c['fill_rule']],
                           isVisible=p['visible'])
            if kind == 102:
                paint_id = allocate()
                element(node, 'SolidColor', id=paint_id, colorValue=color_hex(c['color'], 1 if i in animated_opacity else c['opacity']))
                paint_targets[i] = [(paint_id, 37)]
            else:
                paint_id = allocate()
                start, end = c['start'], c['end']
                if kind == 106 and c['secondary_radius_scale'] != 1:
                    raise ValueError('Elliptical radial gradients are not implemented')
                gradient = element(node, 'RadialGradient' if kind == 106 else 'LinearGradient',
                                   id=paint_id, startX=start[0], startY=start[1],
                                   endX=end[0], endY=end[1], opacity=c['opacity'])
                opacity_targets[i] = (paint_id, 46)
                stops = c['stops']
                paint_targets[i] = []
                for stop in stops:
                    stop_id = allocate()
                    element(gradient, 'GradientStop', id=stop_id, colorValue=color_hex(stop[:4]), position=stop[4])
                    paint_targets[i].append((stop_id, 38))
        elif kind in (101, 108, 109):
            node = element(parent, 'PointsPath', **common,
                           isClosed=c.get('closed', True), pathFlags=0 if c.get('visible', True) else 1)
            points = (c['points'] if kind == 101 else rectangle_points(c) if kind == 109
                      else ellipse_points(c['width'], c['height']))
            if kind == 101 and i not in rounded_morphs and any(
                    p['type'] == 0 and p['radius'] != 0 for p in points):
                raise ValueError('Static rounded path corners need Flare-specific geometry')
            vertex_targets[i] = []
            if i in rounded_morphs:
                if not c['closed'] or any(p['type'] != 0 for p in points):
                    raise ValueError('Rounded morphs require closed straight-vertex paths')
                values = [v for p in points for v in (*p['position'], p['radius'])]
                for params in rounded_parameters(values):
                    vertex_id = allocate()
                    vertex_targets[i].append(vertex_id)
                    element(node, 'CubicDetachedVertex', id=vertex_id,
                            **dict(zip(('x', 'y', 'inRotation', 'inDistance', 'outRotation', 'outDistance'), params)))
                points = []
            for point in points:
                vertex_id = allocate()
                vertex_targets[i].append(vertex_id)
                x, y = point['position']
                if point['type'] == 0:
                    element(node, 'StraightVertex', id=vertex_id, x=x, y=y, radius=point['radius'])
                else:
                    handles = {}
                    for direction in ('in', 'out'):
                        dx, dy = point[direction][0] - x, point[direction][1] - y
                        handles[direction+'Rotation'] = math.atan2(dy, dx)
                        handles[direction+'Distance'] = math.hypot(dx, dy)
                    element(node, 'CubicDetachedVertex', id=vertex_id, x=x, y=y, **handles)
        elif kind == 100:
            fills = [components[j] for j in children[i] if components[j]['kind'] in (102, 104, 106)]
            animated = [f for f in fills if f['id'] in animated_opacity and f['kind'] == 102]
            if animated:
                if len(fills) != 1 or any(components[j]['kind'] == 100 for j in children[i]):
                    raise ValueError('Animated solid paint opacity requires a single-fill shape without nested drawables')
                # 2026-09-13: Separate transform opacity from paint opacity.
                # A nested drawable is the native Rive equivalent; a uniform
                # gradient would introduce shader dithering into solid fills.
                node = element(parent, 'Node', **common)
                drawable = element(node, 'Shape', id=allocate(), name=c['name']+' paint', opacity=animated[0]['opacity'])
                opacity_targets[animated[0]['id']] = (drawable.get('id'), 18)
            else:
                node = drawable = element(parent, 'Shape', **common)
            drawables[i] = drawable
        else:
            node = element(parent, NODE_TYPES[kind], **common)
        emitted[i] = node
        if len(c.get('clips', [])) > 1:
            raise ValueError('Multiple clip sources in one Flare group are not implemented')
        for clip in c.get('clips', []):
            if clip not in components:
                raise ValueError(f'Missing clip source {clip}')
            def clip_shapes(i):
                own = [i] if components[i]['kind'] == 100 else []
                return own + [s for j in children[i] for s in clip_shapes(j)]
            shapes = clip_shapes(clip)
            if not shapes:
                raise ValueError('Empty clipping groups are not implemented')
            if any(components[s]['collapsed'] for s in shapes):
                raise ValueError('Collapsed clip sources are not implemented')
            # Pre-v23 Flare combines multi-shape clip groups in a non-zero
            # path. A single shape keeps its first fill's winding rule.
            rule = 1
            if len(shapes) == 1:
                fills = [components[j] for j in children[shapes[0]]
                         if components[j]['kind'] in (102, 104, 106)]
                if fills: rule = fills[0]['fill_rule']
            element(node, 'ClippingShape', sourceId=rid(clip),
                    fillRule=('evenOdd', 'nonZero')[rule])
        for child in children[i]:
            emit(drawables.get(i, node), child)

    for i in children[0]: emit(art, i)
    # Flare's drawable order is global and may interleave transform subtrees.
    # A complete acyclic DrawRules chain preserves it without flattening away
    # animated parents. Rive's "after" places a shape behind the target.
    shapes = sorted((c for c in components.values() if c['kind'] == 100),
                    key=lambda c: c['draw_order'], reverse=True)
    dynamic_order = any(t['property'] == 7 for a in b['animations'] for t in a['tracks'])
    draw_rules, draw_targets = {}, {}
    # Immutable rank anchors avoid dependency cycles across *all* DrawTargets,
    # including inactive ones. Every animated shape targets a fixed rank;
    # movable shapes never depend on each other's alternate permutations.
    rank_anchors = {}
    if dynamic_order:
        for rank in range(len(shapes), 0, -1):
            rank_anchors[rank] = element(art, 'Shape', id=allocate(), name=f'Draw rank {rank}').get('id')
    for index, current in enumerate(shapes):
        if index == 0 and not dynamic_order:
            continue
        previous_id = rank_anchors[len(shapes)-index] if dynamic_order else drawables[shapes[index-1]['id']].get('id')
        rules_id, target_id = allocate(), allocate()
        rules = element(drawables[current['id']], 'DrawRules', id=rules_id, drawTargetId=target_id)
        element(rules, 'DrawTarget', id=target_id, drawableId=previous_id, placementValue='after')
        draw_rules[current['id']] = rules
        draw_targets[(current['id'], previous_id)] = target_id
    for a in b['animations']:
        animation_id = allocate()
        fps = a['fps'] * (MORPH_SUBDIVISIONS if any(t['component'] in rounded_morphs and t['property'] == 19 for t in a['tracks']) else 1)
        def frame(time):
            value = time * fps
            if not math.isclose(value, round(value), abs_tol=1e-4):
                raise ValueError(f'Non-integral keyframe {value}; avoid silently quantizing')
            return round(value)
        animation = element(art, 'LinearAnimation', id=animation_id, name=a['name'], fps=fps,
                            duration=round(a['duration']*a['fps'])*fps//a['fps'], loopValue='loop' if a['loop'] else 'oneShot')
        keyed_objects = {}
        def emit_track(target, property_key, keys, key_type='KeyFrameDouble'):
            if target not in keyed_objects:
                keyed_objects[target] = element(animation, 'KeyedObject', objectId=target)
            prop = element(keyed_objects[target], 'KeyedProperty', propertyKey=property_key)
            for key in keys:
                node = element(prop, key_type, frame=frame(key['time']), value=key['value'],
                               interpolationType=('hold', 'linear', 'cubic')[key['interpolation']])
                if key['interpolation'] == 2:
                    element(node, 'CubicEaseInterpolator', **dict(zip(('x1', 'y1', 'x2', 'y2'), key['bezier'])))

        for track in a['tracks']:
            cid, kind, keys = track['component'], track['property'], track['keys']
            c = components[cid]
            if kind in NUMERIC_PROPERTIES:
                if c['kind'] not in NODE_TYPES:
                    raise ValueError('Numeric track targets a non-node')
                emit_track(rid(cid), NUMERIC_PROPERTIES[kind], keys)
            elif kind == 28:
                emit_track(*opacity_targets[cid], keys)
            elif kind == 20:
                opacity = c['opacity'] if cid not in animated_opacity else 1
                values = [{**k, 'value': color_hex(k['value'], opacity)} for k in keys]
                for target, prop in paint_targets[cid]:
                    emit_track(target, prop, values, 'KeyFrameColor')
            elif kind == 19:
                if cid in rounded_morphs:
                    baked = sample_rounded_track(keys, fps)
                    for vi, target in enumerate(vertex_targets[cid]):
                        for axis, prop in enumerate((24, 25, 84, 85, 86, 87)):
                            emit_track(target, prop, [{**k, 'value': k['value'][vi][axis]} for k in baked])
                    continue
                if any(p['type'] != 0 or p['radius'] != 0 for p in c['points']):
                    raise ValueError('Only straight, unrounded path morphs are implemented')
                for vi, target in enumerate(vertex_targets[cid]):
                    if any(k['value'][vi*3+2] != 0 for k in keys):
                        raise ValueError('Animated corner radii need Flare-specific geometry')
                    for axis in (0, 1):
                        emit_track(target, 24 + axis, [{**k, 'value': k['value'][vi*3+axis]} for k in keys])
            elif kind == 7:
                values = {s['id']: [] for s in shapes}
                rest = {s['id']: s['draw_order'] for s in shapes}
                for key in keys:
                    order = {**rest, **{v['component']: v['order'] for v in key['value']}}
                    if set(order) != set(rest) or len(set(order.values())) != len(order):
                        raise ValueError('Draw order must reference unique drawable ranks')
                    for rank, shape_id in enumerate(sorted(order, key=order.get), 1):
                        target_anchor = rank_anchors[rank]
                        pair = (shape_id, target_anchor)
                        if pair not in draw_targets:
                            draw_targets[pair] = allocate()
                            element(draw_rules[shape_id], 'DrawTarget', id=draw_targets[pair],
                                    drawableId=target_anchor, placementValue='after')
                        values[shape_id].append({**key, 'value': draw_targets[pair]})
                for shape_id, values in values.items():
                    emit_track(draw_rules[shape_id].get('id'), 121, values, 'KeyFrameId')
        # A standard timeline state keeps the file usable in current Rive widgets.
        sm_id, state_id = allocate(), allocate()
        sm = element(art, 'StateMachine', id=sm_id, name=a['name'])
        layer = element(sm, 'StateMachineLayer', name='Playback')
        element(layer, 'AnyState', x=0, y=-120)
        element(layer, 'ExitState', x=220, y=-120)
        entry = element(layer, 'EntryState', x=0, y=0)
        element(entry, 'StateTransition', stateToId=state_id)
        element(layer, 'AnimationState', id=state_id, animationId=animation_id, x=220, y=0)
        if 'defaultStateMachineId' not in art.attrib:
            art.set('defaultStateMachineId', sm_id)
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='unicode') + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    data = args.input.read_bytes()
    document = read_flare(data)
    rml = to_rml(document)
    args.project.mkdir(parents=True, exist_ok=True)
    (args.project / 'scene.rml').write_text(rml)
    report = {'source': args.input.name, 'sha256': hashlib.sha256(data).hexdigest(), **document}
    (args.project / 'source.json').write_text(json.dumps(report, indent=2) + '\n')
    b = document['artboards'][0]
    print(json.dumps({'version': document['version'], 'size': b['size'],
                      'components': dict(Counter(c['kind'] for c in b['components'])),
                      'animations': b['animations']}, indent=2))


if __name__ == '__main__':
    main()
