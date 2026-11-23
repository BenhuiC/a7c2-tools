"""One continuous mean-CIEDE2000 objective for C2 fitting and selection."""
import numpy as np

EPSILON=1e-6


def distances(prediction,target):
    from perceptual import to_lab,de2000
    p,t=[np.clip(np.asarray(v,dtype=np.float64),0,1) for v in (prediction,target)]
    if p.ndim!=2 or p.shape[1]!=3 or t.shape!=p.shape:
        raise ValueError('Expected matching Nx3 color arrays')
    return de2000(to_lab(p*255),to_lab(t*255))


def rows(prediction,target):
    distance=distances(prediction,target)
    return np.sqrt(distance*distance+EPSILON**2)-EPSILON


def mean(prediction,target,weights=None):
    values=rows(prediction,target)
    return float(np.mean(values) if weights is None else np.average(values,weights=weights))


def tensor_rows(tools,prediction,target):
    from stack_objective import de00_squared
    squared=de00_squared(tools,tools.lab(prediction.clamp(0,1)),tools.lab(target.clamp(0,1)))
    return tools.torch.sqrt(squared+EPSILON**2)-EPSILON


def tensor_mean(tools,prediction,target,weights=None):
    values=tensor_rows(tools,prediction,target)
    return values.mean() if weights is None else (values*weights).sum()/weights.sum()


def grid_penalty(base,prediction,grid,output_weight=.01,node_weight=.001):
    correction=np.sqrt(np.mean(((prediction-base)*255)**2,axis=1)+EPSILON**2)-EPSILON
    nodes=np.sqrt(np.mean(np.asarray(grid,dtype=float)**2)+EPSILON**2)-EPSILON
    return float(output_weight*np.mean(correction)+node_weight*nodes)


def tensor_grid_penalty(tools,base,prediction,grid,output_weight=.01,node_weight=.001):
    t=tools.torch
    correction=t.sqrt(((prediction-base)*255).square().mean(dim=1)+EPSILON**2)-EPSILON
    nodes=t.sqrt(grid.square().mean()+EPSILON**2)-EPSILON
    return output_weight*correction.mean()+node_weight*nodes
