"""Exact signed7 parity descent in latent response units; CPU64 acceptance."""
import numpy as np
from gpu_tensor import TensorTools,de2000_tensor

def refine(grid,base,target,gate,weights,sweeps,perceptual_weight,response,progress,parameter_smoothing):
    import torch
    from measured_response import get
    from perceptual import to_lab,de2000
    model=get(response);tools=TensorTools();t=tools.tensor
    source=t(base);desired=t(target).clamp(0,1);mass=t(np.asarray(weights)/np.sum(weights));lab=tools.lab(desired)
    prep=model.prepare_tensor(tools,source);ids,w=prep['ids'],prep['weights']
    table=t(grid);original=np.asarray(grid).copy();d=(table[ids]*w[:,:,None]).sum(1)
    from grid_regularization import get_penalty
    regularizer=get_penalty(response) if parameter_smoothing else None
    def render(delta):return model.from_delta_tensor(tools,source,delta,prep)
    def costs(delta):
        p=render(delta);loss=(p-desired).square().mean(1)*255**2
        if perceptual_weight:loss=loss+perceptual_weight*(2.55*de2000_tensor(tools,tools.lab(p),lab)).square()
        return loss
    nodes=torch.arange(405,device=source.device);groups=(nodes//81%2)*4+(nodes//9%9%2)*2+nodes%9%2
    current=costs(d);accepted=0;actual=0
    def penalty(g):return regularizer.tensor_loss(tools,g,parameter_smoothing)*255**2 if regularizer else t(0.)
    for sweep in range(sweeps):
        changed=False;actual=sweep+1
        for group in range(8):
            mask=(groups[ids]==group)&(w>0);rownode=(ids*mask).sum(1);rw=(w*mask).sum(1);active=groups==group
            for c in range(3):
                losses=[]
                # Data scores remain exact. A nonlinear path regularizer
                # couples nodes; accept an actual combined objective below.
                for sign in (-1,1):
                    delta=d.clone();delta[:,c]+=sign*rw
                    loss=torch.zeros(405,device=source.device);loss.index_add_(0,rownode,(costs(delta)-current)*mass)
                    legal=active&(table[:,c]+sign>=-64)&(table[:,c]+sign<=63)
                    losses.append(torch.where(legal,loss,torch.full_like(loss,float('inf'))))
                values,choice=torch.stack(losses).min(0);move=torch.where(values< -1e-7,choice*2-1,0).to(torch.float32)
                count=int(torch.count_nonzero(move).cpu())
                if not count:continue
                before_gpu=(current*mass).sum()+penalty(table)
                order=torch.argsort(torch.where(move!=0,values,torch.full_like(values,float('inf'))));kept=count
                while kept:
                    subset=torch.zeros_like(move);subset[order[:kept]]=move[order[:kept]]
                    trial=table.clone();trial[:,c]+=subset
                    delta=d.clone();delta[:,c]+=subset[rownode]*rw
                    nextcost=costs(delta);score=(nextcost*mass).sum()+penalty(trial)
                    if float(score.cpu())<float(before_gpu.cpu())-1e-7:
                        table=trial;d=delta;current=nextcost;accepted+=kept;changed=True;break
                    kept//=2
            if progress:progress(sweep=sweep+1,total_sweeps=sweeps,point=(group+1)*405//8,total_points=405,gpu_backend='AMD ROCm/PyTorch')
        if not changed:break
    result=table.cpu().numpy().astype(np.int8);yy=np.clip(np.asarray(target,float),0,1)
    def cost(g):
        p=model.predict_cpu(base,g);rows=np.mean(((p-yy)*255)**2,axis=1)
        if perceptual_weight:rows+=perceptual_weight*(2.55*de2000(to_lab(p*255),to_lab(yy*255)))**2
        return float(rows@np.asarray(weights)/np.sum(weights))+(regularizer.cost(g,parameter_smoothing) if regularizer else 0.)
    before,after=cost(original),cost(result)
    if not np.isfinite(after) or after>before:result=original;after=before;accepted=0
    return result,dict(before=before,after=after,accepted=accepted,sweeps=actual,backend='AMD ROCm/PyTorch',
        optimizer='exact latent signed7 parity increments; coupled objective acceptance; CPU64 final check',
        cpu_final_objective_check=True,training_only=True,parameter_smoothing=parameter_smoothing)
