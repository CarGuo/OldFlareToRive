"""Flare rounded morphs, adaptively expressed as ordinary Rive cubic vertices.

2026-09-13: Rive rounds polygon corners using a different radius clamp and
control-point formula. Mapping the radius property directly changes the bird's
silhouette. Follow Flare's 0.55 geometry and subdivide only where interpolation
of Rive's polar handles deviates from that geometry. No bitmap frames/scripts.
"""
import math

MORPH_SUBDIVISIONS = 1024  # dyadic time grid per original frame, no key quantization
MORPH_TOLERANCE = 0.001  # artboard units, checked at 1/4, 1/2, 3/4 of each interval


def rounded_parameters(values):
    vertices = [values[i:i+3] for i in range(0, len(values), 3)]
    previous = vertices[-1][:2]
    result = []
    for i, (x, y, radius) in enumerate(vertices):
        following = vertices[(i+1) % len(vertices)]
        dx, dy = previous[0]-x, previous[1]-y
        ex, ey = following[0]-x, following[1]-y
        before_length, after_length = math.hypot(dx, dy), math.hypot(ex, ey)
        if radius > 0 and min(before_length, after_length) == 0:
            raise ValueError('Degenerate rounded Flare corner')
        r = min(before_length, after_length, max(0, radius))
        ux, uy = (dx/before_length, dy/before_length) if before_length else (0, 0)
        vx, vy = (ex/after_length, ey/after_length) if after_length else (0, 0)
        a, z = (x+r*ux, y+r*uy), (x+r*vx, y+r*vy)
        result.extend([
            [*a, 0, 0, math.atan2(-uy, -ux), r*.55],
            [*z, math.atan2(-vy, -vx), r*.55, 0, 0],
        ])
        previous = z if radius > 0 else (x, y)
    return result


def cartesian(params):
    x, y, ir, il, out, ol = params
    return [x, y, x+math.cos(ir)*il, y+math.sin(ir)*il,
            x+math.cos(out)*ol, y+math.sin(out)*ol]


def eased(f, key):
    if key['interpolation'] == 0:
        return 0
    if key['interpolation'] == 1:
        return f
    x1, y1, x2, y2 = key['bezier']
    def bezier(t, a, b):
        return 3*(1-t)**2*t*a + 3*(1-t)*t*t*b + t**3
    low, high = 0.0, 1.0
    for _ in range(40):
        t = (low+high)/2
        if bezier(t, x1, x2) < f: low = t
        else: high = t
    return bezier((low+high)/2, y1, y2)


def unwrap(values, reference):
    result = [v[:] for v in values]
    for v, ref in zip(result, reference):
        for axis in (2, 4):
            v[axis] = ref[axis] + (v[axis]-ref[axis]+math.pi) % (2*math.pi)-math.pi
    return result


def sample_rounded_track(keys, fps):
    if not keys:
        raise ValueError('Empty morph track')
    result = [{'time': keys[0]['time'], 'value': rounded_parameters(keys[0]['value']), 'interpolation': 1}]
    for left, right in zip(keys, keys[1:]):
        start, end = round(left['time']*fps), round(right['time']*fps)
        if end <= start:
            raise ValueError('Morph keys must have increasing times')
        def evaluate(tick):
            f = eased((tick-start)/(end-start), left)
            values = [a+(b-a)*f for a, b in zip(left['value'], right['value'])]
            return rounded_parameters(values)
        if left['interpolation'] == 0:
            result[-1]['interpolation'] = 0
            result.append({'time': right['time'], 'value': rounded_parameters(right['value']), 'interpolation': 1})
            continue
        def subdivide(lo, hi, a, b):
            b = unwrap(b, a)
            error = 0.0
            for f in (.25, .5, .75):
                actual = evaluate(lo+(hi-lo)*f)
                for av, bv, actual_v in zip(a, b, actual):
                    interpolated = [x+(y-x)*f for x, y in zip(av, bv)]
                    error = max(error, *(abs(x-y) for x, y in zip(cartesian(interpolated), cartesian(actual_v))))
            if error <= MORPH_TOLERANCE:
                result.append({'time': hi/fps, 'value': b, 'interpolation': 1})
                return
            if hi-lo <= 1:
                raise ValueError(f'Rounded morph cannot meet tolerance: {error}')
            middle = (lo+hi)//2
            mid = evaluate(middle)
            subdivide(lo, middle, a, mid)
            subdivide(middle, hi, result[-1]['value'], b)
        subdivide(start, end, result[-1]['value'], rounded_parameters(right['value']))
    return result
