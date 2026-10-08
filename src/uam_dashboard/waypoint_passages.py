"""Linear trajectory/cylinder intersections and mutually exclusive encounters."""
import math


def contact(previous, current, feature, radius):
    p = feature['properties']; lon, lat = feature['geometry']['coordinates']
    intervals = p.get('vertical_intervals_m')
    if intervals is None and p.get('altitude_m') is not None:
        intervals = [(p['altitude_m'] - radius, p['altitude_m'] + radius)]
    if not intervals:
        return []
    scale = 111320 * math.cos(math.radians(lat))
    def xy(row):
        return ((row[3] - lon)*scale, (row[2] - lat)*111320)
    x,y = xy(previous); bx,by = xy(current); dx,dy = bx-x,by-y
    aa=dx*dx+dy*dy; bb=2*(x*dx+y*dy); cc=x*x+y*y-radius*radius
    if aa < 1e-12:
        if cc > 0: return []
        left,right=0.,1.
    else:
        discriminant=bb*bb-4*aa*cc
        if discriminant < 0: return []
        root=math.sqrt(discriminant)
        left=max(0.,(-bb-root)/(2*aa)); right=min(1.,(-bb+root)/(2*aa))
        if left > right: return []
    contacts=[]; dz=current[4]-previous[4]
    for low, high in intervals:
        if abs(dz)<1e-12:
            if not low <= previous[4] <= high: continue
            lo,hi=left,right
        else:
            z0,z1=sorted(((low-previous[4])/dz,(high-previous[4])/dz))
            lo,hi=max(left,z0),min(right,z1)
            if lo>hi: continue
        u=max(lo,min(hi,-(x*dx+y*dy)/aa if aa else lo))
        distance=math.hypot(x+u*dx,y+u*dy)
        contacts.append((lo,hi,u,distance))
    return contacts


def percentile95(values):
    if not values: return None
    values=sorted(values); position=.95*(len(values)-1); lower=int(position)
    return values[lower]+(values[min(lower+1,len(values)-1)]-values[lower])*(position-lower)
